"""Integration harness: real PostgreSQL (a dedicated `<db>_test` database migrated with
Alembic), real API app, in-memory storage, inline task execution and the mock AI provider.

Start PostgreSQL/Redis/MinIO first: `docker compose up -d --wait postgres redis minio`.
"""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.ai import MockAIProvider
from app.core.config import Settings, get_settings
from app.core.security import FieldEncryptor
from app.db.session import create_db_engine, create_session_factory
from app.demo.pdf import DemoLine, invoice_pdf
from app.demo.seed import make_gstin
from app.infra.rate_limit import MemoryRateLimiter
from app.infra.redis import create_redis_client
from app.infra.resources import ReadinessCheck, Resources
from app.infra.storage import MemoryStorageProvider
from app.infra.tasks import (
    PROCESS_INBOUND_EMAIL,
    PROCESS_INVOICE,
    REANALYZE_INVOICE,
    InlineTaskDispatcher,
)
from app.main import Overrides, create_app
from app.modules.email_ingestion import service as email_service
from app.modules.invoices import pipeline

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(scope="session")
def test_database_url(live_settings: Settings) -> str:
    url = make_url(live_settings.database_url.get_secret_value())
    test_url = url.set(database=f"{url.database}_test")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_url.database}
        ).scalar()
        if exists:
            conn.execute(text(f'DROP DATABASE "{test_url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    admin.dispose()
    rendered = test_url.render_as_string(hide_password=False)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = rendered
    get_settings.cache_clear()
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    command.upgrade(config, "head")
    if previous is None:
        os.environ.pop("DATABASE_URL")
    else:
        os.environ["DATABASE_URL"] = previous
    get_settings.cache_clear()
    return rendered


@pytest.fixture(scope="session")
def api_settings(live_settings: Settings, test_database_url: str) -> Settings:
    values = live_settings.model_dump()
    values.update(
        database_url=test_database_url,
        app_env="test",
        ai_provider="mock",
        gemini_api_key=None,
        session_cookie_secure=False,
        cors_allowed_origins=["http://localhost:3000"],
        app_base_url="http://localhost:3000",
        trusted_proxy_hops=0,
    )
    for key in (
        "auth_secret",
        "data_encryption_key",
        "redis_url",
        "object_storage_access_key_id",
        "object_storage_secret_access_key",
        "celery_broker_url",
        "celery_result_backend",
    ):
        secret = getattr(live_settings, key)
        values[key] = secret.get_secret_value() if secret is not None else None
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
def engine(api_settings: Settings) -> Iterator[Any]:
    engine = create_db_engine(api_settings)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Any) -> Iterator[sessionmaker[Session]]:
    with engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    yield create_session_factory(engine)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def storage() -> MemoryStorageProvider:
    return MemoryStorageProvider()


@pytest.fixture
def ai() -> MockAIProvider:
    return MockAIProvider()


@pytest.fixture
def dispatcher(
    api_settings: Settings,
    session_factory: sessionmaker[Session],
    storage: MemoryStorageProvider,
    ai: MockAIProvider,
) -> InlineTaskDispatcher:
    deps = pipeline.PipelineDeps(storage, ai, FieldEncryptor(api_settings.encryption_key_bytes))
    inline = InlineTaskDispatcher()

    def process(invoice_id: str) -> None:
        with session_factory() as s:
            pipeline.process_invoice(s, deps, uuid.UUID(invoice_id))

    def reanalyze(invoice_id: str) -> None:
        with session_factory() as s:
            pipeline.reanalyze_invoice(s, deps, uuid.UUID(invoice_id))

    def inbound(inbound_email_id: str) -> None:
        with session_factory() as s:
            email_service.process(s, api_settings, storage, inline, uuid.UUID(inbound_email_id))

    inline.register(PROCESS_INVOICE, process)
    inline.register(REANALYZE_INVOICE, reanalyze)
    inline.register(PROCESS_INBOUND_EMAIL, inbound)
    return inline


@pytest.fixture
def api(
    api_settings: Settings,
    engine: Any,
    session_factory: sessionmaker[Session],
    storage: MemoryStorageProvider,
    dispatcher: InlineTaskDispatcher,
    ai: MockAIProvider,
) -> Iterator[FastAPI]:
    resources = Resources(
        engine=engine,
        session_factory=session_factory,
        redis=create_redis_client(api_settings),
        storage=storage,
    )
    app = create_app(
        api_settings,
        overrides=Overrides(
            resources=resources,
            dispatcher=dispatcher,
            rate_limiter=MemoryRateLimiter(),
            ai=ai,
            readiness_checks=[ReadinessCheck("database", lambda: None)],
        ),
    )
    with TestClient(app):  # runs the lifespan once; clients below share app.state
        yield app


class Client:
    """A browser-like user: its own cookie jar, sends the CSRF header automatically."""

    def __init__(self, app: FastAPI) -> None:
        self.http = TestClient(
            app, raise_server_exceptions=False, headers={"Origin": "http://localhost:3000"}
        )
        self.me: dict[str, Any] = {}

    @property
    def csrf(self) -> str:
        return str(self.http.cookies.get("irs_csrf", ""))

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        headers = {"X-CSRF-Token": self.csrf, **kwargs.pop("headers", {})}
        return self.http.request(method, url, headers=headers, **kwargs)

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)

    def ok(self, method: str, url: str, expected: int = 200, **kwargs: Any) -> Any:
        response = self.request(method, url, **kwargs)
        assert response.status_code == expected, (method, url, response.status_code, response.text)
        return response.json()

    def signup(self, email: str, organization: str) -> "Client":
        self.me = self.ok(
            "POST",
            "/api/v1/auth/signup",
            201,
            json={
                "email": email,
                "password": PASSWORD,
                "full_name": email.split("@")[0],
                "organization_name": organization,
            },
        )
        return self

    def login(self, email: str, password: str = PASSWORD) -> Response:
        response = self.post("/api/v1/auth/login", json={"email": email, "password": password})
        if response.status_code == 200:
            self.me = response.json()
        return response

    def invite(self, app: FastAPI, email: str, role: str) -> "Client":
        invitation = self.ok(
            "POST", "/api/v1/organization/invitations", 201, json={"email": email, "role": role}
        )
        token = invitation["invitation_url"].rsplit("/", 1)[-1]
        member = Client(app)
        member.me = member.ok(
            "POST",
            f"/api/v1/auth/invitations/{token}/accept",
            json={"full_name": email.split("@")[0], "password": PASSWORD},
        )
        return member


@pytest.fixture
def owner(api: FastAPI) -> Client:
    return Client(api).signup("owner@org-a.example", "Org A Manufacturing")


@pytest.fixture
def team(api: FastAPI, owner: Client) -> dict[str, Client]:
    return {
        "owner": owner,
        "admin": owner.invite(api, "admin@org-a.example", "admin"),
        "reviewer": owner.invite(api, "reviewer@org-a.example", "reviewer"),
        "viewer": owner.invite(api, "viewer@org-a.example", "viewer"),
    }


@pytest.fixture
def other_org(api: FastAPI) -> Client:
    return Client(api).signup("owner@org-b.example", "Org B Traders")


ORG_GSTIN = make_gstin("27", "AABCD1234E")
VENDOR_GSTIN = make_gstin("27", "AAECA5678F")


def sample_invoice(
    number: str = "INV-100",
    total: str = "7,788.00",
    *,
    gstin: str | None = VENDOR_GSTIN,
    vendor: str = "Acme Industrial Supplies Pvt Ltd",
    po: str | None = None,
    account: str | None = "501002345678",
    ifsc: str | None = "HDFC0001234",
    extra: list[str] | None = None,
    date: str = "20/09/2026",
) -> bytes:
    return invoice_pdf(
        vendor_name=vendor,
        vendor_gstin=gstin,
        buyer_gstin=None,
        invoice_number=number,
        invoice_date=date,
        due_date=None,
        po_number=po,
        lines=[
            DemoLine("Steel bolts M8", "400", "12.50", "18", "5000.00"),
            DemoLine("Hex nuts M8", "800", "2.00", "18", "1600.00"),
        ],
        subtotal="6,600.00",
        cgst="594.00",
        sgst="594.00",
        igst=None,
        total=total,
        account_number=account,
        ifsc=ifsc,
        extra_lines=extra,
    )


def upload(client: Client, data: bytes, name: str = "invoice.pdf", expected: int = 201) -> Any:
    return client.ok(
        "POST", "/api/v1/invoices/upload", expected, files={"file": (name, data, "application/pdf")}
    )


def create_vendor(client: Client, **overrides: Any) -> Any:
    body = {
        "name": "Acme Industrial Supplies Pvt Ltd",
        "gstin": VENDOR_GSTIN,
        "bank_account": {
            "account_holder_name": "Acme Industrial Supplies",
            "account_number": "501002345678",
            "ifsc": "HDFC0001234",
        },
    }
    body.update(overrides)
    return client.ok("POST", "/api/v1/vendors", 201, json=body)

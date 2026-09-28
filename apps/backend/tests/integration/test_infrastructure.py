"""Real infrastructure: PostgreSQL, Redis, S3-compatible storage (MinIO), Celery, migrations."""

import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from celery.contrib.testing.worker import start_worker
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, ping_database
from app.infra.rate_limit import RedisRateLimiter
from app.infra.redis import create_redis_client, ping_redis
from app.infra.storage import ObjectNotFound, S3StorageProvider
from app.infra.tasks import PING
from app.worker.celery_app import create_celery_app
from tests.integration.conftest import BACKEND_DIR

pytestmark = pytest.mark.integration


def test_database_connectivity(live_settings: Settings) -> None:
    engine = create_db_engine(live_settings)
    try:
        ping_database(engine)
        with engine.connect() as connection:
            version: str = connection.execute(text("SHOW server_version")).scalar_one()
        assert int(version.split(".")[0]) >= 17
    finally:
        engine.dispose()


def test_redis_connectivity_and_rate_limiter(live_settings: Settings) -> None:
    client = create_redis_client(live_settings)
    key = f"test:{uuid.uuid4().hex}"
    try:
        ping_redis(client)
        limiter = RedisRateLimiter(client, prefix="test-ratelimit:")
        results = [limiter.hit(key, 2, 60).allowed for _ in range(3)]
        assert results == [True, True, False]
        limiter.reset(key)
        assert limiter.hit(key, 2, 60).allowed
    finally:
        RedisRateLimiter(client, prefix="test-ratelimit:").reset(key)
        client.close()


def test_object_storage_round_trip(live_settings: Settings) -> None:
    storage = S3StorageProvider(live_settings)
    storage.ensure_bucket()
    storage.check()
    key = f"integration-tests/{uuid.uuid4().hex}.txt"
    storage.put(key, b"synthetic test data", "text/plain")
    try:
        assert storage.get(key) == b"synthetic test data"
    finally:
        storage.delete(key)
    with pytest.raises(ObjectNotFound):
        storage.get(key)


def test_celery_task_executes_through_redis(live_settings: Settings) -> None:
    app = create_celery_app(live_settings)
    app.loader.import_default_modules()
    app.conf.task_default_queue = f"test-{uuid.uuid4().hex}"  # isolated from the compose worker
    with start_worker(app, perform_ping_check=False, loglevel="WARNING", shutdown_timeout=10):
        assert app.send_task(PING).get(timeout=15) == "pong"


def test_migrations_upgrade_downgrade_upgrade(live_settings: Settings) -> None:
    url = make_url(live_settings.database_url.get_secret_value())
    scratch = url.set(database=f"{url.database}_migration_test")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{scratch.database}"'))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = scratch.render_as_string(hide_password=False)
    get_settings.cache_clear()
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    try:
        command.upgrade(config, "head")
        engine = create_engine(scratch)
        tables = set(inspect(engine).get_table_names())
        assert {"organizations", "invoices", "risk_signals", "audit_events"} <= tables
        engine.dispose()
        command.downgrade(config, "base")
        engine = create_engine(scratch)
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        engine.dispose()
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)'))
        admin.dispose()

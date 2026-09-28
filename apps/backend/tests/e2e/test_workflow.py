"""End-to-end workflow against the running Docker Compose stack.

Browser-equivalent HTTP through the web app's /api/v1 proxy -> FastAPI -> Redis -> Celery
worker -> MinIO -> PostgreSQL, with AI_PROVIDER=mock (no real Gemini calls).

    docker compose up -d --wait && uv run pytest -m e2e
"""

import os
import time
import uuid
from typing import Any

import httpx2 as httpx
import pytest

from app.core.config import get_settings
from app.demo.pdf import DemoLine, invoice_pdf
from app.demo.seed import make_gstin

pytestmark = pytest.mark.e2e

BASE_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
PASSWORD = "e2e-correct-horse-battery"
VENDOR_GSTIN = make_gstin("27", "AAECE2468K")


_OPEN_CLIENTS: list[httpx.Client] = []


class Browser:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=BASE_URL, timeout=30, headers={"Origin": BASE_URL})
        _OPEN_CLIENTS.append(self.http)

    def call(self, method: str, path: str, expected: int = 200, **kwargs: Any) -> Any:
        headers = {
            "X-CSRF-Token": self.http.cookies.get("irs_csrf") or "",
            **kwargs.pop("headers", {}),
        }
        response = self.http.request(method, f"/api/v1{path}", headers=headers, **kwargs)
        assert response.status_code == expected, (method, path, response.status_code, response.text)
        return response.json() if response.content else None


def wait_for_review(browser: Browser, invoice_id: str, timeout: float = 60) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        invoice = browser.call("GET", f"/invoices/{invoice_id}")
        if invoice["status"] not in (
            "uploaded",
            "queued",
            "processing",
            "extracted",
            "risk_analysis",
        ):
            return invoice
        time.sleep(0.5)
    raise AssertionError(f"invoice {invoice_id} still processing after {timeout}s")


def pdf(number: str, account: str = "501002345678", ifsc: str = "HDFC0001234") -> bytes:
    return invoice_pdf(
        vendor_name="E2E Components Pvt Ltd",
        vendor_gstin=VENDOR_GSTIN,
        buyer_gstin=None,
        invoice_number=number,
        invoice_date="15/09/2026",
        due_date=None,
        po_number=None,
        lines=[DemoLine("Bearings 6204", "100", "45.00", "18", "4500.00")],
        subtotal="4,500.00",
        cgst="405.00",
        sgst="405.00",
        igst=None,
        total="5,310.00",
        account_number=account,
        ifsc=ifsc,
    )


@pytest.fixture(autouse=True)
def _close_clients() -> Any:
    yield
    while _OPEN_CLIENTS:
        _OPEN_CLIENTS.pop().close()


@pytest.fixture(scope="module")
def stack_available() -> None:
    try:
        httpx.get(f"{BASE_URL}/api/backend-health", timeout=5).raise_for_status()
    except httpx.HTTPError as exc:
        pytest.fail(f"The Docker Compose stack is not reachable at {BASE_URL}: {exc}")


def test_full_invoice_control_workflow(stack_available: None) -> None:
    run = uuid.uuid4().hex[:8]
    # 1. Create organization (owner) through the web proxy; session cookie is first-party.
    owner = Browser()
    me = owner.call(
        "POST",
        "/auth/signup",
        201,
        json={
            "email": f"owner-{run}@e2e.example",
            "password": PASSWORD,
            "full_name": "E2E Owner",
            "organization_name": f"E2E Org {run}",
        },
    )
    assert me["organization"]["role"] == "owner"
    assert owner.http.cookies.get("irs_session")

    # 2. Create users via invitations.
    def invite(email: str, role: str) -> Browser:
        link = owner.call(
            "POST", "/organization/invitations", 201, json={"email": email, "role": role}
        )
        member = Browser()
        member.call(
            "POST",
            f"/auth/invitations/{link['invitation_url'].rsplit('/', 1)[-1]}/accept",
            json={"full_name": role.title(), "password": PASSWORD},
        )
        return member

    reviewer = invite(f"reviewer-{run}@e2e.example", "reviewer")
    admin = invite(f"admin-{run}@e2e.example", "admin")

    # 3. Create vendor with a bank account; verified by a different person.
    vendor = reviewer.call(
        "POST",
        "/vendors",
        201,
        json={
            "name": "E2E Components Pvt Ltd",
            "gstin": VENDOR_GSTIN,
            "bank_account": {
                "account_holder_name": "E2E Components",
                "account_number": "501002345678",
                "ifsc": "HDFC0001234",
            },
        },
    )
    admin.call(
        "POST",
        f"/vendors/{vendor['id']}/bank-accounts/{vendor['current_bank_account']['id']}/verify",
        json={"note": "Confirmed by phone"},
    )

    # 4-6. Upload invoices; the Celery worker extracts and runs the risk engine asynchronously.
    clean = reviewer.call(
        "POST",
        "/invoices/upload",
        201,
        files={"file": ("clean.pdf", pdf(f"E2E-{run}-1"), "application/pdf")},
    )
    diverted = reviewer.call(
        "POST",
        "/invoices/upload",
        201,
        files={
            "file": (
                "diverted.pdf",
                pdf(f"E2E-{run}-2", "778899001122", "YESB0009988"),
                "application/pdf",
            )
        },
    )
    clean = wait_for_review(reviewer, clean["id"])
    diverted = wait_for_review(reviewer, diverted["id"])
    assert clean["status"] == diverted["status"] == "review_required"
    assert clean["vendor"]["id"] == vendor["id"]
    assert clean["fields"]["total"]["value"] == "5310.00"
    # CI runs the stack with the mock provider (deterministic path only); a stack configured
    # with a real Gemini key must produce validated AI assistance.
    expected_ai = "succeeded" if get_settings().ai_provider.value == "gemini" else "unavailable"
    assert clean["assessment"]["ai_status"] == expected_ai
    codes = {s["rule_code"] for s in diverted["assessment"]["signals"]}
    assert "bank_account_mismatch" in codes and diverted["assessment"]["risk_level"] == "high"

    # The original document round-trips through MinIO.
    document = clean["documents"][0]
    original = reviewer.http.get(f"/api/v1/invoices/{clean['id']}/documents/{document['id']}")
    assert original.status_code == 200 and original.content.startswith(b"%PDF-")

    # 7-8. Review: high-risk invoice is blocked, then rejected; clean invoice approved.
    blocked = reviewer.http.post(
        f"/api/v1/invoices/{diverted['id']}/decisions",
        headers={"X-CSRF-Token": reviewer.http.cookies.get("irs_csrf") or ""},
        json={"decision": "approve", "reason": "trying"},
    )
    assert blocked.status_code == 409
    reviewer.call(
        "POST",
        f"/invoices/{diverted['id']}/decisions",
        201,
        json={"decision": "reject", "reason": "Bank account differs; vendor denies change"},
    )
    for signal in clean["assessment"]["signals"]:
        if signal["severity"] == "high":
            admin.call(
                "POST",
                f"/invoices/{clean['id']}/signals/{signal['id']}/resolve",
                json={"resolution": "risk_accepted", "reason": "Reviewed in E2E"},
            )
    reviewer.call(
        "POST",
        f"/invoices/{clean['id']}/decisions",
        201,
        json={"decision": "approve", "reason": "Matches goods receipt"},
    )
    assert reviewer.call("GET", f"/invoices/{clean['id']}")["status"] == "approved"
    assert reviewer.call("GET", f"/invoices/{diverted['id']}")["status"] == "rejected"

    # 9. Audit trail is complete and the hash chain verifies.
    events = owner.call("GET", f"/audit-events?entity_type=invoice&entity_id={diverted['id']}")[
        "items"
    ]
    actions = [e["action"] for e in reversed(events)]
    assert actions[0] == "invoice.uploaded" and actions[-1] == "invoice.rejected"
    assert "risk.assessed" in actions
    assert events[0]["actor_label"] == f"reviewer-{run}@e2e.example"
    assert owner.call("GET", "/audit-events/verify")["valid"] is True
    dashboard = owner.call("GET", "/dashboard")
    assert dashboard["approved"] == 1 and dashboard["rejected"] == 1

"""Vendor master data, bank-account change control, purchase orders."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, VendorBankAccount
from tests.integration.conftest import VENDOR_GSTIN, Client, create_vendor

pytestmark = pytest.mark.integration

NEW_ACCOUNT = {
    "account_holder_name": "Acme",
    "account_number": "778899001122",
    "ifsc": "YESB0009988",
    "change_reason": "Vendor letter dated 1 Sep",
}


def test_vendor_crud_search_and_gstin_validation(team: dict[str, Client]) -> None:
    reviewer = team["reviewer"]
    vendor = create_vendor(reviewer)
    assert vendor["state_code"] == "27" and vendor["pan"] == VENDOR_GSTIN[2:12]
    assert vendor["current_bank_account"]["account_number_masked"] == "•••• 5678"
    assert "501002345678" not in str(vendor)
    bad = reviewer.post("/api/v1/vendors", json={"name": "Bad", "gstin": "27AAECA5678F1ZZ"})
    assert bad.json()["error"]["code"] == "invalid_gstin"
    dup = reviewer.post("/api/v1/vendors", json={"name": "Dup", "gstin": VENDOR_GSTIN})
    assert dup.status_code == 409
    updated = reviewer.ok(
        "PATCH", f"/api/v1/vendors/{vendor['id']}", json={"phone": "+91 99999 00000"}
    )
    assert updated["phone"] == "+91 99999 00000"
    assert reviewer.ok("GET", "/api/v1/vendors?q=industrial")["total"] == 1
    detail = reviewer.ok("GET", f"/api/v1/vendors/{vendor['id']}")
    assert detail["risk"]["invoice_count"] == 0
    history = reviewer.ok(
        "GET", f"/api/v1/audit-events?entity_type=vendor&entity_id={vendor['id']}"
    )
    assert {e["action"] for e in history["items"]} >= {"vendor.created", "vendor.updated"}


def test_bank_change_is_versioned_audited_and_notified(
    team: dict[str, Client], db: Session
) -> None:
    reviewer, admin = team["reviewer"], team["admin"]
    vendor = create_vendor(reviewer)
    old = vendor["current_bank_account"]
    no_reason = reviewer.post(
        f"/api/v1/vendors/{vendor['id']}/bank-accounts", json={**NEW_ACCOUNT, "change_reason": None}
    )
    assert no_reason.json()["error"]["code"] == "change_reason_required"
    new = reviewer.ok(
        "POST", f"/api/v1/vendors/{vendor['id']}/bank-accounts", 201, json=NEW_ACCOUNT
    )
    assert new["status"] == "pending_verification" and new["previous_account_id"] == old["id"]
    history = reviewer.ok("GET", f"/api/v1/vendors/{vendor['id']}/bank-accounts")
    assert [a["status"] for a in history] == ["pending_verification", "superseded"]
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "vendor.bank_account.changed"))
    assert event is not None
    assert event.details["previous"]["last4"] == "5678" and event.details["new"]["last4"] == "1122"
    assert "778899001122" not in str(event.details)
    rows = db.scalars(select(VendorBankAccount)).all()
    assert all("778899001122" not in r.account_number_encrypted for r in rows)
    alerts = admin.ok("GET", "/api/v1/notifications")["items"]
    assert any(
        n["kind"] == "vendor.bank_account_changed" and n["severity"] == "high" for n in alerts
    )


def test_bank_verification_requires_permission_and_different_person(
    team: dict[str, Client],
) -> None:
    reviewer, admin, owner = team["reviewer"], team["admin"], team["owner"]
    vendor = create_vendor(admin)
    account = vendor["current_bank_account"]["id"]
    url = f"/api/v1/vendors/{vendor['id']}/bank-accounts/{account}"
    assert reviewer.post(f"{url}/verify", json={"note": "Verified by phone"}).status_code == 403
    same = admin.post(f"{url}/verify", json={"note": "Verified by phone"})
    assert same.json()["error"]["code"] == "segregation_of_duties"
    verified = owner.ok("POST", f"{url}/verify", json={"note": "Called known contact"})
    assert (
        verified["status"] == "verified" and verified["verified_by_email"] == "owner@org-a.example"
    )


def test_rejecting_a_change_restores_previous_account(team: dict[str, Client]) -> None:
    reviewer, owner = team["reviewer"], team["owner"]
    vendor = create_vendor(reviewer)
    old_id = vendor["current_bank_account"]["id"]
    owner.ok(
        "POST",
        f"/api/v1/vendors/{vendor['id']}/bank-accounts/{old_id}/verify",
        json={"note": "Verified by phone"},
    )
    new = reviewer.ok(
        "POST", f"/api/v1/vendors/{vendor['id']}/bank-accounts", 201, json=NEW_ACCOUNT
    )
    owner.ok(
        "POST",
        f"/api/v1/vendors/{vendor['id']}/bank-accounts/{new['id']}/reject",
        json={"note": "Vendor denies sending this request"},
    )
    current = owner.ok("GET", f"/api/v1/vendors/{vendor['id']}")["current_bank_account"]
    assert current["id"] == old_id and current["status"] == "verified"


def test_reveal_is_restricted_and_audited(team: dict[str, Client], db: Session) -> None:
    vendor = create_vendor(team["reviewer"])
    url = f"/api/v1/vendors/{vendor['id']}/bank-accounts/{vendor['current_bank_account']['id']}/reveal"
    assert team["reviewer"].post(url).status_code == 403
    assert team["admin"].ok("POST", url)["account_number"] == "501002345678"
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "vendor.bank_account.revealed"))


def test_purchase_orders_compute_totals_server_side(team: dict[str, Client]) -> None:
    reviewer = team["reviewer"]
    vendor = create_vendor(reviewer)
    po = reviewer.ok(
        "POST",
        "/api/v1/purchase-orders",
        201,
        json={
            "vendor_id": vendor["id"],
            "po_number": "PO-1001",
            "lines": [
                {
                    "description": "Steel bolts M8",
                    "quantity": "1000",
                    "unit_price": "12.50",
                    "tax_rate": "18",
                },
                {
                    "description": "Hex nuts M8",
                    "quantity": "3",
                    "unit_price": "0.33",
                    "tax_rate": "18",
                },
            ],
        },
    )
    assert (
        po["subtotal"] == "12500.99" and po["tax_total"] == "2250.18" and po["total"] == "14751.17"
    )
    dup = reviewer.post(
        "/api/v1/purchase-orders",
        json={
            "vendor_id": vendor["id"],
            "po_number": "PO-1001",
            "lines": [{"description": "x", "quantity": "1", "unit_price": "1"}],
        },
    )
    assert dup.status_code == 409
    closed = reviewer.ok("PATCH", f"/api/v1/purchase-orders/{po['id']}", json={"status": "closed"})
    assert closed["status"] == "closed"
    locked = reviewer.patch(
        f"/api/v1/purchase-orders/{po['id']}",
        json={"lines": [{"description": "x", "quantity": "1", "unit_price": "1"}]},
    )
    assert locked.json()["error"]["code"] == "po_not_editable"
    viewer = team["viewer"].post(
        "/api/v1/purchase-orders",
        json={
            "vendor_id": vendor["id"],
            "po_number": "PO-9",
            "lines": [{"description": "x", "quantity": "1", "unit_price": "1"}],
        },
    )
    assert viewer.status_code == 403

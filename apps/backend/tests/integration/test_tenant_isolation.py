"""Organization A can never read or change Organization B's data (security boundary)."""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification
from tests.integration.conftest import Client, create_vendor, sample_invoice, upload

pytestmark = pytest.mark.integration


@pytest.fixture
def org_b_data(other_org: Client) -> dict[str, Any]:
    vendor = create_vendor(other_org)
    po = other_org.ok(
        "POST",
        "/api/v1/purchase-orders",
        201,
        json={
            "vendor_id": vendor["id"],
            "po_number": "PO-B1",
            "lines": [{"description": "Item", "quantity": "1", "unit_price": "10.00"}],
        },
    )
    invoice = upload(other_org, sample_invoice("B-1"))
    account = vendor["current_bank_account"]
    signal_id = (
        invoice["assessment"]["signals"][0]["id"] if invoice["assessment"]["signals"] else None
    )
    return {"vendor": vendor, "po": po, "invoice": invoice, "account": account, "signal": signal_id}


def test_reads_across_tenants_return_404(owner: Client, org_b_data: dict[str, Any]) -> None:
    v, po, inv = org_b_data["vendor"]["id"], org_b_data["po"]["id"], org_b_data["invoice"]["id"]
    doc = org_b_data["invoice"]["documents"][0]["id"]
    for url in (
        f"/api/v1/vendors/{v}",
        f"/api/v1/vendors/{v}/bank-accounts",
        f"/api/v1/purchase-orders/{po}",
        f"/api/v1/invoices/{inv}",
        f"/api/v1/invoices/{inv}/documents/{doc}",
    ):
        response = owner.get(url)
        assert response.status_code == 404, url


def test_listings_never_include_other_tenants(owner: Client, org_b_data: dict[str, Any]) -> None:
    create_vendor(owner, name="Org A Vendor", gstin=None, bank_account=None)
    for url in (
        "/api/v1/vendors",
        "/api/v1/purchase-orders",
        "/api/v1/invoices",
        "/api/v1/approvals",
        "/api/v1/notifications",
        "/api/v1/audit-events",
    ):
        body = owner.ok("GET", url)
        ids = {item.get("id") for item in body["items"]}
        assert org_b_data["vendor"]["id"] not in ids and org_b_data["invoice"]["id"] not in ids, url
    events = owner.ok("GET", "/api/v1/audit-events?limit=100")["items"]
    assert all("org-b" not in (e["actor_label"] or "") for e in events)
    vendors = owner.ok("GET", "/api/v1/vendors?q=acme")["items"]
    assert vendors == []


def test_writes_across_tenants_are_rejected(owner: Client, org_b_data: dict[str, Any]) -> None:
    v, inv = org_b_data["vendor"]["id"], org_b_data["invoice"]["id"]
    account = org_b_data["account"]["id"]
    attempts = [
        ("PATCH", f"/api/v1/vendors/{v}", {"name": "Hijacked"}),
        (
            "POST",
            f"/api/v1/vendors/{v}/bank-accounts",
            {
                "account_holder_name": "Attacker",
                "account_number": "999999999",
                "ifsc": "HDFC0001234",
                "change_reason": "attack",
            },
        ),
        ("POST", f"/api/v1/vendors/{v}/bank-accounts/{account}/verify", {"note": "attack"}),
        ("POST", f"/api/v1/vendors/{v}/bank-accounts/{account}/reveal", None),
        ("PATCH", f"/api/v1/purchase-orders/{org_b_data['po']['id']}", {"status": "closed"}),
        ("PATCH", f"/api/v1/invoices/{inv}", {"reason": "attack", "total": "1.00"}),
        ("POST", f"/api/v1/invoices/{inv}/decisions", {"decision": "approve", "reason": "attack"}),
        ("POST", f"/api/v1/invoices/{inv}/reprocess", None),
    ]
    if org_b_data["signal"]:
        attempts.append(
            (
                "POST",
                f"/api/v1/invoices/{inv}/signals/{org_b_data['signal']}/resolve",
                {"resolution": "risk_accepted", "reason": "attack"},
            )
        )
    for method, url, body in attempts:
        response = owner.request(method, url, json=body) if body else owner.request(method, url)
        assert response.status_code == 404, (method, url, response.status_code)


def test_cannot_link_other_tenants_vendor_or_po(owner: Client, org_b_data: dict[str, Any]) -> None:
    mine = upload(owner, sample_invoice("A-1"))
    for field, value in (
        ("vendor_id", org_b_data["vendor"]["id"]),
        ("purchase_order_id", org_b_data["po"]["id"]),
    ):
        response = owner.patch(
            f"/api/v1/invoices/{mine['id']}", json={"reason": "link", field: value}
        )
        assert response.status_code == 422, field
    response = owner.post(
        "/api/v1/purchase-orders",
        json={
            "vendor_id": org_b_data["vendor"]["id"],
            "po_number": "X",
            "lines": [{"description": "a", "quantity": "1", "unit_price": "1"}],
        },
    )
    assert response.status_code == 422


def test_same_gstin_and_same_document_are_independent_per_tenant(
    owner: Client, org_b_data: dict[str, Any]
) -> None:
    create_vendor(owner)  # identical GSTIN is allowed in a different tenant
    invoice = upload(owner, sample_invoice("B-1"))  # same bytes as org B's upload
    codes = {s["rule_code"] for s in invoice["assessment"]["signals"]}
    assert "duplicate_document" not in codes and "duplicate_invoice_number" not in codes


def test_notifications_and_members_are_tenant_scoped(
    api: FastAPI, owner: Client, other_org: Client, db: Session, org_b_data: dict[str, Any]
) -> None:
    notification = db.scalar(
        select(Notification).where(Notification.recipient_id == other_org.me["user_id"])
    )
    assert notification is not None  # org B's owner was notified about the upload
    assert owner.post(f"/api/v1/notifications/{notification.id}/read").status_code == 404
    members = owner.ok("GET", "/api/v1/organization/members")
    assert {m["email"] for m in members} == {"owner@org-a.example"}
    b_member = other_org.ok("GET", "/api/v1/organization/members")[0]
    response = owner.patch(
        f"/api/v1/organization/members/{b_member['membership_id']}", json={"role": "viewer"}
    )
    assert response.status_code == 404

"""Human review, approval workflow, audit trail integrity, notifications and dashboard."""

from typing import Any

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditEvent
from tests.integration.conftest import Client, create_vendor, sample_invoice, upload

pytestmark = pytest.mark.integration


def verified_vendor(team: dict[str, Client]) -> Any:
    vendor = create_vendor(team["reviewer"])
    team["admin"].ok(
        "POST",
        f"/api/v1/vendors/{vendor['id']}/bank-accounts/{vendor['current_bank_account']['id']}/verify",
        json={"note": "Confirmed with known contact"},
    )
    return vendor


def decide(client: Client, invoice_id: str, decision: str, reason: str = "Checked evidence") -> Any:
    return client.post(
        f"/api/v1/invoices/{invoice_id}/decisions", json={"decision": decision, "reason": reason}
    )


def test_low_risk_invoice_single_approval(team: dict[str, Client]) -> None:
    verified_vendor(team)
    reviewer = team["reviewer"]
    upload(reviewer, sample_invoice("INV-1", date="01/09/2026"))  # history for "new vendor"
    invoice = upload(reviewer, sample_invoice("INV-2", date="10/09/2026"))
    assert invoice["required_approvals"] == 1
    assert "approve" in invoice["allowed_actions"]
    response = decide(reviewer, invoice["id"], "approve", "Matches delivery note")
    assert response.status_code == 201
    review = response.json()
    assert review["evidence_snapshot"]["risk_level"] == invoice["assessment"]["risk_level"]
    detail = reviewer.ok("GET", f"/api/v1/invoices/{invoice['id']}")
    assert detail["status"] == "approved" and detail["decided_at"]
    assert detail["reviews"][0]["reason"] == "Matches delivery note"
    assert (
        decide(reviewer, invoice["id"], "reject").json()["error"]["code"] == "invoice_not_decidable"
    )


def test_viewer_cannot_decide_and_reason_is_required(team: dict[str, Client]) -> None:
    invoice = upload(team["reviewer"], sample_invoice("INV-3"))
    assert decide(team["viewer"], invoice["id"], "approve").status_code == 403
    assert (
        "approve"
        not in team["viewer"].ok("GET", f"/api/v1/invoices/{invoice['id']}")["allowed_actions"]
    )
    assert decide(team["reviewer"], invoice["id"], "approve", "").status_code == 422


def test_high_signals_block_approval_until_authorised_override(team: dict[str, Client]) -> None:
    reviewer, admin = team["reviewer"], team["admin"]
    invoice = upload(reviewer, sample_invoice("Q-1", gstin=None, vendor="Unknown Vendor Co"))
    blocked = decide(reviewer, invoice["id"], "approve")
    assert (
        blocked.status_code == 409 and blocked.json()["error"]["code"] == "open_high_risk_signals"
    )
    high = next(s for s in invoice["assessment"]["signals"] if s["severity"] == "high")
    url = f"/api/v1/invoices/{invoice['id']}/signals/{high['id']}/resolve"
    body = {"resolution": "risk_accepted", "reason": "Vendor onboarding in progress; PO on file"}
    assert reviewer.post(url, json=body).status_code == 403  # reviewers cannot override
    resolved = admin.ok("POST", url, json=body)
    signal = next(s for s in resolved["assessment"]["signals"] if s["id"] == high["id"])
    assert signal["resolution"] == "risk_accepted"
    assert signal["resolved_by_email"] == "admin@org-a.example"
    assert admin.post(url, json=body).json()["error"]["code"] == "already_resolved"
    assert decide(reviewer, invoice["id"], "approve").status_code == 201


def test_high_value_requires_second_different_approver(team: dict[str, Client]) -> None:
    owner, admin, reviewer = team["owner"], team["admin"], team["reviewer"]
    settings = owner.ok("GET", "/api/v1/organization")["settings"]
    owner.ok(
        "PATCH",
        "/api/v1/organization",
        json={"settings": {**settings, "high_value_threshold": "5000", "require_po_above": None}},
    )
    verified_vendor(team)
    upload(reviewer, sample_invoice("H-0", date="01/08/2026"))
    invoice = upload(reviewer, sample_invoice("H-1", date="15/09/2026"))
    assert invoice["required_approvals"] == 2
    assert [s["name"] for s in invoice["approval_steps"]] == ["review", "final_approval"]
    for signal in invoice["assessment"]["signals"]:
        if signal["severity"] == "high":
            admin.ok(
                "POST",
                f"/api/v1/invoices/{invoice['id']}/signals/{signal['id']}/resolve",
                json={"resolution": "risk_accepted", "reason": "Reviewed with vendor"},
            )
    assert decide(admin, invoice["id"], "approve").status_code == 201
    state = admin.ok("GET", f"/api/v1/invoices/{invoice['id']}")
    assert state["status"] == "pending_approval"
    assert invoice["id"] in {i["id"] for i in owner.ok("GET", "/api/v1/approvals")["items"]}
    # The first approver must not be offered the second step.
    assert invoice["id"] not in {i["id"] for i in admin.ok("GET", "/api/v1/approvals")["items"]}
    assert decide(reviewer, invoice["id"], "approve").status_code == 403  # lacks final permission
    same = decide(admin, invoice["id"], "approve")
    assert same.json()["error"]["code"] == "segregation_of_duties"
    assert decide(owner, invoice["id"], "approve", "Second approval").status_code == 201
    final = owner.ok("GET", f"/api/v1/invoices/{invoice['id']}")
    assert final["status"] == "approved"
    assert [s["status"] for s in final["approval_steps"]] == ["approved", "approved"]
    assert {s["decided_by_email"] for s in final["approval_steps"]} == {
        "admin@org-a.example",
        "owner@org-a.example",
    }


def test_reject_and_request_changes_flow(team: dict[str, Client]) -> None:
    reviewer = team["reviewer"]
    first = upload(reviewer, sample_invoice("R-1"))
    assert decide(reviewer, first["id"], "reject", "Duplicate of paid invoice").status_code == 201
    assert reviewer.ok("GET", f"/api/v1/invoices/{first['id']}")["status"] == "rejected"

    second = upload(reviewer, sample_invoice("R-2"))
    decide(reviewer, second["id"], "request_changes", "GSTIN missing on invoice")
    state = reviewer.ok("GET", f"/api/v1/invoices/{second['id']}")
    assert state["status"] == "needs_changes"
    assert "replace_document" in state["allowed_actions"]
    replaced = reviewer.ok(
        "POST",
        f"/api/v1/invoices/{second['id']}/documents",
        files={"file": ("fixed.pdf", sample_invoice("R-2", total="7,788.00"), "application/pdf")},
    )
    assert replaced["status"] == "review_required" and len(replaced["documents"]) == 2
    cycles = {s["cycle"] for s in replaced["approval_steps"]}
    assert cycles == {2}
    uploader_notes = reviewer.ok("GET", "/api/v1/notifications")["items"]
    assert any(n["kind"] == "invoice.review_required" for n in uploader_notes)


def test_audit_trail_reconstructs_decisions_and_chain_verifies(team: dict[str, Client]) -> None:
    owner, reviewer = team["owner"], team["reviewer"]
    invoice = upload(reviewer, sample_invoice("A-1"))
    decide(reviewer, invoice["id"], "reject", "Not ordered")
    history = reviewer.ok(
        "GET", f"/api/v1/audit-events?entity_type=invoice&entity_id={invoice['id']}"
    )
    actions = [e["action"] for e in reversed(history["items"])]
    assert actions[:3] == ["invoice.uploaded", "risk.assessed", "invoice.processed"]
    assert actions[-1] == "invoice.rejected"
    rejected = history["items"][0]
    assert rejected["actor_label"] == "reviewer@org-a.example"
    assert rejected["details"]["reason"] == "Not ordered"
    assert "risk_level" in rejected["details"]["evidence"]
    assert team["viewer"].get("/api/v1/audit-events").status_code == 403  # full log: admins
    assert owner.ok("GET", "/api/v1/audit-events/verify")["valid"] is True


def test_audit_events_are_append_only_in_the_database(team: dict[str, Client], db: Session) -> None:
    upload(team["reviewer"], sample_invoice("A-2"))
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(update(AuditEvent).values(action="tampered"))
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_events"))
    db.rollback()


def test_tampering_is_detected_by_chain_verification(team: dict[str, Client], db: Session) -> None:
    upload(team["reviewer"], sample_invoice("A-3"))
    db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only"))
    db.execute(
        text(
            'UPDATE audit_events SET details = \'{"reason": "edited"}\' '
            "WHERE sequence = 2 AND organization_id IS NOT NULL"
        )
    )
    db.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only"))
    db.commit()
    result = team["owner"].ok("GET", "/api/v1/audit-events/verify")
    assert result == {
        "valid": False,
        "events_checked": 1,
        "first_invalid_sequence": 2,
        "reason": "hash_mismatch",
    }


def test_dashboard_and_analytics_reflect_real_data(team: dict[str, Client]) -> None:
    reviewer = team["reviewer"]
    create_vendor(reviewer)
    upload(reviewer, sample_invoice("D-1"))
    duplicate = upload(reviewer, sample_invoice("D-1"))
    decide(reviewer, duplicate["id"], "reject", "Duplicate")
    dashboard = team["viewer"].ok("GET", "/api/v1/dashboard")
    assert dashboard["invoices_received"] == 2
    assert dashboard["requiring_review"] == 1 and dashboard["rejected"] == 1
    assert dashboard["potential_duplicates"] == 1
    assert dashboard["flagged_and_rejected"]["count"] == 1
    assert dashboard["flagged_and_rejected"]["total_value"] == "7788.00"
    assert "not a savings estimate" in dashboard["flagged_and_rejected"]["label"]
    assert dashboard["recent_activity"]
    analytics = team["viewer"].ok("GET", "/api/v1/analytics?days=30")
    assert analytics["duplicate_detections"] >= 2
    assert analytics["decisions"] == {"rejected": 1}
    assert analytics["invoice_volume"][0]["count"] == 2


def test_member_management_rules(team: dict[str, Client]) -> None:
    owner, admin = team["owner"], team["admin"]
    members = {m["email"]: m for m in owner.ok("GET", "/api/v1/organization/members")}
    reviewer_id = members["reviewer@org-a.example"]["membership_id"]
    owner_id = members["owner@org-a.example"]["membership_id"]
    admin_id = members["admin@org-a.example"]["membership_id"]
    assert (
        admin.patch(
            f"/api/v1/organization/members/{reviewer_id}", json={"role": "admin"}
        ).status_code
        == 403
    )  # admins cannot mint admins
    assert (
        admin.patch(
            f"/api/v1/organization/members/{owner_id}", json={"status": "disabled"}
        ).status_code
        == 403
    )
    assert (
        owner.patch(f"/api/v1/organization/members/{owner_id}", json={"role": "viewer"}).json()[
            "error"
        ]["code"]
        == "self_change"
    )
    admin.ok("PATCH", f"/api/v1/organization/members/{reviewer_id}", json={"status": "disabled"})
    blocked = team["reviewer"].get("/api/v1/invoices")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "membership_inactive"
    owner.ok("PATCH", f"/api/v1/organization/members/{admin_id}", json={"role": "viewer"})
    assert team["admin"].get("/api/v1/audit-events").status_code == 403
    assert team["viewer"].patch("/api/v1/organization", json={"name": "Hacked"}).status_code == 403

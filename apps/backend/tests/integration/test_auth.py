"""Authentication, sessions, CSRF, lockout, invitations."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, User, UserSession
from tests.integration.conftest import PASSWORD, Client

pytestmark = pytest.mark.integration


def test_signup_creates_owner_org_session_and_audit(api: FastAPI, db: Session) -> None:
    client = Client(api).signup("founder@acme.example", "Acme")
    assert client.me["organization"]["role"] == "owner"
    assert "invoice.approve_final" in client.me["permissions"]
    cookies = client.http.cookies
    assert cookies.get("irs_session") and cookies.get("irs_csrf")
    user = db.scalar(select(User).where(User.email == "founder@acme.example"))
    assert user is not None and user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    token = cookies.get("irs_session")
    assert db.scalar(select(UserSession.id).where(UserSession.token_hash == token)) is None
    actions = set(db.scalars(select(AuditEvent.action)))
    assert {"organization.created", "auth.signup"} <= actions


def test_session_cookie_is_httponly_and_samesite(api: FastAPI) -> None:
    response = Client(api).post(
        "/api/v1/auth/signup",
        json={
            "email": "c@x.example",
            "password": PASSWORD,
            "full_name": "C",
            "organization_name": "C Org",
        },
    )
    header = "; ".join(response.headers.get_list("set-cookie")).lower()
    assert "irs_session=" in header and "httponly" in header and "samesite=lax" in header


def test_duplicate_signup_and_weak_password_rejected(api: FastAPI, owner: Client) -> None:
    dup = Client(api).post(
        "/api/v1/auth/signup",
        json={
            "email": "OWNER@org-a.example",
            "password": PASSWORD,
            "full_name": "x",
            "organization_name": "Another",
        },
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"
    weak = Client(api).post(
        "/api/v1/auth/signup",
        json={
            "email": "w@x.example",
            "password": "short",
            "full_name": "x",
            "organization_name": "Org",
        },
    )
    assert weak.json()["error"]["code"] == "weak_password"


def test_login_logout_and_me(api: FastAPI, owner: Client) -> None:
    client = Client(api)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.login("owner@org-a.example").status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == "owner@org-a.example"
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_the_session_server_side(api: FastAPI, owner: Client) -> None:
    stolen = owner.http.cookies.get("irs_session")
    owner.post("/api/v1/auth/logout")
    attacker = Client(api)
    attacker.http.cookies.set("irs_session", stolen or "")
    assert attacker.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_is_generic_and_audited(api: FastAPI, owner: Client, db: Session) -> None:
    unknown = Client(api).login("nobody@x.example", "whatever-password")
    wrong = Client(api).login("owner@org-a.example", "wrong-password-123")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    failures = db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.login_failed")).all()
    assert len(failures) == 2
    assert all("password" not in str(e.details) for e in failures)


def test_account_locks_after_repeated_failures(api: FastAPI, owner: Client) -> None:
    client = Client(api)
    for _ in range(5):
        client.login("owner@org-a.example", "wrong-password-123")
    locked = client.login("owner@org-a.example")  # correct password, still locked
    assert locked.status_code == 401 and locked.json()["error"]["code"] == "account_locked"


def test_rate_limit_on_login(api: FastAPI) -> None:
    client = Client(api)
    codes = [client.login(f"user{i}@x.example", "whatever-password").status_code for i in range(40)]
    assert 429 in codes


def test_csrf_token_required_for_state_changes(api: FastAPI, owner: Client) -> None:
    body = {"name": "Vendor Without Csrf"}
    missing = owner.http.post("/api/v1/vendors", json=body)
    forged = owner.http.post("/api/v1/vendors", json=body, headers={"X-CSRF-Token": "forged"})
    assert missing.status_code == forged.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"
    assert owner.post("/api/v1/vendors", json=body).status_code == 201


def test_cross_origin_requests_rejected(api: FastAPI, owner: Client) -> None:
    response = owner.post(
        "/api/v1/vendors", json={"name": "Evil"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "origin_not_allowed"


def test_expired_and_idle_sessions_are_rejected(api: FastAPI, owner: Client, db: Session) -> None:
    db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert owner.get("/api/v1/auth/me").status_code == 401
    other = Client(api)
    other.login("owner@org-a.example")
    db.execute(
        update(UserSession)
        .where(UserSession.revoked_at.is_(None))
        .values(last_seen_at=datetime.now(UTC) - timedelta(hours=5))
    )
    db.commit()
    assert other.get("/api/v1/auth/me").status_code == 401


def test_invitation_flow_and_single_use(api: FastAPI, owner: Client) -> None:
    invitation = owner.ok(
        "POST",
        "/api/v1/organization/invitations",
        201,
        json={"email": "new@org-a.example", "role": "reviewer"},
    )
    token = invitation["invitation_url"].rsplit("/", 1)[-1]
    preview = Client(api).ok("GET", f"/api/v1/auth/invitations/{token}")
    assert preview["role"] == "reviewer" and preview["existing_user"] is False
    member = Client(api)
    member.ok(
        "POST",
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": "New", "password": PASSWORD},
    )
    assert member.get("/api/v1/auth/me").json()["organization"]["role"] == "reviewer"
    reuse = Client(api).post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "x", "password": PASSWORD}
    )
    assert reuse.status_code == 404


def test_user_in_two_orgs_can_switch(api: FastAPI, owner: Client, other_org: Client) -> None:
    invitation = other_org.ok(
        "POST",
        "/api/v1/organization/invitations",
        201,
        json={"email": "owner@org-a.example", "role": "viewer"},
    )
    token = invitation["invitation_url"].rsplit("/", 1)[-1]
    owner.ok("POST", f"/api/v1/auth/invitations/{token}/accept", json={"password": PASSWORD})
    me = owner.ok("GET", "/api/v1/auth/me")
    assert len(me["organizations"]) == 2
    org_b = next(o for o in me["organizations"] if o["name"] == "Org B Traders")
    switched = owner.ok(
        "POST", "/api/v1/auth/switch-organization", json={"organization_id": org_b["id"]}
    )
    assert switched["organization"]["role"] == "viewer"

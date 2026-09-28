"""Authentication, sessions, organizations, memberships and invitations."""

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    Conflict,
    InvalidInput,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    RateLimited,
)
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.finance.gst import gstin_state_code, normalize_gstin, validate_gstin
from app.infra.rate_limit import RateLimiter
from app.models import Invitation, Membership, Organization, User, UserSession
from app.models.enums import ActorType, MembershipStatus, Role
from app.modules.audit import service as audit
from app.modules.context import TenantContext
from app.modules.identity.schemas import (
    InvitationCreate,
    LoginRequest,
    OrganizationSettings,
    OrganizationUpdate,
    SignupRequest,
)
from app.modules.permissions import ASSIGNABLE_ROLES, Permission

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
_SESSION_TOUCH_SECONDS = 60


def _now() -> datetime:
    return datetime.now(UTC)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    return f"{slug}-{secrets.token_hex(3)}"


def organization_settings(org: Organization) -> OrganizationSettings:
    return OrganizationSettings.model_validate(org.settings or {})


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: UserSession


def create_session(
    db: Session,
    settings: Settings,
    user: User,
    organization_id: uuid.UUID | None,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    token = generate_token()
    now = _now()
    session = UserSession(
        user_id=user.id,
        organization_id=organization_id,
        token_hash=hash_token(token, settings.auth_secret.get_secret_value()),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(session)
    db.flush()
    return IssuedSession(token, session)


def resolve_session(
    db: Session, settings: Settings, token: str | None
) -> tuple[UserSession, User] | None:
    if not token or len(token) > 200:
        return None
    token_hash = hash_token(token, settings.auth_secret.get_secret_value())
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_hash)
    ).first()
    if row is None:
        return None
    session, user = row
    now = _now()
    idle_limit = session.last_seen_at + timedelta(minutes=settings.session_idle_timeout_minutes)
    if session.revoked_at or session.expires_at <= now or idle_limit <= now or not user.is_active:
        return None
    if (now - session.last_seen_at).total_seconds() > _SESSION_TOUCH_SECONDS:
        session.last_seen_at = now
        db.commit()
    return session, user


def active_memberships(db: Session, user_id: uuid.UUID) -> list[tuple[Membership, Organization]]:
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Membership.created_at)
    ).all()
    return [(m, o) for m, o in rows]


def membership_for(
    db: Session, user_id: uuid.UUID, organization_id: uuid.UUID
) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )


def signup(
    db: Session,
    settings: Settings,
    limiter: RateLimiter,
    request: SignupRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    limit = limiter.hit(f"signup:ip:{ip_address}", settings.signup_max_per_ip, 3600)
    if not limit.allowed:
        raise RateLimited(retry_after=limit.retry_after_seconds)
    email = request.email.lower()
    validate_password_policy(request.password, email)
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this email already exists", code="email_taken")

    user = User(
        email=email,
        full_name=request.full_name.strip(),
        password_hash=hash_password(request.password),
    )
    org = Organization(
        name=request.organization_name.strip(),
        slug=_slugify(request.organization_name),
        settings=OrganizationSettings().model_dump(mode="json"),
    )
    db.add_all([user, org])
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("An account with this email already exists", code="email_taken") from exc
    db.add(Membership(organization_id=org.id, user_id=user.id, role=Role.OWNER))
    issued = create_session(db, settings, user, org.id, ip_address, user_agent)
    ctx = TenantContext(org.id, user.id, user.email, Role.OWNER, ip_address=ip_address)
    audit.record(db, ctx, "organization.created", "organization", org.id, {"name": org.name})
    audit.record(db, ctx, "auth.signup", "user", user.id, {"email": email})
    db.commit()
    return issued


def login(
    db: Session,
    settings: Settings,
    limiter: RateLimiter,
    request: LoginRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    email = request.email.lower()
    window = settings.rate_limit_window_seconds
    for key, limit in (
        (f"login:ip:{ip_address}", settings.login_max_attempts_per_ip),
        (f"login:email:{email}", settings.login_max_attempts_per_email),
    ):
        result = limiter.hit(key, limit, window)
        if not result.allowed:
            raise RateLimited(retry_after=result.retry_after_seconds)

    user = db.scalar(select(User).where(User.email == email))
    now = _now()
    invalid = NotAuthenticated("Invalid email or password", code="invalid_credentials")

    if user is not None and user.locked_until and user.locked_until > now:
        verify_password(request.password, None)  # equalise timing
        audit.record(
            db,
            None,
            "auth.login_blocked",
            "user",
            user.id,
            {"reason": "locked"},
            actor_user_id=user.id,
            actor_label=email,
            actor_type=ActorType.USER,
            ip_address=ip_address,
        )
        db.commit()
        raise NotAuthenticated(
            "Account temporarily locked after repeated failed sign-ins. Try again later.",
            code="account_locked",
        )

    if (
        user is None
        or not user.is_active
        or not verify_password(request.password, user.password_hash if user else None)
    ):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_count = 0
        audit.record(
            db,
            None,
            "auth.login_failed",
            "user",
            user.id if user else None,
            {"email": email, "known_user": user is not None},
            actor_user_id=user.id if user else None,
            actor_label=email,
            actor_type=ActorType.USER,
            ip_address=ip_address,
        )
        db.commit()
        raise invalid

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(request.password)
    memberships = active_memberships(db, user.id)
    org_id = memberships[0][1].id if memberships else None
    issued = create_session(db, settings, user, org_id, ip_address, user_agent)
    if org_id:
        role = memberships[0][0].role
        audit.record(
            db,
            TenantContext(org_id, user.id, user.email, role, ip_address=ip_address),
            "auth.login",
            "user",
            user.id,
            {},
        )
    db.commit()
    limiter.reset(f"login:email:{email}")
    return issued


def logout(db: Session, session: UserSession, user: User) -> None:
    session.revoked_at = _now()
    if session.organization_id:
        membership = membership_for(db, user.id, session.organization_id)
        if membership:
            ctx = TenantContext(session.organization_id, user.id, user.email, membership.role)
            audit.record(db, ctx, "auth.logout", "user", user.id, {})
    db.commit()


def switch_organization(
    db: Session, session: UserSession, user: User, organization_id: uuid.UUID
) -> None:
    membership = membership_for(db, user.id, organization_id)
    if membership is None:
        raise NotFound()
    session.organization_id = organization_id
    audit.record(
        db,
        TenantContext(organization_id, user.id, user.email, membership.role),
        "auth.organization_switched",
        "user",
        user.id,
        {},
    )
    db.commit()


# --- Organization -------------------------------------------------------------------


def get_organization(db: Session, ctx: TenantContext) -> Organization:
    org = db.get(Organization, ctx.organization_id)
    if org is None:
        raise NotFound()
    return org


def inbound_email_address(settings: Settings, org: Organization) -> str:
    return f"invoices+{org.slug}@{settings.inbound_email_domain}"


def update_organization(
    db: Session, ctx: TenantContext, update: OrganizationUpdate
) -> Organization:
    ctx.require(Permission.ORG_MANAGE_SETTINGS)
    org = get_organization(db, ctx)
    changes: dict[str, object] = {}
    if update.name is not None and update.name.strip() != org.name:
        changes["name"] = {"from": org.name, "to": update.name.strip()}
        org.name = update.name.strip()
    if update.gstin is not None:
        gstin = normalize_gstin(update.gstin)
        if gstin:
            validation = validate_gstin(gstin)
            if not validation.valid:
                raise InvalidInput(f"Invalid GSTIN ({validation.reason})", code="invalid_gstin")
        if gstin != org.gstin:
            changes["gstin"] = {"from": org.gstin, "to": gstin}
            org.gstin = gstin
            org.state_code = gstin_state_code(gstin)
    if update.settings is not None:
        new_settings = update.settings.model_dump(mode="json")
        old_settings = organization_settings(org).model_dump(mode="json")
        diff = {
            k: {"from": old_settings.get(k), "to": v}
            for k, v in new_settings.items()
            if old_settings.get(k) != v
        }
        if diff:
            changes["settings"] = diff
            org.settings = new_settings
    if changes:
        audit.record(db, ctx, "organization.updated", "organization", org.id, changes)
    db.commit()
    return org


def rotate_ingestion_token(db: Session, settings: Settings, ctx: TenantContext) -> str:
    ctx.require(Permission.EMAIL_INGESTION_MANAGE)
    org = get_organization(db, ctx)
    token = generate_token()
    org.inbound_email_token_hash = hash_token(token, settings.auth_secret.get_secret_value())
    audit.record(db, ctx, "email_ingestion.token_rotated", "organization", org.id, {})
    db.commit()
    return token


# --- Members and invitations -----------------------------------------------------------


def list_members(db: Session, ctx: TenantContext) -> list[tuple[Membership, User]]:
    ctx.require(Permission.MEMBERS_READ)
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization_id)
        .order_by(Membership.created_at)
    ).all()
    return [(m, u) for m, u in rows]


def _owner_count(db: Session, organization_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == Role.OWNER,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        or 0
    )


def update_member(
    db: Session,
    ctx: TenantContext,
    membership_id: uuid.UUID,
    role: Role | None,
    status: MembershipStatus | None,
) -> Membership:
    ctx.require(Permission.MEMBERS_MANAGE)
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id, Membership.organization_id == ctx.organization_id
        )
    )
    if membership is None:
        raise NotFound()
    if membership.user_id == ctx.user_id:
        raise PermissionDenied("You cannot change your own membership", code="self_change")
    assignable = ASSIGNABLE_ROLES[ctx.role]
    if membership.role not in assignable or (role is not None and role not in assignable):
        raise PermissionDenied("Your role cannot manage this member or grant that role")
    removing_owner = membership.role == Role.OWNER and (
        (role is not None and role != Role.OWNER) or status == MembershipStatus.DISABLED
    )
    if removing_owner and _owner_count(db, ctx.organization_id) <= 1:
        raise Conflict("An organization must keep at least one owner", code="last_owner")
    changes: dict[str, object] = {}
    if role is not None and role != membership.role:
        changes["role"] = {"from": membership.role.value, "to": role.value}
        membership.role = role
    if status is not None and status != membership.status:
        changes["status"] = {"from": membership.status.value, "to": status.value}
        membership.status = status
    if changes:
        audit.record(
            db,
            ctx,
            "member.updated",
            "membership",
            membership.id,
            {"user_id": membership.user_id, **changes},
        )
    db.commit()
    return membership


def create_invitation(
    db: Session, settings: Settings, ctx: TenantContext, request: InvitationCreate
) -> tuple[Invitation, str]:
    ctx.require(Permission.MEMBERS_MANAGE)
    if request.role not in ASSIGNABLE_ROLES[ctx.role]:
        raise PermissionDenied("Your role cannot grant that role")
    existing_member = db.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization_id, User.email == request.email)
    )
    if existing_member:
        raise Conflict("That user is already a member", code="already_member")
    token = generate_token()
    invitation = Invitation(
        organization_id=ctx.organization_id,
        email=request.email,
        role=request.role,
        token_hash=hash_token(token, settings.auth_secret.get_secret_value()),
        invited_by_id=ctx.user_id,
        expires_at=_now() + timedelta(hours=settings.invitation_ttl_hours),
    )
    db.add(invitation)
    db.flush()
    audit.record(
        db,
        ctx,
        "member.invited",
        "invitation",
        invitation.id,
        {"email": request.email, "role": request.role.value},
    )
    db.commit()
    return invitation, f"{settings.app_base_url.rstrip('/')}/invite/{token}"


def list_invitations(db: Session, ctx: TenantContext) -> list[Invitation]:
    ctx.require(Permission.MEMBERS_MANAGE)
    return list(
        db.scalars(
            select(Invitation)
            .where(
                Invitation.organization_id == ctx.organization_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.created_at.desc())
        )
    )


def revoke_invitation(db: Session, ctx: TenantContext, invitation_id: uuid.UUID) -> None:
    ctx.require(Permission.MEMBERS_MANAGE)
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.organization_id == ctx.organization_id
        )
    )
    if invitation is None or invitation.accepted_at:
        raise NotFound()
    invitation.revoked_at = _now()
    audit.record(
        db,
        ctx,
        "member.invitation_revoked",
        "invitation",
        invitation.id,
        {"email": invitation.email},
    )
    db.commit()


def _open_invitation(db: Session, settings: Settings, token: str) -> Invitation:
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.token_hash == hash_token(token, settings.auth_secret.get_secret_value())
        )
    )
    if (
        invitation is None
        or invitation.accepted_at
        or invitation.revoked_at
        or invitation.expires_at <= _now()
    ):
        raise NotFound("Invitation is invalid or has expired", code="invitation_invalid")
    return invitation


def preview_invitation(
    db: Session, settings: Settings, token: str
) -> tuple[Invitation, Organization, bool]:
    invitation = _open_invitation(db, settings, token)
    org = db.get(Organization, invitation.organization_id)
    assert org is not None  # noqa: S101
    exists = db.scalar(select(User.id).where(User.email == invitation.email)) is not None
    return invitation, org, exists


def accept_invitation(
    db: Session,
    settings: Settings,
    token: str,
    full_name: str | None,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    invitation = _open_invitation(db, settings, token)
    user = db.scalar(select(User).where(User.email == invitation.email))
    if user is None:
        if not full_name or not full_name.strip():
            raise InvalidInput("Full name is required", code="full_name_required")
        validate_password_policy(password, invitation.email)
        user = User(
            email=invitation.email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(password, user.password_hash):
        raise NotAuthenticated(
            "Invalid password for the existing account", code="invalid_credentials"
        )
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == invitation.organization_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        membership = Membership(
            organization_id=invitation.organization_id, user_id=user.id, role=invitation.role
        )
        db.add(membership)
    else:
        membership.status = MembershipStatus.ACTIVE
        membership.role = invitation.role
    invitation.accepted_at = _now()
    db.flush()
    ctx = TenantContext(
        invitation.organization_id, user.id, user.email, membership.role, ip_address=ip_address
    )
    audit.record(
        db,
        ctx,
        "member.joined",
        "membership",
        membership.id,
        {"role": membership.role.value, "invitation_id": invitation.id},
    )
    issued = create_session(db, settings, user, invitation.organization_id, ip_address, user_agent)
    db.commit()
    return issued

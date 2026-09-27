"""Authentication: signup, login, logout, current user, organization switching, invitations."""

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    AuthDep,
    DbDep,
    LimiterDep,
    SettingsDep,
    client_ip,
    verify_origin,
)
from app.api.v1.common import Message
from app.core.config import Settings
from app.core.errors import NotFound, RateLimited
from app.core.security import csrf_token_for
from app.models import User, UserSession
from app.modules.identity import service
from app.modules.identity.schemas import (
    InvitationAccept,
    InvitationPreview,
    LoginRequest,
    MeResponse,
    OrganizationSummary,
    SignupRequest,
    SwitchOrganizationRequest,
)
from app.modules.permissions import permissions_for

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(verify_origin)])


def _set_session_cookies(
    response: Response, settings: Settings, issued: service.IssuedSession
) -> None:
    max_age = settings.session_ttl_hours * 3600
    common = {
        "max_age": max_age,
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(SESSION_COOKIE, issued.token, httponly=True, **common)  # type: ignore[arg-type]
    csrf = csrf_token_for(issued.session.token_hash, settings.auth_secret.get_secret_value())
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)  # type: ignore[arg-type]


def _clear_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name, path="/", secure=settings.session_cookie_secure, samesite="lax"
        )


def build_me(db: DbDep, settings: Settings, session: UserSession, user: User) -> MeResponse:
    memberships = service.active_memberships(db, user.id)
    summaries = [
        OrganizationSummary(id=o.id, name=o.name, slug=o.slug, role=m.role) for m, o in memberships
    ]
    current = next((s for s in summaries if s.id == session.organization_id), None)
    return MeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        organization=current,
        organizations=summaries,
        permissions=permissions_for(current.role) if current else [],
        csrf_token=csrf_token_for(session.token_hash, settings.auth_secret.get_secret_value()),
        session_expires_at=session.expires_at,
    )


def _user(db: DbDep, issued: service.IssuedSession) -> User:
    user = db.get(User, issued.session.user_id)
    if user is None:
        raise NotFound()
    return user


@router.post("/signup", response_model=MeResponse, status_code=201)
def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
) -> MeResponse:
    issued = service.signup(
        db, settings, limiter, body, client_ip(request), request.headers.get("user-agent")
    )
    _set_session_cookies(response, settings, issued)
    user = _user(db, issued)
    return build_me(db, settings, issued.session, user)


@router.post("/login", response_model=MeResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
) -> MeResponse:
    issued = service.login(
        db, settings, limiter, body, client_ip(request), request.headers.get("user-agent")
    )
    _set_session_cookies(response, settings, issued)
    user = _user(db, issued)
    return build_me(db, settings, issued.session, user)


@router.post("/logout", response_model=Message)
def logout(auth: AuthDep, response: Response, db: DbDep, settings: SettingsDep) -> Message:
    service.logout(db, auth.session, auth.user)
    _clear_cookies(response, settings)
    return Message(message="Signed out")


@router.get("/me", response_model=MeResponse)
def me(auth: AuthDep, db: DbDep, settings: SettingsDep) -> MeResponse:
    return build_me(db, settings, auth.session, auth.user)


@router.post("/switch-organization", response_model=MeResponse)
def switch_organization(
    body: SwitchOrganizationRequest, auth: AuthDep, db: DbDep, settings: SettingsDep
) -> MeResponse:
    service.switch_organization(db, auth.session, auth.user, body.organization_id)
    return build_me(db, settings, auth.session, auth.user)


@router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, db: DbDep, settings: SettingsDep) -> InvitationPreview:
    invitation, org, exists = service.preview_invitation(db, settings, token)
    return InvitationPreview(
        organization_name=org.name,
        email=invitation.email,
        role=invitation.role,
        existing_user=exists,
    )


@router.post("/invitations/{token}/accept", response_model=MeResponse)
def accept_invitation(
    token: str,
    body: InvitationAccept,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
) -> MeResponse:
    result = limiter.hit(
        f"invite:ip:{client_ip(request)}",
        settings.login_max_attempts_per_ip,
        settings.rate_limit_window_seconds,
    )
    if not result.allowed:
        raise RateLimited(retry_after=result.retry_after_seconds)
    issued = service.accept_invitation(
        db,
        settings,
        token,
        body.full_name,
        body.password,
        client_ip(request),
        request.headers.get("user-agent"),
    )
    _set_session_cookies(response, settings, issued)
    user = _user(db, issued)
    return build_me(db, settings, issued.session, user)

"""FastAPI dependencies: infrastructure handles, sessions, CSRF, tenant context, RBAC."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.ai.provider import AIProvider
from app.core.config import Settings
from app.core.errors import NotAuthenticated, PermissionDenied
from app.core.logging import organization_id_var, user_id_var
from app.core.security import FieldEncryptor, csrf_token_for, tokens_match
from app.infra.rate_limit import RateLimiter
from app.infra.storage import StorageProvider
from app.infra.tasks import TaskDispatcher
from app.models import User, UserSession
from app.modules.context import TenantContext
from app.modules.identity.service import membership_for, resolve_session
from app.modules.permissions import Permission

SESSION_COOKIE = "irs_session"
CSRF_COOKIE = "irs_csrf"
CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.resources.session_factory() as session:
        yield session


def get_storage(request: Request) -> StorageProvider:
    storage: StorageProvider = request.app.state.resources.storage
    return storage


def get_dispatcher(request: Request) -> TaskDispatcher:
    dispatcher: TaskDispatcher = request.app.state.dispatcher
    return dispatcher


def get_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def get_encryptor(request: Request) -> FieldEncryptor:
    encryptor: FieldEncryptor = request.app.state.encryptor
    return encryptor


def get_ai(request: Request) -> AIProvider:
    ai: AIProvider = request.app.state.ai
    return ai


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]
StorageDep = Annotated[StorageProvider, Depends(get_storage)]
DispatcherDep = Annotated[TaskDispatcher, Depends(get_dispatcher)]
LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]
EncryptorDep = Annotated[FieldEncryptor, Depends(get_encryptor)]


def client_ip(request: Request) -> str | None:
    settings: Settings = request.app.state.settings
    hops = settings.trusted_proxy_hops
    if hops:
        forwarded = [
            p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
        ]
        if len(forwarded) >= hops:
            return forwarded[-hops][:64]
    return request.client.host if request.client else None


def _allowed_origins(settings: Settings) -> set[str]:
    origins = {o.rstrip("/") for o in settings.cors_allowed_origins}
    parts = urlsplit(settings.app_base_url)
    origins.add(f"{parts.scheme}://{parts.netloc}")
    return origins


def verify_origin(request: Request, settings: SettingsDep) -> None:
    """Rejects cross-site state-changing requests (defence in depth with SameSite + CSRF)."""
    if request.method in _SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in _allowed_origins(settings):
        raise PermissionDenied("Cross-origin request rejected", code="origin_not_allowed")


@dataclass(frozen=True)
class AuthSession:
    session: UserSession
    user: User


def require_session(request: Request, db: DbDep, settings: SettingsDep) -> AuthSession:
    resolved = resolve_session(db, settings, request.cookies.get(SESSION_COOKIE))
    if resolved is None:
        raise NotAuthenticated()
    session, user = resolved
    user_id_var.set(str(user.id))
    if request.method not in _SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER, "")
        expected = csrf_token_for(session.token_hash, settings.auth_secret.get_secret_value())
        if not header or not tokens_match(header, expected):
            raise PermissionDenied("Missing or invalid CSRF token", code="csrf_failed")
    return AuthSession(session, user)


AuthDep = Annotated[AuthSession, Depends(require_session)]


def require_tenant(request: Request, auth: AuthDep, db: DbDep) -> TenantContext:
    org_id = auth.session.organization_id
    if org_id is None:
        raise PermissionDenied("No active organization", code="no_organization")
    membership = membership_for(db, auth.user.id, org_id)
    if membership is None:
        raise PermissionDenied(
            "You are no longer a member of this organization", code="membership_inactive"
        )
    organization_id_var.set(str(org_id))
    return TenantContext(
        organization_id=org_id,
        user_id=auth.user.id,
        user_email=auth.user.email,
        role=membership.role,
        request_id=getattr(request.state, "request_id", None),
        ip_address=client_ip(request),
    )


TenantDep = Annotated[TenantContext, Depends(require_tenant)]


def require_permission(permission: Permission) -> Callable[[TenantContext], TenantContext]:
    def dependency(ctx: TenantDep) -> TenantContext:
        ctx.require(permission)
        return ctx

    return dependency


def parse_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)

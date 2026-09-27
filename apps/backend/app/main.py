"""FastAPI application factory."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai import create_ai_provider
from app.ai.provider import AIProvider
from app.api import health
from app.api.v1.router import build_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.security import FieldEncryptor
from app.infra.rate_limit import RateLimiter, RedisRateLimiter
from app.infra.resources import ReadinessCheck, Resources
from app.infra.tasks import CeleryTaskDispatcher, TaskDispatcher
from app.worker.celery_app import create_celery_app

API_VERSION = "1.0.0"


@dataclass
class Overrides:
    """Test seams: replace infrastructure without touching production wiring."""

    readiness_checks: Sequence[ReadinessCheck] | None = None
    resources: Resources | None = None
    dispatcher: TaskDispatcher | None = None
    rate_limiter: RateLimiter | None = None
    ai: AIProvider | None = None


def create_app(
    settings: Settings | None = None,
    readiness_checks: Sequence[ReadinessCheck] | None = None,
    overrides: Overrides | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    overrides = overrides or Overrides(readiness_checks=readiness_checks)
    if readiness_checks is not None:
        overrides.readiness_checks = readiness_checks
    configure_logging(settings.log_level, service="api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = overrides.resources or Resources.from_settings(settings)
        celery = create_celery_app(settings)
        app.state.settings = settings
        app.state.resources = resources
        app.state.celery = celery
        app.state.encryptor = FieldEncryptor(settings.encryption_key_bytes)
        app.state.dispatcher = overrides.dispatcher or CeleryTaskDispatcher(celery)
        app.state.rate_limiter = overrides.rate_limiter or RedisRateLimiter(resources.redis)
        app.state.ai = overrides.ai or create_ai_provider(settings)
        app.state.readiness_checks = (
            list(overrides.readiness_checks)
            if overrides.readiness_checks is not None
            else resources.readiness_checks()
        )
        try:
            yield
        finally:
            if overrides.resources is None:
                resources.close()
            celery.close()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version=API_VERSION,
        debug=False,  # never render tracebacks to clients, in any environment
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(build_v1_router(settings))

    # Middleware added last runs first: request context wraps everything.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_request_body_bytes,
        path_limits={
            r"/api/v1/email-ingestion/inbound": settings.max_inbound_email_bytes,
            # Multipart overhead on top of the file itself.
            r"/api/v1/invoices/upload": settings.max_upload_bytes + 65_536,
            r"/api/v1/invoices/[0-9a-fA-F-]{36}/documents": settings.max_upload_bytes + 65_536,
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware, google_cloud_project=settings.google_cloud_project)
    return app

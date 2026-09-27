"""FastAPI application factory."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1.router import build_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.infra.resources import ReadinessCheck, Resources
from app.worker.celery_app import create_celery_app

API_VERSION = "0.1.0"


def create_app(
    settings: Settings | None = None,
    readiness_checks: Sequence[ReadinessCheck] | None = None,
) -> FastAPI:
    """Builds the API.

    `readiness_checks` lets tests replace real dependency probes; when omitted, the
    probes are built from real infrastructure clients at startup.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resources = Resources.from_settings(settings)
        celery = create_celery_app(settings)
        app.state.resources = resources
        app.state.celery = celery
        app.state.readiness_checks = (
            list(readiness_checks) if readiness_checks is not None else resources.readiness_checks()
        )
        try:
            yield
        finally:
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

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(build_v1_router(settings))

    # Middleware added last runs first: request context wraps everything.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    return app

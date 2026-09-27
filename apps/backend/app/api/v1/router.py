"""Version 1 of the public API, mounted at /api/v1.

Domain modules (auth, organizations, vendors, invoices, ...) will register their
routers here as they are built.
"""

from fastapi import APIRouter

from app.api.v1 import diagnostics
from app.core.config import Settings


def build_v1_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    if settings.enable_diagnostics_endpoints:
        router.include_router(diagnostics.router)
    return router

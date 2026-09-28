"""Version 1 of the public API, mounted at /api/v1."""

from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    audit,
    auth,
    dashboard,
    diagnostics,
    email_ingestion,
    invoices,
    notifications,
    organization,
    purchase_orders,
    vendors,
)
from app.core.config import Settings


def build_v1_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    for module in (
        auth,
        organization,
        vendors,
        purchase_orders,
        invoices,
        approvals,
        notifications,
        audit,
        dashboard,
        email_ingestion,
    ):
        router.include_router(module.router)
    if settings.enable_diagnostics_endpoints:
        router.include_router(diagnostics.router)
    return router

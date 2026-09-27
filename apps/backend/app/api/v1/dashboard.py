"""Dashboard and analytics."""

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import DbDep, TenantDep
from app.modules.analytics import service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(ctx: TenantDep, db: DbDep) -> dict[str, Any]:
    return service.dashboard(db, ctx)


@router.get("/analytics")
def analytics(
    ctx: TenantDep, db: DbDep, days: int = Query(default=90, ge=7, le=730)
) -> dict[str, Any]:
    return service.analytics(db, ctx, days)

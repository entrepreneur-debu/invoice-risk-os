"""Audit log (read-only; there is no endpoint that edits or deletes audit events)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import DbDep, TenantDep
from app.api.v1.common import Page, Pagination
from app.core.errors import PermissionDenied
from app.models import AuditEvent
from app.modules.audit import service
from app.modules.permissions import Permission

router = APIRouter(prefix="/audit-events", tags=["audit"])


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    sequence: int
    occurred_at: datetime
    actor_type: str
    actor_label: str | None
    action: str
    entity_type: str
    entity_id: str | None
    request_id: str | None
    ip_address: str | None
    details: dict[str, Any]
    hash: str


class ChainVerificationResponse(BaseModel):
    valid: bool
    events_checked: int
    first_invalid_sequence: int | None
    reason: str | None


_ENTITY_READ_PERMISSIONS = {
    "invoice": Permission.INVOICE_READ,
    "vendor": Permission.VENDOR_READ,
    "purchase_order": Permission.PO_READ,
}


@router.get("", response_model=Page[AuditEventResponse])
def list_events(
    ctx: TenantDep,
    db: DbDep,
    page: Pagination = Depends(),
    entity_type: str | None = Query(default=None, max_length=32),
    entity_id: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=100),
) -> Page[AuditEventResponse]:
    # The full log needs audit.read; an entity's own history needs read access to that entity.
    if not ctx.can(Permission.AUDIT_READ):
        needed = _ENTITY_READ_PERMISSIONS.get(entity_type or "")
        if needed is None or entity_id is None or not ctx.can(needed):
            raise PermissionDenied(permission=Permission.AUDIT_READ.value)
    stmt = select(AuditEvent).where(AuditEvent.organization_id == ctx.organization_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AuditEvent.action).like(like),
                func.lower(AuditEvent.actor_label).like(like),
            )
        )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    events = db.scalars(
        stmt.order_by(AuditEvent.sequence.desc()).limit(page.limit).offset(page.offset)
    )
    return Page(
        items=[
            AuditEventResponse.model_validate(
                {
                    **{
                        c: getattr(e, c)
                        for c in (
                            "id",
                            "sequence",
                            "occurred_at",
                            "actor_label",
                            "action",
                            "entity_type",
                            "entity_id",
                            "request_id",
                            "ip_address",
                            "details",
                            "hash",
                        )
                    },
                    "actor_type": e.actor_type.value,
                }
            )
            for e in events
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/verify", response_model=ChainVerificationResponse)
def verify_chain(ctx: TenantDep, db: DbDep) -> ChainVerificationResponse:
    ctx.require(Permission.AUDIT_READ)
    result = service.verify_chain(db, ctx.organization_id)
    return ChainVerificationResponse(
        valid=result.valid,
        events_checked=result.events_checked,
        first_invalid_sequence=result.first_invalid_sequence,
        reason=result.reason,
    )

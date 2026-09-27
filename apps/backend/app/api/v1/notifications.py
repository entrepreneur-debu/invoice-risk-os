"""In-app notifications for the current user."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import DbDep, TenantDep, verify_origin
from app.api.v1.common import Message, Page, Pagination
from app.models.enums import Severity
from app.modules.notifications import service

router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(verify_origin)]
)


class NotificationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    severity: Severity
    title: str
    body: str
    entity_type: str | None
    entity_id: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


@router.get("", response_model=Page[NotificationResponse])
def list_notifications(
    ctx: TenantDep, db: DbDep, page: Pagination = Depends(), unread_only: bool = False
) -> Page[NotificationResponse]:
    items, total = service.list_for_user(
        db, ctx, unread_only=unread_only, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[NotificationResponse.model_validate(n, from_attributes=True) for n in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(ctx: TenantDep, db: DbDep) -> UnreadCount:
    return UnreadCount(unread=service.unread_count(db, ctx))


@router.post("/{notification_id}/read", response_model=Message)
def mark_read(notification_id: uuid.UUID, ctx: TenantDep, db: DbDep) -> Message:
    service.mark_read(db, ctx, notification_id)
    return Message(message="Marked as read")


@router.post("/read-all", response_model=Message)
def mark_all_read(ctx: TenantDep, db: DbDep) -> Message:
    count = service.mark_all_read(db, ctx)
    return Message(message=f"{count} notification(s) marked as read")

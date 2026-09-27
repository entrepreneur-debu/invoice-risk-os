"""Internal notifications, addressed by permission (e.g. everyone who can review).

In-app records are the source of truth. External channels (email, Slack) are delivered
asynchronously from those records through `NotificationChannel` implementations; only
a logging channel exists in V1 (see docs/architecture.md "Notifications").
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Membership, Notification
from app.models.enums import MembershipStatus, Role, Severity
from app.modules.context import TenantContext
from app.modules.permissions import ROLE_PERMISSIONS, Permission

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    name: str

    def deliver(self, notification: Notification) -> None: ...


class LogChannel:
    """Records that a notification would be sent; never logs its body."""

    name = "log"

    def deliver(self, notification: Notification) -> None:
        logger.info(
            "notification delivered",
            extra={
                "channel": self.name,
                "kind": notification.kind,
                "notification_id": str(notification.id),
            },
        )


def recipients_with_permission(
    db: Session, organization_id: uuid.UUID, permission: Permission
) -> list[uuid.UUID]:
    roles = [role for role in Role if permission in ROLE_PERMISSIONS[role]]
    return list(
        db.scalars(
            select(Membership.user_id).where(
                Membership.organization_id == organization_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.role.in_(roles),
            )
        )
    )


def notify(
    db: Session,
    organization_id: uuid.UUID,
    recipient_ids: list[uuid.UUID],
    *,
    kind: str,
    title: str,
    body: str,
    severity: Severity = Severity.INFO,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    exclude_user_id: uuid.UUID | None = None,
) -> list[Notification]:
    created: list[Notification] = []
    for recipient_id in dict.fromkeys(recipient_ids):
        if recipient_id == exclude_user_id:
            continue
        notification = Notification(
            organization_id=organization_id,
            recipient_id=recipient_id,
            kind=kind,
            severity=severity,
            title=title[:200],
            body=body,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
        )
        db.add(notification)
        created.append(notification)
    db.flush()
    return created


def notify_permission(
    db: Session,
    organization_id: uuid.UUID,
    permission: Permission,
    **kwargs: object,
) -> list[Notification]:
    recipients = recipients_with_permission(db, organization_id, permission)
    return notify(db, organization_id, recipients, **kwargs)  # type: ignore[arg-type]


def list_for_user(
    db: Session, ctx: TenantContext, *, unread_only: bool, limit: int, offset: int
) -> tuple[list[Notification], int]:
    base = select(Notification).where(
        Notification.organization_id == ctx.organization_id,
        Notification.recipient_id == ctx.user_id,
    )
    if unread_only:
        base = base.where(Notification.read_at.is_(None))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    items = list(
        db.scalars(base.order_by(Notification.created_at.desc()).limit(limit).offset(offset))
    )
    return items, total


def unread_count(db: Session, ctx: TenantContext) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.organization_id == ctx.organization_id,
                Notification.recipient_id == ctx.user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def mark_read(db: Session, ctx: TenantContext, notification_id: uuid.UUID) -> Notification:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == ctx.organization_id,
            Notification.recipient_id == ctx.user_id,
        )
    )
    if notification is None:
        raise NotFound()
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
    db.commit()
    return notification


def mark_all_read(db: Session, ctx: TenantContext) -> int:
    result = db.execute(
        update(Notification)
        .where(
            Notification.organization_id == ctx.organization_id,
            Notification.recipient_id == ctx.user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]

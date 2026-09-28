"""In-app notifications. Other channels (email, Slack) deliver from the same records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, UUIDPrimaryKey
from app.db.types import enum_column
from app.models.enums import Severity


class Notification(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_unread", "recipient_id", "read_at"),)

    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64))
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "notification_severity"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

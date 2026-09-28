"""Inbound invoice emails (traceability for the email ingestion channel)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, UUIDPrimaryKey
from app.db.types import enum_column
from app.models.enums import InboundEmailStatus


class InboundEmail(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "inbound_emails"
    __table_args__ = (UniqueConstraint("organization_id", "message_id", name="org_message"),)

    message_id: Mapped[str] = mapped_column(String(255))
    from_address: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(300))
    storage_key: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[InboundEmailStatus] = mapped_column(
        enum_column(InboundEmailStatus, "inbound_email_status"),
        default=InboundEmailStatus.RECEIVED,
    )
    attachments_accepted: Mapped[int] = mapped_column(Integer, default=0)
    attachments_rejected: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_invoice_ids: Mapped[str | None] = mapped_column(String(2000))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

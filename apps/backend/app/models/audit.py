"""Tamper-evident audit trail.

Rows are append-only: a database trigger (see the initial migration) rejects UPDATE and
DELETE. Each row stores a SHA-256 hash chained to the previous row of the same
organization, so gaps or edits are detectable by `GET /api/v1/audit-events/verify`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey
from app.db.types import JSONType, enum_column
from app.models.enums import ActorType


class AuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "sequence", name="org_sequence"),
        Index("ix_audit_events_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_audit_events_org_occurred", "organization_id", "occurred_at"),
    )

    # Null only for events outside any tenant (e.g. failed login for an unknown email).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[ActorType] = mapped_column(enum_column(ActorType, "audit_actor_type"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_label: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    # Sanitised details (no secrets, masked bank data). Enough to reconstruct the event.
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

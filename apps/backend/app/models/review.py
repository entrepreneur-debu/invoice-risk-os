"""Human review decisions and approval steps. Decisions are append-only."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, UUIDPrimaryKey
from app.db.types import JSONType, enum_column
from app.models.enums import ApprovalStepStatus, ReviewDecision


class Review(UUIDPrimaryKey, TenantOwned, Base):
    """Every reviewer action: who, when, what decision, why, and the evidence they saw."""

    __tablename__ = "reviews"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision: Mapped[ReviewDecision] = mapped_column(enum_column(ReviewDecision, "review_decision"))
    step_no: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    # Risk level, open/accepted signal ids and amounts at decision time.
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalStep(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "approval_steps"
    __table_args__ = (UniqueConstraint("invoice_id", "step_no", "cycle", name="invoice_step"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    # A new cycle starts each time the invoice re-enters review (e.g. after changes).
    cycle: Mapped[int] = mapped_column(Integer, default=1)
    step_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    required_permission: Mapped[str] = mapped_column(String(64))
    status: Mapped[ApprovalStepStatus] = mapped_column(
        enum_column(ApprovalStepStatus, "approval_step_status"),
        default=ApprovalStepStatus.PENDING,
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="SET NULL")
    )
    reason_required: Mapped[str | None] = mapped_column(Text)

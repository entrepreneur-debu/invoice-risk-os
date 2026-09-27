"""Invoice state machine. Every transition is validated and recorded (no silent changes)."""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import Invoice, InvoiceStatusChange
from app.models.enums import ActorType, InvoiceStatus

S = InvoiceStatus
ALLOWED_TRANSITIONS: dict[InvoiceStatus, frozenset[InvoiceStatus]] = {
    S.UPLOADED: frozenset({S.QUEUED, S.FAILED}),
    S.QUEUED: frozenset({S.PROCESSING, S.FAILED}),
    S.PROCESSING: frozenset({S.EXTRACTED, S.FAILED, S.QUEUED}),
    S.EXTRACTED: frozenset({S.RISK_ANALYSIS, S.FAILED}),
    S.RISK_ANALYSIS: frozenset({S.REVIEW_REQUIRED, S.FAILED}),
    S.REVIEW_REQUIRED: frozenset(
        {S.PENDING_APPROVAL, S.APPROVED, S.REJECTED, S.NEEDS_CHANGES, S.RISK_ANALYSIS}
    ),
    S.PENDING_APPROVAL: frozenset({S.APPROVED, S.REJECTED, S.NEEDS_CHANGES, S.RISK_ANALYSIS}),
    S.NEEDS_CHANGES: frozenset({S.QUEUED, S.RISK_ANALYSIS}),
    S.FAILED: frozenset({S.QUEUED, S.RISK_ANALYSIS}),
    S.APPROVED: frozenset(),
    S.REJECTED: frozenset(),
}


def transition(
    db: Session,
    invoice: Invoice,
    to_status: InvoiceStatus,
    *,
    actor_type: ActorType,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> None:
    current = invoice.status
    if to_status == current:
        return
    if to_status not in ALLOWED_TRANSITIONS[current]:
        raise Conflict(
            f"Invoice cannot move from {current.value} to {to_status.value}",
            code="invalid_status_transition",
        )
    invoice.status = to_status
    db.add(
        InvoiceStatusChange(
            organization_id=invoice.organization_id,
            invoice_id=invoice.id,
            from_status=current.value,
            to_status=to_status.value,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            reason=reason[:1000] if reason else None,
        )
    )

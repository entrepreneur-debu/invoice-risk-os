"""Human review and approval workflow. Humans are the control point.

Policy (per organization, see OrganizationSettings):
- Every invoice needs step 1 "review" (permission invoice.review).
- A second step "final_approval" (permission invoice.approve_final) is added when the
  total >= high_value_threshold or the risk level is in second_approval_risk_levels.
- The final approver must be a different person from the step-1 approver.
- Open HIGH-severity rule signals block approval until an authorised user records
  "risk accepted" (or dismisses them) with a reason.
- Every decision requires a reason and stores an evidence snapshot. Nothing is automatic:
  no invoice is approved or rejected by the system or by AI. There is no payment step.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, PermissionDenied
from app.models import ApprovalStep, Invoice, Review, RiskAssessment, RiskSignal
from app.models.enums import (
    DECIDABLE_STATUSES,
    ActorType,
    ApprovalStepStatus,
    InvoiceStatus,
    ReviewDecision,
    RiskLevel,
    Severity,
    SignalResolution,
    SignalSource,
)
from app.modules.audit import service as audit
from app.modules.context import TenantContext
from app.modules.identity.schemas import OrganizationSettings
from app.modules.invoices.schemas import DecisionRequest, SignalResolutionRequest
from app.modules.invoices.state import transition
from app.modules.notifications import service as notifications
from app.modules.permissions import Permission

STEP_REVIEW = ("review", Permission.INVOICE_REVIEW)
STEP_FINAL = ("final_approval", Permission.INVOICE_APPROVE_FINAL)


def required_approvals(
    invoice: Invoice, settings: OrganizationSettings, risk_level: RiskLevel
) -> int:
    high_value = invoice.total is not None and invoice.total >= settings.high_value_threshold
    risky = risk_level in settings.second_approval_risk_levels
    return 2 if high_value or risky else 1


def current_cycle(db: Session, invoice_id: uuid.UUID) -> int:
    return int(
        db.scalar(select(func.max(ApprovalStep.cycle)).where(ApprovalStep.invoice_id == invoice_id))
        or 0
    )


def steps_for_cycle(db: Session, invoice_id: uuid.UUID, cycle: int) -> list[ApprovalStep]:
    return list(
        db.scalars(
            select(ApprovalStep)
            .where(
                ApprovalStep.invoice_id == invoice_id,
                ApprovalStep.cycle == cycle,
            )
            .order_by(ApprovalStep.step_no)
        )
    )


def open_approval_cycle(
    db: Session, invoice: Invoice, settings: OrganizationSettings, risk_level: RiskLevel
) -> int:
    """Starts a fresh approval cycle (earlier pending steps are cancelled)."""
    previous = current_cycle(db, invoice.id)
    for step in steps_for_cycle(db, invoice.id, previous):
        if step.status == ApprovalStepStatus.PENDING:
            step.status = ApprovalStepStatus.CANCELLED
    cycle = previous + 1
    needed = required_approvals(invoice, settings, risk_level)
    invoice.required_approvals = needed
    definitions = [STEP_REVIEW, STEP_FINAL][:needed]
    for step_no, (name, permission) in enumerate(definitions, start=1):
        db.add(
            ApprovalStep(
                organization_id=invoice.organization_id,
                invoice_id=invoice.id,
                cycle=cycle,
                step_no=step_no,
                name=name,
                required_permission=permission.value,
            )
        )
    db.flush()
    return needed


def _get_invoice(db: Session, ctx: TenantContext, invoice_id: uuid.UUID) -> Invoice:
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.organization_id == ctx.organization_id)
        .with_for_update()
    )
    if invoice is None:
        raise NotFound()
    return invoice


def current_assessment(db: Session, invoice: Invoice) -> RiskAssessment | None:
    return db.scalar(
        select(RiskAssessment).where(
            RiskAssessment.invoice_id == invoice.id,
            RiskAssessment.organization_id == invoice.organization_id,
            RiskAssessment.is_current.is_(True),
        )
    )


def _signals(db: Session, assessment: RiskAssessment | None) -> list[RiskSignal]:
    if assessment is None:
        return []
    return list(
        db.scalars(
            select(RiskSignal).where(
                RiskSignal.assessment_id == assessment.id,
                RiskSignal.organization_id == assessment.organization_id,
            )
        )
    )


def _snapshot(
    invoice: Invoice, assessment: RiskAssessment | None, signals: list[RiskSignal]
) -> dict[str, object]:
    return {
        "assessment_id": str(assessment.id) if assessment else None,
        "risk_level": assessment.risk_level.value if assessment else None,
        "risk_score": assessment.score if assessment else None,
        "total": str(invoice.total) if invoice.total is not None else None,
        "vendor_id": str(invoice.vendor_id) if invoice.vendor_id else None,
        "purchase_order_id": str(invoice.purchase_order_id) if invoice.purchase_order_id else None,
        "open_signals": [
            {"id": str(s.id), "rule_code": s.rule_code, "severity": s.severity.value}
            for s in signals
            if s.resolution == SignalResolution.OPEN and s.source == SignalSource.RULE
        ],
        "accepted_signals": [
            {"id": str(s.id), "rule_code": s.rule_code, "resolution": s.resolution.value}
            for s in signals
            if s.resolution != SignalResolution.OPEN
        ],
        "ai_status": assessment.ai_status.value if assessment else None,
    }


def decide(
    db: Session, ctx: TenantContext, invoice_id: uuid.UUID, request: DecisionRequest
) -> Review:
    ctx.require(Permission.INVOICE_REVIEW)
    invoice = _get_invoice(db, ctx, invoice_id)
    if request.decision != ReviewDecision.COMMENT and invoice.status not in DECIDABLE_STATUSES:
        raise Conflict(
            f"Invoice is {invoice.status.value}; no decision can be recorded",
            code="invoice_not_decidable",
        )
    assessment = current_assessment(db, invoice)
    signals = _signals(db, assessment)
    cycle = current_cycle(db, invoice.id)
    steps = steps_for_cycle(db, invoice.id, cycle)
    pending = next((s for s in steps if s.status == ApprovalStepStatus.PENDING), None)

    review = Review(
        organization_id=ctx.organization_id,
        invoice_id=invoice.id,
        reviewer_id=ctx.user_id,
        decision=request.decision,
        reason=request.reason.strip(),
        evidence_snapshot=_snapshot(invoice, assessment, signals),
    )
    now = datetime.now(UTC)

    if request.decision == ReviewDecision.APPROVE:
        if pending is None:
            raise Conflict("There is no pending approval step", code="no_pending_step")
        if not ctx.can(Permission(pending.required_permission)):
            raise PermissionDenied(
                f"The {pending.name.replace('_', ' ')} step requires "
                f"permission {pending.required_permission}"
            )
        if any(
            s.decided_by_id == ctx.user_id and s.status == ApprovalStepStatus.APPROVED
            for s in steps
        ):
            raise PermissionDenied(
                "A different person must approve the next step", code="segregation_of_duties"
            )
        blocking = [
            s
            for s in signals
            if s.source == SignalSource.RULE
            and s.severity == Severity.HIGH
            and s.resolution == SignalResolution.OPEN
        ]
        if blocking:
            raise Conflict(
                "High-severity risk signals must be resolved (risk accepted or dismissed by an "
                "authorised user) before approval",
                code="open_high_risk_signals",
                signal_ids=[str(s.id) for s in blocking],
            )
        review.step_no = pending.step_no
        db.add(review)
        db.flush()
        pending.status = ApprovalStepStatus.APPROVED
        pending.decided_by_id = ctx.user_id
        pending.decided_at = now
        pending.review_id = review.id
        remaining = [s for s in steps if s.status == ApprovalStepStatus.PENDING]
        if remaining:
            transition(
                db,
                invoice,
                InvoiceStatus.PENDING_APPROVAL,
                actor_type=ActorType.USER,
                actor_user_id=ctx.user_id,
                reason=request.reason,
            )
            notifications.notify_permission(
                db,
                ctx.organization_id,
                Permission(remaining[0].required_permission),
                kind="invoice.approval_required",
                severity=Severity.MEDIUM,
                title=f"Final approval required: invoice {invoice.invoice_number or ''}".strip(),
                body="The first review is complete; a second approver must decide.",
                entity_type="invoice",
                entity_id=invoice.id,
                exclude_user_id=ctx.user_id,
            )
            action = "invoice.step_approved"
        else:
            transition(
                db,
                invoice,
                InvoiceStatus.APPROVED,
                actor_type=ActorType.USER,
                actor_user_id=ctx.user_id,
                reason=request.reason,
            )
            invoice.decided_at = now
            action = "invoice.approved"
    elif request.decision in (ReviewDecision.REJECT, ReviewDecision.REQUEST_CHANGES):
        review.step_no = pending.step_no if pending else None
        db.add(review)
        db.flush()
        for step in steps:
            if step.status == ApprovalStepStatus.PENDING:
                step.status = (
                    ApprovalStepStatus.REJECTED
                    if step is pending and request.decision == ReviewDecision.REJECT
                    else ApprovalStepStatus.CANCELLED
                )
                step.decided_by_id = ctx.user_id
                step.decided_at = now
                step.review_id = review.id
        if request.decision == ReviewDecision.REJECT:
            transition(
                db,
                invoice,
                InvoiceStatus.REJECTED,
                actor_type=ActorType.USER,
                actor_user_id=ctx.user_id,
                reason=request.reason,
            )
            invoice.decided_at = now
            action = "invoice.rejected"
        else:
            transition(
                db,
                invoice,
                InvoiceStatus.NEEDS_CHANGES,
                actor_type=ActorType.USER,
                actor_user_id=ctx.user_id,
                reason=request.reason,
            )
            action = "invoice.changes_requested"
    else:
        db.add(review)
        db.flush()
        action = "invoice.commented"

    audit.record(
        db,
        ctx,
        action,
        "invoice",
        invoice.id,
        {
            "review_id": review.id,
            "decision": request.decision.value,
            "reason": review.reason,
            "step_no": review.step_no,
            "evidence": review.evidence_snapshot,
        },
    )
    if request.decision != ReviewDecision.COMMENT and invoice.uploaded_by_id:
        notifications.notify(
            db,
            ctx.organization_id,
            [invoice.uploaded_by_id],
            kind=action,
            severity=Severity.INFO,
            title=f"Invoice {invoice.invoice_number or ''}: {action.split('.')[-1].replace('_', ' ')}",
            body=f"Decision by {ctx.user_email}: {review.reason}",
            entity_type="invoice",
            entity_id=invoice.id,
            exclude_user_id=ctx.user_id,
        )
    db.commit()
    return review


def resolve_signal(
    db: Session,
    ctx: TenantContext,
    invoice_id: uuid.UUID,
    signal_id: uuid.UUID,
    request: SignalResolutionRequest,
) -> RiskSignal:
    ctx.require(Permission.RISK_OVERRIDE)
    if request.resolution == SignalResolution.OPEN:
        raise Conflict("Choose risk_accepted or dismissed", code="invalid_resolution")
    invoice = _get_invoice(db, ctx, invoice_id)
    if invoice.status not in DECIDABLE_STATUSES:
        raise Conflict(
            "Signals can only be resolved while the invoice is under review",
            code="invoice_not_decidable",
        )
    signal = db.scalar(
        select(RiskSignal).where(
            RiskSignal.id == signal_id,
            RiskSignal.invoice_id == invoice.id,
            RiskSignal.organization_id == ctx.organization_id,
        )
    )
    if signal is None:
        raise NotFound()
    if signal.resolution != SignalResolution.OPEN:
        raise Conflict("This signal has already been resolved", code="already_resolved")
    signal.resolution = request.resolution
    signal.resolved_by_id = ctx.user_id
    signal.resolved_at = datetime.now(UTC)
    signal.resolution_reason = request.reason.strip()
    audit.record(
        db,
        ctx,
        "risk.signal_resolved",
        "invoice",
        invoice.id,
        {
            "signal_id": signal.id,
            "rule_code": signal.rule_code,
            "severity": signal.severity.value,
            "resolution": request.resolution.value,
            "reason": signal.resolution_reason,
            "evidence": signal.evidence,
        },
    )
    db.commit()
    return signal


def approval_queue(
    db: Session, ctx: TenantContext, limit: int, offset: int
) -> tuple[list[Invoice], int]:
    """Invoices awaiting a step the current user is allowed to decide."""
    ctx.require(Permission.INVOICE_READ)
    permissions = [p.value for p in Permission if ctx.can(p)]
    latest_cycle = (
        select(ApprovalStep.invoice_id, func.max(ApprovalStep.cycle).label("cycle"))
        .where(ApprovalStep.organization_id == ctx.organization_id)
        .group_by(ApprovalStep.invoice_id)
        .subquery()
    )
    stmt = (
        select(Invoice)
        .join(ApprovalStep, ApprovalStep.invoice_id == Invoice.id)
        .join(
            latest_cycle,
            (latest_cycle.c.invoice_id == ApprovalStep.invoice_id)
            & (latest_cycle.c.cycle == ApprovalStep.cycle),
        )
        .where(
            Invoice.organization_id == ctx.organization_id,
            Invoice.status.in_(list(DECIDABLE_STATUSES)),
            ApprovalStep.status == ApprovalStepStatus.PENDING,
            ApprovalStep.required_permission.in_(permissions),
            # Segregation of duties: hide invoices this user already approved a step of.
            ~Invoice.id.in_(
                select(ApprovalStep.invoice_id).where(
                    ApprovalStep.organization_id == ctx.organization_id,
                    ApprovalStep.decided_by_id == ctx.user_id,
                    ApprovalStep.status == ApprovalStepStatus.APPROVED,
                    ApprovalStep.cycle
                    == select(func.max(ApprovalStep.cycle))
                    .where(ApprovalStep.invoice_id == Invoice.id)
                    .correlate(Invoice)
                    .scalar_subquery(),
                )
            ),
        )
        .distinct()
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    items = list(db.scalars(stmt.order_by(Invoice.review_requested_at).limit(limit).offset(offset)))
    return items, total

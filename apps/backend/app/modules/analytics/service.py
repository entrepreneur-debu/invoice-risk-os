"""Dashboard and analytics: SQL aggregates over the tenant's own data only.

Every number is computed from stored records. "Potential savings" is deliberately NOT
shown; instead we report the value of invoices that were flagged by a duplicate or
bank-account rule AND then rejected by a human, labelled exactly as that.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Invoice, RiskAssessment, RiskSignal, Vendor
from app.models.enums import (
    DECIDABLE_STATUSES,
    IN_FLIGHT_STATUSES,
    InvoiceStatus,
    RiskLevel,
    Severity,
    SignalResolution,
    SignalSource,
)
from app.modules.context import TenantContext
from app.modules.permissions import Permission

DUPLICATE_RULES = ("duplicate_document", "duplicate_invoice_number", "possible_duplicate")
BANK_RULES = ("bank_account_mismatch", "bank_account_unverified", "bank_account_recently_changed")
PO_RULES = (
    "po_amount_exceeded",
    "po_quantity_mismatch",
    "po_price_mismatch",
    "po_item_not_ordered",
    "po_vendor_mismatch",
    "po_not_found",
    "po_missing",
)


def _current_signals(org_id: uuid.UUID) -> Any:
    return (
        select(RiskSignal)
        .join(RiskAssessment, RiskAssessment.id == RiskSignal.assessment_id)
        .where(
            RiskSignal.organization_id == org_id,
            RiskAssessment.is_current.is_(True),
            RiskSignal.source == SignalSource.RULE,
        )
    )


def dashboard(db: Session, ctx: TenantContext) -> dict[str, Any]:
    ctx.require(Permission.ANALYTICS_READ)
    org = ctx.organization_id
    counts = dict(
        db.execute(
            select(Invoice.status, func.count())
            .where(Invoice.organization_id == org)
            .group_by(Invoice.status)
        ).all()
    )
    by_status = {s.value: int(counts.get(s, 0)) for s in InvoiceStatus}
    pending_decision = [s for s in DECIDABLE_STATUSES]
    high_risk_pending = int(
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(
                Invoice.organization_id == org,
                Invoice.status.in_(pending_decision),
                Invoice.risk_level == RiskLevel.HIGH,
            )
        )
        or 0
    )

    signals = _current_signals(org).subquery()
    duplicate_invoices = int(
        db.scalar(
            select(func.count(func.distinct(signals.c.invoice_id))).where(
                signals.c.rule_code.in_(DUPLICATE_RULES)
            )
        )
        or 0
    )
    flagged_rejected = db.execute(
        select(
            func.count(func.distinct(Invoice.id)), func.coalesce(func.sum(Invoice.total), 0)
        ).where(
            Invoice.organization_id == org,
            Invoice.status == InvoiceStatus.REJECTED,
            Invoice.id.in_(
                select(signals.c.invoice_id).where(
                    signals.c.rule_code.in_(DUPLICATE_RULES + BANK_RULES)
                )
            ),
        )
    ).one()
    pending_value = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.organization_id == org, Invoice.status.in_(pending_decision)
        )
    )

    vendor_rows = db.execute(
        select(Vendor.id, Vendor.name, func.count(signals.c.id))
        .join(Invoice, Invoice.vendor_id == Vendor.id)
        .join(signals, signals.c.invoice_id == Invoice.id)
        .where(
            Vendor.organization_id == org, signals.c.severity.in_([Severity.HIGH, Severity.MEDIUM])
        )
        .group_by(Vendor.id, Vendor.name)
        .order_by(func.count(signals.c.id).desc())
        .limit(5)
    ).all()
    recent = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.organization_id == org)
            .order_by(AuditEvent.sequence.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )
    return {
        "invoices_received": sum(by_status.values()),
        "by_status": by_status,
        "requiring_review": sum(by_status[s.value] for s in DECIDABLE_STATUSES),
        "processing": sum(by_status[s.value] for s in IN_FLIGHT_STATUSES),
        "high_risk_pending": high_risk_pending,
        "approved": by_status[InvoiceStatus.APPROVED.value],
        "rejected": by_status[InvoiceStatus.REJECTED.value],
        "needs_changes": by_status[InvoiceStatus.NEEDS_CHANGES.value],
        "failed": by_status[InvoiceStatus.FAILED.value],
        "potential_duplicates": duplicate_invoices,
        "pending_value": str(Decimal(pending_value or 0)),
        "flagged_and_rejected": {
            "label": "Invoices flagged by a duplicate or bank-account rule and then rejected "
            "by a reviewer (value of those invoices; not a savings estimate)",
            "count": int(flagged_rejected[0] or 0),
            "total_value": str(Decimal(flagged_rejected[1] or 0)),
        },
        "vendor_risk": [
            {"vendor_id": str(vid), "vendor_name": name, "risk_signals": int(n)}
            for vid, name, n in vendor_rows
        ],
        "recent_activity": [
            {
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "actor": e.actor_label,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in recent
        ],
    }


def analytics(db: Session, ctx: TenantContext, days: int) -> dict[str, Any]:
    ctx.require(Permission.ANALYTICS_READ)
    org = ctx.organization_id
    since = datetime.now(UTC) - timedelta(days=days)
    week = func.date_trunc("week", Invoice.created_at)
    volume = db.execute(
        select(cast(week, Date), func.count(), func.coalesce(func.sum(Invoice.total), 0))
        .where(Invoice.organization_id == org, Invoice.created_at >= since)
        .group_by(week)
        .order_by(week)
    ).all()

    signals = _current_signals(org).where(RiskSignal.created_at >= since).subquery()
    categories = db.execute(
        select(signals.c.category, func.count())
        .group_by(signals.c.category)
        .order_by(func.count().desc())
    ).all()
    severities = db.execute(
        select(signals.c.severity, func.count()).group_by(signals.c.severity)
    ).all()
    rules = db.execute(
        select(signals.c.rule_code, func.count())
        .group_by(signals.c.rule_code)
        .order_by(func.count().desc())
    ).all()
    risk_levels = db.execute(
        select(Invoice.risk_level, func.count())
        .where(
            Invoice.organization_id == org,
            Invoice.created_at >= since,
            Invoice.risk_level.is_not(None),
        )
        .group_by(Invoice.risk_level)
    ).all()
    decisions = db.execute(
        select(Invoice.status, func.count())
        .where(
            Invoice.organization_id == org,
            Invoice.decided_at >= since,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.REJECTED]),
        )
        .group_by(Invoice.status)
    ).all()
    turnaround = db.execute(
        select(
            func.avg(func.extract("epoch", Invoice.decided_at - Invoice.review_requested_at)),
            func.percentile_cont(0.5).within_group(
                func.extract("epoch", Invoice.decided_at - Invoice.review_requested_at)
            ),
            func.count(),
        ).where(
            Invoice.organization_id == org,
            Invoice.decided_at >= since,
            Invoice.review_requested_at.is_not(None),
        )
    ).one()
    overrides = db.scalar(
        select(func.count())
        .select_from(signals)
        .where(signals.c.resolution != SignalResolution.OPEN)
    )
    duplicate_count = sum(int(n) for code, n in rules if code in DUPLICATE_RULES)
    po_mismatch_count = sum(int(n) for code, n in rules if code in PO_RULES)
    vendor_anomalies = db.execute(
        select(Vendor.name, func.count(signals.c.id))
        .join(Invoice, Invoice.vendor_id == Vendor.id)
        .join(signals, signals.c.invoice_id == Invoice.id)
        .where(
            Vendor.organization_id == org,
            signals.c.category.in_(["anomaly", "bank", "vendor", "duplicate"]),
        )
        .group_by(Vendor.name)
        .order_by(func.count(signals.c.id).desc())
        .limit(10)
    ).all()

    def hours(seconds: Any) -> float | None:
        return round(float(seconds) / 3600, 2) if seconds is not None else None

    return {
        "period_days": days,
        "invoice_volume": [
            {
                "week_start": d.isoformat() if isinstance(d, date) else str(d),
                "count": int(c),
                "total_value": str(Decimal(v or 0)),
            }
            for d, c, v in volume
        ],
        "risk_categories": [{"category": c, "count": int(n)} for c, n in categories],
        "severity_distribution": {
            s.value if hasattr(s, "value") else s: int(n) for s, n in severities
        },
        "risk_level_distribution": {
            str(getattr(lvl, "value", lvl)): int(n) for lvl, n in risk_levels if lvl is not None
        },
        "top_rules": [{"rule_code": code, "count": int(n)} for code, n in rules[:15]],
        "decisions": {s.value if hasattr(s, "value") else s: int(n) for s, n in decisions},
        "review_turnaround_hours": {
            "average": hours(turnaround[0]),
            "median": hours(turnaround[1]),
            "decided_invoices": int(turnaround[2] or 0),
        },
        "duplicate_detections": duplicate_count,
        "po_mismatch_signals": po_mismatch_count,
        "signals_resolved_by_override": int(overrides or 0),
        "vendor_anomalies": [
            {"vendor_name": name, "signals": int(n)} for name, n in vendor_anomalies
        ],
    }

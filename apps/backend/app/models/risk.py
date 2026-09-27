"""Risk assessments (one per analysis run) and the explainable signals they produced."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantOwned, UUIDPrimaryKey
from app.db.types import JSONType, enum_column
from app.models.enums import AIStatus, RiskLevel, Severity, SignalResolution, SignalSource


class RiskAssessment(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "risk_assessments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    engine_version: Mapped[str] = mapped_column(String(32))
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel, "assessment_level"))
    score: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(default=True)
    # Deterministic inputs the rules saw (for reproducibility of the assessment).
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    ai_status: Mapped[AIStatus] = mapped_column(enum_column(AIStatus, "ai_status"))
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    ai_model: Mapped[str | None] = mapped_column(String(64))
    # Schema-validated AI output (labelled AI-generated wherever it is shown).
    ai_output: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    ai_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signals: Mapped[list["RiskSignal"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class RiskSignal(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "risk_signals"
    __table_args__ = (Index("ix_risk_signals_org_rule", "organization_id", "rule_code"),)

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    rule_code: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[Severity] = mapped_column(enum_column(Severity, "severity"))
    source: Mapped[SignalSource] = mapped_column(enum_column(SignalSource, "signal_source"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    # [{"label": str, "value": str | None, "source": str}] - what the rule saw.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    resolution: Mapped[SignalResolution] = mapped_column(
        enum_column(SignalResolution, "signal_resolution"), default=SignalResolution.OPEN
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    assessment: Mapped[RiskAssessment] = relationship(back_populates="signals")

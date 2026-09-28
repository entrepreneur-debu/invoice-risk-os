"""Invoice contracts. Extracted values are returned together with their provenance."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AIStatus,
    ApprovalStepStatus,
    InvoiceSource,
    InvoiceStatus,
    ReviewDecision,
    RiskLevel,
    Severity,
    SignalResolution,
    SignalSource,
)


class InvoiceSummary(BaseModel):
    id: uuid.UUID
    status: InvoiceStatus
    source: InvoiceSource
    invoice_number: str | None
    invoice_date: date | None
    total: Decimal | None
    currency: str | None
    vendor_id: uuid.UUID | None
    vendor_name: str | None
    risk_level: RiskLevel | None
    risk_score: int | None
    open_high_signals: int
    required_approvals: int
    created_at: datetime
    processing_error_code: str | None


class FieldValue(BaseModel):
    value: Any
    source: str | None
    confidence: float | None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    edited_by: str | None = None


class InvoiceLineResponse(BaseModel):
    line_no: int
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    tax_rate: Decimal | None
    amount: Decimal | None
    source: str


class DocumentResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    source_url_host: str | None
    created_at: datetime


class EvidenceItem(BaseModel):
    label: str
    value: str | None
    source: str


class RiskSignalResponse(BaseModel):
    id: uuid.UUID
    rule_code: str
    category: str
    severity: Severity
    source: SignalSource
    title: str
    description: str
    evidence: list[EvidenceItem]
    resolution: SignalResolution
    resolved_by_email: str | None
    resolved_at: datetime | None
    resolution_reason: str | None
    ai_explanation: str | None


class RiskAssessmentResponse(BaseModel):
    id: uuid.UUID
    engine_version: str
    risk_level: RiskLevel
    score: int
    created_at: datetime
    ai_status: AIStatus
    ai_provider: str | None
    ai_model: str | None
    ai_error_code: str | None
    ai_summary: str | None
    ai_reviewer_focus: list[str]
    ai_observations: list[dict[str, Any]]
    signals: list[RiskSignalResponse]


class ApprovalStepResponse(BaseModel):
    step_no: int
    cycle: int
    name: str
    required_permission: str
    status: ApprovalStepStatus
    decided_by_email: str | None
    decided_at: datetime | None


class ReviewResponse(BaseModel):
    id: uuid.UUID
    reviewer_email: str
    decision: ReviewDecision
    step_no: int | None
    reason: str
    evidence_snapshot: dict[str, Any]
    created_at: datetime


class StatusChangeResponse(BaseModel):
    from_status: str | None
    to_status: str
    actor_type: str
    actor_email: str | None
    reason: str | None
    created_at: datetime


class LinkedPurchaseOrder(BaseModel):
    id: uuid.UUID
    po_number: str
    status: str
    total: Decimal
    vendor_id: uuid.UUID


class LinkedVendor(BaseModel):
    id: uuid.UUID
    name: str
    gstin: str | None
    status: str


class InvoiceDetail(BaseModel):
    id: uuid.UUID
    status: InvoiceStatus
    source: InvoiceSource
    created_at: datetime
    uploaded_by_email: str | None
    review_requested_at: datetime | None
    decided_at: datetime | None
    processing_error_code: str | None
    processing_error_message: str | None
    required_approvals: int
    fields: dict[str, FieldValue]
    lines: list[InvoiceLineResponse]
    documents: list[DocumentResponse]
    vendor: LinkedVendor | None
    vendor_match: str | None
    purchase_order: LinkedPurchaseOrder | None
    assessment: RiskAssessmentResponse | None
    approval_steps: list[ApprovalStepResponse]
    reviews: list[ReviewResponse]
    status_history: list[StatusChangeResponse]
    allowed_actions: list[str]


class InvoiceLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=3)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=3)
    amount: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)


class InvoiceUpdate(BaseModel):
    """Manual corrections. Each changed field is recorded with source=manual and audited."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=1000)
    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    subtotal: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    tax_total: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    cgst: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    sgst: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    igst: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    total: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    vendor_gstin: str | None = Field(default=None, max_length=20)
    buyer_gstin: str | None = Field(default=None, max_length=20)
    po_number: str | None = Field(default=None, max_length=64)
    vendor_id: uuid.UUID | None = None
    purchase_order_id: uuid.UUID | None = None
    lines: list[InvoiceLineInput] | None = Field(default=None, max_length=200)


class UrlImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class DecisionRequest(BaseModel):
    decision: ReviewDecision
    reason: str = Field(min_length=3, max_length=2000)


class SignalResolutionRequest(BaseModel):
    resolution: SignalResolution
    reason: str = Field(min_length=3, max_length=2000)

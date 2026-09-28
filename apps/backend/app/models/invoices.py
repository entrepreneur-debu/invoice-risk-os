"""Invoices, their lines, stored documents, extraction runs and status history."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Quantity, Rate, TenantOwned, Timestamps, UUIDPrimaryKey
from app.db.types import JSONType, enum_column
from app.models.enums import (
    ActorType,
    ExtractionMethod,
    ExtractionStatus,
    InvoiceSource,
    InvoiceStatus,
    RiskLevel,
)


class Invoice(UUIDPrimaryKey, Timestamps, TenantOwned, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_org_status", "organization_id", "status"),
        Index(
            "ix_invoices_org_vendor_number",
            "organization_id",
            "vendor_id",
            "normalized_invoice_number",
        ),
        Index("ix_invoices_org_created", "organization_id", "created_at"),
    )

    status: Mapped[InvoiceStatus] = mapped_column(
        enum_column(InvoiceStatus, "invoice_status"), default=InvoiceStatus.UPLOADED
    )
    source: Mapped[InvoiceSource] = mapped_column(enum_column(InvoiceSource, "invoice_source"))
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"), index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="SET NULL"), index=True
    )

    # Canonical fields. Their origin is recorded per field in `field_provenance`.
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    normalized_invoice_number: Mapped[str | None] = mapped_column(String(64))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None]
    tax_total: Mapped[Decimal | None]
    cgst: Mapped[Decimal | None]
    sgst: Mapped[Decimal | None]
    igst: Mapped[Decimal | None]
    total: Mapped[Decimal | None]
    vendor_name_on_invoice: Mapped[str | None] = mapped_column(String(200))
    vendor_gstin_on_invoice: Mapped[str | None] = mapped_column(String(15))
    buyer_gstin_on_invoice: Mapped[str | None] = mapped_column(String(15))
    po_number_on_invoice: Mapped[str | None] = mapped_column(String(64))
    # Bank details printed on the invoice: never stored in full.
    bank_account_last4_on_invoice: Mapped[str | None] = mapped_column(String(4))
    bank_account_fingerprint_on_invoice: Mapped[str | None] = mapped_column(String(64))
    bank_ifsc_on_invoice: Mapped[str | None] = mapped_column(String(11))
    field_provenance: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    risk_level: Mapped[RiskLevel | None] = mapped_column(enum_column(RiskLevel, "risk_level"))
    risk_score: Mapped[int | None] = mapped_column(Integer)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    processing_error_code: Mapped[str | None] = mapped_column(String(64))
    processing_error_message: Mapped[str | None] = mapped_column(String(500))
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.line_no"
    )
    documents: Mapped[list["InvoiceDocument"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceDocument.created_at",
    )


class InvoiceLine(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal | None] = mapped_column(Quantity)
    unit_price: Mapped[Decimal | None]
    tax_rate: Mapped[Decimal | None] = mapped_column(Rate)
    amount: Mapped[Decimal | None]
    source: Mapped[str] = mapped_column(String(32))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceDocument(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "invoice_documents"
    __table_args__ = (Index("ix_invoice_documents_org_sha256", "organization_id", "sha256"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    source_url_host: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="documents")


class InvoiceExtraction(UUIDPrimaryKey, TenantOwned, Base):
    """One extraction attempt (AI, text layer or manual edit) and its validated output."""

    __tablename__ = "invoice_extractions"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[ExtractionMethod] = mapped_column(
        enum_column(ExtractionMethod, "extraction_method")
    )
    status: Mapped[ExtractionStatus] = mapped_column(
        enum_column(ExtractionStatus, "extraction_status")
    )
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvoiceStatusChange(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "invoice_status_changes"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[ActorType] = mapped_column(enum_column(ActorType, "status_actor_type"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

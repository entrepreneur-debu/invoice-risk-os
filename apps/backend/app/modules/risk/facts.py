"""Immutable facts the risk rules evaluate.

Rules receive only these plain dataclasses (no ORM, no I/O), so each rule is a pure,
independently testable function of its inputs. `builder.py` assembles them from the DB.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.modules.identity.schemas import OrganizationSettings


@dataclass(frozen=True)
class LineFact:
    description: str
    normalized: str
    quantity: Decimal | None
    unit_price: Decimal | None
    tax_rate: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True)
class HistoricalInvoice:
    id: str
    invoice_number: str | None
    normalized_number: str | None
    invoice_date: date | None
    total: Decimal | None
    status: str
    created_at: datetime
    vendor_id: str | None = None


@dataclass(frozen=True)
class BankFact:
    last4: str
    fingerprint: str
    ifsc: str
    status: str  # pending_verification | verified | ...
    created_at: datetime
    is_change: bool  # replaced an earlier account


@dataclass(frozen=True)
class VendorFact:
    id: str
    name: str
    gstin: str | None
    status: str
    created_at: datetime
    current_bank: BankFact | None
    history: tuple[HistoricalInvoice, ...] = ()
    # normalized line description -> [(invoice date, unit price)], oldest first
    price_history: dict[str, tuple[tuple[date, Decimal], ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class POLineFact:
    description: str
    normalized: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    invoiced_quantity_other: Decimal  # on other non-rejected invoices


@dataclass(frozen=True)
class POFact:
    id: str
    po_number: str
    vendor_id: str
    status: str
    total: Decimal
    invoiced_total_other: Decimal
    lines: tuple[POLineFact, ...]


@dataclass(frozen=True)
class InvoiceFact:
    id: str
    invoice_number: str | None
    normalized_number: str | None
    invoice_date: date | None
    due_date: date | None
    currency: str | None
    subtotal: Decimal | None
    tax_total: Decimal | None
    cgst: Decimal | None
    sgst: Decimal | None
    igst: Decimal | None
    total: Decimal | None
    vendor_name: str | None
    vendor_gstin: str | None
    buyer_gstin: str | None
    po_number: str | None
    bank_last4: str | None
    bank_fingerprint: str | None
    bank_ifsc: str | None
    lines: tuple[LineFact, ...]
    created_at: datetime
    field_confidence: dict[str, float] = field(default_factory=dict)
    extraction_conflicts: tuple[str, ...] = ()
    vendor_match_method: str | None = None  # gstin | name | manual | None


@dataclass(frozen=True)
class RiskContext:
    invoice: InvoiceFact
    vendor: VendorFact | None
    purchase_order: POFact | None
    po_reference_unresolved: bool  # a PO number is printed but no PO matches it
    org_gstin: str | None
    org_state_code: str | None
    settings: OrganizationSettings
    today: date
    same_document_invoices: tuple[HistoricalInvoice, ...] = ()
    injection_indicators: tuple[str, ...] = ()

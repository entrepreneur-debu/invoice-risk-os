"""Builds `RiskContext` from the database. All queries are scoped to the invoice's tenant."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Invoice,
    InvoiceDocument,
    InvoiceExtraction,
    InvoiceLine,
    Organization,
    PurchaseOrder,
    Vendor,
    VendorBankAccount,
)
from app.models.enums import ExtractionMethod, InvoiceStatus
from app.modules.identity.service import organization_settings
from app.modules.invoices.extraction import normalize_invoice_number
from app.modules.purchasing.service import invoiced_to_date, normalize_description
from app.modules.risk.facts import (
    BankFact,
    HistoricalInvoice,
    InvoiceFact,
    LineFact,
    POFact,
    POLineFact,
    RiskContext,
    VendorFact,
)

HISTORY_DAYS = 400
_VENDOR_MATCH_METHODS = {
    "matched_by_gstin": "gstin",
    "matched_by_name": "name",
    "manual": "manual",
}


def _line_fact(line: InvoiceLine) -> LineFact:
    return LineFact(
        line.description,
        normalize_description(line.description),
        line.quantity,
        line.unit_price,
        line.tax_rate,
        line.amount,
    )


def _historical(invoice: Invoice) -> HistoricalInvoice:
    return HistoricalInvoice(
        id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        normalized_number=invoice.normalized_invoice_number,
        invoice_date=invoice.invoice_date,
        total=invoice.total,
        status=invoice.status.value,
        created_at=invoice.created_at,
        vendor_id=str(invoice.vendor_id) if invoice.vendor_id else None,
    )


def _invoice_fact(invoice: Invoice) -> InvoiceFact:
    provenance = invoice.field_provenance or {}
    confidence = {
        name: float(entry.get("confidence", 0))
        for name, entry in provenance.items()
        if isinstance(entry, dict) and entry.get("source") not in (None, "manual")
    }
    conflicts = tuple(
        name
        for name, entry in provenance.items()
        if isinstance(entry, dict) and entry.get("alternatives") and entry.get("source") != "manual"
    )
    vendor_source = (provenance.get("vendor_id") or {}).get("source")
    return InvoiceFact(
        id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        normalized_number=invoice.normalized_invoice_number
        or normalize_invoice_number(invoice.invoice_number),
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax_total=invoice.tax_total,
        cgst=invoice.cgst,
        sgst=invoice.sgst,
        igst=invoice.igst,
        total=invoice.total,
        vendor_name=invoice.vendor_name_on_invoice,
        vendor_gstin=invoice.vendor_gstin_on_invoice,
        buyer_gstin=invoice.buyer_gstin_on_invoice,
        po_number=invoice.po_number_on_invoice,
        bank_last4=invoice.bank_account_last4_on_invoice,
        bank_fingerprint=invoice.bank_account_fingerprint_on_invoice,
        bank_ifsc=invoice.bank_ifsc_on_invoice,
        lines=tuple(_line_fact(line) for line in invoice.lines),
        created_at=invoice.created_at,
        field_confidence=confidence,
        extraction_conflicts=conflicts,
        vendor_match_method=_VENDOR_MATCH_METHODS.get(vendor_source or ""),
    )


def _vendor_fact(db: Session, invoice: Invoice, vendor: Vendor) -> VendorFact:
    org_id = invoice.organization_id
    bank = db.scalar(
        select(VendorBankAccount).where(
            VendorBankAccount.organization_id == org_id,
            VendorBankAccount.vendor_id == vendor.id,
            VendorBankAccount.is_current.is_(True),
        )
    )
    since = datetime.now(UTC) - timedelta(days=HISTORY_DAYS)
    others = list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.organization_id == org_id,
                Invoice.vendor_id == vendor.id,
                Invoice.id != invoice.id,
                Invoice.created_at >= since,
            )
            .order_by(Invoice.created_at)
        )
    )
    price_history: dict[str, list[tuple[date, Decimal]]] = {}
    priced = [i for i in others if i.status not in (InvoiceStatus.REJECTED, InvoiceStatus.FAILED)]
    if priced:
        dates = {i.id: (i.invoice_date or i.created_at.date()) for i in priced}
        for line in db.scalars(
            select(InvoiceLine).where(
                InvoiceLine.organization_id == org_id, InvoiceLine.invoice_id.in_(list(dates))
            )
        ):
            if line.unit_price is None:
                continue
            key = normalize_description(line.description)
            price_history.setdefault(key, []).append((dates[line.invoice_id], line.unit_price))
    return VendorFact(
        id=str(vendor.id),
        name=vendor.name,
        gstin=vendor.gstin,
        status=vendor.status.value,
        created_at=vendor.created_at,
        current_bank=BankFact(
            last4=bank.account_last4,
            fingerprint=bank.account_fingerprint,
            ifsc=bank.ifsc,
            status=bank.status.value,
            created_at=bank.created_at,
            is_change=bank.previous_account_id is not None,
        )
        if bank
        else None,
        history=tuple(_historical(i) for i in others),
        price_history={
            k: tuple(sorted(v, key=lambda item: item[0])) for k, v in price_history.items()
        },
    )


def _po_fact(db: Session, invoice: Invoice, po: PurchaseOrder) -> POFact:
    total_other, quantities, _ = invoiced_to_date(db, invoice.organization_id, po.id, invoice.id)
    return POFact(
        id=str(po.id),
        po_number=po.po_number,
        vendor_id=str(po.vendor_id),
        status=po.status.value,
        total=po.total,
        invoiced_total_other=total_other,
        lines=tuple(
            POLineFact(
                line.description,
                normalize_description(line.description),
                line.quantity,
                line.unit_price,
                line.amount,
                quantities.get(normalize_description(line.description), Decimal(0)),
            )
            for line in po.lines
        ),
    )


def build_context(db: Session, invoice: Invoice, today: date | None = None) -> RiskContext:
    org = db.get(Organization, invoice.organization_id)
    assert org is not None  # noqa: S101
    org_id = invoice.organization_id

    vendor = None
    if invoice.vendor_id:
        vendor = db.scalar(
            select(Vendor).where(Vendor.id == invoice.vendor_id, Vendor.organization_id == org_id)
        )
    po = None
    if invoice.purchase_order_id:
        po = db.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == invoice.purchase_order_id,
                PurchaseOrder.organization_id == org_id,
            )
        )

    shas = [d.sha256 for d in invoice.documents]
    same_document: list[HistoricalInvoice] = []
    if shas:
        same_document = [
            _historical(i)
            for i in db.scalars(
                select(Invoice)
                .join(InvoiceDocument, InvoiceDocument.invoice_id == Invoice.id)
                .where(
                    Invoice.organization_id == org_id,
                    InvoiceDocument.organization_id == org_id,
                    InvoiceDocument.sha256.in_(shas),
                    Invoice.id != invoice.id,
                )
                .distinct()
            )
        ]

    text_extraction = db.scalar(
        select(InvoiceExtraction)
        .where(
            InvoiceExtraction.invoice_id == invoice.id,
            InvoiceExtraction.organization_id == org_id,
            InvoiceExtraction.method == ExtractionMethod.TEXT_LAYER,
        )
        .order_by(InvoiceExtraction.created_at.desc())
        .limit(1)
    )
    indicators = (
        tuple((text_extraction.output or {}).get("injection_indicators", []))
        if text_extraction
        else ()
    )

    return RiskContext(
        invoice=_invoice_fact(invoice),
        vendor=_vendor_fact(db, invoice, vendor) if vendor else None,
        purchase_order=_po_fact(db, invoice, po) if po else None,
        po_reference_unresolved=bool(invoice.po_number_on_invoice) and po is None,
        org_gstin=org.gstin,
        org_state_code=org.state_code,
        settings=organization_settings(org),
        today=today or datetime.now(UTC).date(),
        same_document_invoices=tuple(same_document),
        injection_indicators=indicators,
    )

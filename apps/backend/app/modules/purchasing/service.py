"""Purchase orders: CRUD with deterministic totals, and invoiced-to-date tracking."""

import re
import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import Conflict, InvalidInput, NotFound
from app.finance.money import ZERO, money, percent_of
from app.models import Invoice, InvoiceLine, PurchaseOrder, PurchaseOrderLine, Vendor
from app.models.enums import InvoiceStatus, PurchaseOrderStatus
from app.modules.audit import service as audit
from app.modules.context import TenantContext
from app.modules.permissions import Permission
from app.modules.purchasing.schemas import POCreate, POLineInput, POUpdate

# Invoices that count toward "invoiced to date" against a PO.
COUNTED_STATUSES = frozenset(
    s for s in InvoiceStatus if s not in (InvoiceStatus.REJECTED, InvoiceStatus.FAILED)
)


def normalize_po_number(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    return cleaned or None


def _build_lines(
    ctx: TenantContext, lines: list[POLineInput]
) -> tuple[list[PurchaseOrderLine], Decimal, Decimal]:
    built: list[PurchaseOrderLine] = []
    subtotal = ZERO
    tax = ZERO
    for index, line in enumerate(lines, start=1):
        amount = money(line.quantity * line.unit_price)
        subtotal += amount
        tax += percent_of(amount, line.tax_rate)
        built.append(
            PurchaseOrderLine(
                organization_id=ctx.organization_id,
                line_no=index,
                description=line.description.strip(),
                sku=line.sku,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                amount=amount,
            )
        )
    return built, money(subtotal), money(tax)


def get_po(db: Session, ctx: TenantContext, po_id: uuid.UUID) -> PurchaseOrder:
    ctx.require(Permission.PO_READ)
    po = db.scalar(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.id == po_id, PurchaseOrder.organization_id == ctx.organization_id)
    )
    if po is None:
        raise NotFound()
    return po


def find_by_number(
    db: Session, organization_id: uuid.UUID, number: str | None
) -> PurchaseOrder | None:
    normalized = normalize_po_number(number)
    if not normalized:
        return None
    # Compare on the normalized form in SQL ("PO-1001" matches "po 1001").
    normalized_column = func.upper(
        func.regexp_replace(PurchaseOrder.po_number, "[^A-Za-z0-9]", "", "g")
    )
    return db.scalar(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.organization_id == organization_id, normalized_column == normalized)
    )


def list_pos(
    db: Session,
    ctx: TenantContext,
    *,
    query: str | None,
    vendor_id: uuid.UUID | None,
    status: PurchaseOrderStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[PurchaseOrder, str]], int]:
    ctx.require(Permission.PO_READ)
    stmt = (
        select(PurchaseOrder, Vendor.name)
        .join(Vendor, Vendor.id == PurchaseOrder.vendor_id)
        .where(PurchaseOrder.organization_id == ctx.organization_id)
    )
    if query:
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(PurchaseOrder.po_number).like(like), func.lower(Vendor.name).like(like))
        )
    if vendor_id:
        stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(stmt.order_by(PurchaseOrder.created_at.desc()).limit(limit).offset(offset))
    return [(po, name) for po, name in rows], total


def create_po(db: Session, ctx: TenantContext, request: POCreate) -> PurchaseOrder:
    ctx.require(Permission.PO_WRITE)
    vendor = db.scalar(
        select(Vendor).where(
            Vendor.id == request.vendor_id, Vendor.organization_id == ctx.organization_id
        )
    )
    if vendor is None:
        raise InvalidInput("Unknown vendor", code="unknown_vendor")
    if request.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.OPEN):
        raise InvalidInput("New purchase orders must be draft or open", code="invalid_status")
    lines, subtotal, tax = _build_lines(ctx, request.lines)
    po = PurchaseOrder(
        organization_id=ctx.organization_id,
        vendor_id=vendor.id,
        po_number=request.po_number.strip(),
        issue_date=request.issue_date,
        currency=request.currency,
        status=request.status,
        subtotal=subtotal,
        tax_total=tax,
        total=money(subtotal + tax),
        notes=request.notes,
        created_by_id=ctx.user_id,
        lines=lines,
    )
    db.add(po)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "A purchase order with this number already exists", code="duplicate_po_number"
        ) from exc
    audit.record(
        db,
        ctx,
        "purchase_order.created",
        "purchase_order",
        po.id,
        {
            "po_number": po.po_number,
            "vendor_id": vendor.id,
            "total": po.total,
            "line_count": len(lines),
        },
    )
    db.commit()
    return po


_ALLOWED_TRANSITIONS = {
    PurchaseOrderStatus.DRAFT: {PurchaseOrderStatus.OPEN, PurchaseOrderStatus.CANCELLED},
    PurchaseOrderStatus.OPEN: {PurchaseOrderStatus.CLOSED, PurchaseOrderStatus.CANCELLED},
    PurchaseOrderStatus.CLOSED: {PurchaseOrderStatus.OPEN},
    PurchaseOrderStatus.CANCELLED: set(),
}


def update_po(
    db: Session, ctx: TenantContext, po_id: uuid.UUID, request: POUpdate
) -> PurchaseOrder:
    ctx.require(Permission.PO_WRITE)
    po = get_po(db, ctx, po_id)
    changes: dict[str, object] = {}
    if request.lines is not None:
        if po.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.OPEN):
            raise Conflict(
                "Lines can only be changed on draft or open purchase orders", code="po_not_editable"
            )
        lines, subtotal, tax = _build_lines(ctx, request.lines)
        changes["lines"] = {
            "from_total": po.total,
            "to_total": money(subtotal + tax),
            "line_count": len(lines),
        }
        po.lines.clear()
        db.flush()
        po.lines.extend(lines)
        po.subtotal, po.tax_total, po.total = subtotal, tax, money(subtotal + tax)
    if request.status is not None and request.status != po.status:
        if request.status not in _ALLOWED_TRANSITIONS[po.status]:
            raise Conflict(
                f"Cannot change status from {po.status.value} to {request.status.value}",
                code="invalid_transition",
            )
        changes["status"] = {"from": po.status.value, "to": request.status.value}
        po.status = request.status
    if "issue_date" in request.model_fields_set and request.issue_date != po.issue_date:
        changes["issue_date"] = {"from": po.issue_date, "to": request.issue_date}
        po.issue_date = request.issue_date
    if "notes" in request.model_fields_set and request.notes != po.notes:
        changes["notes"] = "updated"
        po.notes = request.notes
    if changes:
        audit.record(db, ctx, "purchase_order.updated", "purchase_order", po.id, changes)
    db.commit()
    return po


def invoiced_to_date(
    db: Session,
    organization_id: uuid.UUID,
    po_id: uuid.UUID,
    exclude_invoice_id: uuid.UUID | None = None,
) -> tuple[Decimal, dict[str, Decimal], list[uuid.UUID]]:
    """Total invoiced and quantity invoiced per normalized description against a PO."""
    stmt = select(Invoice).where(
        Invoice.organization_id == organization_id,
        Invoice.purchase_order_id == po_id,
        Invoice.status.in_(COUNTED_STATUSES),
    )
    if exclude_invoice_id:
        stmt = stmt.where(Invoice.id != exclude_invoice_id)
    invoices = list(db.scalars(stmt))
    total = money(sum((i.total or ZERO for i in invoices), ZERO))
    quantities: dict[str, Decimal] = {}
    if invoices:
        for line in db.scalars(
            select(InvoiceLine).where(InvoiceLine.invoice_id.in_([i.id for i in invoices]))
        ):
            key = normalize_description(line.description)
            quantities[key] = quantities.get(key, ZERO) + (line.quantity or ZERO)
    return total, quantities, [i.id for i in invoices]


def normalize_description(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

"""Purchase orders."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbDep, TenantDep, verify_origin
from app.api.v1.common import Page, Pagination
from app.models import PurchaseOrder, Vendor
from app.models.enums import PurchaseOrderStatus
from app.modules.context import TenantContext
from app.modules.purchasing import service
from app.modules.purchasing.schemas import POCreate, POLineResponse, POResponse, POUpdate

router = APIRouter(
    prefix="/purchase-orders", tags=["purchase-orders"], dependencies=[Depends(verify_origin)]
)


def _response(db: DbDep, ctx: TenantContext, po: PurchaseOrder) -> POResponse:
    invoiced_total, quantities, invoice_ids = service.invoiced_to_date(
        db, ctx.organization_id, po.id
    )
    vendor_name = db.scalar(select(Vendor.name).where(Vendor.id == po.vendor_id)) or ""
    return POResponse(
        id=po.id,
        vendor_id=po.vendor_id,
        vendor_name=vendor_name,
        po_number=po.po_number,
        issue_date=po.issue_date,
        currency=po.currency,
        status=po.status,
        subtotal=po.subtotal,
        tax_total=po.tax_total,
        total=po.total,
        invoiced_total=invoiced_total,
        notes=po.notes,
        created_at=po.created_at,
        linked_invoice_ids=invoice_ids,
        lines=[
            POLineResponse(
                id=line.id,
                line_no=line.line_no,
                description=line.description,
                sku=line.sku,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                amount=line.amount,
                invoiced_quantity=quantities.get(
                    service.normalize_description(line.description), 0
                ),
            )
            for line in po.lines
        ],
    )


@router.get("", response_model=Page[POResponse])
def list_pos(
    ctx: TenantDep,
    db: DbDep,
    page: Pagination = Depends(),
    q: str | None = Query(default=None, max_length=100),
    vendor_id: uuid.UUID | None = None,
    status: PurchaseOrderStatus | None = None,
) -> Page[POResponse]:
    rows, total = service.list_pos(
        db, ctx, query=q, vendor_id=vendor_id, status=status, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[_response(db, ctx, service.get_po(db, ctx, po.id)) for po, _ in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=POResponse, status_code=201)
def create_po(body: POCreate, ctx: TenantDep, db: DbDep) -> POResponse:
    po = service.create_po(db, ctx, body)
    return _response(db, ctx, service.get_po(db, ctx, po.id))


@router.get("/{po_id}", response_model=POResponse)
def get_po(po_id: uuid.UUID, ctx: TenantDep, db: DbDep) -> POResponse:
    return _response(db, ctx, service.get_po(db, ctx, po_id))


@router.patch("/{po_id}", response_model=POResponse)
def update_po(po_id: uuid.UUID, body: POUpdate, ctx: TenantDep, db: DbDep) -> POResponse:
    service.update_po(db, ctx, po_id, body)
    return _response(db, ctx, service.get_po(db, ctx, po_id))

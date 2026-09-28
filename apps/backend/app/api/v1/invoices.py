"""Invoices: ingestion, review detail, corrections, documents, decisions."""

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import (
    DbDep,
    DispatcherDep,
    SettingsDep,
    StorageDep,
    TenantDep,
    verify_origin,
)
from app.api.v1.common import Page, Pagination
from app.core.errors import InvalidInput
from app.models.enums import InvoiceStatus, RiskLevel
from app.modules.invoices import service
from app.modules.invoices.schemas import (
    DecisionRequest,
    InvoiceDetail,
    InvoiceSummary,
    InvoiceUpdate,
    ReviewResponse,
    SignalResolutionRequest,
    UrlImportRequest,
)
from app.modules.review import service as review

router = APIRouter(prefix="/invoices", tags=["invoices"], dependencies=[Depends(verify_origin)])


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise InvalidInput(f"File exceeds the {limit // 1_048_576} MB limit", code="file_too_large")
    return data


@router.get("", response_model=Page[InvoiceSummary])
def list_invoices(
    ctx: TenantDep,
    db: DbDep,
    page: Pagination = Depends(),
    status: list[InvoiceStatus] | None = Query(default=None),
    risk_level: RiskLevel | None = None,
    vendor_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
) -> Page[InvoiceSummary]:
    items, total = service.list_invoices(
        db,
        ctx,
        status=status,
        risk_level=risk_level.value if risk_level else None,
        vendor_id=vendor_id,
        query=q,
        limit=page.limit,
        offset=page.offset,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("/upload", response_model=InvoiceDetail, status_code=201)
async def upload_invoice(
    ctx: TenantDep,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
    dispatcher: DispatcherDep,
    file: UploadFile = File(...),
) -> InvoiceDetail:
    data = await _read_upload(file, settings.max_upload_bytes)
    result = service.upload(
        db, settings, storage, dispatcher, ctx, data, file.filename, file.content_type
    )
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, result.invoice.id))


@router.post("/import-url", response_model=InvoiceDetail, status_code=201)
def import_invoice_url(
    body: UrlImportRequest,
    ctx: TenantDep,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
    dispatcher: DispatcherDep,
) -> InvoiceDetail:
    result = service.import_from_url(db, settings, storage, dispatcher, ctx, body.url)
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, result.invoice.id))


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: uuid.UUID, ctx: TenantDep, db: DbDep) -> InvoiceDetail:
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, invoice_id))


@router.patch("/{invoice_id}", response_model=InvoiceDetail)
def update_invoice(
    invoice_id: uuid.UUID, body: InvoiceUpdate, ctx: TenantDep, db: DbDep, dispatcher: DispatcherDep
) -> InvoiceDetail:
    service.update_invoice(db, dispatcher, ctx, invoice_id, body)
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, invoice_id))


@router.post("/{invoice_id}/documents", response_model=InvoiceDetail)
async def replace_document(
    invoice_id: uuid.UUID,
    ctx: TenantDep,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
    dispatcher: DispatcherDep,
    file: UploadFile = File(...),
) -> InvoiceDetail:
    data = await _read_upload(file, settings.max_upload_bytes)
    service.replace_document(
        db, settings, storage, dispatcher, ctx, invoice_id, data, file.filename, file.content_type
    )
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, invoice_id))


@router.post("/{invoice_id}/reprocess", response_model=InvoiceDetail)
def reprocess(
    invoice_id: uuid.UUID, ctx: TenantDep, db: DbDep, dispatcher: DispatcherDep
) -> InvoiceDetail:
    service.reprocess(db, dispatcher, ctx, invoice_id)
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, invoice_id))


@router.get("/{invoice_id}/documents/{document_id}")
def download_document(
    invoice_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: TenantDep,
    db: DbDep,
    storage: StorageDep,
    inline: bool = False,
) -> Response:
    document, data = service.get_document(db, storage, ctx, invoice_id, document_id)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=document.content_type,
        headers={
            # Filename was sanitised at upload; quote it anyway.
            "Content-Disposition": f'{disposition}; filename="{document.original_filename}"',
            # Allow the same-origin review page to embed the document, nothing else.
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self'; "
            "object-src 'self'; frame-ancestors 'self'",
            "X-Frame-Options": "SAMEORIGIN",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{invoice_id}/decisions", response_model=ReviewResponse, status_code=201)
def decide(
    invoice_id: uuid.UUID, body: DecisionRequest, ctx: TenantDep, db: DbDep
) -> ReviewResponse:
    result = review.decide(db, ctx, invoice_id, body)
    return ReviewResponse(
        id=result.id,
        reviewer_email=ctx.user_email,
        decision=result.decision,
        step_no=result.step_no,
        reason=result.reason,
        evidence_snapshot=result.evidence_snapshot,
        created_at=result.created_at,
    )


@router.post("/{invoice_id}/signals/{signal_id}/resolve", response_model=InvoiceDetail)
def resolve_signal(
    invoice_id: uuid.UUID,
    signal_id: uuid.UUID,
    body: SignalResolutionRequest,
    ctx: TenantDep,
    db: DbDep,
) -> InvoiceDetail:
    review.resolve_signal(db, ctx, invoice_id, signal_id, body)
    return service.invoice_detail(db, ctx, service.get_invoice(db, ctx, invoice_id))

"""Invoice ingestion (upload, URL import, email), queries and manual corrections."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import Conflict, InvalidInput, NotFound, ServiceUnavailable
from app.finance.gst import normalize_gstin
from app.infra.storage import StorageError, StorageProvider
from app.infra.tasks import PROCESS_INVOICE, REANALYZE_INVOICE, TaskDispatcher
from app.models import (
    ApprovalStep,
    Invoice,
    InvoiceDocument,
    InvoiceLine,
    InvoiceStatusChange,
    PurchaseOrder,
    Review,
    RiskAssessment,
    RiskSignal,
    User,
    Vendor,
)
from app.models.enums import (
    DECIDABLE_STATUSES,
    ActorType,
    InvoiceSource,
    InvoiceStatus,
    Severity,
    SignalResolution,
    SignalSource,
)
from app.modules.audit import service as audit
from app.modules.context import SystemContext, TenantContext
from app.modules.invoices import schemas
from app.modules.invoices.documents import ValidatedDocument, storage_key, validate_document
from app.modules.invoices.extraction import normalize_invoice_number
from app.modules.invoices.state import transition
from app.modules.invoices.url_import import FetchPolicy, fetch_document
from app.modules.permissions import Permission
from app.modules.review.service import current_cycle, steps_for_cycle

EDITABLE_STATUSES = DECIDABLE_STATUSES | {InvoiceStatus.NEEDS_CHANGES, InvoiceStatus.FAILED}
_MANUAL_FIELDS = (
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "tax_total",
    "cgst",
    "sgst",
    "igst",
    "total",
    "vendor_gstin",
    "buyer_gstin",
    "po_number",
)
_FIELD_TO_COLUMN = {
    "vendor_gstin": "vendor_gstin_on_invoice",
    "buyer_gstin": "buyer_gstin_on_invoice",
    "po_number": "po_number_on_invoice",
    "vendor_name": "vendor_name_on_invoice",
    "bank_account_number": "bank_account_last4_on_invoice",
    "bank_ifsc": "bank_ifsc_on_invoice",
}
DISPLAY_FIELDS = (
    "vendor_name",
    "vendor_gstin",
    "buyer_gstin",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "tax_total",
    "cgst",
    "sgst",
    "igst",
    "total",
    "po_number",
    "bank_account_number",
    "bank_ifsc",
)


def column_for(field: str) -> str:
    return _FIELD_TO_COLUMN.get(field, field)


@dataclass(frozen=True)
class IngestResult:
    invoice: Invoice
    document: InvoiceDocument


def ingest_document(
    db: Session,
    storage: StorageProvider,
    dispatcher: TaskDispatcher,
    actor: TenantContext | SystemContext,
    document: ValidatedDocument,
    source: InvoiceSource,
    *,
    source_url_host: str | None = None,
    extra_audit: dict[str, Any] | None = None,
) -> IngestResult:
    """Stores the original document, creates the invoice and queues processing."""
    org_id = actor.organization_id
    user_id = actor.user_id if isinstance(actor, TenantContext) else None
    invoice = Invoice(
        id=uuid.uuid4(),
        organization_id=org_id,
        source=source,
        status=InvoiceStatus.UPLOADED,
        uploaded_by_id=user_id,
        field_provenance={},
    )
    document_id = uuid.uuid4()
    key = storage_key(org_id, invoice.id, document_id, document.extension)
    try:
        storage.put(key, document.data, document.content_type)
    except StorageError as exc:
        raise ServiceUnavailable(
            "Document storage is temporarily unavailable", code="storage_unavailable"
        ) from exc
    doc = InvoiceDocument(
        id=document_id,
        organization_id=org_id,
        invoice_id=invoice.id,
        storage_key=key,
        original_filename=document.safe_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        page_count=document.page_count,
        source_url_host=source_url_host,
    )
    db.add_all([invoice, doc])
    db.flush()
    db.add(
        InvoiceStatusChange(
            organization_id=org_id,
            invoice_id=invoice.id,
            from_status=None,
            to_status=InvoiceStatus.UPLOADED.value,
            actor_type=ActorType.USER if user_id else ActorType.SYSTEM,
            actor_user_id=user_id,
        )
    )
    transition(
        db,
        invoice,
        InvoiceStatus.QUEUED,
        actor_type=ActorType.USER if user_id else ActorType.SYSTEM,
        actor_user_id=user_id,
    )
    audit.record(
        db,
        actor,
        "invoice.uploaded",
        "invoice",
        invoice.id,
        {
            "source": source.value,
            "document_id": doc.id,
            "filename": doc.original_filename,
            "content_type": doc.content_type,
            "size_bytes": doc.size_bytes,
            "sha256": doc.sha256,
            "source_url_host": source_url_host,
            **(extra_audit or {}),
        },
    )
    db.commit()
    dispatcher.dispatch(PROCESS_INVOICE, invoice_id=str(invoice.id))
    return IngestResult(invoice, doc)


def upload(
    db: Session,
    settings: Settings,
    storage: StorageProvider,
    dispatcher: TaskDispatcher,
    ctx: TenantContext,
    data: bytes,
    filename: str | None,
    content_type: str | None,
) -> IngestResult:
    ctx.require(Permission.INVOICE_UPLOAD)
    document = validate_document(data, filename, content_type, settings.max_upload_bytes)
    return ingest_document(db, storage, dispatcher, ctx, document, InvoiceSource.UPLOAD)


def import_from_url(
    db: Session,
    settings: Settings,
    storage: StorageProvider,
    dispatcher: TaskDispatcher,
    ctx: TenantContext,
    url: str,
    policy: FetchPolicy | None = None,
) -> IngestResult:
    ctx.require(Permission.INVOICE_UPLOAD)
    if not settings.url_import_enabled:
        raise InvalidInput("URL import is disabled", code="url_import_disabled")
    policy = policy or FetchPolicy(
        max_bytes=settings.max_upload_bytes,
        timeout_seconds=settings.url_import_timeout_seconds,
        max_redirects=settings.url_import_max_redirects,
        allow_http=settings.url_import_allow_http,
        allowed_ports=tuple(settings.url_import_allowed_ports),
    )
    fetched = fetch_document(url, policy)
    document = validate_document(
        fetched.data, fetched.filename_hint, fetched.content_type, settings.max_upload_bytes
    )
    return ingest_document(
        db,
        storage,
        dispatcher,
        ctx,
        document,
        InvoiceSource.URL_IMPORT,
        source_url_host=fetched.host,
    )


def get_invoice(db: Session, ctx: TenantContext, invoice_id: uuid.UUID) -> Invoice:
    ctx.require(Permission.INVOICE_READ)
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.lines), selectinload(Invoice.documents))
        .where(Invoice.id == invoice_id, Invoice.organization_id == ctx.organization_id)
        # Background work updates invoices in other sessions; always read current state.
        .execution_options(populate_existing=True)
    )
    if invoice is None:
        raise NotFound()
    return invoice


def list_invoices(
    db: Session,
    ctx: TenantContext,
    *,
    status: list[InvoiceStatus] | None,
    risk_level: str | None,
    vendor_id: uuid.UUID | None,
    query: str | None,
    limit: int,
    offset: int,
    ids: list[uuid.UUID] | None = None,
) -> tuple[list[schemas.InvoiceSummary], int]:
    ctx.require(Permission.INVOICE_READ)
    open_high = (
        select(func.count(RiskSignal.id))
        .join(RiskAssessment, RiskAssessment.id == RiskSignal.assessment_id)
        .where(
            RiskSignal.invoice_id == Invoice.id,
            RiskAssessment.is_current.is_(True),
            RiskSignal.severity == Severity.HIGH,
            RiskSignal.source == SignalSource.RULE,
            RiskSignal.resolution == SignalResolution.OPEN,
        )
        .correlate(Invoice)
        .scalar_subquery()
    )
    stmt = (
        select(Invoice, Vendor.name, open_high.label("open_high"))
        .outerjoin(Vendor, Vendor.id == Invoice.vendor_id)
        .where(Invoice.organization_id == ctx.organization_id)
    )
    if ids is not None:
        stmt = stmt.where(Invoice.id.in_(ids))
    if status:
        stmt = stmt.where(Invoice.status.in_(status))
    if risk_level:
        stmt = stmt.where(Invoice.risk_level == risk_level)
    if vendor_id:
        stmt = stmt.where(Invoice.vendor_id == vendor_id)
    if query:
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Invoice.invoice_number).like(like),
                func.lower(Vendor.name).like(like),
                func.lower(Invoice.vendor_name_on_invoice).like(like),
            )
        )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(stmt.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)).all()
    return [
        schemas.InvoiceSummary(
            id=inv.id,
            status=inv.status,
            source=inv.source,
            invoice_number=inv.invoice_number,
            invoice_date=inv.invoice_date,
            total=inv.total,
            currency=inv.currency,
            vendor_id=inv.vendor_id,
            vendor_name=vendor_name or inv.vendor_name_on_invoice,
            risk_level=inv.risk_level,
            risk_score=inv.risk_score,
            open_high_signals=int(high or 0),
            required_approvals=inv.required_approvals,
            created_at=inv.created_at,
            processing_error_code=inv.processing_error_code,
        )
        for inv, vendor_name, high in rows
    ], total


def get_document(
    db: Session,
    storage: StorageProvider,
    ctx: TenantContext,
    invoice_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[InvoiceDocument, bytes]:
    invoice = get_invoice(db, ctx, invoice_id)
    document = next((d for d in invoice.documents if d.id == document_id), None)
    if document is None:
        raise NotFound()
    try:
        data = storage.get(document.storage_key)
    except StorageError as exc:
        raise ServiceUnavailable(
            "Document storage is temporarily unavailable", code="storage_unavailable"
        ) from exc
    return document, data


def _emails(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    real = {i for i in ids if i}
    if not real:
        return {}
    return dict(db.execute(select(User.id, User.email).where(User.id.in_(real))).all())


def _field_value(invoice: Invoice, name: str, emails: dict[uuid.UUID, str]) -> schemas.FieldValue:
    provenance = (invoice.field_provenance or {}).get(name) or {}
    value: Any = getattr(invoice, column_for(name), None)
    if name == "bank_account_number" and value:
        value = f"•••• {value}"
    edited_by = provenance.get("edited_by")
    return schemas.FieldValue(
        value=value,
        source=provenance.get("source"),
        confidence=provenance.get("confidence"),
        alternatives=provenance.get("alternatives", []),
        edited_by=emails.get(uuid.UUID(edited_by)) if edited_by else None,
    )


def allowed_actions(ctx: TenantContext, invoice: Invoice) -> list[str]:
    actions: list[str] = []
    if invoice.status in DECIDABLE_STATUSES and ctx.can(Permission.INVOICE_REVIEW):
        actions += ["approve", "reject", "request_changes"]
    if invoice.status in DECIDABLE_STATUSES and ctx.can(Permission.RISK_OVERRIDE):
        actions.append("resolve_signal")
    if invoice.status in EDITABLE_STATUSES and ctx.can(Permission.INVOICE_EDIT):
        actions.append("edit")
    if invoice.status in (InvoiceStatus.NEEDS_CHANGES, InvoiceStatus.FAILED) and ctx.can(
        Permission.INVOICE_UPLOAD
    ):
        actions += ["replace_document", "reprocess"]
    if ctx.can(Permission.INVOICE_REVIEW):
        actions.append("comment")
    return actions


def invoice_detail(db: Session, ctx: TenantContext, invoice: Invoice) -> schemas.InvoiceDetail:
    from app.modules.review.service import current_assessment  # local: avoids import cycle

    assessment = current_assessment(db, invoice)
    signals = (
        list(
            db.scalars(
                select(RiskSignal).where(
                    RiskSignal.assessment_id == assessment.id,
                    RiskSignal.organization_id == ctx.organization_id,
                )
            )
        )
        if assessment
        else []
    )
    cycle = current_cycle(db, invoice.id)
    steps = steps_for_cycle(db, invoice.id, cycle) if cycle else []
    reviews = list(
        db.scalars(
            select(Review)
            .where(Review.invoice_id == invoice.id, Review.organization_id == ctx.organization_id)
            .order_by(Review.created_at)
        )
    )
    history = list(
        db.scalars(
            select(InvoiceStatusChange)
            .where(
                InvoiceStatusChange.invoice_id == invoice.id,
                InvoiceStatusChange.organization_id == ctx.organization_id,
            )
            .order_by(InvoiceStatusChange.created_at)
        )
    )
    provenance_editors = {
        uuid.UUID(v["edited_by"])
        for v in (invoice.field_provenance or {}).values()
        if isinstance(v, dict) and v.get("edited_by")
    }
    emails = _emails(
        db,
        {
            invoice.uploaded_by_id,
            *(s.resolved_by_id for s in signals),
            *(s.decided_by_id for s in steps),
            *(r.reviewer_id for r in reviews),
            *(h.actor_user_id for h in history),
            *provenance_editors,
        },
    )
    vendor = (
        db.scalar(
            select(Vendor).where(
                Vendor.id == invoice.vendor_id, Vendor.organization_id == ctx.organization_id
            )
        )
        if invoice.vendor_id
        else None
    )
    po = (
        db.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == invoice.purchase_order_id,
                PurchaseOrder.organization_id == ctx.organization_id,
            )
        )
        if invoice.purchase_order_id
        else None
    )
    ai_output = (assessment.ai_output or {}) if assessment else {}
    explanations = {
        e["rule_code"]: e["explanation"] for e in ai_output.get("signal_explanations", [])
    }
    severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}
    signals.sort(key=lambda s: (s.source != SignalSource.RULE, severity_order[s.severity]))
    return schemas.InvoiceDetail(
        id=invoice.id,
        status=invoice.status,
        source=invoice.source,
        created_at=invoice.created_at,
        uploaded_by_email=emails.get(invoice.uploaded_by_id) if invoice.uploaded_by_id else None,
        review_requested_at=invoice.review_requested_at,
        decided_at=invoice.decided_at,
        processing_error_code=invoice.processing_error_code,
        processing_error_message=invoice.processing_error_message,
        required_approvals=invoice.required_approvals,
        fields={name: _field_value(invoice, name, emails) for name in DISPLAY_FIELDS},
        lines=[
            schemas.InvoiceLineResponse(
                line_no=line.line_no,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                amount=line.amount,
                source=line.source,
            )
            for line in invoice.lines
        ],
        documents=[
            schemas.DocumentResponse(
                id=d.id,
                original_filename=d.original_filename,
                content_type=d.content_type,
                size_bytes=d.size_bytes,
                sha256=d.sha256,
                page_count=d.page_count,
                source_url_host=d.source_url_host,
                created_at=d.created_at,
            )
            for d in invoice.documents
        ],
        vendor=schemas.LinkedVendor(
            id=vendor.id, name=vendor.name, gstin=vendor.gstin, status=vendor.status.value
        )
        if vendor
        else None,
        vendor_match=((invoice.field_provenance or {}).get("vendor_id") or {}).get("source"),
        purchase_order=schemas.LinkedPurchaseOrder(
            id=po.id,
            po_number=po.po_number,
            status=po.status.value,
            total=po.total,
            vendor_id=po.vendor_id,
        )
        if po
        else None,
        assessment=schemas.RiskAssessmentResponse(
            id=assessment.id,
            engine_version=assessment.engine_version,
            risk_level=assessment.risk_level,
            score=assessment.score,
            created_at=assessment.created_at,
            ai_status=assessment.ai_status,
            ai_provider=assessment.ai_provider,
            ai_model=assessment.ai_model,
            ai_error_code=assessment.ai_error_code,
            ai_summary=ai_output.get("summary"),
            ai_reviewer_focus=ai_output.get("reviewer_focus", []),
            ai_observations=ai_output.get("observations", []),
            signals=[
                schemas.RiskSignalResponse(
                    id=s.id,
                    rule_code=s.rule_code,
                    category=s.category,
                    severity=s.severity,
                    source=s.source,
                    title=s.title,
                    description=s.description,
                    evidence=[schemas.EvidenceItem(**e) for e in s.evidence],
                    resolution=s.resolution,
                    resolved_by_email=emails.get(s.resolved_by_id) if s.resolved_by_id else None,
                    resolved_at=s.resolved_at,
                    resolution_reason=s.resolution_reason,
                    ai_explanation=explanations.get(s.rule_code)
                    if s.source == SignalSource.RULE
                    else None,
                )
                for s in signals
            ],
        )
        if assessment
        else None,
        approval_steps=[
            schemas.ApprovalStepResponse(
                step_no=s.step_no,
                cycle=s.cycle,
                name=s.name,
                required_permission=s.required_permission,
                status=s.status,
                decided_by_email=emails.get(s.decided_by_id) if s.decided_by_id else None,
                decided_at=s.decided_at,
            )
            for s in steps
        ],
        reviews=[
            schemas.ReviewResponse(
                id=r.id,
                reviewer_email=emails.get(r.reviewer_id, "unknown"),
                decision=r.decision,
                step_no=r.step_no,
                reason=r.reason,
                evidence_snapshot=r.evidence_snapshot,
                created_at=r.created_at,
            )
            for r in reviews
        ],
        status_history=[
            schemas.StatusChangeResponse(
                from_status=h.from_status,
                to_status=h.to_status,
                actor_type=h.actor_type.value,
                actor_email=emails.get(h.actor_user_id) if h.actor_user_id else None,
                reason=h.reason,
                created_at=h.created_at,
            )
            for h in history
        ],
        allowed_actions=allowed_actions(ctx, invoice),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def update_invoice(
    db: Session,
    dispatcher: TaskDispatcher,
    ctx: TenantContext,
    invoice_id: uuid.UUID,
    update: schemas.InvoiceUpdate,
) -> Invoice:
    ctx.require(Permission.INVOICE_EDIT)
    invoice = get_invoice(db, ctx, invoice_id)
    if invoice.status not in EDITABLE_STATUSES:
        raise Conflict(
            f"Invoice cannot be edited while {invoice.status.value}", code="invoice_not_editable"
        )
    data = update.model_dump(exclude_unset=True, exclude={"reason", "lines"})
    provenance = dict(invoice.field_provenance or {})
    changes: dict[str, Any] = {}

    for name in _MANUAL_FIELDS:
        if name not in data:
            continue
        value = data[name]
        if name in ("vendor_gstin", "buyer_gstin"):
            value = normalize_gstin(value)
        column = column_for(name)
        old = getattr(invoice, column)
        if old != value:
            changes[name] = {"from": _jsonable(old), "to": _jsonable(value)}
            setattr(invoice, column, value)
            provenance[name] = {
                "source": "manual",
                "confidence": 1.0,
                "edited_by": str(ctx.user_id),
            }
            if name == "invoice_number":
                invoice.normalized_invoice_number = normalize_invoice_number(value)

    if "vendor_id" in data and data["vendor_id"] != invoice.vendor_id:
        if (
            data["vendor_id"] is not None
            and db.scalar(
                select(Vendor.id).where(
                    Vendor.id == data["vendor_id"], Vendor.organization_id == ctx.organization_id
                )
            )
            is None
        ):
            raise InvalidInput("Unknown vendor", code="unknown_vendor")
        changes["vendor_id"] = {
            "from": _jsonable(invoice.vendor_id),
            "to": _jsonable(data["vendor_id"]),
        }
        invoice.vendor_id = data["vendor_id"]
        provenance["vendor_id"] = {"source": "manual", "edited_by": str(ctx.user_id)}
    if "purchase_order_id" in data and data["purchase_order_id"] != invoice.purchase_order_id:
        if (
            data["purchase_order_id"] is not None
            and db.scalar(
                select(PurchaseOrder.id).where(
                    PurchaseOrder.id == data["purchase_order_id"],
                    PurchaseOrder.organization_id == ctx.organization_id,
                )
            )
            is None
        ):
            raise InvalidInput("Unknown purchase order", code="unknown_purchase_order")
        changes["purchase_order_id"] = {
            "from": _jsonable(invoice.purchase_order_id),
            "to": _jsonable(data["purchase_order_id"]),
        }
        invoice.purchase_order_id = data["purchase_order_id"]
        provenance["purchase_order_id"] = {"source": "manual", "edited_by": str(ctx.user_id)}

    if update.lines is not None:
        changes["lines"] = {"from_count": len(invoice.lines), "to_count": len(update.lines)}
        invoice.lines.clear()
        db.flush()
        for index, line in enumerate(update.lines, start=1):
            invoice.lines.append(
                InvoiceLine(
                    organization_id=ctx.organization_id,
                    line_no=index,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                    amount=line.amount,
                    source="manual",
                )
            )
        provenance["lines"] = {"source": "manual", "edited_by": str(ctx.user_id)}

    if not changes:
        raise InvalidInput("No changes submitted", code="no_changes")
    invoice.field_provenance = provenance
    transition(
        db,
        invoice,
        InvoiceStatus.RISK_ANALYSIS,
        actor_type=ActorType.USER,
        actor_user_id=ctx.user_id,
        reason=f"Manual correction: {update.reason}",
    )
    audit.record(
        db,
        ctx,
        "invoice.modified",
        "invoice",
        invoice.id,
        {"reason": update.reason, "changes": changes},
    )
    db.commit()
    dispatcher.dispatch(REANALYZE_INVOICE, invoice_id=str(invoice.id))
    return invoice


def replace_document(
    db: Session,
    settings: Settings,
    storage: StorageProvider,
    dispatcher: TaskDispatcher,
    ctx: TenantContext,
    invoice_id: uuid.UUID,
    data: bytes,
    filename: str | None,
    content_type: str | None,
) -> Invoice:
    ctx.require(Permission.INVOICE_UPLOAD)
    invoice = get_invoice(db, ctx, invoice_id)
    if invoice.status not in (InvoiceStatus.NEEDS_CHANGES, InvoiceStatus.FAILED):
        raise Conflict(
            "A corrected document can only be added when changes were requested "
            "or processing failed",
            code="invoice_not_replaceable",
        )
    document = validate_document(data, filename, content_type, settings.max_upload_bytes)
    document_id = uuid.uuid4()
    key = storage_key(ctx.organization_id, invoice.id, document_id, document.extension)
    try:
        storage.put(key, document.data, document.content_type)
    except StorageError as exc:
        raise ServiceUnavailable(
            "Document storage is temporarily unavailable", code="storage_unavailable"
        ) from exc
    db.add(
        InvoiceDocument(
            id=document_id,
            organization_id=ctx.organization_id,
            invoice_id=invoice.id,
            storage_key=key,
            original_filename=document.safe_filename,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            page_count=document.page_count,
        )
    )
    transition(
        db,
        invoice,
        InvoiceStatus.QUEUED,
        actor_type=ActorType.USER,
        actor_user_id=ctx.user_id,
        reason="Corrected document uploaded",
    )
    audit.record(
        db,
        ctx,
        "invoice.document_replaced",
        "invoice",
        invoice.id,
        {"document_id": document_id, "sha256": document.sha256, "filename": document.safe_filename},
    )
    db.commit()
    dispatcher.dispatch(PROCESS_INVOICE, invoice_id=str(invoice.id))
    return invoice


def reprocess(
    db: Session, dispatcher: TaskDispatcher, ctx: TenantContext, invoice_id: uuid.UUID
) -> Invoice:
    ctx.require(Permission.INVOICE_UPLOAD)
    invoice = get_invoice(db, ctx, invoice_id)
    if invoice.status not in (InvoiceStatus.FAILED, InvoiceStatus.NEEDS_CHANGES):
        raise Conflict(
            "Only failed invoices or invoices needing changes can be reprocessed",
            code="invoice_not_reprocessable",
        )
    transition(
        db,
        invoice,
        InvoiceStatus.QUEUED,
        actor_type=ActorType.USER,
        actor_user_id=ctx.user_id,
        reason="Reprocessing requested",
    )
    invoice.processing_error_code = None
    invoice.processing_error_message = None
    audit.record(db, ctx, "invoice.reprocess_requested", "invoice", invoice.id, {})
    db.commit()
    dispatcher.dispatch(PROCESS_INVOICE, invoice_id=str(invoice.id))
    return invoice


def approval_steps(db: Session, invoice: Invoice) -> list[ApprovalStep]:
    return steps_for_cycle(db, invoice.id, current_cycle(db, invoice.id))

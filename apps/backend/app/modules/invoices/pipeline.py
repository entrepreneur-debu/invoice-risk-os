"""Invoice processing pipeline (runs in the Celery worker).

    queued -> processing -> extracted -> risk_analysis -> review_required
                     \\-> failed (explicit error code; retry for transient failures)

Stages: load document -> text layer -> AI extraction (optional) -> deterministic merge
with provenance -> vendor identification -> PO linking -> deterministic risk rules ->
AI explanation (optional, advisory) -> approval cycle -> notifications.

AI failures never fail the invoice: the deterministic engine still runs, the invoice
still reaches review, and the assessment records why AI assistance was unavailable.
"""

import difflib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from app.ai.prompting import find_injection_indicators
from app.ai.provider import AIProvider, AIProviderError
from app.core.errors import AppError
from app.core.security import FieldEncryptor
from app.infra.storage import StorageError, StorageProvider
from app.models import (
    Invoice,
    InvoiceExtraction,
    InvoiceLine,
    Organization,
    RiskAssessment,
    RiskSignal,
    Vendor,
)
from app.models.enums import (
    ActorType,
    AIStatus,
    ExtractionMethod,
    ExtractionStatus,
    InvoiceStatus,
    RiskLevel,
    Severity,
    SignalSource,
)
from app.modules.audit import service as audit
from app.modules.context import SystemContext
from app.modules.identity.service import organization_settings
from app.modules.invoices.documents import validate_document
from app.modules.invoices.extraction import (
    SCALAR_FIELDS,
    AIInvoiceExtraction,
    MergedExtraction,
    extract_from_text,
    extract_with_ai,
    merge_extractions,
    normalize_invoice_number,
    provenance_entry,
)
from app.modules.invoices.service import column_for
from app.modules.invoices.state import transition
from app.modules.notifications import service as notifications
from app.modules.permissions import Permission
from app.modules.purchasing.service import find_by_number
from app.modules.review.service import open_approval_cycle
from app.modules.risk import ai_assist
from app.modules.risk.builder import build_context
from app.modules.risk.engine import ENGINE_VERSION, run_rules
from app.modules.vendors.service import normalize_vendor_name

logger = logging.getLogger(__name__)

_MAX_REPROCESS_BYTES = 1 << 30  # already validated at upload; no size limit here
_FUZZY_VENDOR_THRESHOLD = 0.92
_TRANSIENT = (StorageError, OperationalError)


@dataclass(frozen=True)
class PipelineDeps:
    storage: StorageProvider
    ai: AIProvider
    encryptor: FieldEncryptor


class TransientPipelineError(Exception):
    """Raised to the task layer so Celery retries with backoff."""


def _load(db: Session, invoice_id: uuid.UUID) -> Invoice | None:
    return db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.lines), selectinload(Invoice.documents))
        .where(Invoice.id == invoice_id)
        .with_for_update()
    )


def _is_manual(invoice: Invoice, field: str) -> bool:
    return ((invoice.field_provenance or {}).get(field) or {}).get("source") == "manual"


def apply_extraction(
    invoice: Invoice,
    merged: MergedExtraction,
    extraction_ids: dict[str, str],
    encryptor: FieldEncryptor,
) -> None:
    """Writes merged values to canonical columns. Manual corrections are never overwritten."""
    provenance = dict(invoice.field_provenance or {})
    for name in SCALAR_FIELDS:
        if _is_manual(invoice, name) or name == "bank_account_holder":
            continue
        field = merged.fields[name]
        if name == "bank_account_number":
            number = field.value
            invoice.bank_account_last4_on_invoice = number[-4:] if number else None
            invoice.bank_account_fingerprint_on_invoice = (
                encryptor.fingerprint(number) if number else None
            )
        else:
            setattr(invoice, column_for(name), field.value)
        provenance[name] = provenance_entry(field, extraction_ids)
    invoice.normalized_invoice_number = normalize_invoice_number(invoice.invoice_number)
    if not _is_manual(invoice, "lines"):
        invoice.lines.clear()
        for index, line in enumerate(merged.lines, start=1):
            invoice.lines.append(
                InvoiceLine(
                    organization_id=invoice.organization_id,
                    line_no=index,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    tax_rate=line.tax_rate,
                    amount=line.amount,
                    source=line.source,
                )
            )
        provenance["lines"] = {"source": merged.lines[0].source if merged.lines else None}
    invoice.field_provenance = provenance


def identify_vendor(db: Session, invoice: Invoice) -> None:
    if _is_manual(invoice, "vendor_id"):
        return
    provenance = dict(invoice.field_provenance or {})
    org_id = invoice.organization_id
    vendor = None
    method = "unmatched"
    if invoice.vendor_gstin_on_invoice:
        vendor = db.scalar(
            select(Vendor).where(
                Vendor.organization_id == org_id, Vendor.gstin == invoice.vendor_gstin_on_invoice
            )
        )
        method = "matched_by_gstin" if vendor else method
    if vendor is None and invoice.vendor_name_on_invoice:
        normalized = normalize_vendor_name(invoice.vendor_name_on_invoice)
        candidates = list(
            db.execute(
                select(Vendor.id, Vendor.normalized_name).where(Vendor.organization_id == org_id)
            )
        )
        exact = [vid for vid, name in candidates if name == normalized]
        if exact:
            vendor = db.get(Vendor, exact[0])
        else:
            scored = sorted(
                (
                    (difflib.SequenceMatcher(None, normalized, name).ratio(), vid)
                    for vid, name in candidates
                ),
                reverse=True,
            )
            if scored and scored[0][0] >= _FUZZY_VENDOR_THRESHOLD:
                vendor = db.get(Vendor, scored[0][1])
        method = "matched_by_name" if vendor else method
    invoice.vendor_id = vendor.id if vendor else None
    provenance["vendor_id"] = {"source": method}
    invoice.field_provenance = provenance


def link_purchase_order(db: Session, invoice: Invoice) -> None:
    if _is_manual(invoice, "purchase_order_id"):
        return
    po = find_by_number(db, invoice.organization_id, invoice.po_number_on_invoice)
    invoice.purchase_order_id = po.id if po else None
    provenance = dict(invoice.field_provenance or {})
    provenance["purchase_order_id"] = {"source": "matched_by_po_number" if po else "unmatched"}
    invoice.field_provenance = provenance


def _extract(db: Session, deps: PipelineDeps, invoice: Invoice, org: Organization) -> None:
    if not invoice.documents:
        raise AppError("Invoice has no document", code="no_document")
    document = invoice.documents[-1]
    data = deps.storage.get(document.storage_key)
    validated = validate_document(
        data, document.original_filename, document.content_type, _MAX_REPROCESS_BYTES
    )
    text = validated.text
    settings = organization_settings(org)

    ai_result: AIInvoiceExtraction | None = None
    ai_record = InvoiceExtraction(
        id=uuid.uuid4(),
        organization_id=invoice.organization_id,
        invoice_id=invoice.id,
        method=ExtractionMethod.DOCUMENT_AI,
        provider=deps.ai.name,
        model=deps.ai.model,
        status=ExtractionStatus.SKIPPED,
        output={},
    )
    if settings.ai_document_extraction_enabled:
        try:
            ai_result = extract_with_ai(deps.ai, data, document.content_type, text)
            ai_record.status = ExtractionStatus.SUCCEEDED
            ai_record.output = ai_result.model_dump(mode="json")
        except AIProviderError as exc:
            ai_record.status = ExtractionStatus.FAILED
            ai_record.error_code = exc.code
            logger.warning(
                "ai extraction failed",
                extra={"error_code": exc.code, "invoice_id": str(invoice.id)},
            )
    else:
        ai_record.error_code = "disabled_by_organization"

    heuristic = extract_from_text(text)
    indicators = find_injection_indicators(text)
    text_record = InvoiceExtraction(
        id=uuid.uuid4(),
        organization_id=invoice.organization_id,
        invoice_id=invoice.id,
        method=ExtractionMethod.TEXT_LAYER,
        status=(
            ExtractionStatus.SKIPPED
            if not text
            else ExtractionStatus.SUCCEEDED
            if heuristic.values
            else ExtractionStatus.PARTIAL
        ),
        output={
            "values": heuristic.values,
            "line_count": len(heuristic.lines),
            "text_characters": len(text or ""),
            "injection_indicators": indicators,
        },
        error_code=None if text else "no_text_layer",
    )
    db.add_all([ai_record, text_record])
    db.flush()

    merged = merge_extractions(ai_result, heuristic)
    if merged.observations:
        ai_record.output = {**ai_record.output, "document_observations": merged.observations}
    apply_extraction(
        invoice,
        merged,
        {"document_ai": str(ai_record.id), "text_layer": str(text_record.id)},
        deps.encryptor,
    )


def analyze(db: Session, deps: PipelineDeps, invoice: Invoice) -> RiskAssessment:
    """Deterministic risk analysis + optional AI explanation, then opens review."""
    system = SystemContext(invoice.organization_id, "risk-engine")
    org = db.get(Organization, invoice.organization_id)
    assert org is not None  # noqa: S101
    settings = organization_settings(org)
    if invoice.status == InvoiceStatus.EXTRACTED:
        transition(db, invoice, InvoiceStatus.RISK_ANALYSIS, actor_type=ActorType.SYSTEM)
    identify_vendor(db, invoice)
    link_purchase_order(db, invoice)
    db.flush()

    ctx = build_context(db, invoice)
    result = run_rules(ctx)
    if settings.ai_assistance_enabled:
        outcome = ai_assist.explain(deps.ai, ctx, result.signals)
    else:
        outcome = ai_assist.AssistOutcome(AIStatus.DISABLED, None, None)

    db.execute(
        update(RiskAssessment)
        .where(
            RiskAssessment.invoice_id == invoice.id,
            RiskAssessment.organization_id == invoice.organization_id,
        )
        .values(is_current=False)
    )
    assessment = RiskAssessment(
        id=uuid.uuid4(),
        organization_id=invoice.organization_id,
        invoice_id=invoice.id,
        engine_version=ENGINE_VERSION,
        risk_level=result.level,
        score=result.score,
        is_current=True,
        context_snapshot={
            "rules_evaluated": result.rules_evaluated,
            "rules_failed": list(result.rules_failed),
            "vendor_id": ctx.vendor.id if ctx.vendor else None,
            "purchase_order_id": ctx.purchase_order.id if ctx.purchase_order else None,
            "vendor_history_count": len(ctx.vendor.history) if ctx.vendor else 0,
        },
        ai_status=outcome.status,
        ai_provider=deps.ai.name if outcome.status != AIStatus.DISABLED else None,
        ai_model=deps.ai.model if outcome.status == AIStatus.SUCCEEDED else None,
        ai_output=outcome.output,
        ai_error_code=outcome.error_code,
    )
    db.add(assessment)
    db.flush()
    for draft in result.signals:
        db.add(
            RiskSignal(
                organization_id=invoice.organization_id,
                assessment_id=assessment.id,
                invoice_id=invoice.id,
                rule_code=draft.rule_code,
                category=draft.category,
                severity=draft.severity,
                source=SignalSource.RULE,
                title=draft.title,
                description=draft.description,
                evidence=[e.as_dict() for e in draft.evidence],
            )
        )
    for observation in (outcome.output or {}).get("observations", []):
        db.add(
            RiskSignal(
                organization_id=invoice.organization_id,
                assessment_id=assessment.id,
                invoice_id=invoice.id,
                rule_code="ai_observation",
                category="ai_observation",
                severity=Severity(observation["suggested_severity"]),
                source=SignalSource.AI,
                title=observation["title"],
                description=observation["detail"],
                evidence=[
                    {
                        "label": "Generated by",
                        "value": f"{deps.ai.name} ({deps.ai.model})",
                        "source": "ai",
                    }
                ],
            )
        )

    invoice.risk_level = result.level
    invoice.risk_score = result.score
    approvals = open_approval_cycle(db, invoice, settings, result.level)
    transition(
        db,
        invoice,
        InvoiceStatus.REVIEW_REQUIRED,
        actor_type=ActorType.SYSTEM,
        reason=f"Risk analysis complete: {result.level.value} ({result.score})",
    )
    invoice.review_requested_at = datetime.now(UTC)
    invoice.processing_error_code = None
    invoice.processing_error_message = None

    audit.record(
        db,
        system,
        "risk.assessed",
        "invoice",
        invoice.id,
        {
            "assessment_id": assessment.id,
            "engine_version": ENGINE_VERSION,
            "risk_level": result.level.value,
            "score": result.score,
            "signals": [
                {"rule_code": s.rule_code, "severity": s.severity.value} for s in result.signals
            ],
            "ai_status": outcome.status.value,
            "ai_error_code": outcome.error_code,
            "required_approvals": approvals,
        },
    )
    severity = {RiskLevel.HIGH: Severity.HIGH, RiskLevel.MEDIUM: Severity.MEDIUM}.get(
        result.level, Severity.INFO
    )
    notifications.notify_permission(
        db,
        invoice.organization_id,
        Permission.INVOICE_REVIEW,
        kind="invoice.review_required",
        severity=severity,
        title=f"Invoice {invoice.invoice_number or '(unnumbered)'} requires review "
        f"({result.level.value} risk)",
        body=f"{len(result.signals)} risk signal(s). Approvals required: {approvals}.",
        entity_type="invoice",
        entity_id=invoice.id,
    )
    return assessment


def _mark_failed(db: Session, invoice_id: uuid.UUID, code: str, message: str) -> None:
    db.rollback()
    invoice = _load(db, invoice_id)
    if invoice is None or invoice.status in (
        InvoiceStatus.FAILED,
        InvoiceStatus.APPROVED,
        InvoiceStatus.REJECTED,
    ):
        db.rollback()
        return
    transition(db, invoice, InvoiceStatus.FAILED, actor_type=ActorType.SYSTEM, reason=message)
    invoice.processing_error_code = code
    invoice.processing_error_message = message[:500]
    audit.record(
        db,
        SystemContext(invoice.organization_id, "pipeline"),
        "invoice.processing_failed",
        "invoice",
        invoice.id,
        {"error_code": code, "attempts": invoice.processing_attempts},
    )
    recipients = [invoice.uploaded_by_id] if invoice.uploaded_by_id else []
    notifications.notify(
        db,
        invoice.organization_id,
        recipients,
        kind="invoice.processing_failed",
        severity=Severity.MEDIUM,
        title="Invoice processing failed",
        body=f"{message} You can reprocess it or upload a corrected document.",
        entity_type="invoice",
        entity_id=invoice.id,
    )
    notifications.notify_permission(
        db,
        invoice.organization_id,
        Permission.INVOICE_REVIEW,
        kind="invoice.processing_failed",
        severity=Severity.MEDIUM,
        title="Invoice processing failed",
        body=message,
        entity_type="invoice",
        entity_id=invoice.id,
        exclude_user_id=invoice.uploaded_by_id,
    )
    db.commit()
    logger.error(
        "invoice processing failed", extra={"invoice_id": str(invoice_id), "error_code": code}
    )


def process_invoice(
    db: Session, deps: PipelineDeps, invoice_id: uuid.UUID, *, final_attempt: bool = True
) -> None:
    invoice = _load(db, invoice_id)
    if invoice is None:
        logger.warning("invoice not found for processing", extra={"invoice_id": str(invoice_id)})
        return
    if invoice.status != InvoiceStatus.QUEUED:
        # Idempotency: duplicate deliveries of the same task are ignored.
        logger.info(
            "invoice not queued; skipping",
            extra={"invoice_id": str(invoice_id), "status": invoice.status.value},
        )
        db.rollback()
        return
    org = db.get(Organization, invoice.organization_id)
    assert org is not None  # noqa: S101
    try:
        transition(db, invoice, InvoiceStatus.PROCESSING, actor_type=ActorType.SYSTEM)
        invoice.processing_attempts += 1
        db.flush()
        _extract(db, deps, invoice, org)
        transition(db, invoice, InvoiceStatus.EXTRACTED, actor_type=ActorType.SYSTEM)
        analyze(db, deps, invoice)
        audit.record(
            db,
            SystemContext(invoice.organization_id, "pipeline"),
            "invoice.processed",
            "invoice",
            invoice.id,
            {"attempt": invoice.processing_attempts},
        )
        db.commit()
    except _TRANSIENT as exc:
        logger.warning(
            "transient pipeline failure",
            extra={
                "invoice_id": str(invoice_id),
                "error_type": type(exc).__name__,
                "final_attempt": final_attempt,
            },
        )
        if final_attempt:
            _mark_failed(
                db,
                invoice_id,
                "dependency_unavailable",
                "A storage or database dependency was unavailable.",
            )
            return
        db.rollback()
        requeue = _load(db, invoice_id)
        if requeue is not None and requeue.status == InvoiceStatus.QUEUED:
            requeue.processing_attempts += 1
        db.commit()
        raise TransientPipelineError(str(type(exc).__name__)) from exc
    except AppError as exc:
        _mark_failed(db, invoice_id, exc.code, exc.message)
    except Exception as exc:
        logger.exception("unexpected pipeline failure", extra={"invoice_id": str(invoice_id)})
        _mark_failed(
            db,
            invoice_id,
            "processing_error",
            f"Unexpected processing error ({type(exc).__name__}).",
        )


def reanalyze_invoice(db: Session, deps: PipelineDeps, invoice_id: uuid.UUID) -> None:
    invoice = _load(db, invoice_id)
    if invoice is None or invoice.status != InvoiceStatus.RISK_ANALYSIS:
        db.rollback()
        return
    try:
        analyze(db, deps, invoice)
        db.commit()
    except Exception as exc:
        logger.exception("re-analysis failed", extra={"invoice_id": str(invoice_id)})
        _mark_failed(
            db, invoice_id, "analysis_error", f"Risk analysis failed ({type(exc).__name__})."
        )

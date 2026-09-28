"""Concurrent processing must not defeat duplicate detection (regression test).

Found while running the seeded demo on the real worker (concurrency 2): two invoices with
the same number, processed at the same moment, did not flag each other because each ran
its duplicate check before the other's extracted data was committed.
"""

import threading
import time
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AIRequest, AIUnavailable, T
from app.core.config import Settings
from app.core.security import FieldEncryptor
from app.infra.storage import MemoryStorageProvider
from app.infra.tasks import RecordingTaskDispatcher
from app.models import Invoice, RiskAssessment, RiskSignal
from app.models.enums import InvoiceSource
from app.modules.context import SystemContext
from app.modules.invoices import pipeline
from app.modules.invoices.documents import validate_document
from app.modules.invoices.service import ingest_document
from tests.integration.conftest import Client, create_vendor, sample_invoice

pytestmark = pytest.mark.integration


class SlowUnavailableAI:
    """Makes both pipelines spend time in extraction so their work overlaps."""

    name = "slow-mock"
    model = "slow-mock"

    def generate_structured(self, request: AIRequest, schema: type[T]) -> T:
        time.sleep(0.4)
        raise AIUnavailable("slow mock")


def test_concurrent_duplicates_are_detected(
    owner: Client,
    api_settings: Settings,
    session_factory: sessionmaker[Session],
    storage: MemoryStorageProvider,
) -> None:
    create_vendor(owner)
    org_id = uuid.UUID(owner.me["organization"]["id"])
    recorder = RecordingTaskDispatcher()
    invoice_ids = []
    for date in ("10/09/2026", "11/09/2026"):  # different bytes, same invoice number
        with session_factory() as db:
            document = validate_document(
                sample_invoice("DUP-77", date=date), "d.pdf", "application/pdf", 10_000_000
            )
            result = ingest_document(
                db, storage, recorder, SystemContext(org_id), document, InvoiceSource.UPLOAD
            )
            invoice_ids.append(result.invoice.id)

    deps = pipeline.PipelineDeps(
        storage,
        SlowUnavailableAI(),
        FieldEncryptor(api_settings.encryption_key_bytes),
    )
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run(invoice_id: uuid.UUID) -> None:
        try:
            barrier.wait()
            with session_factory() as db:
                pipeline.process_invoice(db, deps, invoice_id)
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in invoice_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors

    with session_factory() as db:
        statuses = {
            i.status.value for i in db.scalars(select(Invoice).where(Invoice.id.in_(invoice_ids)))
        }
        flagged = db.scalars(
            select(RiskSignal.invoice_id)
            .join(RiskAssessment, RiskAssessment.id == RiskSignal.assessment_id)
            .where(
                RiskSignal.rule_code == "duplicate_invoice_number",
                RiskAssessment.is_current.is_(True),
                RiskSignal.invoice_id.in_(invoice_ids),
            )
        ).all()
    assert statuses == {"review_required"}
    assert len(set(flagged)) == 1  # the later of the pair is flagged; the original is not

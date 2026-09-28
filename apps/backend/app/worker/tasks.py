"""Background tasks. Thin wrappers: all logic lives in the domain modules.

Retries: only for transient failures (storage/database unavailable), with exponential
backoff and a hard cap (TASK_MAX_RETRIES). Permanent failures are recorded on the
invoice (status `failed` + error code) instead of being retried forever.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import Task, current_app, shared_task

from app.infra.storage import StorageError
from app.infra.tasks import (
    PING,
    PROCESS_INBOUND_EMAIL,
    PROCESS_INVOICE,
    REANALYZE_INVOICE,
    CeleryTaskDispatcher,
)
from app.modules.email_ingestion import service as email_service
from app.modules.invoices import pipeline
from app.worker.runtime import runtime

logger = logging.getLogger(__name__)

PING_TASK_NAME = PING


def _backoff(retries: int) -> int:
    return int(min(300, 10 * 2**retries))


@shared_task(name=PING)
def ping() -> str:
    """Round-trip check: API -> Redis broker -> worker -> Redis result backend."""
    return "pong"


@shared_task(name=PROCESS_INVOICE, bind=True, acks_late=True)
def process_invoice(self: Task[Any, Any], invoice_id: str) -> None:
    rt = runtime()
    final = self.request.retries >= rt.settings.task_max_retries
    with rt.session_factory() as db:
        try:
            pipeline.process_invoice(db, rt.deps, uuid.UUID(invoice_id), final_attempt=final)
        except pipeline.TransientPipelineError as exc:
            logger.warning(
                "retrying invoice processing",
                extra={"invoice_id": invoice_id, "retry": self.request.retries + 1},
            )
            raise self.retry(
                exc=exc,
                countdown=_backoff(self.request.retries),
                max_retries=rt.settings.task_max_retries,
            ) from exc


@shared_task(name=REANALYZE_INVOICE, acks_late=True)
def reanalyze_invoice(invoice_id: str) -> None:
    rt = runtime()
    with rt.session_factory() as db:
        pipeline.reanalyze_invoice(db, rt.deps, uuid.UUID(invoice_id))


@shared_task(name=PROCESS_INBOUND_EMAIL, bind=True, acks_late=True)
def process_inbound_email(self: Task[Any, Any], inbound_email_id: str) -> None:
    rt = runtime()
    with rt.session_factory() as db:
        try:
            email_service.process(
                db,
                rt.settings,
                rt.storage,
                CeleryTaskDispatcher(current_app),
                uuid.UUID(inbound_email_id),
            )
        except StorageError as exc:
            if self.request.retries >= rt.settings.task_max_retries:
                logger.error(
                    "inbound email processing failed permanently",
                    extra={"inbound_email_id": inbound_email_id},
                )
                raise
            raise self.retry(
                exc=exc,
                countdown=_backoff(self.request.retries),
                max_retries=rt.settings.task_max_retries,
            ) from exc

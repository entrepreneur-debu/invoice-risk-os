"""Celery application factory.

The worker runs the same codebase as the API (modular monolith); only the process
entrypoint differs. See `app.worker.main` for the worker entrypoint.
"""

from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.core.config import Settings
from app.core.logging import configure_logging

TASK_MODULES = ["app.worker.tasks"]


def create_celery_app(settings: Settings) -> Celery:
    app = Celery("invoice_risk", include=TASK_MODULES)
    app.conf.update(
        broker_url=settings.broker_url,
        result_backend=settings.result_backend_url,
        broker_connection_retry_on_startup=True,  # wait for Redis instead of crashing
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],  # never unpickle untrusted payloads
        result_expires=3600,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_hijack_root_logger=False,
        # Explicit, bounded behaviour for long-running work.
        task_time_limit=15 * 60,
        task_soft_time_limit=12 * 60,
        worker_max_tasks_per_child=500,
        task_track_started=True,
        broker_transport_options={"visibility_timeout": 3600},
        timezone="UTC",
        enable_utc=True,
    )
    return app


def install_worker_logging(settings: Settings) -> None:
    @setup_logging.connect(weak=False)
    def _configure(**_: Any) -> None:
        configure_logging(settings.log_level, service="worker")

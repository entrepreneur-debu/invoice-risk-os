"""Task dispatch boundary between services and the background worker.

Services call `dispatcher.dispatch(TASK_NAME, **kwargs)`; they never import Celery.
Production uses `CeleryTaskDispatcher` (Redis broker). Tests use `InlineTaskDispatcher`
to run handlers synchronously, or `RecordingTaskDispatcher` to assert what was queued.
"""

import logging
from collections.abc import Callable
from typing import Any, Protocol

from celery import Celery

logger = logging.getLogger(__name__)

PROCESS_INVOICE = "invoices.process"
REANALYZE_INVOICE = "invoices.reanalyze"
PROCESS_INBOUND_EMAIL = "email.process_inbound"
DELIVER_NOTIFICATION = "notifications.deliver"
PING = "system.ping"


class TaskDispatcher(Protocol):
    def dispatch(self, name: str, **kwargs: Any) -> None: ...


class CeleryTaskDispatcher:
    def __init__(self, celery: Celery) -> None:
        self._celery = celery

    def dispatch(self, name: str, **kwargs: Any) -> None:
        self._celery.send_task(name, kwargs=kwargs)
        logger.info("task dispatched", extra={"task": name})


class RecordingTaskDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def dispatch(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))


class InlineTaskDispatcher:
    """Runs registered handlers immediately (tests, local CLI). Unknown tasks are recorded."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[..., Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        self.handlers[name] = handler

    def dispatch(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))
        handler = self.handlers.get(name)
        if handler is not None:
            handler(**kwargs)

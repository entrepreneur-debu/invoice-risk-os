"""Structured (JSON) logging, compatible with Google Cloud Logging.

One JSON object per line on stdout. Cloud Logging reads `severity`, `message` and
`logging.googleapis.com/trace` natively. Request context (request ID, organization,
user, trace) is attached automatically from context variables. Values passed through
`extra=` whose key looks sensitive are redacted before they are written.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "redis_url",
    "account_number",
    "encryption_key",
)
REDACTED = "[REDACTED]"

# Uvicorn duplicates messages with ANSI colour codes in `color_message`.
_DROPPED_EXTRA_KEYS = frozenset({"color_message"})

# Attributes present on every LogRecord; anything else came from `extra=`.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys() | {"message", "asctime"}
)

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
organization_id_var: ContextVar[str | None] = ContextVar("organization_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
trace_var: ContextVar[str | None] = ContextVar("trace", default=None)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def redact(value: Any, key: str = "") -> Any:
    if key and _is_sensitive(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "level": record.levelname,
            "logger": record.name,
            "service": self._service,
            "message": record.getMessage(),
        }
        for name, var in (
            ("request_id", request_id_var),
            ("organization_id", organization_id_var),
            ("user_id", user_id_var),
        ):
            value = var.get()
            if value:
                payload[name] = value
        trace = trace_var.get()
        if trace:
            payload["logging.googleapis.com/trace"] = trace
        for key, value in record.__dict__.items():
            if (
                key not in _STANDARD_RECORD_ATTRS
                and key not in _DROPPED_EXTRA_KEYS
                and not key.startswith("_")
            ):
                payload[key] = redact(value, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=service))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Route server/framework loggers through the root JSON handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "alembic"):
        framework_logger = logging.getLogger(name)
        framework_logger.handlers = []
        framework_logger.propagate = True
    # Our request middleware logs requests; uvicorn's access log would duplicate them.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Third-party HTTP client libraries can log URLs and headers at DEBUG.
    for noisy in ("httpx", "httpcore", "urllib3", "botocore", "google_genai"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))


def trace_from_header(header: str | None, project: str | None) -> str | None:
    """Builds the Cloud Logging trace resource name from X-Cloud-Trace-Context."""
    if not header or not project:
        return None
    trace_id = header.split("/", 1)[0].strip()
    if not trace_id or not all(c in "0123456789abcdefABCDEF" for c in trace_id):
        return None
    return f"projects/{project}/traces/{trace_id}"

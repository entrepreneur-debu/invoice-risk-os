"""Structured (JSON) logging on top of the standard library.

Log records are emitted as one JSON object per line. Values passed through `extra=`
whose key looks sensitive are redacted before they are written.
"""

import json
import logging
import sys
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
)
REDACTED = "[REDACTED]"

# Attributes present on every LogRecord; anything else came from `extra=`.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys() | {"message", "asctime"}
)


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
            "level": record.levelname,
            "logger": record.name,
            "service": self._service,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
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
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery"):
        framework_logger = logging.getLogger(name)
        framework_logger.handlers = []
        framework_logger.propagate = True
    # Our request middleware logs requests; uvicorn's access log would duplicate them.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

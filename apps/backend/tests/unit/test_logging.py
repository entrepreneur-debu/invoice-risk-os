import json
import logging

from app.core.logging import REDACTED, JsonFormatter, redact


def _format(**extra: object) -> dict[str, object]:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.__dict__.update(extra)
    result: dict[str, object] = json.loads(JsonFormatter(service="api").format(record))
    return result


def test_emits_single_line_json_with_context() -> None:
    payload = _format(request_id="abc")

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["service"] == "api"
    assert payload["request_id"] == "abc"


def test_redacts_sensitive_extra_fields() -> None:
    payload = _format(api_key="sk-live", headers={"Authorization": "Bearer x", "accept": "json"})

    assert payload["api_key"] == REDACTED
    assert payload["headers"] == {"Authorization": REDACTED, "accept": "json"}


def test_redact_handles_nested_structures() -> None:
    assert redact({"items": [{"password": "p", "name": "n"}]}) == {
        "items": [{"password": REDACTED, "name": "n"}]
    }

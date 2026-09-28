import time

import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.infra.resources import ReadinessCheck
from app.main import create_app
from tests.conftest import SettingsFactory


def _raise_connection_error() -> None:
    raise ConnectionError("postgresql://user:hunter2@db/secret")


def test_health_reports_process_alive(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Invoice Risk & Payment Control OS",
        "version": "1.0.0",
    }


def test_ready_when_all_dependencies_available(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok", "object_storage": "ok"},
    }


def test_ready_returns_503_without_leaking_error_details(make_settings: SettingsFactory) -> None:
    checks = [
        ReadinessCheck("database", _raise_connection_error),
        ReadinessCheck("redis", lambda: None),
    ]
    app = create_app(make_settings(), readiness_checks=checks)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable", "redis": "ok"},
    }
    assert "hunter2" not in response.text


def test_ready_times_out_slow_dependency(
    make_settings: SettingsFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "READINESS_CHECK_TIMEOUT_SECONDS", 0.05)
    app = create_app(
        make_settings(), readiness_checks=[ReadinessCheck("redis", lambda: time.sleep(0.5))]
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"redis": "unavailable"}


def test_default_readiness_checks_cover_all_dependencies(make_settings: SettingsFactory) -> None:
    app = create_app(make_settings())

    with TestClient(app) as client:
        names = [check.name for check in client.app.state.readiness_checks]  # type: ignore[attr-defined]

    assert names == ["database", "redis", "object_storage"]


def test_responses_carry_request_id(client: TestClient) -> None:
    generated = client.get("/health")
    echoed = client.get("/health", headers={"X-Request-ID": "abc-123"})
    rejected = client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})

    assert len(generated.headers["x-request-id"]) == 32
    assert echoed.headers["x-request-id"] == "abc-123"
    assert rejected.headers["x-request-id"] != "bad id\nwith newline"

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import SettingsFactory, passing_checks

PRODUCTION_SECRET = "x" * 40


def test_app_starts_and_stops_cleanly(make_settings: SettingsFactory) -> None:
    app = create_app(make_settings(), readiness_checks=passing_checks())

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.app.state.resources is not None  # type: ignore[attr-defined]


def test_api_docs_disabled_in_production(make_settings: SettingsFactory) -> None:
    app = create_app(
        make_settings(
            app_env="production", auth_secret=PRODUCTION_SECRET, session_cookie_secure=True
        ),
        readiness_checks=passing_checks(),
    )

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_api_docs_available_in_development(make_settings: SettingsFactory) -> None:
    app = create_app(make_settings(app_env="development"), readiness_checks=passing_checks())

    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200


def test_diagnostics_endpoints_only_mounted_when_enabled(make_settings: SettingsFactory) -> None:
    disabled = create_app(make_settings(), readiness_checks=passing_checks())
    enabled = create_app(
        make_settings(enable_diagnostics_endpoints=True), readiness_checks=passing_checks()
    )

    assert "/api/v1/diagnostics/worker-ping" not in disabled.openapi()["paths"]
    assert "/api/v1/diagnostics/worker-ping" in enabled.openapi()["paths"]


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers

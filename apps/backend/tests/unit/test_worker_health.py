import json
import urllib.request

import pytest

from app.worker.health_server import start_if_configured


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKER_HEALTH_PORT", raising=False)
    assert start_if_configured() is None


def test_serves_liveness_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_HEALTH_PORT", "0")
    server = start_if_configured()
    assert server is not None
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()

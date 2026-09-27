from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


class _Payload(BaseModel):
    amount: int


def _add_failing_routes(app: FastAPI) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    @app.post("/echo")
    def echo(payload: _Payload) -> _Payload:
        return payload


def test_unhandled_error_returns_generic_message(app: FastAPI) -> None:
    _add_failing_routes(app)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "req-1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
            "request_id": "req-1",
        }
    }
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text


def test_not_found_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


def test_validation_error_does_not_echo_input(app: FastAPI) -> None:
    _add_failing_routes(app)

    with TestClient(app) as client:
        response = client.post("/echo", json={"amount": "secret-value"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "amount"]
    assert "secret-value" not in response.text

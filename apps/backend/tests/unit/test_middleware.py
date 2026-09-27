from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def _add_upload_route(app: FastAPI) -> None:
    @app.post("/upload")
    async def upload(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}


def test_body_within_limit_is_accepted(app: FastAPI) -> None:
    _add_upload_route(app)

    with TestClient(app) as client:
        response = client.post("/upload", content=b"x" * 1024)

    assert response.status_code == 200
    assert response.json() == {"size": 1024}


def test_declared_oversized_body_is_rejected(app: FastAPI) -> None:
    _add_upload_route(app)

    with TestClient(app) as client:
        response = client.post("/upload", content=b"x" * 1025)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_streamed_oversized_body_is_rejected(app: FastAPI) -> None:
    _add_upload_route(app)

    def chunks() -> Iterator[bytes]:
        for _ in range(4):
            yield b"x" * 512

    with TestClient(app) as client:
        # A generator body is sent chunked, without a Content-Length header.
        response = client.post("/upload", content=chunks())

    assert response.status_code == 413

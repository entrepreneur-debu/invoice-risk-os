import uuid

import pytest
from celery.contrib.testing.worker import start_worker
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import create_db_engine, get_db_session, ping_database
from app.infra.redis import create_redis_client, ping_redis
from app.infra.storage import create_s3_client, ensure_bucket, ping_bucket
from app.main import create_app
from app.worker.celery_app import create_celery_app
from app.worker.tasks import PING_TASK_NAME

pytestmark = pytest.mark.integration


def test_database_connectivity(live_settings: Settings) -> None:
    engine = create_db_engine(live_settings)
    try:
        ping_database(engine)
        with engine.connect() as connection:
            version: str = connection.execute(text("SHOW server_version")).scalar_one()
        assert int(str(version).split(".")[0]) >= 17
    finally:
        engine.dispose()


def test_request_scoped_session_dependency(live_settings: Settings) -> None:
    app = create_app(live_settings)

    @app.get("/probe-session")
    def probe(session: Session = Depends(get_db_session)) -> dict[str, int]:  # noqa: B008
        return {"value": session.execute(text("SELECT 41 + 1")).scalar_one()}

    with TestClient(app) as client:
        assert client.get("/probe-session").json() == {"value": 42}


def test_redis_connectivity(live_settings: Settings) -> None:
    client = create_redis_client(live_settings)
    key = f"test:integration:{uuid.uuid4().hex}"
    try:
        ping_redis(client)
        client.set(key, "value", ex=30)
        assert client.get(key) == b"value"
    finally:
        client.delete(key)
        client.close()


def test_object_storage_round_trip(live_settings: Settings) -> None:
    client = create_s3_client(live_settings)
    ensure_bucket(client, live_settings.s3_bucket)
    ping_bucket(client, live_settings.s3_bucket)
    key = f"integration-tests/{uuid.uuid4().hex}.txt"
    try:
        client.put_object(Bucket=live_settings.s3_bucket, Key=key, Body=b"synthetic test data")
        body = client.get_object(Bucket=live_settings.s3_bucket, Key=key)["Body"].read()
        assert body == b"synthetic test data"
    finally:
        client.delete_object(Bucket=live_settings.s3_bucket, Key=key)


def test_celery_task_executes_through_redis(live_settings: Settings) -> None:
    app = create_celery_app(live_settings)
    app.loader.import_default_modules()
    app.conf.task_default_queue = f"test-{uuid.uuid4().hex}"

    with start_worker(app, perform_ping_check=False, loglevel="WARNING", shutdown_timeout=10):
        result = app.send_task(PING_TASK_NAME)
        assert result.get(timeout=15) == "pong"


def test_ready_endpoint_against_real_dependencies(live_settings: Settings) -> None:
    ensure_bucket(create_s3_client(live_settings), live_settings.s3_bucket)
    app: FastAPI = create_app(live_settings)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infra.resources import ReadinessCheck
from app.main import create_app

# Unreachable, obviously-fake endpoints: unit tests must never touch real services.
UNIT_SETTINGS: dict[str, Any] = {
    "app_env": "test",
    "auth_secret": "test-secret-for-unit-tests-only-0000",
    "data_encryption_key": "dGVzdC1vbmx5LWVuY3J5cHRpb24ta2V5LTAwMDAwMDA=",
    "log_level": "WARNING",
    "cors_allowed_origins": ["http://localhost:3000"],
    "max_request_body_bytes": 1024,
    "session_cookie_secure": False,
    "database_url": "postgresql+psycopg://test:test@127.0.0.1:1/test",
    "redis_url": "redis://127.0.0.1:1/0",
    "object_storage_endpoint_url": "http://127.0.0.1:1",
    "object_storage_access_key_id": "test",
    "object_storage_secret_access_key": "test",
    "object_storage_bucket": "test-bucket",
}

SettingsFactory = Callable[..., Settings]


@pytest.fixture
def make_settings() -> SettingsFactory:
    def factory(**overrides: Any) -> Settings:
        # _env_file=None: unit tests ignore any developer .env file.
        return Settings(_env_file=None, **{**UNIT_SETTINGS, **overrides})

    return factory


@pytest.fixture
def settings(make_settings: SettingsFactory) -> Settings:
    return make_settings()


def passing_checks() -> list[ReadinessCheck]:
    return [ReadinessCheck(name, lambda: None) for name in ("database", "redis", "object_storage")]


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings, readiness_checks=passing_checks())


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

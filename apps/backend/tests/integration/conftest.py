"""Integration tests run against real PostgreSQL, Redis and MinIO.

Start them with `docker compose up -d postgres redis minio` and point the settings
at them (the repository `.env` created from `.env.example` already does).
"""

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()

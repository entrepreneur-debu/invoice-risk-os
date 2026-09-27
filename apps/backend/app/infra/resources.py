"""Process-wide infrastructure clients, created at startup and released at shutdown."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory, ping_database
from app.infra.redis import create_redis_client, ping_redis
from app.infra.storage import create_s3_client, ping_bucket

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass(frozen=True)
class ReadinessCheck:
    """A named, blocking probe that raises when its dependency is unavailable."""

    name: str
    probe: Callable[[], None]


@dataclass
class Resources:
    engine: Engine
    session_factory: sessionmaker[Session]
    redis: Redis
    s3: S3Client
    s3_bucket: str

    @classmethod
    def from_settings(cls, settings: Settings) -> Resources:
        # Constructing clients does not open connections, so startup never blocks on
        # a dependency that is still booting; /ready reports it instead.
        engine = create_db_engine(settings)
        return cls(
            engine=engine,
            session_factory=create_session_factory(engine),
            redis=create_redis_client(settings),
            s3=create_s3_client(settings),
            s3_bucket=settings.s3_bucket,
        )

    def readiness_checks(self) -> list[ReadinessCheck]:
        return [
            ReadinessCheck("database", lambda: ping_database(self.engine)),
            ReadinessCheck("redis", lambda: ping_redis(self.redis)),
            ReadinessCheck("object_storage", lambda: ping_bucket(self.s3, self.s3_bucket)),
        ]

    def close(self) -> None:
        self.engine.dispose()
        self.redis.close()
        self.s3.close()

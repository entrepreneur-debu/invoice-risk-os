"""Database engine and session lifecycle."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # transparently replace connections dropped by the server
        pool_recycle=1800,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
        hide_parameters=True,  # keep bound parameters out of exception messages and logs
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed after the request."""
    factory: sessionmaker[Session] = request.app.state.resources.session_factory
    with factory() as session:
        yield session


def ping_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

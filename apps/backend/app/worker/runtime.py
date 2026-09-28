"""Per-process infrastructure for the worker (created lazily, once per process)."""

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from app.ai import create_ai_provider
from app.core.config import Settings, get_settings
from app.core.security import FieldEncryptor
from app.db.session import create_db_engine, create_session_factory
from app.infra.storage import StorageProvider, create_storage
from app.modules.invoices.pipeline import PipelineDeps


@dataclass(frozen=True)
class WorkerRuntime:
    settings: Settings
    session_factory: sessionmaker[Session]
    storage: StorageProvider
    deps: PipelineDeps


@lru_cache
def runtime() -> WorkerRuntime:
    settings = get_settings()
    storage = create_storage(settings)
    return WorkerRuntime(
        settings=settings,
        session_factory=create_session_factory(create_db_engine(settings)),
        storage=storage,
        deps=PipelineDeps(
            storage=storage,
            ai=create_ai_provider(settings),
            encryptor=FieldEncryptor(settings.encryption_key_bytes),
        ),
    )

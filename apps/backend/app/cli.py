"""Operational commands: `python -m app.cli <command>`.

ensure-bucket              create the storage bucket if allowed (local dev)
seed-demo [--inline]       create a demo organization with synthetic data (non-production)
ingest-email FILE --token  submit a raw .eml through the email-ingestion pipeline (local test)
"""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from celery import Celery

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.security import FieldEncryptor
from app.db.session import create_db_engine, create_session_factory
from app.infra.storage import create_storage
from app.infra.tasks import (
    PROCESS_INBOUND_EMAIL,
    PROCESS_INVOICE,
    REANALYZE_INVOICE,
    CeleryTaskDispatcher,
    InlineTaskDispatcher,
    TaskDispatcher,
)

logger = logging.getLogger("app.cli")


def _ensure_bucket(settings: Settings, _: argparse.Namespace) -> int:
    if not settings.object_storage_auto_create_bucket:
        logger.info("OBJECT_STORAGE_AUTO_CREATE_BUCKET is disabled; skipping bucket creation")
        return 0
    created = create_storage(settings).ensure_bucket()
    logger.info(
        "object storage bucket ready",
        extra={"bucket": settings.object_storage_bucket, "bucket_created": created},
    )
    return 0


def _dispatcher(settings: Settings, inline: bool) -> TaskDispatcher:
    if not inline:
        from app.worker.celery_app import create_celery_app

        celery: Celery = create_celery_app(settings)
        return CeleryTaskDispatcher(celery)
    import uuid

    from app.ai import create_ai_provider
    from app.modules.email_ingestion import service as email_service
    from app.modules.invoices import pipeline

    session_factory = create_session_factory(create_db_engine(settings))
    storage = create_storage(settings)
    deps = pipeline.PipelineDeps(
        storage, create_ai_provider(settings), FieldEncryptor(settings.encryption_key_bytes)
    )
    inline_dispatcher = InlineTaskDispatcher()

    def run(fn: Callable[..., object]) -> Callable[..., None]:
        def handler(**kwargs: str) -> None:
            with session_factory() as db:
                fn(db, **kwargs)

        return handler

    inline_dispatcher.register(
        PROCESS_INVOICE,
        run(lambda db, invoice_id: pipeline.process_invoice(db, deps, uuid.UUID(invoice_id))),
    )
    inline_dispatcher.register(
        REANALYZE_INVOICE,
        run(lambda db, invoice_id: pipeline.reanalyze_invoice(db, deps, uuid.UUID(invoice_id))),
    )
    inline_dispatcher.register(
        PROCESS_INBOUND_EMAIL,
        run(
            lambda db, inbound_email_id: email_service.process(
                db, settings, storage, inline_dispatcher, uuid.UUID(inbound_email_id)
            )
        ),
    )
    return inline_dispatcher


def _seed_demo(settings: Settings, args: argparse.Namespace) -> int:
    import os

    from app.demo.seed import seed_demo

    session_factory = create_session_factory(create_db_engine(settings))
    with session_factory() as db:
        result = seed_demo(
            db,
            settings,
            create_storage(settings),
            _dispatcher(settings, args.inline),
            password=os.environ.get("DEMO_PASSWORD") or None,
        )
    # Printed to the operator's terminal once; never logged.
    print("Demo organization created. Sign in with any of:")
    for role, email in result.users.items():
        print(f"  {role:9} {email}")
    print(f"  password  {result.password}")
    print(f"{result.invoices_queued} demo invoices queued for processing.")
    return 0


def _ingest_email(settings: Settings, args: argparse.Namespace) -> int:
    from app.modules.email_ingestion import service as email_service

    raw = Path(args.file).read_bytes()
    session_factory = create_session_factory(create_db_engine(settings))
    with session_factory() as db:
        org = email_service.organization_for_token(db, settings, args.token)
        inbound = email_service.receive(
            db,
            create_storage(settings),
            _dispatcher(settings, args.inline),
            org,
            raw,
            email_service.RawMimeParser(),
        )
        print(f"Inbound email {inbound.id} accepted ({inbound.status.value})")
    return 0


COMMANDS = {"ensure-bucket": _ensure_bucket, "seed-demo": _seed_demo, "ingest-email": _ingest_email}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ensure-bucket")
    seed = sub.add_parser("seed-demo")
    seed.add_argument("--inline", action="store_true", help="process invoices in this process")
    ingest = sub.add_parser("ingest-email")
    ingest.add_argument("file")
    ingest.add_argument("--token", required=True)
    ingest.add_argument("--inline", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, service="cli")
    return COMMANDS[args.command](settings, args)


if __name__ == "__main__":
    sys.exit(main())

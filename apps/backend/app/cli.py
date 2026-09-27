"""Operational commands: `python -m app.cli <command>`."""

import argparse
import logging
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infra.storage import create_s3_client, ensure_bucket

logger = logging.getLogger("app.cli")


def _ensure_bucket() -> int:
    settings = get_settings()
    if not settings.s3_auto_create_bucket:
        logger.info("S3_AUTO_CREATE_BUCKET is disabled; skipping bucket creation")
        return 0
    client = create_s3_client(settings)
    created = ensure_bucket(client, settings.s3_bucket)
    logger.info(
        "object storage bucket ready",
        extra={"bucket": settings.s3_bucket, "bucket_created": created},
    )
    return 0


COMMANDS = {"ensure-bucket": _ensure_bucket}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    configure_logging(get_settings().log_level, service="cli")
    return COMMANDS[args.command]()


if __name__ == "__main__":
    sys.exit(main())

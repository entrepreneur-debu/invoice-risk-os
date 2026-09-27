"""S3-compatible object storage client (MinIO locally, any S3 API in other environments)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings

if TYPE_CHECKING:
    # Type stubs are a dev-only dependency; never import them at runtime.
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)


def create_s3_client(settings: Settings) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},  # MinIO does not use virtual-hosted buckets
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def ping_bucket(client: S3Client, bucket: str) -> None:
    """Raises if the configured bucket is unreachable or missing."""
    client.head_bucket(Bucket=bucket)


def ensure_bucket(client: S3Client, bucket: str) -> bool:
    """Creates the bucket if it does not exist. Returns True when it was created."""
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
            raise
    client.create_bucket(Bucket=bucket)
    logger.info("object storage bucket created", extra={"bucket": bucket})
    return True

"""Object storage abstraction.

Business code depends only on `StorageProvider`. Implementations:
- `S3StorageProvider`: MinIO locally, or any S3-compatible API.
- `GCSStorageProvider`: Google Cloud Storage with Application Default Credentials
  (Cloud Run service account; no keys in configuration).
- `MemoryStorageProvider`: in-process, for unit/API tests.

Objects are private. They are only ever served back through the API, which enforces
tenant authorization; no public or pre-signed URLs are issued.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, StorageBackend

if TYPE_CHECKING:
    # Type stubs are a dev-only dependency; never import them at runtime.
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised for storage failures callers should treat as transient/unavailable."""


class ObjectNotFound(StorageError):
    pass


class StorageProvider(Protocol):
    @property
    def backend(self) -> str: ...

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def check(self) -> None:
        """Raises if the bucket is unreachable (used by /ready)."""

    def ensure_bucket(self) -> bool:
        """Creates the bucket if allowed and missing. Returns True when created."""


class S3StorageProvider:
    def __init__(self, settings: Settings, client: S3Client | None = None) -> None:
        self._bucket = settings.object_storage_bucket
        if client is None:
            assert settings.object_storage_access_key_id is not None  # noqa: S101
            assert settings.object_storage_secret_access_key is not None  # noqa: S101
            client = boto3.client(
                "s3",
                endpoint_url=settings.object_storage_endpoint_url,
                region_name=settings.object_storage_region,
                aws_access_key_id=settings.object_storage_access_key_id.get_secret_value(),
                aws_secret_access_key=settings.object_storage_secret_access_key.get_secret_value(),
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    connect_timeout=3,
                    read_timeout=15,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        self._client = client

    @property
    def backend(self) -> str:
        return "s3"

    @property
    def client(self) -> S3Client:
        return self._client

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except ClientError as exc:
            raise StorageError(f"put failed: {exc.response.get('Error', {}).get('Code')}") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise ObjectNotFound(key) from exc
            raise StorageError(f"get failed: {code}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise StorageError("delete failed") from exc

    def check(self) -> None:
        self._client.head_bucket(Bucket=self._bucket)

    def ensure_bucket(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return False
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
                raise
        self._client.create_bucket(Bucket=self._bucket)
        logger.info("object storage bucket created", extra={"bucket": self._bucket})
        return True


class GCSStorageProvider:
    """Google Cloud Storage. Credentials come from ADC (the runtime service account)."""

    def __init__(self, settings: Settings) -> None:
        from google.cloud import storage  # imported lazily: only needed on GCP

        self._client = storage.Client(project=settings.google_cloud_project)
        self._bucket = self._client.bucket(settings.object_storage_bucket)

    @property
    def backend(self) -> str:
        return "gcs"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        from google.api_core import exceptions

        try:
            self._bucket.blob(key).upload_from_string(data, content_type=content_type)
        except exceptions.GoogleAPIError as exc:
            raise StorageError("put failed") from exc

    def get(self, key: str) -> bytes:
        from google.api_core import exceptions

        try:
            return bytes(self._bucket.blob(key).download_as_bytes())
        except exceptions.NotFound as exc:
            raise ObjectNotFound(key) from exc
        except exceptions.GoogleAPIError as exc:
            raise StorageError("get failed") from exc

    def delete(self, key: str) -> None:
        from google.api_core import exceptions

        try:
            self._bucket.blob(key).delete()
        except exceptions.GoogleAPIError as exc:
            raise StorageError("delete failed") from exc

    def check(self) -> None:
        if not self._bucket.exists():
            raise StorageError("bucket not found")

    def ensure_bucket(self) -> bool:
        # Buckets on GCP are provisioned by infrastructure (IaC), never by the app.
        self.check()
        return False


class MemoryStorageProvider:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._lock = threading.Lock()
        self.fail_next: Exception | None = None

    @property
    def backend(self) -> str:
        return "memory"

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._maybe_fail()
        with self._lock:
            self._objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        self._maybe_fail()
        with self._lock:
            if key not in self._objects:
                raise ObjectNotFound(key)
            return self._objects[key][0]

    def delete(self, key: str) -> None:
        with self._lock:
            self._objects.pop(key, None)

    def check(self) -> None:
        self._maybe_fail()

    def ensure_bucket(self) -> bool:
        return False

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._objects)


def create_storage(settings: Settings) -> StorageProvider:
    if settings.object_storage_backend is StorageBackend.GCS:
        return GCSStorageProvider(settings)
    return S3StorageProvider(settings)

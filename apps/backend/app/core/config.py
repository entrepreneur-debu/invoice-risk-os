"""Application settings, loaded from environment variables.

Every setting is documented in the repository root `.env.example`. Secrets are held
as `SecretStr` so they are never rendered by `repr()`, logs, or error pages.
The same code runs in development, test and production; only configuration differs.
"""

import base64
import binascii
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Repository-root .env, used when running the backend directly on the host.
# Inside containers the file does not exist and values come from the environment.
_PARENTS = Path(__file__).resolve().parents
_REPO_ROOT_ENV_FILE = _PARENTS[4] / ".env" if len(_PARENTS) > 4 else None

# Placeholders shipped in .env.example. Refused in production.
DEV_SECRET_PLACEHOLDER = "dev-only-insecure-secret-change-me"  # noqa: S105
DEV_ENCRYPTION_KEY_PLACEHOLDER = "ZGV2LW9ubHktaW5zZWN1cmUtZGF0YS1rZXktMDAwMDA="

_OPTIONAL_KEYS = (
    "celery_broker_url",
    "celery_result_backend",
    "object_storage_endpoint_url",
    "object_storage_access_key_id",
    "object_storage_secret_access_key",
    "gemini_api_key",
    "google_cloud_project",
)
_LIST_KEYS = ("cors_allowed_origins", "url_import_allowed_ports")


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AIProviderName(StrEnum):
    MOCK = "mock"
    GEMINI = "gemini"


class StorageBackend(StrEnum):
    S3 = "s3"  # MinIO locally, or any S3-compatible API
    GCS = "gcs"  # Google Cloud Storage via Application Default Credentials


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Validation errors must not echo raw input: it contains secrets and DSNs.
        hide_input_in_errors=True,
    )

    app_name: str = "Invoice Risk & Payment Control OS"
    app_env: Environment = Environment.PRODUCTION
    log_level: str = "INFO"
    # Public URL of the web application; used to build invitation links.
    app_base_url: str = "http://localhost:3000"

    # --- Authentication / sessions -------------------------------------------------
    auth_secret: SecretStr
    session_ttl_hours: int = Field(default=12, gt=0, le=24 * 30)
    session_idle_timeout_minutes: int = Field(default=120, gt=0)
    # Secure cookies require HTTPS; only development/test may disable them.
    session_cookie_secure: bool = True
    invitation_ttl_hours: int = Field(default=72, gt=0)
    login_max_attempts_per_ip: int = Field(default=30, gt=0)
    login_max_attempts_per_email: int = Field(default=10, gt=0)
    signup_max_per_ip: int = Field(default=10, gt=0)
    rate_limit_window_seconds: int = Field(default=900, gt=0)

    # --- Data protection -----------------------------------------------------------
    # base64-encoded 32-byte key for field-level encryption (bank account numbers).
    data_encryption_key: SecretStr

    # --- HTTP ----------------------------------------------------------------------
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)
    max_upload_bytes: int = Field(default=15 * 1_048_576, gt=0)
    max_inbound_email_bytes: int = Field(default=25 * 1_048_576, gt=0)
    enable_diagnostics_endpoints: bool = False
    # Number of trusted proxies that append to X-Forwarded-For in front of the API.
    # 0 = use the socket peer address. Compose (web proxy) = 1; Cloud Run behind the
    # web service = 2. Used only for rate limiting and audit IP addresses.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    # --- URL import (SSRF-protected) -----------------------------------------------
    url_import_enabled: bool = True
    url_import_allow_http: bool = False
    url_import_allowed_ports: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [443, 80]
    )
    url_import_max_redirects: int = Field(default=3, ge=0, le=10)
    url_import_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    # --- PostgreSQL ----------------------------------------------------------------
    database_url: SecretStr
    database_pool_size: int = Field(default=5, gt=0)
    database_max_overflow: int = Field(default=5, ge=0)
    database_connect_timeout_seconds: int = Field(default=5, gt=0)

    # --- Redis / Celery ------------------------------------------------------------
    redis_url: SecretStr
    celery_broker_url: SecretStr | None = None
    celery_result_backend: SecretStr | None = None
    task_max_retries: int = Field(default=3, ge=0, le=10)

    # --- Object storage ------------------------------------------------------------
    object_storage_backend: StorageBackend = StorageBackend.S3
    object_storage_bucket: str
    object_storage_endpoint_url: str | None = None
    object_storage_region: str = "us-east-1"
    object_storage_access_key_id: SecretStr | None = None
    object_storage_secret_access_key: SecretStr | None = None
    object_storage_auto_create_bucket: bool = False

    # --- AI provider ---------------------------------------------------------------
    ai_provider: AIProviderName = AIProviderName.MOCK
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_request_timeout_seconds: int = Field(default=60, gt=0)

    # --- Email ingestion -----------------------------------------------------------
    inbound_email_domain: str = "inbound.localhost"

    # --- Google Cloud (optional) ---------------------------------------------------
    # Enables Cloud Logging trace correlation when running on Google Cloud.
    google_cloud_project: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_raw_values(cls, data: object) -> object:
        if isinstance(data, dict):
            for key in _LIST_KEYS:
                raw = data.get(key)
                if isinstance(raw, str):
                    data[key] = [item.strip() for item in raw.split(",") if item.strip()]
            # `KEY=` in an env file means "not set" for optional values.
            for key in _OPTIONAL_KEYS:
                if data.get(key) == "":
                    data[key] = None
        return data

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.database_url.get_secret_value() or not self.redis_url.get_secret_value():
            raise ValueError("DATABASE_URL and REDIS_URL must not be empty")
        try:
            key = base64.b64decode(self.data_encryption_key.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("DATA_ENCRYPTION_KEY must be base64") from exc
        if len(key) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes")

        if self.object_storage_backend is StorageBackend.S3 and not (
            self.object_storage_access_key_id and self.object_storage_secret_access_key
        ):
            raise ValueError("OBJECT_STORAGE_ACCESS_KEY_ID/SECRET_ACCESS_KEY are required for s3")
        if self.ai_provider is AIProviderName.GEMINI and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")

        if self.app_env is Environment.PRODUCTION:
            secret = self.auth_secret.get_secret_value()
            if secret == DEV_SECRET_PLACEHOLDER or len(secret) < 32:
                raise ValueError(
                    "AUTH_SECRET must be a unique value of at least 32 characters in production"
                )
            if self.data_encryption_key.get_secret_value() == DEV_ENCRYPTION_KEY_PLACEHOLDER:
                raise ValueError("DATA_ENCRYPTION_KEY must not be the development placeholder")
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            if "*" in self.cors_allowed_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if self.enable_diagnostics_endpoints:
                raise ValueError("Diagnostics endpoints must be disabled in production")
            if self.url_import_allow_http:
                raise ValueError("URL_IMPORT_ALLOW_HTTP must be false in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @property
    def broker_url(self) -> str:
        return (self.celery_broker_url or self.redis_url).get_secret_value()

    @property
    def result_backend_url(self) -> str:
        return (self.celery_result_backend or self.redis_url).get_secret_value()

    @property
    def encryption_key_bytes(self) -> bytes:
        return base64.b64decode(self.data_encryption_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from the environment

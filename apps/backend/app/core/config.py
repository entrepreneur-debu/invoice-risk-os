"""Application settings, loaded from environment variables.

Every setting is documented in the repository root `.env.example`. Secrets are held
as `SecretStr` so they are never rendered by `repr()`, logs, or error pages.
"""

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

# Placeholder value shipped in .env.example. Refused outside development/test.
DEV_SECRET_PLACEHOLDER = "dev-only-insecure-secret-change-me"  # noqa: S105


_OPTIONAL_KEYS = (
    "celery_broker_url",
    "celery_result_backend",
    "s3_endpoint_url",
    "anthropic_api_key",
    "gemini_api_key",
)


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AIProviderName(StrEnum):
    MOCK = "mock"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


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
    app_secret_key: SecretStr
    log_level: str = "INFO"

    # HTTP
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)
    enable_diagnostics_endpoints: bool = False

    # PostgreSQL
    database_url: SecretStr
    database_pool_size: int = Field(default=5, gt=0)
    database_max_overflow: int = Field(default=5, ge=0)
    database_connect_timeout_seconds: int = Field(default=5, gt=0)

    # Redis / Celery
    redis_url: SecretStr
    celery_broker_url: SecretStr | None = None
    celery_result_backend: SecretStr | None = None

    # S3-compatible object storage (MinIO locally)
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr
    s3_secret_access_key: SecretStr
    s3_bucket: str
    s3_auto_create_bucket: bool = False

    # AI provider boundary. Nothing calls a provider yet; tests always use the mock.
    ai_provider: AIProviderName = AIProviderName.MOCK
    anthropic_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_request_timeout_seconds: int = Field(default=60, gt=0)

    @model_validator(mode="before")
    @classmethod
    def _normalize_raw_values(cls, data: object) -> object:
        if isinstance(data, dict):
            raw = data.get("cors_allowed_origins")
            if isinstance(raw, str):
                data["cors_allowed_origins"] = [o.strip() for o in raw.split(",") if o.strip()]
            # `KEY=` in an env file means "not set" for optional values.
            for key in _OPTIONAL_KEYS:
                if data.get(key) == "":
                    data[key] = None
        return data

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Self:
        if self.app_env is Environment.PRODUCTION:
            secret = self.app_secret_key.get_secret_value()
            if secret == DEV_SECRET_PLACEHOLDER or len(secret) < 32:
                raise ValueError(
                    "APP_SECRET_KEY must be a unique value of at least 32 characters in production"
                )
            if "*" in self.cors_allowed_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if self.enable_diagnostics_endpoints:
                raise ValueError("Diagnostics endpoints must be disabled in production")
        if self.ai_provider is AIProviderName.ANTHROPIC and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
        if self.ai_provider is AIProviderName.GEMINI and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from the environment

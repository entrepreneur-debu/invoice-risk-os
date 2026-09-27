import pytest
from pydantic import ValidationError

from app.core.config import DEV_SECRET_PLACEHOLDER, Settings
from tests.conftest import UNIT_SETTINGS, SettingsFactory


def test_defaults_to_production_environment() -> None:
    values = {k: v for k, v in UNIT_SETTINGS.items() if k != "app_env"}
    values["app_secret_key"] = "y" * 40

    settings = Settings(_env_file=None, **values)

    assert settings.is_production


def test_production_rejects_placeholder_secret(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
        make_settings(app_env="production", app_secret_key=DEV_SECRET_PLACEHOLDER)


def test_production_rejects_wildcard_cors_and_diagnostics(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        make_settings(app_env="production", app_secret_key="z" * 40, cors_allowed_origins=["*"])
    with pytest.raises(ValidationError, match="Diagnostics"):
        make_settings(
            app_env="production", app_secret_key="z" * 40, enable_diagnostics_endpoints=True
        )


def test_anthropic_provider_requires_api_key(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        make_settings(ai_provider="anthropic")


def test_gemini_provider_requires_api_key(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        make_settings(ai_provider="gemini", gemini_api_key="")


def test_gemini_api_key_is_masked(make_settings: SettingsFactory) -> None:
    settings = make_settings(ai_provider="gemini", gemini_api_key="placeholder-key-value")

    assert "placeholder-key-value" not in repr(settings)


def test_reads_comma_separated_cors_origins_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in UNIT_SETTINGS.items():
        if not isinstance(value, list):
            monkeypatch.setenv(key.upper(), str(value))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://app.example.com")

    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://app.example.com"]


def test_secrets_are_masked_in_repr(settings: Settings) -> None:
    rendered = repr(settings)

    assert "test-secret" not in rendered
    assert "test:test@" not in rendered


def test_celery_urls_fall_back_to_redis_url(make_settings: SettingsFactory) -> None:
    default = make_settings()
    explicit = make_settings(celery_broker_url="redis://broker:6379/1")

    assert default.broker_url == default.result_backend_url == "redis://127.0.0.1:1/0"
    assert explicit.broker_url == "redis://broker:6379/1"


def test_empty_optional_values_are_treated_as_unset(make_settings: SettingsFactory) -> None:
    settings = make_settings(celery_broker_url="", anthropic_api_key="")

    assert settings.celery_broker_url is None
    assert settings.anthropic_api_key is None
    assert settings.broker_url == "redis://127.0.0.1:1/0"


def test_validation_errors_do_not_echo_secret_inputs(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(
            app_env="production",
            app_secret_key="short",
            database_url="postgresql+psycopg://user:hunter2@db/app",
        )

    assert "hunter2" not in str(exc_info.value)
    assert "short" not in str(exc_info.value)

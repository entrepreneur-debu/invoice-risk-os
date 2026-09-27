import pytest
from pydantic import ValidationError

from app.core.config import (
    DEV_ENCRYPTION_KEY_PLACEHOLDER,
    DEV_SECRET_PLACEHOLDER,
    Settings,
    StorageBackend,
)
from tests.conftest import UNIT_SETTINGS, SettingsFactory

STRONG = "p" * 40
PRODUCTION = {"app_env": "production", "auth_secret": STRONG, "session_cookie_secure": True}


def test_defaults_to_production_environment() -> None:
    values = {
        k: v for k, v in UNIT_SETTINGS.items() if k not in ("app_env", "session_cookie_secure")
    }
    values["auth_secret"] = STRONG

    settings = Settings(_env_file=None, **values)

    assert settings.is_production
    assert settings.session_cookie_secure is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"auth_secret": DEV_SECRET_PLACEHOLDER}, "AUTH_SECRET"),
        ({"auth_secret": "short"}, "AUTH_SECRET"),
        ({"data_encryption_key": DEV_ENCRYPTION_KEY_PLACEHOLDER}, "DATA_ENCRYPTION_KEY"),
        ({"session_cookie_secure": False}, "SESSION_COOKIE_SECURE"),
        ({"cors_allowed_origins": ["*"]}, "Wildcard CORS"),
        ({"enable_diagnostics_endpoints": True}, "Diagnostics"),
        ({"url_import_allow_http": True}, "URL_IMPORT_ALLOW_HTTP"),
    ],
)
def test_production_rejects_unsafe_configuration(
    make_settings: SettingsFactory, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_settings(**{**PRODUCTION, **overrides})


def test_production_accepts_safe_configuration(make_settings: SettingsFactory) -> None:
    assert make_settings(**PRODUCTION).is_production


@pytest.mark.parametrize("key", ["not-base64!!", "c2hvcnQ="])
def test_encryption_key_must_be_32_bytes_of_base64(
    make_settings: SettingsFactory, key: str
) -> None:
    with pytest.raises(ValidationError, match="DATA_ENCRYPTION_KEY"):
        make_settings(data_encryption_key=key)


def test_gemini_provider_requires_api_key(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        make_settings(ai_provider="gemini", gemini_api_key="")


def test_s3_backend_requires_keys_but_gcs_does_not(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="OBJECT_STORAGE_ACCESS_KEY_ID"):
        make_settings(object_storage_access_key_id="")
    gcs = make_settings(
        object_storage_backend="gcs",
        object_storage_access_key_id="",
        object_storage_secret_access_key="",
    )
    assert gcs.object_storage_backend is StorageBackend.GCS


def test_empty_required_urls_are_rejected(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        make_settings(database_url="")


def test_reads_lists_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in UNIT_SETTINGS.items():
        if not isinstance(value, list):
            monkeypatch.setenv(key.upper(), str(value))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://app.example.com")
    monkeypatch.setenv("URL_IMPORT_ALLOWED_PORTS", "443")

    settings = Settings(_env_file=None)

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://app.example.com"]
    assert settings.url_import_allowed_ports == [443]


def test_secrets_are_masked_in_repr(make_settings: SettingsFactory) -> None:
    rendered = repr(make_settings(gemini_api_key="AIza-placeholder-key"))

    assert UNIT_SETTINGS["auth_secret"] not in rendered
    assert "AIza-placeholder-key" not in rendered
    assert "test:test@" not in rendered


def test_validation_errors_do_not_echo_secret_inputs(make_settings: SettingsFactory) -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(
            app_env="production",
            auth_secret="short-secret-value",
            database_url="postgresql+psycopg://user:hunter2@db/app",
        )

    assert "hunter2" not in str(exc_info.value)
    assert "short-secret-value" not in str(exc_info.value)


def test_empty_optional_values_are_treated_as_unset(make_settings: SettingsFactory) -> None:
    settings = make_settings(celery_broker_url="", gemini_api_key="")

    assert settings.celery_broker_url is None
    assert settings.gemini_api_key is None
    assert settings.broker_url == "redis://127.0.0.1:1/0"

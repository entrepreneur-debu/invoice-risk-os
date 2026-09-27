from app.core.config import Settings
from app.worker.celery_app import create_celery_app
from app.worker.tasks import PING_TASK_NAME, ping


def test_ping_task_returns_pong() -> None:
    assert ping.apply().get() == "pong"


def test_celery_app_is_configured_from_settings(settings: Settings) -> None:
    app = create_celery_app(settings)

    assert app.conf.broker_url == "redis://127.0.0.1:1/0"
    assert app.conf.accept_content == ["json"]
    assert app.conf.broker_connection_retry_on_startup is True
    app.loader.import_default_modules()
    assert PING_TASK_NAME in app.tasks

from app.core.config import Settings
from app.infra.tasks import PING, PROCESS_INVOICE
from app.worker.celery_app import create_celery_app
from app.worker.tasks import ping


def test_ping_task_returns_pong() -> None:
    assert ping.apply().get() == "pong"


def test_celery_app_is_configured_safely(settings: Settings) -> None:
    app = create_celery_app(settings)

    assert app.conf.broker_url == "redis://127.0.0.1:1/0"
    assert app.conf.accept_content == ["json"]
    assert app.conf.broker_connection_retry_on_startup is True
    assert app.conf.task_time_limit and app.conf.task_soft_time_limit
    app.loader.import_default_modules()
    assert {PING, PROCESS_INVOICE} <= set(app.tasks)

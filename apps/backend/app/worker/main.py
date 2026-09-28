"""Worker entrypoint: `celery -A app.worker.main worker`."""

from app.core.config import get_settings
from app.worker.celery_app import create_celery_app, install_worker_logging
from app.worker.health_server import start_if_configured

settings = get_settings()
install_worker_logging(settings)
celery_app = create_celery_app(settings)
start_if_configured()

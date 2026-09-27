"""Worker entrypoint: `celery -A app.worker.main worker`."""

from app.core.config import get_settings
from app.worker.celery_app import create_celery_app, install_worker_logging

settings = get_settings()
install_worker_logging(settings)
celery_app = create_celery_app(settings)

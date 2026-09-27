"""Background tasks.

Only an infrastructure diagnostic task exists in Step 1. Business tasks (for example
invoice extraction) will live in their own modules and be added to TASK_MODULES.
"""

from celery import shared_task

PING_TASK_NAME = "system.ping"


@shared_task(name=PING_TASK_NAME)
def ping() -> str:
    """Round-trip check: API -> Redis broker -> worker -> Redis result backend."""
    return "pong"

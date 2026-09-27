"""Development-only diagnostics. Mounted only when ENABLE_DIAGNOSTICS_ENDPOINTS=true,
which settings validation forbids in production."""

from typing import Literal

from celery import Celery
from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.worker.tasks import PING_TASK_NAME

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

WORKER_PING_TIMEOUT_SECONDS = 10.0


class WorkerPingResponse(BaseModel):
    task_id: str
    status: Literal["SUCCESS"]
    result: str


@router.post("/worker-ping", response_model=WorkerPingResponse)
def worker_ping(request: Request) -> WorkerPingResponse:
    """Enqueues the ping task via Redis and waits for a worker to execute it."""
    celery: Celery = request.app.state.celery
    async_result = celery.send_task(PING_TASK_NAME)
    try:
        result = async_result.get(timeout=WORKER_PING_TIMEOUT_SECONDS)
    except CeleryTimeoutError as exc:
        raise HTTPException(status_code=504, detail="No worker completed the task in time") from exc
    return WorkerPingResponse(task_id=async_result.id, status="SUCCESS", result=str(result))

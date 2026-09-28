"""Unversioned operational endpoints used by orchestrators and load balancers."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.infra.resources import ReadinessCheck

logger = logging.getLogger(__name__)

router = APIRouter(tags=["operations"])

READINESS_CHECK_TIMEOUT_SECONDS = 5.0

CheckStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckStatus]


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Liveness: the process is up and serving requests. Touches no dependencies."""
    return HealthResponse(status="ok", service=request.app.title, version=request.app.version)


async def _run_check(check: ReadinessCheck) -> CheckStatus:
    try:
        await asyncio.wait_for(
            run_in_threadpool(check.probe), timeout=READINESS_CHECK_TIMEOUT_SECONDS
        )
    except Exception as exc:
        # Details stay in server logs; the response only says which dependency failed.
        logger.warning(
            "readiness check failed",
            extra={"check": check.name, "error_type": type(exc).__name__},
        )
        return "unavailable"
    return "ok"


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    """Readiness: every dependency needed for normal operation is reachable."""
    checks: list[ReadinessCheck] = request.app.state.readiness_checks
    results = await asyncio.gather(*(_run_check(check) for check in checks))
    statuses = {check.name: result for check, result in zip(checks, results, strict=True)}
    all_ok = all(status == "ok" for status in statuses.values())
    if not all_ok:
        response.status_code = 503
    return ReadinessResponse(status="ready" if all_ok else "not_ready", checks=statuses)

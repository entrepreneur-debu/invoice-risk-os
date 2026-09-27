"""Consistent, safe error responses.

All errors share the shape `{"error": {"code", "message", ...}}`. Unhandled exceptions
are logged server-side with the request ID; the client only receives a generic message
and the request ID, never a stack trace or exception text.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_body(code: str, message: str, request_id: str | None, **extra: Any) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, **extra}
    if request_id:
        error["request_id"] = request_id
    return {"error": error}


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(f"http_{exc.status_code}", message, _request_id(request)),
        headers=exc.headers,
    )


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Echo field locations and messages only, never the submitted input values.
    details = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error", "Request validation failed", _request_id(request), details=details
        ),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled exception",
        exc_info=exc,
        extra={"request_id": _request_id(request), "path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Internal server error", _request_id(request)),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

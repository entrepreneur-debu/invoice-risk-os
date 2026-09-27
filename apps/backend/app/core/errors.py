"""Consistent, safe error responses.

All errors share the shape `{"error": {"code", "message", "request_id", ...}}`.
Services raise `AppError` subclasses with stable machine-readable codes; route
handlers never build error responses by hand. Unhandled exceptions are logged
server-side; the client only receives a generic message and the request ID.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Request could not be processed"

    def __init__(
        self, message: str | None = None, *, code: str | None = None, **details: Any
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Authentication required"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to perform this action"


class NotFound(AppError):
    """Also used for other tenants' resources, so existence is never revealed."""

    status_code = 404
    code = "not_found"
    message = "Resource not found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state"


class InvalidInput(AppError):
    status_code = 422
    code = "invalid_input"
    message = "Invalid input"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Try again later."


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "A required service is temporarily unavailable"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_body(code: str, message: str, request_id: str | None, **extra: Any) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, **extra}
    if request_id:
        error["request_id"] = request_id
    return {"error": error}


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101
    headers = (
        {"Retry-After": str(exc.details.pop("retry_after"))}
        if ("retry_after" in exc.details)
        else None
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, _request_id(request), **exc.details),
        headers=headers,
    )


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
        extra={"path": request.url.path, "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "Internal server error", _request_id(request)),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

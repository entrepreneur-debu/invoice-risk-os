"""Pure ASGI middleware: request context, request logging, body size limits, headers."""

import json
import logging
import re
import time
import uuid
from collections.abc import Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import (
    organization_id_var,
    request_id_var,
    trace_from_header,
    trace_var,
    user_id_var,
)

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Applied to every API response. The API only serves JSON and stored documents.
_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-origin"),
)
_DEFAULT_FRAME_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
)


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope["headers"]:
        if key == name:
            return str(value.decode("latin-1"))
    return ""


class RequestContextMiddleware:
    """Assigns a request ID, sets logging context, adds security headers, logs requests.

    Only method, path, status and duration are logged: never headers, query strings
    or bodies, which may carry credentials or customer data.
    """

    def __init__(self, app: ASGIApp, google_cloud_project: str | None = None) -> None:
        self.app = app
        self.google_cloud_project = google_cloud_project

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, REQUEST_ID_HEADER.encode())
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        tokens = (
            request_id_var.set(request_id),
            trace_var.set(
                trace_from_header(
                    _header(scope, b"x-cloud-trace-context"), self.google_cloud_project
                )
            ),
            organization_id_var.set(None),
            user_id_var.set(None),
        )

        status_code = 500
        started = time.perf_counter()

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                present = {key.lower() for key, _ in headers}
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                for key, value in _SECURITY_HEADERS:
                    if key not in present:
                        headers.append((key, value))
                # Document endpoints set their own framing policy for the review viewer.
                for key, value in _DEFAULT_FRAME_HEADERS:
                    if key not in present:
                        headers.append((key, value))
                if b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            logger.info(
                "request completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(tokens[0])
            trace_var.reset(tokens[1])
            organization_id_var.reset(tokens[2])
            user_id_var.reset(tokens[3])


class RequestBodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Rejects request bodies larger than the applicable limit with 413.

    `path_limits` maps full-match path regexes to higher limits (upload endpoints only). Checks the
    declared Content-Length up front and also counts streamed bytes, so chunked
    requests without a Content-Length cannot bypass the limit.
    """

    def __init__(
        self, app: ASGIApp, max_bytes: int, path_limits: Mapping[str, int] | None = None
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_limits = [(re.compile(p), limit) for p, limit in (path_limits or {}).items()]

    def _limit_for(self, path: str) -> int:
        for pattern, limit in self.path_limits:
            if pattern.fullmatch(path):
                return limit
        return self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope["path"])
        declared = _header(scope, b"content-length")
        if declared.isdigit() and int(declared) > limit:
            await self._reject(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            if not response_started:
                await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {"error": {"code": "request_too_large", "message": "Request body too large"}}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

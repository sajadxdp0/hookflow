"""HTTP middleware: body limits, correlation, security headers and access logs."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.responses import JSONResponse

logger = logging.getLogger("hookflow")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


class RequestBodyTooLarge(Exception):
    """Raised while streaming a request body beyond the configured limit."""


class BodyLimitMiddleware:
    """Bound request buffering before FastAPI parses JSON or resolves auth."""

    def __init__(self, app: Callable, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope["headers"]:
            if name.lower() != b"content-length":
                continue
            try:
                declared = int(value)
            except ValueError:
                continue
            if declared > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._reject(scope, receive, send)

    async def _reject(self, scope, receive, send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "request body exceeds the configured limit"},
        )
        await response(scope, receive, send)


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach a bounded request ID for log correlation."""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex[:16]
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id})
        raise
    latency_ms = int((time.monotonic() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/v1/", "/ready")):
        response.headers["Cache-Control"] = "no-store"
    logger.info(
        "%s %r -> %s (%sms)",
        request.method,
        request.url.path,
        getattr(response, "status_code", "?"),
        latency_ms,
        extra={"request_id": request_id},
    )
    return response

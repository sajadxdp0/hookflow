"""HTTP middleware: request correlation and access logging."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response

logger = logging.getLogger("hookflow")


async def request_id_middleware(request: Request, call_next) -> Response:
    """Attach a request ID for log correlation, honoring an incoming one."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id})
        raise
    latency_ms = int((time.monotonic() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s -> %s (%sms)",
        request.method,
        request.url.path,
        getattr(response, "status_code", "?"),
        latency_ms,
        extra={"request_id": request_id},
    )
    return response

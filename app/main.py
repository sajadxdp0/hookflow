"""HookFlow API entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__, state
from .admin import build_admin_router
from .config import Settings, get_settings
from .events import build_events_router
from .health import build_health_router
from .middleware import BodyLimitMiddleware, logger, request_id_middleware  # noqa: F401
from .state import bump as _bump  # noqa: F401
from .state import get_db, get_settings_dep, init_state, to_delivery_out  # noqa: F401

_REBOUND_STATE = ("engine", "SessionLocal", "rate_limiter", "delivery_queue", "_counters")


def __getattr__(name: str):
    if name in _REBOUND_STATE:
        return getattr(state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    if state.engine is not None:
        state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Configure process state and assemble the FastAPI application."""
    resolved = settings or get_settings()
    init_state(resolved)
    app = FastAPI(
        title="HookFlow",
        version=__version__,
        summary="Reliable webhook and event delivery infrastructure",
        description=(
            "Persist-first event ingest, signed at-least-once delivery, "
            "exponential backoff, tenant isolation, and dead-letter replay."
        ),
        lifespan=_lifespan,
        openapi_tags=[
            {"name": "endpoints and events", "description": "Tenant-facing delivery API"},
            {"name": "admin", "description": "Tenant and API-key provisioning"},
            {"name": "operations", "description": "Health, readiness, and metrics"},
        ],
    )
    app.add_middleware(BodyLimitMiddleware, max_body_bytes=resolved.max_body_bytes)
    app.middleware("http")(request_id_middleware)
    app.include_router(build_health_router())
    app.include_router(build_events_router())
    app.include_router(build_admin_router(get_db))

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "hookflow", "version": __version__, "docs": "/docs"}

    return app


app = create_app()

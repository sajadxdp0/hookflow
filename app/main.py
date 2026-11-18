"""HookFlow API entry point: app assembly and thin compatibility re-exports."""

from __future__ import annotations

from fastapi import FastAPI

from . import state
from .admin import build_admin_router
from .config import Settings, get_settings
from .events import build_events_router
from .health import build_health_router
from .middleware import logger, request_id_middleware  # noqa: F401  (re-export)
from .state import bump as _bump  # noqa: F401  (re-export)
from .state import get_db, get_settings_dep, init_state, to_delivery_out  # noqa: F401  (re-export)

# These names are rebound by init_state(), so resolve them from the state module
# on every access instead of binding a stale value at import time.
_REBOUND_STATE = ("engine", "SessionLocal", "rate_limiter", "delivery_queue", "_counters")


def __getattr__(name: str):
    if name in _REBOUND_STATE:
        return getattr(state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Configure process state and assemble the FastAPI application."""
    init_state(settings or get_settings())
    app = FastAPI(title="HookFlow", version="0.2.0")
    app.middleware("http")(request_id_middleware)
    app.include_router(build_health_router())
    app.include_router(build_events_router())
    app.include_router(build_admin_router(get_db))
    return app


app = create_app()

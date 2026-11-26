"""Operational routes: liveness, readiness and Prometheus metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import __version__, state
from .config import get_settings
from .crypto import get_secret_box
from .db import Endpoint
from .state import (
    DELIVERIES_REQUEUED,
    EVENTS_DEDUPLICATED,
    EVENTS_INGESTED,
    get_db,
)


def _render_metrics() -> str:
    lines = [
        "# HELP hookflow_events_ingested_total Accepted events (excluding dedupes).",
        "# TYPE hookflow_events_ingested_total counter",
        f"hookflow_events_ingested_total {state._counters.get(EVENTS_INGESTED, 0)}",
        "# HELP hookflow_events_deduplicated_total Idempotent replays returned without insert.",
        "# TYPE hookflow_events_deduplicated_total counter",
        f"hookflow_events_deduplicated_total {state._counters.get(EVENTS_DEDUPLICATED, 0)}",
        "# HELP hookflow_deliveries_requeued_total DLQ/manual replays.",
        "# TYPE hookflow_deliveries_requeued_total counter",
        f"hookflow_deliveries_requeued_total {state._counters.get(DELIVERIES_REQUEUED, 0)}",
        '# HELP hookflow_build_info Build information.',
        "# TYPE hookflow_build_info gauge",
        f'hookflow_build_info{{version="{__version__}"}} 1',
    ]
    return "\n".join(lines) + "\n"


def build_health_router() -> APIRouter:
    router = APIRouter(tags=["operations"])

    @router.get("/health")
    def health():
        return {"status": "ok", "service": "hookflow", "version": __version__}

    @router.get("/metrics")
    def metrics():
        return Response(
            content=_render_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @router.get("/ready")
    def ready(db: Session = Depends(get_db)):
        checks: dict[str, str] = {}
        try:
            db.query(Endpoint.id).limit(1).all()
            checks["database"] = "ok"
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "database schema is not present or unreachable; "
                    "run `alembic upgrade head` before starting the app"
                ),
            ) from exc

        settings = get_settings()
        queue = state.delivery_queue
        if queue.has_redis:
            try:
                queue.ping()
                checks["redis"] = "ok"
            except Exception as exc:
                raise HTTPException(status_code=503, detail="redis unreachable") from exc
        else:
            checks["redis"] = "not-configured"

        try:
            box = get_secret_box(settings.secret_encryption_key)
            checks["secret_encryption"] = (
                "development-key" if box.using_development_key else "ok"
            )
        except ValueError:
            checks["secret_encryption"] = "invalid-key"
        if settings.environment == "production":
            if db.get_bind().dialect.name != "postgresql":
                checks["database"] = "postgresql-required"
            if checks["secret_encryption"] != "ok":
                checks["secret_encryption"] = "production-key-required"
            if len(settings.admin_token) < 32:
                checks["admin_token"] = "32-characters-minimum"
            if not settings.redis_url:
                checks["redis"] = "required-in-production"
        if settings.environment == "production" and any(
            value != "ok" for value in checks.values()
        ):
            raise HTTPException(
                status_code=503,
                detail={"status": "not-ready", "checks": checks},
            )
        return {"status": "ok", **checks}

    return router

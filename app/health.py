"""Operational routes: liveness, readiness and Prometheus metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from . import state
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
    """Render the in-process counters in Prometheus text exposition format."""
    lines = [
        "# HELP hookflow_events_ingested_total Accepted events (excluding dedupes).",
        "# TYPE hookflow_events_ingested_total counter",
        f"hookflow_events_ingested_total {state._counters.get(EVENTS_INGESTED, 0)}",
        "# HELP hookflow_events_deduplicated_total Idempotent replays returned without insert.",
        "# TYPE hookflow_events_deduplicated_total counter",
        f"hookflow_events_deduplicated_total {state._counters.get(EVENTS_DEDUPLICATED, 0)}",
        "# HELP hookflow_deliveries_requeued_total DLQ/manual requeues via replay endpoint.",
        "# TYPE hookflow_deliveries_requeued_total counter",
        f"hookflow_deliveries_requeued_total {state._counters.get(DELIVERIES_REQUEUED, 0)}",
    ]
    return "\n".join(lines) + "\n"


def build_health_router() -> APIRouter:
    """Build the unauthenticated operational-probe router."""
    router = APIRouter()

    @router.get("/health")
    def health():
        return {"status": "ok", "service": "hookflow"}

    @router.get("/metrics")
    def metrics():
        """Prometheus-text metrics. No dependency; scrape-ready exposition format."""
        return Response(content=_render_metrics(), media_type="text/plain")

    @router.get("/ready")
    def ready(db: Session = Depends(get_db)):
        checks: dict[str, str] = {}
        try:
            db.query(Endpoint.id).limit(1).all()
            checks["database"] = "ok"
        except OperationalError as exc:
            # Almost always "relation does not exist": migrations were never
            # applied. Say so plainly rather than returning a bare 500.
            raise HTTPException(
                status_code=503,
                detail=(
                    "database schema is not present or unreachable; "
                    "run `alembic upgrade head` before starting the app"
                ),
            ) from exc

        queue = state.delivery_queue
        if queue.has_redis:
            try:
                queue._redis.ping()  # type: ignore[union-attr]
                checks["redis"] = "ok"
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"redis unreachable: {exc}")
        else:
            checks["redis"] = "not-configured"

        # A development key is a deploy mistake, and /ready is what operators watch.
        box = get_secret_box(get_settings().secret_encryption_key)
        checks["secret_encryption"] = "development-key" if box.using_development_key else "ok"
        return {"status": "ok", **checks}

    return router

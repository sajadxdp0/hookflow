"""Process-wide application state and shared request helpers.

The engine, session factory, queue and limiter are rebuilt by :func:`init_state`
whenever the app is configured (once at import, and again in tests). Keeping them
here gives every router one authoritative place to read the current instances;
:mod:`app.main` re-exports them for callers that import from the entry point.
"""

from threading import Lock

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings, get_settings, set_settings
from .db import Delivery, as_utc_iso, make_engine
from .queue import DeliveryQueue
from .ratelimit import RateLimiter
from .schemas import DeliveryOut

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None
rate_limiter = RateLimiter()
delivery_queue = DeliveryQueue()

_counters_lock = Lock()

# In-process counters exposed as Prometheus text at /metrics. No dependency on
# prometheus_client, so the dependency set stays small.
_counters: dict[str, int] = {
    "events_ingested_total": 0,
    "events_deduplicated_total": 0,
    "deliveries_requeued_total": 0,
}

EVENTS_INGESTED = "events_ingested_total"
EVENTS_DEDUPLICATED = "events_deduplicated_total"
DELIVERIES_REQUEUED = "deliveries_requeued_total"


def bump(counter: str) -> None:
    """Increment a named metric counter atomically."""
    with _counters_lock:
        _counters[counter] = _counters.get(counter, 0) + 1


def get_settings_dep() -> Settings:
    """FastAPI-friendly wrapper around :func:`app.config.get_settings`."""
    return get_settings()


def init_state(settings: Settings | None = None) -> None:
    """Bind the engine and helpers to ``settings``.

    Settings are pinned process-wide so routers resolving configuration through
    ``get_settings()`` stay in agreement with the engine. Schema creation is a
    deployment step (``alembic upgrade head``), never a side effect of boot.
    """
    global engine, SessionLocal, rate_limiter, delivery_queue
    settings = settings or get_settings()
    set_settings(settings)
    engine = make_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # Rebind helpers to the current settings (tests override redis_url="").
    rate_limiter = RateLimiter(settings.redis_url)
    delivery_queue = DeliveryQueue(settings.redis_url)


def get_db():
    """Yield a session scoped to one request and always close it."""
    assert SessionLocal is not None, "call init_state() first"
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def to_delivery_out(delivery: Delivery) -> DeliveryOut:
    """Serialize a Delivery row into its API representation."""
    return DeliveryOut(
        id=delivery.id,
        event_id=delivery.event_id,
        endpoint_id=delivery.endpoint_id,
        status=delivery.status,
        attempts=delivery.attempts,
        next_attempt_at=(
            as_utc_iso(delivery.next_attempt_at) if delivery.next_attempt_at else None
        ),
        last_status_code=delivery.last_status_code,
        last_error=delivery.last_error,
        latency_ms=delivery.latency_ms,
    )

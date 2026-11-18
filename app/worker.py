"""Delivery worker: sign, POST with timeout, retry with backoff, or DLQ."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from .config import Settings
from .constants import RETRYABLE_STATUSES, STATUS_DLQ, STATUS_RETRYING, STATUS_SUCCESS
from .crypto import get_secret_box
from .db import Delivery, Endpoint, utcnow
from .queue import DeliveryQueue
from .ratelimit import RateLimiter
from .security import SIGNATURE_HEADER, sign_payload


def backoff_delay_seconds(attempt: int, schedule: list[int]) -> int:
    """Delay after a failed attempt (1-indexed). Past the schedule, repeat last."""
    if attempt < 1:
        return schedule[0]
    if attempt <= len(schedule):
        return schedule[attempt - 1]
    return schedule[-1]


def _due_conditions(now: datetime, lease_seconds: float | None):
    """SQL conditions selecting deliveries ready for an attempt.

    ``lease_seconds`` is ``None`` for the unclaimed single-worker path; when set,
    rows held by another worker with a live lease are excluded.
    """
    conditions = [
        Delivery.status.in_(RETRYABLE_STATUSES),
        (Delivery.next_attempt_at.is_(None)) | (Delivery.next_attempt_at <= now),
    ]
    if lease_seconds is not None:
        stale_before = now - timedelta(seconds=lease_seconds)
        conditions.append(
            (Delivery.claim_token.is_(None)) | (Delivery.claimed_at < stale_before)
        )
    return conditions


def deliver_once(
    body: bytes,
    url: str,
    secret: str,
    timeout_seconds: float,
    client: httpx.Client | None = None,
) -> tuple[int | None, str | None, int]:
    """POST the payload once. Returns (status_code, error, latency_ms)."""
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(secret, body),
        "User-Agent": "hookflow/0.1.0",
    }
    start = time.monotonic()
    try:
        if client is not None:
            status = client.post(url, content=body, headers=headers).status_code
        else:
            with httpx.Client(timeout=timeout_seconds) as http:
                status = http.post(url, content=body, headers=headers).status_code
        latency_ms = int((time.monotonic() - start) * 1000)
        if 200 <= status < 300:
            return status, None, latency_ms
        return status, f"unexpected status {status}", latency_ms
    except Exception as exc:  # timeouts, DNS, connection errors -> retryable
        latency_ms = int((time.monotonic() - start) * 1000)
        return None, f"{type(exc).__name__}: {exc}", latency_ms


def _plan_outcome(delivery: Delivery, settings: Settings) -> None:
    """Set the delivery's next state after an attempt has been recorded."""
    if delivery.last_error is None:
        delivery.status = STATUS_SUCCESS
        delivery.next_attempt_at = None
    elif delivery.attempts >= settings.max_attempts:
        delivery.status = STATUS_DLQ
        delivery.next_attempt_at = None
    else:
        delivery.status = STATUS_RETRYING
        delay = backoff_delay_seconds(delivery.attempts, settings.backoff_schedule_seconds)
        delivery.next_attempt_at = utcnow() + timedelta(seconds=delay)


def settle_delivery(
    session: Session,
    settings: Settings,
    delivery: Delivery,
    endpoint: Endpoint,
    body: bytes,
    client: httpx.Client | None = None,
) -> Delivery:
    """Attempt one delivery and persist its outcome, retry or dead-letter."""
    delivery.attempts += 1
    # The stored secret is ciphertext; decrypt only here, at the moment it is
    # needed for signing, and never write it back or log it.
    plaintext_secret = get_secret_box(settings.secret_encryption_key).decrypt(endpoint.secret)
    status_code, error, latency_ms = deliver_once(
        body, endpoint.url, plaintext_secret, settings.delivery_timeout_seconds, client
    )
    delivery.last_status_code = status_code
    delivery.last_error = error
    delivery.latency_ms = latency_ms
    _plan_outcome(delivery, settings)
    delivery.updated_at = utcnow()
    session.add(delivery)
    session.commit()
    return delivery


def fetch_due_deliveries(session: Session, limit: int = 20) -> list[Delivery]:
    """Return due rows for the single-worker path (no claim bookkeeping)."""
    return (
        session.query(Delivery)
        .filter(*_due_conditions(utcnow(), None))
        .order_by(Delivery.created_at)
        .limit(limit)
        .all()
    )


def claim_due_deliveries(
    session: Session,
    token: str,
    limit: int = 20,
    lease_seconds: float = 60.0,
) -> list[Delivery]:
    """Atomically take ownership of up to ``limit`` due deliveries.

    Ownership is a single UPDATE whose subquery excludes rows with a live lease:
    the database serialises racing workers, and the loser simply finds fewer
    candidates. On PostgreSQL the subquery uses FOR UPDATE SKIP LOCKED so workers
    do not queue behind one another; SQLite serialises writers instead.
    """
    now = utcnow()
    due = (
        session.query(Delivery.id)
        .filter(*_due_conditions(now, lease_seconds))
        .order_by(Delivery.created_at)
        .limit(limit)
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        due = due.with_for_update(skip_locked=True)

    session.query(Delivery).filter(Delivery.id.in_(due)).update(
        {Delivery.claim_token: token, Delivery.claimed_at: now},
        synchronize_session=False,
    )
    session.commit()

    return (
        session.query(Delivery)
        .filter(Delivery.claim_token == token)
        .order_by(Delivery.created_at)
        .all()
    )


def release_claim(session: Session, delivery: Delivery) -> None:
    """Drop the lease so the row is immediately claimable again."""
    delivery.claim_token = None
    delivery.claimed_at = None
    session.add(delivery)


def _release_claim_if_needed(
    session: Session, delivery: Delivery, exclusive: bool
) -> None:
    """Release a lease when processing under a claim token."""
    if exclusive:
        release_claim(session, delivery)


def release_expired_claims(session: Session, lease_seconds: float = 60.0) -> int:
    """Free rows held by a worker that died mid-delivery. Returns rows freed."""
    stale_before = utcnow() - timedelta(seconds=lease_seconds)
    freed = (
        session.query(Delivery)
        .filter(Delivery.claim_token.isnot(None))
        .filter(Delivery.claimed_at < stale_before)
        .update(
            {Delivery.claim_token: None, Delivery.claimed_at: None},
            synchronize_session=False,
        )
    )
    session.commit()
    return freed


def process_due_deliveries(
    session: Session,
    settings: Settings,
    rate_limiter: RateLimiter,
    client: httpx.Client | None = None,
    limit: int = 20,
    claim_token: str | None = None,
) -> dict[str, int]:
    """Run one worker pass, returning counts by outcome.

    Pass ``claim_token`` to claim the batch exclusively; omit it for the
    single-worker case, where claiming would be pure overhead. Rate-limited
    endpoints are skipped and their leases released.
    """
    stats = {"success": 0, "retrying": 0, "dlq": 0, "rate_limited": 0}
    token = claim_token or uuid.uuid4().hex
    exclusive = claim_token is not None
    lease_seconds = settings.claim_lease_seconds

    if exclusive:
        release_expired_claims(session, lease_seconds)
        batch = claim_due_deliveries(session, token, limit, lease_seconds)
    else:
        batch = fetch_due_deliveries(session, limit)

    for delivery in batch:
        endpoint = session.get(Endpoint, delivery.endpoint_id)
        if endpoint is None:
            delivery.status = STATUS_DLQ
            delivery.last_error = "endpoint deleted"
            _release_claim_if_needed(session, delivery, exclusive)
            session.add(delivery)
            session.commit()
            stats["dlq"] += 1
            continue
        if not rate_limiter.allow(endpoint.id, endpoint.rate_limit_per_minute):
            # Leave the row queued for the next pass, but free the lease: a full
            # rate-limit window must not stall the delivery.
            _release_claim_if_needed(session, delivery, exclusive)
            if exclusive:
                session.commit()
            stats["rate_limited"] += 1
            continue
        event_body = delivery.event.payload.encode() if delivery.event else b"{}"
        _release_claim_if_needed(session, delivery, exclusive)
        settled = settle_delivery(session, settings, delivery, endpoint, event_body, client)
        stats[settled.status if settled.status in stats else "retrying"] += 1
    return stats


def run_worker_forever(
    session_factory: Callable[[], Session], settings: Settings, poll_seconds: float = 2.0
) -> None:
    """Long-running worker loop (used by ``python -m app.worker``).

    Each batch is claimed under a fresh token, so several workers against one
    database never hold the same delivery at once.
    """
    rate_limiter = RateLimiter(settings.redis_url)
    queue = DeliveryQueue(settings.redis_url)
    while True:
        session = session_factory()
        try:
            process_due_deliveries(
                session,
                settings,
                rate_limiter,
                claim_token=uuid.uuid4().hex,
            )
        finally:
            session.close()
        # Redis only shortens the wait: drain any wake-ups, then sleep.
        while queue.dequeue(timeout=0):
            pass
        time.sleep(poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    from .config import get_settings
    from .db import make_engine, make_session_factory

    _settings = get_settings()
    _engine = make_engine(_settings.database_url)
    run_worker_forever(make_session_factory(_engine), _settings)

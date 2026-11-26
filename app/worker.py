"""Lease-fenced worker: sign, POST with timeout, retry, or dead-letter."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from redis import RedisError
from sqlalchemy.orm import Session

from . import __version__
from .config import Settings
from .constants import RETRYABLE_STATUSES, STATUS_DLQ, STATUS_RETRYING, STATUS_SUCCESS
from .crypto import get_secret_box
from .db import Delivery, Endpoint, utcnow
from .egress import prepare_outbound_request, validate_endpoint_url
from .queue import DeliveryQueue
from .ratelimit import RateLimiter
from .security import SIGNATURE_HEADER, sign_payload

logger = logging.getLogger("hookflow.worker")
_RETRYABLE_CLIENT_STATUSES = frozenset({408, 409, 425, 429})


class ClaimLostError(RuntimeError):
    """The delivery lease moved to another worker before settlement."""


def backoff_delay_seconds(attempt: int, schedule: list[int]) -> int:
    """Delay after a failed 1-indexed attempt; saturate at the final entry."""
    if attempt < 1:
        return schedule[0]
    if attempt <= len(schedule):
        return schedule[attempt - 1]
    return schedule[-1]


def _due_conditions(now: datetime, lease_seconds: float | None):
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
    *,
    event_id: str = "",
    delivery_id: str = "",
    attempt: int = 0,
) -> tuple[int | None, str | None, int]:
    """POST once. A supplied client is a trusted transport used by tests.

    Production calls omit it, resolve the destination under the egress policy,
    pin the validated IP, disable environment proxies, and refuse redirects.
    """
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(secret, body),
        "User-Agent": f"hookflow/{__version__}",
        "X-Hookflow-Timestamp": datetime.now(UTC).isoformat(),
    }
    if event_id:
        headers["X-Hookflow-Event-Id"] = event_id
    if delivery_id:
        headers["X-Hookflow-Delivery-Id"] = delivery_id
    if attempt:
        headers["X-Hookflow-Attempt"] = str(attempt)

    start = time.monotonic()
    try:
        if client is not None:
            validate_endpoint_url(url)
            with client.stream("POST", url, content=body, headers=headers) as response:
                status_code = response.status_code
        else:
            outbound = prepare_outbound_request(url)
            headers.update(outbound.headers)
            with httpx.Client(
                timeout=timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as http:
                with http.stream(
                    "POST",
                    outbound.url,
                    content=body,
                    headers=headers,
                    extensions=outbound.extensions,
                ) as response:
                    status_code = response.status_code
        latency_ms = int((time.monotonic() - start) * 1000)
        if 200 <= status_code < 300:
            return status_code, None, latency_ms
        return status_code, f"unexpected status {status_code}", latency_ms
    except Exception as exc:  # transport, DNS, TLS and policy failures are retryable
        latency_ms = int((time.monotonic() - start) * 1000)
        return None, f"{type(exc).__name__}: {exc}"[:2000], latency_ms


def fetch_due_deliveries(session: Session, limit: int = 20) -> list[Delivery]:
    """Return due rows for the single-worker path."""
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
    """Atomically claim up to ``limit`` due deliveries."""
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


def release_expired_claims(session: Session, lease_seconds: float = 60.0) -> int:
    """Free abandoned leases. Kept as an operational/test helper."""
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


def _claimed_update(
    session: Session,
    delivery_id: str,
    claim_token: str | None,
    values: dict,
) -> bool:
    query = session.query(Delivery).filter(Delivery.id == delivery_id)
    if claim_token is not None:
        query = query.filter(Delivery.claim_token == claim_token)
    changed = query.update(values, synchronize_session=False)
    session.commit()
    session.expire_all()
    return bool(changed)


def renew_claim(
    session: Session,
    delivery: Delivery,
    claim_token: str,
    lease_seconds: float,
) -> None:
    """Fence a serial batch: renew immediately before the network attempt."""
    if not _claimed_update(
        session,
        delivery.id,
        claim_token,
        {Delivery.claimed_at: utcnow()},
    ):
        raise ClaimLostError(delivery.id)


def settle_delivery(
    session: Session,
    settings: Settings,
    delivery: Delivery,
    endpoint: Endpoint,
    body: bytes,
    client: httpx.Client | None = None,
    claim_token: str | None = None,
) -> Delivery:
    """Attempt one delivery and settle only if this worker still owns it."""
    attempt = delivery.attempts + 1
    try:
        plaintext_secret = get_secret_box(settings.secret_encryption_key).decrypt(
            endpoint.secret
        )
        status_code, error, latency_ms = deliver_once(
            body,
            endpoint.url,
            plaintext_secret,
            settings.delivery_timeout_seconds,
            client,
            event_id=delivery.event_id,
            delivery_id=delivery.id,
            attempt=attempt,
        )
    except Exception as exc:  # decryption/configuration failures must not kill the worker
        status_code, error, latency_ms = None, f"{type(exc).__name__}: {exc}"[:2000], 0

    permanent_failure = (
        status_code is not None
        and 400 <= status_code < 500
        and status_code not in _RETRYABLE_CLIENT_STATUSES
    )
    if error is None:
        status = STATUS_SUCCESS
        next_attempt_at = None
    elif permanent_failure or attempt >= settings.max_attempts:
        status = STATUS_DLQ
        next_attempt_at = None
    else:
        status = STATUS_RETRYING
        delay = backoff_delay_seconds(attempt, settings.backoff_schedule_seconds)
        next_attempt_at = utcnow() + timedelta(seconds=delay)

    changed = _claimed_update(
        session,
        delivery.id,
        claim_token,
        {
            Delivery.status: status,
            Delivery.attempts: attempt,
            Delivery.next_attempt_at: next_attempt_at,
            Delivery.last_status_code: status_code,
            Delivery.last_error: error,
            Delivery.latency_ms: latency_ms,
            Delivery.claim_token: None,
            Delivery.claimed_at: None,
            Delivery.updated_at: utcnow(),
        },
    )
    if not changed:
        raise ClaimLostError(delivery.id)
    settled = session.get(Delivery, delivery.id)
    assert settled is not None
    return settled


def process_due_deliveries(
    session: Session,
    settings: Settings,
    rate_limiter: RateLimiter,
    client: httpx.Client | None = None,
    limit: int = 20,
    claim_token: str | None = None,
) -> dict[str, int]:
    """Run one worker pass with per-row lease renewal and fenced settlement."""
    stats = {
        "success": 0,
        "retrying": 0,
        "dlq": 0,
        "rate_limited": 0,
        "disabled": 0,
        "stale": 0,
    }
    exclusive = claim_token is not None
    lease_seconds = settings.claim_lease_seconds
    if exclusive:
        batch = claim_due_deliveries(session, claim_token, limit, lease_seconds)
    else:
        batch = fetch_due_deliveries(session, limit)

    for delivery in batch:
        endpoint = session.get(Endpoint, delivery.endpoint_id)
        if endpoint is None:
            if not _claimed_update(
                session,
                delivery.id,
                claim_token,
                {
                    Delivery.status: STATUS_DLQ,
                    Delivery.last_error: "endpoint deleted",
                    Delivery.next_attempt_at: None,
                    Delivery.claim_token: None,
                    Delivery.claimed_at: None,
                    Delivery.updated_at: utcnow(),
                },
            ):
                stats["stale"] += 1
                continue
            stats["dlq"] += 1
            continue
        if not endpoint.enabled:
            if not _claimed_update(
                session,
                delivery.id,
                claim_token,
                {
                    Delivery.next_attempt_at: utcnow() + timedelta(seconds=60),
                    Delivery.claim_token: None,
                    Delivery.claimed_at: None,
                    Delivery.updated_at: utcnow(),
                },
            ):
                stats["stale"] += 1
                continue
            stats["disabled"] += 1
            continue
        if not rate_limiter.allow(endpoint.id, endpoint.rate_limit_per_minute):
            if not _claimed_update(
                session,
                delivery.id,
                claim_token,
                {Delivery.claim_token: None, Delivery.claimed_at: None},
            ):
                stats["stale"] += 1
                continue
            stats["rate_limited"] += 1
            continue

        event_body = delivery.event.payload.encode() if delivery.event else b"{}"
        if exclusive:
            try:
                renew_claim(session, delivery, claim_token, lease_seconds)
            except ClaimLostError:
                stats["stale"] += 1
                continue
        try:
            settled = settle_delivery(
                session,
                settings,
                delivery,
                endpoint,
                event_body,
                client,
                claim_token=claim_token,
            )
        except ClaimLostError:
            stats["stale"] += 1
            continue
        stats[settled.status if settled.status in stats else "retrying"] += 1
    return stats


def run_worker_forever(
    session_factory: Callable[[], Session], settings: Settings, poll_seconds: float = 2.0
) -> None:
    """Poll forever; Redis only shortens the wait and can never stop recovery."""
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
        except Exception:
            logger.exception("worker_pass_failed; retrying after poll interval")
            session.rollback()
        finally:
            session.close()
        # A positive BRPOP timeout is essential: Redis timeout=0 blocks forever,
        # which previously prevented retries from ever becoming due.
        try:
            queue.dequeue(timeout=min(4, max(1, int(poll_seconds))))
        except RedisError:
            logger.warning("queue_unavailable; continuing database polling")
            time.sleep(poll_seconds)
        if not queue.has_redis:
            time.sleep(poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    from .config import get_settings
    from .db import make_engine, make_session_factory

    _settings = get_settings()
    _engine = make_engine(_settings.database_url)
    run_worker_forever(make_session_factory(_engine), _settings)

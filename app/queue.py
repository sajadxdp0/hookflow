"""Best-effort Redis wake-up queue; PostgreSQL polling is the source of truth."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from redis import RedisError

if TYPE_CHECKING:  # pragma: no cover
    import redis

logger = logging.getLogger("hookflow.queue")
QUEUE_KEY = "hookflow:deliveries"


class DeliveryQueue:
    """Redis-backed wake-up queue, or a safe no-op when unconfigured."""

    def __init__(self, redis_url: str = "") -> None:
        self._redis: redis.Redis | None = None
        if redis_url:
            import redis

            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=5.0,
                health_check_interval=30,
            )

    @property
    def has_redis(self) -> bool:
        return self._redis is not None

    def ping(self) -> bool:
        if self._redis is None:
            return True
        return bool(self._redis.ping())

    def enqueue(self, delivery_id: str) -> bool:
        """Publish a hint. Failure never invalidates committed database work."""
        if self._redis is None:
            return True
        try:
            self._redis.lpush(QUEUE_KEY, delivery_id)
            return True
        except RedisError:
            logger.warning("queue_publish_failed; database poller will recover")
            return False

    def dequeue(self, timeout: int = 5) -> str | None:
        """Wait at most ``timeout`` seconds; zero means nonblocking, never infinite.

        Redis errors propagate so the caller can apply its own poll backoff.
        """
        if self._redis is None:
            return None
        if timeout <= 0:
            return self._redis.rpop(QUEUE_KEY)
        item = self._redis.brpop(QUEUE_KEY, timeout=timeout)
        return item[1] if item else None

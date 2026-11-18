"""Fixed-window rate limiting. Redis when configured, in-process memory otherwise.

Memory fallback is single-replica only — documented in docs/architecture.md.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import used only for type checking
    import redis

REDIS_KEY_PREFIX = "hookflow:rl"


class MemoryRateLimiter:
    """Single-replica rate limiter backed by an in-memory timestamp log."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str, limit_per_minute: int, now: float | None = None) -> bool:
        """Record a hit and report whether it is within the 60-second window."""
        now = time.time() if now is None else now
        window_start = now - 60.0
        hits = [t for t in self._hits.get(key, []) if t > window_start]
        if len(hits) >= limit_per_minute:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


class RateLimiter:
    """Redis-backed limiter, falling back to :class:`MemoryRateLimiter`."""

    def __init__(self, redis_url: str = "") -> None:
        self._redis: redis.Redis | None = None
        self._memory = MemoryRateLimiter()
        if redis_url:
            import redis

            self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def allow(self, key: str, limit_per_minute: int) -> bool:
        """Consume one unit of ``key``'s per-minute budget, if available."""
        if self._redis is None:
            return self._memory.allow(key, limit_per_minute)
        window = int(time.time() // 60)
        redis_key = f"{REDIS_KEY_PREFIX}:{key}:{window}"
        count = self._redis.incr(redis_key)
        if count == 1:
            self._redis.expire(redis_key, 65)
        return count <= limit_per_minute

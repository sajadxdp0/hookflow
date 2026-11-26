"""Fixed-window rate limiting with Redis coordination and bounded fallback."""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import TYPE_CHECKING

from redis import RedisError

if TYPE_CHECKING:  # pragma: no cover
    import redis

logger = logging.getLogger("hookflow.ratelimit")
REDIS_KEY_PREFIX = "hookflow:rl"
_ALLOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return count
"""


class MemoryRateLimiter:
    """Single-replica limiter with periodic eviction of idle keys."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._next_prune = 0.0
        self._lock = Lock()

    def allow(self, key: str, limit_per_minute: int, now: float | None = None) -> bool:
        with self._lock:
            now = time.time() if now is None else now
            window_start = now - 60.0
            if now >= self._next_prune:
                self._hits = {
                    item: hits
                    for item, hits in self._hits.items()
                    if hits and hits[-1] > window_start
                }
                self._next_prune = now + 60.0
            hits = [hit for hit in self._hits.get(key, []) if hit > window_start]
            if limit_per_minute < 1 or len(hits) >= limit_per_minute:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


class RateLimiter:
    """Redis-backed limiter with a per-process fallback during Redis outages."""

    def __init__(self, redis_url: str = "") -> None:
        self._redis: redis.Redis | None = None
        self._memory = MemoryRateLimiter()
        if redis_url:
            import redis

            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                health_check_interval=30,
            )

    def allow(self, key: str, limit_per_minute: int) -> bool:
        if self._redis is None:
            return self._memory.allow(key, limit_per_minute)
        window = int(time.time() // 60)
        redis_key = f"{REDIS_KEY_PREFIX}:{key}:{window}"
        try:
            count = self._redis.eval(_ALLOW_SCRIPT, 1, redis_key, limit_per_minute, 65)
            return int(count) <= limit_per_minute
        except RedisError:
            logger.warning("rate_limit_fallback; using process-local budget")
            return self._memory.allow(key, limit_per_minute)

"""Fixed-window rate limiting. Redis in deployed environments, in-memory for tests."""

import threading
import time
from dataclasses import dataclass
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult: ...

    def reset(self, key: str) -> None: ...


class RedisRateLimiter:
    """INCR + EXPIRE per window. Fails open on Redis errors: availability of login must
    not depend on Redis, and the per-account lockout in the database still applies."""

    def __init__(self, client: Redis, prefix: str = "ratelimit:") -> None:
        self._client = client
        self._prefix = prefix

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        window = int(time.time() // window_seconds)
        redis_key = f"{self._prefix}{key}:{window}"
        try:
            pipe = self._client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds)
            count = int(pipe.execute()[0])
        except RedisError:
            return RateLimitResult(True, 0)
        retry_after = window_seconds - int(time.time() % window_seconds)
        return RateLimitResult(count <= limit, retry_after if count > limit else 0)

    def reset(self, key: str) -> None:
        try:
            for redis_key in self._client.scan_iter(f"{self._prefix}{key}:*"):
                self._client.delete(redis_key)
        except RedisError:
            return


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        window_key = f"{key}:{int(time.time() // window_seconds)}"
        with self._lock:
            self._counts[window_key] = self._counts.get(window_key, 0) + 1
            count = self._counts[window_key]
        return RateLimitResult(count <= limit, window_seconds if count > limit else 0)

    def reset(self, key: str) -> None:
        with self._lock:
            for window_key in [k for k in self._counts if k.startswith(f"{key}:")]:
                del self._counts[window_key]

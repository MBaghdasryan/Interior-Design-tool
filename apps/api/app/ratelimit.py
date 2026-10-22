"""Fixed-window rate limiting. In-memory per process by default; Redis (shared across
API replicas and workers) when REDIS_URL is set. Exceeding a limit → 429 `rate_limited`
with a `Retry-After` header."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import Request

from .config import get_settings
from .errors import ApiError


class MemoryBackend:
    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window_s: int) -> tuple[int, float]:
        now = time.time()
        with self._lock:
            n, start = self._hits.get(key, (0, now))
            if now - start >= window_s:
                n, start = 0, now
            n += 1
            self._hits[key] = (n, start)
            if len(self._hits) > 50_000:  # bound memory: drop expired windows
                self._hits = {k: v for k, v in self._hits.items() if now - v[1] < 3600}
            return n, start + window_s - now

    def peek(self, key: str, window_s: int) -> tuple[int, float]:
        now = time.time()
        with self._lock:
            n, start = self._hits.get(key, (0, now))
            return (0, 0.0) if now - start >= window_s else (n, start + window_s - now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisBackend:
    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url)

    def hit(self, key: str, window_s: int) -> tuple[int, float]:
        k = f"rl:{key}"
        pipe = self.r.pipeline()
        pipe.incr(k)
        pipe.expire(k, window_s, nx=True)
        pipe.ttl(k)
        n, _, ttl = pipe.execute()
        return int(n), float(max(ttl, 0))

    def peek(self, key: str, window_s: int) -> tuple[int, float]:
        k = f"rl:{key}"
        n, ttl = self.r.get(k), self.r.ttl(k)
        return int(n or 0), float(max(ttl, 0))

    def reset(self) -> None:
        for k in self.r.scan_iter("rl:*"):
            self.r.delete(k)


_backend: MemoryBackend | RedisBackend | None = None


def backend() -> MemoryBackend | RedisBackend:
    global _backend
    if _backend is None:
        url = get_settings().redis_url
        _backend = RedisBackend(url) if url else MemoryBackend()
    return _backend


def client_ip(request: Request) -> str:
    # behind nginx the real client is the first X-Forwarded-For hop
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "unknown")


def check(key: str, limit: int, window_s: int) -> None:
    if not get_settings().rate_limit_enabled:
        return
    n, retry = backend().hit(key, window_s)
    if n > limit:
        raise ApiError(429, "rate_limited", retry_after=int(retry) + 1)


def failures_exceeded(key: str, limit: int, window_s: int) -> None:
    """Raise 429 when `key` already has `limit` recorded failures (does not count this attempt)."""
    if not get_settings().rate_limit_enabled:
        return
    n, retry = backend().peek(key, window_s)
    if n >= limit:
        raise ApiError(429, "rate_limited", retry_after=int(retry) + 1)


def record_failure(key: str, window_s: int) -> None:
    if get_settings().rate_limit_enabled:
        backend().hit(key, window_s)


def limit(scope: str, limit_n: int, window_s: int, key: Callable[[Request], str] | None = None):
    """FastAPI dependency: `Depends(limit("generate", 10, 3600))` — keyed by client IP unless `key` is given."""

    def dep(request: Request) -> None:
        check(f"{scope}:{key(request) if key else client_ip(request)}", limit_n, window_s)

    return dep

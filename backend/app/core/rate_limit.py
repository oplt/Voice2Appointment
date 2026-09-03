"""Distributed Redis rate limiter with trusted-proxy IP resolution (P3-06)."""

from __future__ import annotations

import ipaddress
import logging
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Process-local fallback used only when Redis is unavailable."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            # Evict empty/expired buckets to bound memory.
            stale = [k for k, bucket in self._hits.items() if not bucket or bucket[-1] < cutoff]
            for k in stale[:64]:
                self._hits.pop(k, None)
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


limiter = SlidingWindowRateLimiter()


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    raw = (settings.trusted_proxy_cidrs or "").strip()
    if not raw:
        return []
    nets: list[ipaddress._BaseNetwork] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid TRUSTED_PROXY_CIDRS entry")
    return nets


def _ip_in_trusted(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_proxy_networks())


def client_ip(request: Request) -> str:
    """Resolve client IP; honor X-Forwarded-For only from trusted proxies."""
    direct = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and direct and _ip_in_trusted(direct):
        # Right-most / first hop after trusted proxy: take left-most client.
        return forwarded.split(",")[0].strip() or direct or "unknown"
    if direct:
        return direct
    return "unknown"


def _redis_allow(key: str, *, limit: int, window_seconds: int) -> bool | None:
    """Return True/False from Redis, or None if Redis unavailable."""
    try:
        from app.core.cache import _redis

        client = _redis()
        if client is None:
            return None
        redis_key = f"rl:{key}"
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, max(1, int(window_seconds)))
        return int(count) <= limit
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis rate-limit unavailable: %s", type(exc).__name__)
        return None


def allow_request(key: str, *, limit: int, window_seconds: int) -> bool:
    redis_result = _redis_allow(key, limit=limit, window_seconds=window_seconds)
    if redis_result is not None:
        return redis_result
    # Fail-open locally when Redis is down so auth is not a total outage,
    # but still apply a process-local bound.
    return limiter.allow(key, limit=limit, window_seconds=window_seconds)


def rate_limit(*, limit: int, window_seconds: int, name: str):
    """FastAPI dependency factory for sensitive routes."""

    def _dep(request: Request) -> None:
        ip = client_ip(request)
        key = f"{name}:{ip}"
        if not allow_request(key, limit=limit, window_seconds=window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Too many requests. Try again later.",
                    "retryable": True,
                },
            )

    return _dep

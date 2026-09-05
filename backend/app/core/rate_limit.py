"""Distributed Redis rate limiter with trusted-proxy IP resolution (P3-06)."""

from __future__ import annotations

import hashlib
import hmac
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
        try:
            hops = [item.strip() for item in forwarded.split(",")] + [direct]
            if not all(hops):
                return direct
            parsed = [str(ipaddress.ip_address(item)) for item in hops]
        except ValueError:
            return direct
        # Work inward from the connected trusted edge. A client-injected left
        # prefix is ignored when nginx appends the actual client address.
        for hop in reversed(parsed):
            if not _ip_in_trusted(hop):
                return hop
        return direct
    if direct:
        return direct
    return "unknown"


_REDIS_WINDOW_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


def _redis_allow(key: str, *, limit: int, window_seconds: int) -> bool | None:
    """Return True/False from Redis, or None if Redis unavailable."""
    try:
        from app.core.cache import _redis

        client = _redis()
        if client is None:
            return None
        redis_key = f"rl:{key}"
        count, _ttl = client.eval(
            _REDIS_WINDOW_LUA, 1, redis_key, max(1, int(window_seconds))
        )
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


def _account_bucket(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip() or not settings.secret_key:
        return None
    normalized = value.strip().casefold().encode("utf-8")
    return hmac.new(
        settings.secret_key.encode("utf-8"), normalized, hashlib.sha256
    ).hexdigest()


def rate_limit(*, limit: int, window_seconds: int, name: str, account_field: str | None = None):
    """FastAPI dependency factory for sensitive routes."""

    async def _dep(request: Request) -> None:
        ip = client_ip(request)
        keys = [f"{name}:ip:{ip}"]
        if account_field:
            try:
                body = await request.json()
            except Exception:
                body = {}
            account = _account_bucket(body.get(account_field) if isinstance(body, dict) else None)
            if account:
                keys.append(f"{name}:account:{account}")
        if any(not allow_request(key, limit=limit, window_seconds=window_seconds) for key in keys):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Too many requests. Try again later.",
                    "retryable": True,
                },
            )

    return _dep

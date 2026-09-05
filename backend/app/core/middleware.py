"""ASGI middleware: security headers + double-submit CSRF."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

_CSRF_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/ws/",
    "/api/v1/telephony/twilio/",
)


def _is_csrf_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _CSRF_EXEMPT_PREFIXES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Realistic CSP for SPA + Google Calendar iframe embeds + API.
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' wss: https:; "
                "frame-src 'self' https://calendar.google.com https://*.google.com; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "frame-ancestors 'none'; "
                "object-src 'none'"
            ),
        )
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response


class ContentLengthLimitMiddleware(BaseHTTPMiddleware):
    """Reject known oversized direct requests before route/body parsing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw_length = request.headers.get("content-length")
        try:
            content_length = int(raw_length) if raw_length else 0
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        if content_length > settings.request_max_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF for cookie-authenticated SPA mutations."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in _SAFE_METHODS and not _is_csrf_exempt(request.url.path):
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if not cookie_token or not header_token:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF validation failed"},
                )
            try:
                valid = secrets.compare_digest(cookie_token, header_token)
            except (TypeError, ValueError):
                valid = False
            if not valid:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF validation failed"},
                )

        response = await call_next(request)

        # Ensure a CSRF cookie exists for subsequent mutating calls.
        # Do not overwrite a cookie the route already set (e.g. GET /auth/csrf).
        if CSRF_COOKIE_NAME not in request.cookies and not _response_sets_csrf(
            response
        ):
            token = secrets.token_urlsafe(32)
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=token,
                httponly=False,  # readable by SPA to echo as header
                secure=settings.cookie_secure,
                samesite=settings.cookie_samesite,
                max_age=60 * 60 * 24 * 7,
                path="/",
            )
        return response


def _response_sets_csrf(response: Response) -> bool:
    for key, value in response.raw_headers:
        if key.lower() == b"set-cookie" and value.startswith(
            CSRF_COOKIE_NAME.encode("ascii") + b"="
        ):
            return True
    return False


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request_id / operation and emit structured HTTP timing logs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import time

        from app.core.logging import (
            bind_log_context,
            log_event,
            new_request_id,
            reset_log_context,
        )

        request_id = request.headers.get("X-Request-ID") or new_request_id()
        operation = f"{request.method} {request.url.path}"
        tokens = bind_log_context(request_id=request_id, operation=operation)
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            if not request.url.path.startswith("/health"):
                log_event(
                    logging.getLogger("app.http"),
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    latency_ms=latency_ms,
                )
                try:
                    from app.core.metrics import metrics

                    class_bucket = f"{(status_code // 100)}xx"
                    metrics.incr("http_requests", labels={"status": class_bucket})
                    metrics.observe(
                        "http_latency_ms",
                        latency_ms,
                        labels={"status": class_bucket},
                    )
                except Exception:  # noqa: BLE001
                    pass
            reset_log_context(tokens)

"""Stable domain/provider errors safe for HTTP and voice (P3-05)."""

from __future__ import annotations

import logging
from typing import Any, NoReturn

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Internal error with a client-safe message and stable code."""

    code: str = "internal_error"
    message: str = "Something went wrong. Please try again."
    http_status: int = 500
    retryable: bool = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        http_status: int | None = None,
        retryable: bool | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.message = message or type(self).message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        if retryable is not None:
            self.retryable = retryable
        self.cause = cause
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    message = "Resource not found."
    http_status = 404


class ValidationAppError(AppError):
    code = "validation_error"
    message = "Invalid request."
    http_status = 422


class ConflictAppError(AppError):
    code = "conflict"
    message = "The requested change conflicts with existing data."
    http_status = 409


class AuthAppError(AppError):
    code = "auth_error"
    message = "Authentication failed."
    http_status = 401


class ProviderUnavailableError(AppError):
    code = "provider_unavailable"
    message = "An external service is temporarily unavailable."
    http_status = 502
    retryable = True


class ProviderAuthError(AppError):
    code = "provider_auth"
    message = "Calendar connection is missing or expired. Reconnect Google Calendar."
    http_status = 400


class RateLimitedError(AppError):
    code = "rate_limited"
    message = "Too many requests. Try again later."
    http_status = 429
    retryable = True


def _safe_client_detail(exc: AppError) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        "retryable": exc.retryable,
    }


def raise_http(exc: AppError) -> NoReturn:
    """Raise FastAPI HTTPException with a stable, non-leaky body."""
    if exc.cause is not None:
        logger.warning(
            "app_error code=%s status=%s cause=%s",
            exc.code,
            exc.http_status,
            type(exc.cause).__name__,
        )
    raise HTTPException(
        status_code=exc.http_status,
        detail=_safe_client_detail(exc),
    ) from exc.cause


def voice_error_payload(exc: BaseException) -> dict[str, Any]:
    """Map any failure to a voice-safe tool result (no vendor text)."""
    mapped = map_exception(exc)
    return {
        "success": False,
        "error": mapped.message,
        "code": mapped.code,
        "retryable": mapped.retryable,
    }


def map_exception(exc: BaseException) -> AppError:
    """Classify arbitrary exceptions into AppError without leaking details."""
    if isinstance(exc, AppError):
        return exc

    from app.appointments.policy import BookingConflictError, BookingPolicyError

    if isinstance(exc, BookingConflictError):
        return ConflictAppError(
            "That time conflicts with an existing appointment.",
            cause=exc,
        )
    if isinstance(exc, BookingPolicyError):
        msg = str(exc)
        # Policy messages are intentionally user-facing and free of secrets.
        if msg and len(msg) < 200 and "http" not in msg.lower():
            return ValidationAppError(msg, cause=exc)
        return ValidationAppError(cause=exc)

    name = type(exc).__name__
    text = str(exc).lower()

    if name in {"HttpError"} or "httperror" in name.lower():
        if "401" in text or "403" in text or "invalid_grant" in text:
            return ProviderAuthError(cause=exc)
        if "429" in text or "rate" in text:
            return RateLimitedError(cause=exc)
        return ProviderUnavailableError(cause=exc)

    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return ProviderUnavailableError(cause=exc)

    if isinstance(exc, ValueError):
        if "credential" in text or "authentication" in text or "token" in text:
            return ProviderAuthError(cause=exc)
        return ValidationAppError(cause=exc)

    logger.exception("Unmapped error type=%s", name)
    return AppError(cause=exc)


def register_exception_handlers(app: Any) -> None:
    """Register FastAPI handlers that never leak stack traces to clients."""
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail
        if not isinstance(detail, (str, list, dict)):
            detail = str(detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic includes the rejected input by default. It can contain a
        # credential (including the retired tenant Deepgram field), so retain
        # only structural validation information in the browser response.
        errors = [
            {key: value for key, value in error.items() if key != "input"}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "Internal server error",
                    "retryable": False,
                }
            },
        )

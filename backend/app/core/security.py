"""Password hashing and JWT cookie helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request, status

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_COOKIE_NAME = "access_token"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
RESET_TOKEN_EXPIRE_MINUTES = 60
RESET_TOKEN_PURPOSE = "password_reset"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(*, subject: str, expires_delta: timedelta | None = None) -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_password_reset_token(*, user_id: int) -> str:
    """Expiring signed token for password reset."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "purpose": RESET_TOKEN_PURPOSE,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> int | None:
    """Return user id if token is valid, else None. Never raises for bad tokens."""
    if not settings.secret_key or not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != RESET_TOKEN_PURPOSE:
        return None
    subject = payload.get("sub")
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None


def decode_access_token(token: str) -> dict[str, Any]:
    if not settings.secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc


def get_token_from_request(request: Request) -> str | None:
    cookie_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None

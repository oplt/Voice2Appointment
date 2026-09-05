"""Password hashing and JWT cookie helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_COOKIE_NAME = "access_token"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
RESET_TOKEN_EXPIRE_MINUTES = 60
RESET_TOKEN_PURPOSE = "password_reset"
OAUTH_STATE_PURPOSE = "google_oauth"


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


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    subject: str,
    auth_version: int = 0,
    expires_delta: timedelta | None = None,
) -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "av": int(auth_version),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def mint_password_reset_token(db: Session, user: Any) -> str:
    """Create a one-time reset token and persist its hash on the user (P3-07)."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    nonce = secrets.token_urlsafe(32)
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    user.password_reset_token_hash = hash_token(nonce)
    user.password_reset_expires_at = expire
    user.password_reset_consumed_at = None
    db.add(user)
    db.commit()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "purpose": RESET_TOKEN_PURPOSE,
        "nonce": nonce,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_password_reset_token(*, user_id: int, nonce: str | None = None) -> str:
    """Legacy helper for tests — prefer mint_password_reset_token with DB persist."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    expire = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "purpose": RESET_TOKEN_PURPOSE,
        "nonce": nonce or secrets.token_urlsafe(32),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> int | None:
    """Return user id if JWT shape is valid (does not check one-time consume)."""
    payload = _decode_reset_payload(token)
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (TypeError, ValueError, KeyError):
        return None


def _decode_reset_payload(token: str) -> dict[str, Any] | None:
    if not settings.secret_key or not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != RESET_TOKEN_PURPOSE:
        return None
    return payload


def consume_password_reset_token(db: Session, *, token: str, new_password: str) -> bool:
    """Atomically consume nonce, update password, bump auth_version."""
    payload = _decode_reset_payload(token)
    if payload is None:
        return False
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return False
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return False

    from app.db.models import User

    now = datetime.now(timezone.utc)
    # The matching predicates and state transition must be one statement: two
    # independent workers may otherwise both observe an unconsumed token.
    result = db.execute(
        update(User)
        .where(
            User.id == user_id,
            User.password_reset_token_hash == hash_token(nonce),
            User.password_reset_consumed_at.is_(None),
            or_(
                User.password_reset_expires_at.is_(None),
                User.password_reset_expires_at >= now,
            ),
        )
        .values(
            password=hash_password(new_password),
            password_reset_consumed_at=now,
            password_reset_token_hash=None,
            password_reset_expires_at=None,
            auth_version=User.auth_version + 1,
        )
    )
    db.commit()
    return result.rowcount == 1


def create_oauth_state(*, user_id: int, code_verifier: str) -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {
        "purpose": OAUTH_STATE_PURPOSE,
        "uid": user_id,
        "cv": code_verifier,
        "n": secrets.token_urlsafe(8),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_oauth_state(state: str) -> tuple[int, str] | None:
    if not settings.secret_key or not state:
        return None
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != OAUTH_STATE_PURPOSE:
        return None
    try:
        user_id = int(payload["uid"])
    except (TypeError, ValueError, KeyError):
        return None
    verifier = payload.get("cv")
    if not isinstance(verifier, str) or not verifier:
        return None
    return user_id, verifier


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

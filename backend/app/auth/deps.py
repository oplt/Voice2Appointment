"""FastAPI dependencies for authenticated requests."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.core.security import decode_access_token, get_token_from_request
from app.db.models import User
from app.db.session import SessionLocal, get_db


def require_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )
    yield from get_db()


def get_current_user(
    request: Request,
    db: Session = Depends(require_db),
) -> User:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc

    user = auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    token_av = payload.get("av", 0)
    try:
        token_av_int = int(token_av)
    except (TypeError, ValueError):
        token_av_int = 0
    if token_av_int != int(user.auth_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return user

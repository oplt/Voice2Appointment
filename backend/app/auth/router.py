"""Authentication HTTP routes."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.deps import get_current_user, require_db
from app.auth.schemas import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserPublic,
)
from app.core.config import settings
from app.core.middleware import CSRF_COOKIE_NAME
from app.core.rate_limit import rate_limit
from app.core.security import (
    ACCESS_COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def _clear_access_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        httponly=True,
    )


@router.get("/csrf")
def csrf_bootstrap(response: Response) -> dict[str, str]:
    """Issue a readable CSRF cookie for the SPA double-submit pattern."""
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return {"csrf_token": token}


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(limit=10, window_seconds=60, name="login"))],
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(require_db),
) -> AuthResponse:
    user = auth_service.authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(subject=str(user.id))
    _set_access_cookie(response, token)
    return AuthResponse(user=UserPublic.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(require_db),
) -> AuthResponse:
    if auth_service.get_user_by_email(db, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    try:
        user = auth_service.create_user(
            db,
            username=payload.username,
            email=payload.email,
            password=payload.password,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        ) from exc

    token = create_access_token(subject=str(user.id))
    _set_access_cookie(response, token)
    return AuthResponse(user=UserPublic.model_validate(user))


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response) -> MessageResponse:
    _clear_access_cookie(response)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    dependencies=[
        Depends(rate_limit(limit=5, window_seconds=60, name="password-reset-request"))
    ],
)
def password_reset_request(
    payload: PasswordResetRequest,
    db: Session = Depends(require_db),
) -> MessageResponse:
    message = auth_service.request_password_reset(db, payload.email)
    return MessageResponse(message=message)


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    dependencies=[
        Depends(rate_limit(limit=5, window_seconds=60, name="password-reset-confirm"))
    ],
)
def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(require_db),
) -> MessageResponse:
    ok = auth_service.reset_password_with_token(
        db, token=payload.token, new_password=payload.password
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    return MessageResponse(message="Your password has been updated. You can log in.")

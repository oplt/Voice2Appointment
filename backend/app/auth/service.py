"""Auth domain operations (framework-agnostic aside from HTTPException at edges)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_password_reset_token,
    hash_password,
    verify_password,
    verify_password_reset_token,
)
from app.db.models import User

logger = logging.getLogger(__name__)

GENERIC_RESET_MESSAGE = (
    "If an account exists for this email, reset instructions have been sent."
)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password):
        return None
    return user


def create_user(db: Session, *, username: str, email: str, password: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def request_password_reset(db: Session, email: str) -> str:
    """Always return the same message; do not reveal whether the email exists."""
    user = get_user_by_email(db, email)
    if user is not None:
        token = create_password_reset_token(user_id=user.id)
        _send_reset_email(user.email, token)
    return GENERIC_RESET_MESSAGE


def reset_password_with_token(db: Session, *, token: str, new_password: str) -> bool:
    user_id = verify_password_reset_token(token)
    if user_id is None:
        return False
    user = get_user_by_id(db, user_id)
    if user is None:
        return False
    user.password = hash_password(new_password)
    db.commit()
    return True


def _send_reset_email(email: str, token: str) -> None:
    reset_url = f"{settings.public_base_url.rstrip('/')}/reset-password?token={token}"
    body = (
        "To reset your password, visit the following link:\n"
        f"{reset_url}\n\n"
        "If you did not make this request, ignore this email."
    )

    if not settings.mail_username or not settings.mail_password:
        logger.info(
            "Password reset email (mail not configured) to=%s url=%s", email, reset_url
        )
        return

    msg = EmailMessage()
    msg["Subject"] = "Password Reset Request"
    msg["From"] = settings.mail_username
    msg["To"] = email
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.mail_server, settings.mail_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.mail_username, settings.mail_password)
            smtp.send_message(msg)
    except OSError:
        logger.exception("Failed to send password reset email to %s", email)

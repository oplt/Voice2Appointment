"""Auth domain operations (framework-agnostic aside from HTTPException at edges)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    consume_password_reset_token,
    hash_password,
    mint_password_reset_token,
    verify_password,
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


def _send_reset_email(email: str, token: str) -> None:
    reset_url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
    body = (
        "To reset your password, visit the following link:\n"
        f"{reset_url}\n\n"
        "If you did not make this request, ignore this email."
    )

    if not settings.mail_username or not settings.mail_password:
        if settings.is_production:
            logger.error(
                "Password reset mail transport unavailable; refusing delivery"
            )
            raise RuntimeError("mail transport not configured")
        # Dev only: never log token, URL, or email address.
        logger.info("Password reset email skipped (mail not configured)")
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
        logger.exception("Failed to send password reset email")
        if settings.is_production:
            raise


def request_password_reset(db: Session, email: str) -> str:
    """Always return the same message; do not reveal whether the email exists."""
    user = get_user_by_email(db, email)
    if user is not None:
        token = mint_password_reset_token(db, user)
        try:
            if settings.mail_username and settings.mail_password:
                from app.workers.tasks import send_password_reset_email

                try:
                    send_password_reset_email.delay(user.email, token)
                except Exception:
                    _send_reset_email(user.email, token)
            else:
                _send_reset_email(user.email, token)
        except RuntimeError:
            if not settings.is_production:
                raise
    return GENERIC_RESET_MESSAGE


def reset_password_with_token(db: Session, *, token: str, new_password: str) -> bool:
    return consume_password_reset_token(db, token=token, new_password=new_password)

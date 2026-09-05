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
    hash_token,
    mint_password_reset_token,
    verify_password,
)
from app.db.models import User

logger = logging.getLogger(__name__)

GENERIC_RESET_MESSAGE = (
    "If an account exists for this email, reset instructions have been sent."
)


class ResetDeliveryUnavailable(RuntimeError):
    """The reset request could not be durably accepted for delivery."""


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
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send password reset email")
        if settings.is_production:
            raise


def request_password_reset(db: Session, email: str) -> str:
    """Always return the same message; do not reveal whether the email exists."""
    if settings.is_production:
        if (
            not settings.password_reset_enabled
            or not settings.mail_username
            or not settings.mail_password
        ):
            raise ResetDeliveryUnavailable("password reset delivery is unavailable")
        from app.workers.tasks import process_password_reset_request

        try:
            normalized_email = email.strip().lower()
            user = get_user_by_email(db, normalized_email)
            # Persist the nonce before publication.  Retries receive this exact
            # token, rather than minting a replacement link after SMTP ambiguity.
            # Unknown accounts still enqueue a no-op job to preserve the public
            # enumeration-safe behavior.
            token = mint_password_reset_token(db, user) if user is not None else None
            publish_options: dict[str, str] = {
                # Celery event/log metadata must not render the recipient or
                # bearer token.  The message payload remains available only to
                # the configured trusted broker and worker.
                "argsrepr": "(<redacted>, <redacted>)",
            }
            if token is not None:
                # The persisted nonce hash is unique per request and gives an
                # ambiguous publish/retry the same delivery identity.
                publish_options["task_id"] = f"password-reset-{hash_token(token)}"
            process_password_reset_request.apply_async(
                args=(normalized_email, token), **publish_options
            )
        except Exception as exc:
            raise ResetDeliveryUnavailable(
                "password reset delivery is unavailable"
            ) from exc
        return GENERIC_RESET_MESSAGE

    user = get_user_by_email(db, email)
    if user is not None:
        token = mint_password_reset_token(db, user)
        _send_reset_email(user.email, token)
    return GENERIC_RESET_MESSAGE


def process_queued_password_reset(
    db: Session, email: str, token: str | None = None
) -> dict[str, bool]:
    """Deliver the persisted reset token; an unknown-account job is a no-op."""
    if token is None:
        return {"delivered": False}
    _send_reset_email(email, token)
    return {"delivered": True}


def reset_password_with_token(db: Session, *, token: str, new_password: str) -> bool:
    return consume_password_reset_token(db, token=token, new_password=new_password)

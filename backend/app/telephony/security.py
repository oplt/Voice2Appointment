"""Twilio webhook signature validation."""

from __future__ import annotations

import logging
from typing import Mapping

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.core.config import settings

logger = logging.getLogger(__name__)


def webhook_public_url(request: Request) -> str:
    """Canonical HTTPS URL Twilio signed, based on PUBLIC_BASE_URL."""
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured")
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{base}{path}{query}"


def resolve_auth_token(db: Session, account_sid: str | None) -> str | None:
    """Prefer tenant Twilio token; fall back to platform settings."""
    if account_sid:
        from app.telephony.service import find_user_by_twilio_account

        user = find_user_by_twilio_account(db, account_sid)
        if user is not None and user.twilio_auth_token:
            return user.twilio_auth_token
    return settings.twilio_auth_token or None


def validate_twilio_request(
    db: Session,
    request: Request,
    form: Mapping[str, str],
) -> None:
    """Reject absent/invalid X-Twilio-Signature before any side effect."""
    signature = request.headers.get("X-Twilio-Signature") or request.headers.get(
        "x-twilio-signature"
    )
    if not signature:
        raise HTTPException(status_code=403, detail="Forbidden")

    account_sid = (form.get("AccountSid") or "").strip() or None
    auth_token = resolve_auth_token(db, account_sid)
    if not auth_token:
        logger.warning("Twilio signature: no auth token for AccountSid=%s", account_sid)
        raise HTTPException(status_code=403, detail="Forbidden")

    url = webhook_public_url(request)
    validator = RequestValidator(auth_token)
    params = {k: v for k, v in form.items()}
    if not validator.validate(url, params, signature):
        logger.warning("Twilio signature invalid path=%s", request.url.path)
        raise HTTPException(status_code=403, detail="Forbidden")


def is_allowed_twilio_media_host(hostname: str) -> bool:
    host = (hostname or "").lower().rstrip(".")
    allow = settings.twilio_media_hosts
    if host in allow:
        return True
    return any(host.endswith(f".{suffix}") for suffix in allow)


def twilio_recording_api_url(*, account_sid: str, recording_sid: str) -> str:
    """Canonical Twilio Recording media URL (never trust webhook RecordingUrl host)."""
    return (
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
        f"/Recordings/{recording_sid}.mp3"
    )


def assert_valid_twilio_sid(value: str, *, prefix: str) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) < 34 or not cleaned.startswith(prefix):
        raise ValueError(f"invalid {prefix} SID")
    if not cleaned[2:].isalnum():
        raise ValueError(f"invalid {prefix} SID characters")
    return cleaned

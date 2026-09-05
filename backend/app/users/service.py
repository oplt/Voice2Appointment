"""User settings service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import User


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def get_settings(user: User) -> dict[str, Any]:
    from app.core.cache import CACHE_TTL_SETTINGS, cache_get, cache_set, versioned_key
    from app.core.config import settings as app_settings

    cache_key = versioned_key(
        user.id,
        "settings",
        "me",
        generation=user.cache_settings_version,
    )
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        return cached
    # Deepgram is platform-managed (global DEEPGRAM_API_KEY). Tenant keys are not used.
    deepgram_configured = bool((app_settings.deepgram_api_key or "").strip())
    payload = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "image_file": user.image_file,
        "twilio_account_sid": mask_secret(user.twilio_account_sid),
        "twilio_auth_token": None,
        "twilio_phone_number": user.twilio_phone_number,
        "has_twilio": bool(user.twilio_account_sid and user.twilio_auth_token),
        "has_deepgram": deepgram_configured,
        "twilio_auth_token_set": bool(user.twilio_auth_token),
    }
    cache_set(cache_key, payload, ttl_seconds=CACHE_TTL_SETTINGS)
    return payload


def update_settings(db: Session, user: User, data: dict[str, Any]) -> User:
    from app.telephony.phones import canonical_e164

    # Never overwrite secrets with masked placeholders.
    secret_fields = ("twilio_account_sid", "twilio_auth_token")
    if "config_json" in data:
        raise ValueError("config_json is managed by typed settings endpoints")
    if "deepgram_api_key" in data:
        raise ValueError(
            "deepgram_api_key is no longer accepted; configure DEEPGRAM_API_KEY on the server"
        )
    ignored = {"id", "password", "twilio_phone_e164"}
    for key, value in data.items():
        if key in ignored:
            continue
        if value is None:
            continue
        if key == "twilio_phone_number":
            if value == "":
                user.twilio_phone_number = None
                continue
            if canonical_e164(str(value)) is None:
                raise ValueError("twilio_phone_number must be a valid phone number")
        if key in secret_fields:
            if isinstance(value, str) and value.startswith("****"):
                continue
            if value == "":
                setattr(user, key, None)
                continue
        if hasattr(user, key):
            setattr(user, key, value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(user)
    return user

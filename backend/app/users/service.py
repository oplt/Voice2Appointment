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
    from app.core.cache import cache_get, cache_set

    cached = cache_get(f"user:settings:{user.id}")
    if isinstance(cached, dict):
        return cached
    payload = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "image_file": user.image_file,
        "twilio_account_sid": mask_secret(user.twilio_account_sid),
        "twilio_auth_token": None,
        "twilio_phone_number": user.twilio_phone_number,
        "deepgram_api_key": None,
        "config_json": user.config_json,
        "has_twilio": bool(user.twilio_account_sid and user.twilio_auth_token),
        "has_deepgram": bool(user.deepgram_api_key),
        "twilio_auth_token_set": bool(user.twilio_auth_token),
        "deepgram_api_key_set": bool(user.deepgram_api_key),
    }
    cache_set(f"user:settings:{user.id}", payload, ttl_seconds=180)
    return payload


def update_settings(db: Session, user: User, data: dict[str, Any]) -> User:
    # Never overwrite secrets with masked placeholders.
    secret_fields = ("twilio_account_sid", "twilio_auth_token", "deepgram_api_key")
    for key, value in data.items():
        if value is None:
            continue
        if key in secret_fields:
            if isinstance(value, str) and value.startswith("****"):
                continue
            if value == "":
                setattr(user, key, None)
                continue
        if hasattr(user, key) and key not in ("id", "password"):
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    from app.core.cache import invalidate_user_settings_cache

    invalidate_user_settings_cache(user.id)
    return user

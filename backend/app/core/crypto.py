"""Fernet encryption for provider secrets at rest."""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "enc:"


def _fernet() -> Fernet:
    key = (settings.fernet_key or "").strip()
    if not key:
        raise RuntimeError("FERNET_KEY is not configured")
    return Fernet(key.encode("utf-8") if not isinstance(key, bytes) else key)


def encrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if value.startswith(_PREFIX):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt Fernet values; pass through legacy plaintext."""
    if value is None or value == "":
        return value
    if not value.startswith(_PREFIX):
        return value
    token = value[len(_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.error("Failed to decrypt secret: %s", exc)
        raise RuntimeError("Stored credential could not be decrypted") from exc

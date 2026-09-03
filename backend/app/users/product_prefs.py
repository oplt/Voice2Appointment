"""Typed product preferences stored alongside booking_policy in config_json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.db.models import User
from app.telephony.phones import canonical_e164


class NotificationPrefs(BaseModel):
    channel: Literal["email"] = "email"
    confirmations_enabled: bool = False
    reminders_enabled: bool = False
    consent_at: str | None = None
    quiet_hours_start: str | None = None  # HH:MM local
    quiet_hours_end: str | None = None
    reminder_hours_before: int = Field(default=24, ge=1, le=168)

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def valid_hhmm(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        from datetime import time

        try:
            time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be HH:MM") from exc
        return value


class RetentionPrefs(BaseModel):
    transcript_days: int = Field(default=30, ge=1, le=365)
    recording_days: int = Field(default=14, ge=1, le=365)
    legal_hold: bool = False


class TransferPrefs(BaseModel):
    enabled: bool = False
    destination_e164: str | None = None
    business_hours_only: bool = False

    @field_validator("destination_e164")
    @classmethod
    def valid_dest(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        e164 = canonical_e164(value)
        if e164 is None:
            raise ValueError("destination must be a valid E.164 phone number")
        return e164


class LanguagePrefs(BaseModel):
    """P6-05: multilingual remains gated until eval thresholds pass."""

    primary: str = "en"
    enabled: list[str] = Field(default_factory=lambda: ["en"])


class ProductPrefs(BaseModel):
    notifications: NotificationPrefs = Field(default_factory=NotificationPrefs)
    retention: RetentionPrefs = Field(default_factory=RetentionPrefs)
    transfer: TransferPrefs = Field(default_factory=TransferPrefs)
    languages: LanguagePrefs = Field(default_factory=LanguagePrefs)


def _parse_config(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def load_product_prefs(config_json: str | None) -> ProductPrefs:
    data = _parse_config(config_json)
    blob = data.get("product") if isinstance(data.get("product"), dict) else {}
    # Also accept top-level keys for forward compat.
    if not blob:
        blob = {
            k: data[k]
            for k in ("notifications", "retention", "transfer", "languages")
            if k in data
        }
    try:
        return ProductPrefs.model_validate(blob or {})
    except Exception:  # noqa: BLE001
        return ProductPrefs()


def save_product_prefs(user: User, prefs: ProductPrefs) -> ProductPrefs:
    data = _parse_config(user.config_json)
    data["product"] = prefs.model_dump(mode="json")
    user.config_json = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return prefs


def grant_notification_consent(prefs: NotificationPrefs) -> NotificationPrefs:
    return prefs.model_copy(
        update={"consent_at": datetime.now(timezone.utc).isoformat()}
    )

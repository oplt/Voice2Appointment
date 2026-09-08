"""Typed product preferences stored alongside booking_policy in config_json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class TranscriptPrefs(BaseModel):
    """Explicit tenant consent and redaction policy for stored call text."""

    storage_enabled: bool = False
    consent_at: str | None = None
    redact_phone_numbers: bool = True


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
    transcripts: TranscriptPrefs = Field(default_factory=TranscriptPrefs)
    transfer: TransferPrefs = Field(default_factory=TransferPrefs)
    languages: LanguagePrefs = Field(default_factory=LanguagePrefs)


class NotificationPrefsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["email"] | None = None
    confirmations_enabled: bool | None = None
    reminders_enabled: bool | None = None
    consent_at: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    reminder_hours_before: int | None = Field(default=None, ge=1, le=168)


class RetentionPrefsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript_days: int | None = Field(default=None, ge=1, le=365)
    recording_days: int | None = Field(default=None, ge=1, le=365)
    legal_hold: bool | None = None


class TranscriptPrefsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_enabled: bool | None = None
    # Kept for GET/PUT compatibility. The server, not the client, records it.
    consent_at: str | None = None
    redact_phone_numbers: bool | None = None


class TransferPrefsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    destination_e164: str | None = None
    business_hours_only: bool | None = None

    @field_validator("destination_e164")
    @classmethod
    def valid_dest(cls, value: str | None) -> str | None:
        return TransferPrefs.valid_dest(value)


class LanguagePrefsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str | None = None
    enabled: list[str] | None = None


class ProductPrefsUpdate(BaseModel):
    """Partial preference update that preserves unknown persisted fields."""

    model_config = ConfigDict(extra="forbid")

    notifications: NotificationPrefsPatch | None = None
    retention: RetentionPrefsPatch | None = None
    transcripts: TranscriptPrefsPatch | None = None
    transfer: TransferPrefsPatch | None = None
    languages: LanguagePrefsPatch | None = None
    # This is an explicit acknowledgement, never persisted as a preference.
    transcript_storage_consent: bool = False


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
            for k in ("notifications", "retention", "transcripts", "transfer", "languages")
            if k in data
        }
    try:
        return ProductPrefs.model_validate(blob or {})
    except Exception:  # noqa: BLE001
        # Fail closed: unreadable prefs must not silently enable purge via defaults.
        return ProductPrefs(
            retention=RetentionPrefs(legal_hold=True),
        )


def prefs_policy_valid(config_json: str | None) -> bool:
    """False when product prefs JSON is missing/malformed (fail-closed for purge)."""
    if not config_json or not str(config_json).strip():
        return True  # empty → explicit defaults OK
    try:
        data = json.loads(config_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    blob = data.get("product") if isinstance(data.get("product"), dict) else None
    if blob is None:
        blob = {
            k: data[k]
            for k in ("notifications", "retention", "transcripts", "transfer", "languages")
            if k in data
        }
    if not blob:
        return True
    try:
        ProductPrefs.model_validate(blob)
        return True
    except Exception:  # noqa: BLE001
        return False


def _product_blob(data: dict[str, Any]) -> dict[str, Any]:
    existing = data.get("product")
    if isinstance(existing, dict):
        return dict(existing)
    return {
        key: data[key]
        for key in ("notifications", "retention", "transcripts", "transfer", "languages")
        if key in data
    }


def _persist_product_blob(user: User, data: dict[str, Any], product: dict[str, Any]) -> None:
    data["product"] = product
    user.config_json = json.dumps(data, separators=(",", ":"), sort_keys=True)


def save_product_prefs(user: User, prefs: ProductPrefs) -> ProductPrefs:
    """Save known preferences without deleting unrecognized persisted fields."""
    data = _parse_config(user.config_json)
    product = _product_blob(data)
    for section, values in prefs.model_dump(mode="json").items():
        existing = product.get(section)
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(values)
        product[section] = merged
    _persist_product_blob(user, data, product)
    return prefs


def update_product_prefs(
    user: User,
    update: ProductPrefsUpdate,
) -> ProductPrefs:
    """Apply a partial update while retaining future server-side preference keys."""
    data = _parse_config(user.config_json)
    product = _product_blob(data)
    previous = load_product_prefs(user.config_json)
    changes = update.model_dump(exclude_unset=True)
    transcript_changes = changes.get("transcripts")
    if isinstance(transcript_changes, dict):
        # Consent timestamps are evidence, not client-controlled values.
        transcript_changes.pop("consent_at", None)
        enabling_storage = transcript_changes.get("storage_enabled") is True
        if enabling_storage and not previous.transcripts.consent_at:
            if not update.transcript_storage_consent:
                raise ValueError("explicit transcript storage consent is required")
            transcript_changes["consent_at"] = datetime.now(timezone.utc).isoformat()

    for section in ("notifications", "retention", "transcripts", "transfer", "languages"):
        values = changes.get(section)
        if not isinstance(values, dict):
            continue
        existing = product.get(section)
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(values)
        product[section] = merged

    prefs = ProductPrefs.model_validate(product)
    if (
        prefs.notifications.confirmations_enabled or prefs.notifications.reminders_enabled
    ) and not prefs.notifications.consent_at:
        notifications = dict(product.get("notifications") or {})
        notifications["consent_at"] = datetime.now(timezone.utc).isoformat()
        product["notifications"] = notifications
        prefs = ProductPrefs.model_validate(product)

    # Multilingual operation remains feature-gated. Preserve the existing contract.
    languages = dict(product.get("languages") or {})
    languages.update({"primary": "en", "enabled": ["en"]})
    product["languages"] = languages
    _persist_product_blob(user, data, product)
    return ProductPrefs.model_validate(product)


def grant_notification_consent(prefs: NotificationPrefs) -> NotificationPrefs:
    return prefs.model_copy(
        update={"consent_at": datetime.now(timezone.utc).isoformat()}
    )

"""Appointment idempotency helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_title(summary: str) -> str:
    cleaned = re.sub(r"\s+", " ", (summary or "").strip().lower())
    return cleaned


def build_appointment_idempotency_key(
    *,
    user_id: int,
    calendar_id: str,
    start_utc: datetime,
    end_utc: datetime,
    summary: str,
    call_sid: str | None = None,
) -> str:
    """Stable hash for duplicate appointment / Google event creation."""
    raw = "|".join(
        [
            str(user_id),
            calendar_id or "primary",
            _as_utc_iso(start_utc),
            _as_utc_iso(end_utc),
            normalize_title(summary),
            call_sid or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

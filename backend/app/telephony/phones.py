"""Canonical inbound phone numbers (E.164)."""

from __future__ import annotations

import phonenumbers


def canonical_e164(value: str | None, *, default_region: str = "US") -> str | None:
    """Return E.164 or None when the value cannot be parsed as a phone number."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else default_region)
    except phonenumbers.NumberParseException:
        return None
    if not (phonenumbers.is_valid_number(parsed) or phonenumbers.is_possible_number(parsed)):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

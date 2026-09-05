"""Retry-safe Google Calendar mutation primitives."""

from __future__ import annotations

import hashlib
from typing import Any

from googleapiclient.errors import HttpError


def deterministic_event_id(idempotency_key: str) -> str:
    """Build an allowed Google event ID from the local appointment key."""
    return "va" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def http_status(error: HttpError) -> int | None:
    return getattr(getattr(error, "resp", None), "status", None)


def insert_event(
    events: Any,
    *,
    calendar_id: str,
    event: dict[str, Any],
    idempotency_key: str | None,
) -> dict[str, Any]:
    """Insert once, resolving a duplicate deterministic ID to its event."""
    if idempotency_key:
        event["id"] = deterministic_event_id(idempotency_key)
        event["extendedProperties"] = {
            "private": {"idempotency_key": idempotency_key}
        }
    try:
        return events.insert(calendarId=calendar_id, body=event).execute()
    except HttpError as error:
        if idempotency_key and http_status(error) == 409:
            return events.get(calendarId=calendar_id, eventId=event["id"]).execute()
        raise

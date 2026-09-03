"""High-level calendar operations for the API layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars.providers.google import GoogleCalendarService
from app.core.config import settings
from app.db.models import GoogleCalendarAuth


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((name or settings.default_timezone or "UTC").strip())
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def get_auth_record(db: Session, user_id: int) -> GoogleCalendarAuth | None:
    return db.scalar(
        select(GoogleCalendarAuth)
        .where(
            GoogleCalendarAuth.user_id == user_id,
            GoogleCalendarAuth.revoked.is_(False),
        )
        .order_by(GoogleCalendarAuth.updated_at.desc())
    )


def calendar_status(db: Session, user_id: int) -> dict[str, Any]:
    from app.core.cache import cache_get, cache_set

    cache_key = f"cal:status:{user_id}"
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    auth = get_auth_record(db, user_id)
    if not auth:
        payload = {
            "connected": False,
            "account_email": None,
            "calendar_id": None,
            "time_zone": settings.default_timezone,
            "embedded_link": None,
        }
    else:
        payload = {
            "connected": True,
            "account_email": auth.account_email,
            "calendar_id": auth.calendar_id,
            "time_zone": auth.time_zone or settings.default_timezone,
            "embedded_link": auth.embedded_link,
            "status": auth.status,
        }
    cache_set(cache_key, payload, ttl_seconds=60)
    return payload


def list_events(
    db: Session,
    user_id: int,
    time_min: str,
    time_max: str,
    timezone_str: str | None = None,
) -> list[dict[str, Any]]:
    from app.core.cache import cache_get, cache_set

    cache_key = f"cal:events:{user_id}:{time_min}:{time_max}:{timezone_str or ''}"
    cached = cache_get(cache_key)
    if isinstance(cached, list):
        return cached

    user_tz = _zone(timezone_str or settings.default_timezone)

    def _parse_bound(value: str) -> datetime:
        if "Z" in value or "+" in value or (len(value) > 6 and "-" in value[-6:]):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                user_tz
            )
        naive = datetime.fromisoformat(value)
        return naive.replace(tzinfo=user_tz)

    start_date = _parse_bound(time_min)
    end_date = _parse_bound(time_max)

    service = GoogleCalendarService(db, user_id)
    events_result = service.list_events(start_date.isoformat(), end_date.isoformat())
    events = events_result.get("items", [])

    formatted: list[dict[str, Any]] = []
    for event in events:
        start = event["start"].get("dateTime") or event["start"].get("date")
        end = event["end"].get("dateTime") or event["end"].get("date")
        if start and "T" in start:
            try:
                start = (
                    datetime.fromisoformat(start.replace("Z", "+00:00"))
                    .astimezone(user_tz)
                    .isoformat()
                )
            except (TypeError, ValueError):
                pass
        if end and "T" in end:
            try:
                end = (
                    datetime.fromisoformat(end.replace("Z", "+00:00"))
                    .astimezone(user_tz)
                    .isoformat()
                )
            except (TypeError, ValueError):
                pass
        item = {
            "id": event.get("id"),
            "title": event.get("summary", "No Title"),
            "start": start,
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "allDay": "date" in event["start"],
            "attendees": [
                {
                    "email": att.get("email", ""),
                    "name": att.get("displayName", att.get("email", "")),
                }
                for att in event.get("attendees", [])
            ],
        }
        if end and end != start:
            item["end"] = end
        if event.get("htmlLink"):
            item["url"] = event["htmlLink"]
        formatted.append(item)
    cache_set(cache_key, formatted, ttl_seconds=45)
    return formatted


def check_availability(
    db: Session, user_id: int, datetime_start: str, datetime_end: str
) -> dict[str, Any]:
    service = GoogleCalendarService(db, user_id)
    is_available, conflicts = service.check_availability(datetime_start, datetime_end)
    return {
        "available": is_available,
        "conflicting_events": [
            {"id": e.get("id"), "summary": e.get("summary")} for e in conflicts
        ],
    }


def embed_link(db: Session, user_id: int, view_type: str = "week") -> dict[str, Any]:
    auth = get_auth_record(db, user_id)
    if not auth:
        raise ValueError("Google Calendar not connected")
    service = GoogleCalendarService(db, user_id)
    calendar_list = service.service.calendarList().list().execute()
    primary = next(
        (c for c in calendar_list.get("items", []) if c.get("primary")), None
    )
    if not primary:
        raise ValueError("Primary calendar not found")
    calendar_id = primary["id"]
    timezone = auth.time_zone or settings.default_timezone
    mode = {"week": "WEEK", "month": "MONTH", "agenda": "AGENDA"}.get(view_type)
    if not mode:
        raise ValueError("Invalid view type")
    embed_url = (
        f"https://calendar.google.com/calendar/embed?src={quote(calendar_id)}"
        f"&ctz={quote(timezone)}&mode={mode}"
        "&showTitle=0&showNav=1&showDate=1&showPrint=0&showTabs=1"
        "&showCalendars=0&showTz=0&hl=en&bgcolor=%23ffffff&color=%23000000"
    )
    return {
        "embed_url": embed_url,
        "view_type": view_type,
        "calendar_id": calendar_id,
    }


def disconnect_google(db: Session, user_id: int) -> bool:
    auth = get_auth_record(db, user_id)
    if not auth:
        return False
    auth.revoked = True
    auth.status = "revoked"
    auth.token_json = None
    db.commit()
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return True

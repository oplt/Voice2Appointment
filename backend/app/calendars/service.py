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
    from app.core.cache import CACHE_TTL_STATUS, cache_get, cache_set, versioned_key

    cache_key = versioned_key(user_id, "cal", "status")
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
    cache_set(cache_key, payload, ttl_seconds=CACHE_TTL_STATUS)
    return payload


def list_events(
    db: Session,
    user_id: int,
    time_min: str,
    time_max: str,
    timezone_str: str | None = None,
) -> list[dict[str, Any]]:
    from app.core.cache import CACHE_TTL_CALENDAR, cache_get, cache_set, versioned_key

    cache_key = versioned_key(
        user_id, "cal", "events", time_min, time_max, timezone_str or ""
    )
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
    cache_set(cache_key, formatted, ttl_seconds=CACHE_TTL_CALENDAR)
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


class BookingProviderHooks:
    """Optional Google callbacks for the unified booking service."""

    __slots__ = ("calendar_id", "create_event", "update_event", "delete_event", "check_availability")

    def __init__(
        self,
        *,
        calendar_id: str = "primary",
        create_event=None,
        update_event=None,
        delete_event=None,
        check_availability=None,
    ):
        self.calendar_id = calendar_id
        self.create_event = create_event
        self.update_event = update_event
        self.delete_event = delete_event
        self.check_availability = check_availability


def booking_provider_hooks(db: Session, user_id: int) -> BookingProviderHooks:
    """Return provider hooks when Google is connected; otherwise local-only."""
    auth = get_auth_record(db, user_id)
    if auth is None or not auth.token_json:
        return BookingProviderHooks()
    try:
        service = GoogleCalendarService(db, user_id)
    except Exception:
        return BookingProviderHooks()

    calendar_id = auth.calendar_id or "primary"

    def _create(**kwargs):
        return service.create_event(**kwargs)

    def _update(**kwargs):
        kwargs = dict(kwargs)
        kwargs.setdefault("calendar_id", calendar_id)
        return service.update_event(**kwargs)

    def _delete(*, event_id: str, **_kwargs):
        return service.delete_event(event_id, calendar_id=calendar_id)

    def _availability(start: datetime, end: datetime) -> None:
        ok, _conflicts = service.check_availability(
            start.isoformat(), end.isoformat(), calendar_id=calendar_id
        )
        if not ok:
            from app.appointments.policy import BookingConflictError

            raise BookingConflictError("Google Calendar reports the slot as busy")

    return BookingProviderHooks(
        calendar_id=calendar_id,
        create_event=_create,
        update_event=_update,
        delete_event=_delete,
        check_availability=_availability,
    )


def update_calendar_preferences(
    db: Session,
    user_id: int,
    *,
    calendar_id: str | None = None,
    time_zone: str | None = None,
) -> dict[str, Any]:
    auth = get_auth_record(db, user_id)
    if auth is None:
        raise ValueError("Google Calendar not connected")
    if calendar_id is not None:
        cleaned = calendar_id.strip() or "primary"
        auth.calendar_id = cleaned
    if time_zone is not None:
        from app.appointments.schemas import validate_timezone_name

        auth.time_zone = validate_timezone_name(time_zone)
    db.commit()
    from app.core.cache import invalidate_user_calendar_caches

    invalidate_user_calendar_caches(user_id)
    return calendar_status(db, user_id)


def start_google_oauth(user_id: int) -> dict[str, str]:
    from app.calendars.providers.google import build_authorization_url

    return build_authorization_url(user_id=user_id)


def finish_google_oauth(
    db: Session, *, state: str, code: str | None, error: str | None
) -> str:
    """Persist tokens and return frontend redirect URL."""
    from urllib.parse import urlencode

    from app.calendars.providers.google import exchange_authorization_code

    base = settings.frontend_base_url.rstrip("/")
    settings_path = f"{base}/settings"
    if error:
        return f"{settings_path}?{urlencode({'google': 'denied'})}"
    if not code:
        return f"{settings_path}?{urlencode({'google': 'error'})}"
    try:
        exchange_authorization_code(db, state=state, code=code)
    except Exception:
        return f"{settings_path}?{urlencode({'google': 'error'})}"
    return f"{settings_path}?{urlencode({'google': 'connected'})}"

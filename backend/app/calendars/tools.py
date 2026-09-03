"""Calendar function tools for voice agent (event-id safe mutations)."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars.providers.google import GoogleCalendarService
from app.db.models import Appointment
from app.db.session import SessionLocal
from app.voice.context import current_call_context

# Set by voice gateway for the duration of a call.
voice_db: ContextVar[Session | None] = ContextVar("voice_db", default=None)
voice_user_id: ContextVar[int | None] = ContextVar("voice_user_id", default=None)
voice_calendar_service: ContextVar[GoogleCalendarService | None] = ContextVar(
    "voice_calendar_service", default=None
)


def _record_calendar_latency(operation: str, started: float) -> None:
    try:
        from app.voice.session import get_active_latency

        tracker = get_active_latency()
        if tracker is not None:
            tracker.note_calendar(operation, started)
    except Exception:  # noqa: BLE001
        pass


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _resolve_service() -> tuple[GoogleCalendarService, Session | None, str, str]:
    """Build a GoogleCalendarService using CallContext / voice ContextVars.

    Reuses one GoogleCalendarService per voice call when ContextVar is set (Phase 9.1).
    """
    ctx = current_call_context.get()
    db = voice_db.get()
    user_id = voice_user_id.get()
    timezone_name = "UTC"
    calendar_id = "primary"
    if ctx is not None:
        user_id = ctx.user_id
        timezone_name = ctx.timezone
        calendar_id = ctx.calendar_id

    cached = voice_calendar_service.get()
    if cached is not None and user_id is not None and cached.user_id == user_id:
        return cached, None, timezone_name, calendar_id

    owns = False
    if db is None:
        if SessionLocal is None:
            raise RuntimeError("DATABASE_URL is not configured")
        db = SessionLocal()
        owns = True
    if user_id is None:
        if owns:
            db.close()
        raise ValueError("user_id is required for calendar tools")
    service = GoogleCalendarService(db, user_id)
    if not owns:
        voice_calendar_service.set(service)
    return service, db if owns else None, timezone_name, calendar_id


def _format_local(dt: datetime) -> str:
    return dt.strftime("%A %B %d at %I:%M %p").lstrip("0").replace(" 0", " ")


def check_calendar_availability(datetime_start=None, datetime_end=None):
    owned = None
    started = time.perf_counter()
    try:
        datetime_start = _parse_dt(datetime_start)
        datetime_end = _parse_dt(datetime_end)
        if datetime_start is None or datetime_end is None:
            return {"available": False, "error": "datetime_start and datetime_end are required"}

        start_iso = datetime_start.isoformat()
        end_iso = datetime_end.isoformat()
        calendar_service, owned, _timezone, calendar_id = _resolve_service()
        is_available, conflicting_events = calendar_service.check_availability(
            start_iso, end_iso, calendar_id=calendar_id
        )

        if is_available:
            return {
                "available": True,
                "message": "Time slot is available",
                "suggested_alternatives": [],
            }
        alternatives = generate_alternative_slots(
            datetime_start, datetime_end, calendar_service, calendar_id=calendar_id
        )
        return {
            "available": False,
            "message": "Time slot is not available",
            "conflicting_events": [
                event.get("summary", "Unknown event") for event in conflicting_events
            ],
            "suggested_alternatives": alternatives,
        }
    except Exception as e:
        logging.error("Error checking calendar availability: %s", e.__class__.__name__)
        return {"error": f"Failed to check availability: {str(e)}", "available": False}
    finally:
        _record_calendar_latency("lookup", started)
        if owned is not None:
            owned.close()


def find_appointments(
    datetime_start=None, datetime_end=None, summary_contains=None, **_kwargs
):
    """List candidate events. Never mutates. Use event_id for cancel/reschedule."""
    owned = None
    try:
        datetime_start = _parse_dt(datetime_start)
        datetime_end = _parse_dt(datetime_end)
        if datetime_start is None or datetime_end is None:
            return {
                "success": False,
                "error": "datetime_start and datetime_end are required",
                "count": 0,
                "appointments": [],
            }

        calendar_service, owned, _timezone, calendar_id = _resolve_service()
        events_result = calendar_service.list_events(
            datetime_start.isoformat(),
            datetime_end.isoformat(),
            calendar_id=calendar_id,
        )
        events = events_result.get("items", [])
        needle = (summary_contains or "").strip().lower()
        appointments: list[dict[str, Any]] = []
        for event in events:
            summary = event.get("summary") or ""
            if needle and needle not in summary.lower():
                continue
            appointments.append(
                {
                    "event_id": event.get("id"),
                    "summary": summary,
                    # Omit full description from tool payload (Phase 13.1).
                    "start_time": event["start"].get("dateTime")
                    or event["start"].get("date"),
                    "end_time": event["end"].get("dateTime") or event["end"].get("date"),
                    "status": event.get("status"),
                }
            )

        count = len(appointments)
        if count == 0:
            guidance = "No appointments found. Ask the caller for a clearer date or title."
        elif count == 1:
            guidance = (
                "One match. Read it back, ask for confirmation, then cancel/reschedule "
                "with this event_id and confirmed=true."
            )
        else:
            guidance = (
                "Multiple matches. Ask the caller which appointment to use "
                "(by title/time), then use that event_id."
            )

        return {
            "success": True,
            "count": count,
            "appointments": appointments,
            "guidance": guidance,
            "time_range": {
                "start": datetime_start.isoformat(),
                "end": datetime_end.isoformat(),
            },
        }
    except Exception as e:
        logging.error("Error finding appointments: %s", e)
        return {
            "error": f"Failed to find appointments: {str(e)}",
            "success": False,
            "count": 0,
            "appointments": [],
        }
    finally:
        if owned is not None:
            owned.close()


# Back-compat alias for older prompts / tests.
def get_appointment_details(datetime_start=None, datetime_end=None, **kwargs):
    return find_appointments(
        datetime_start=datetime_start,
        datetime_end=datetime_end,
        summary_contains=kwargs.get("attendee") or kwargs.get("summary_contains"),
    )


def create_calendar_event(
    summary=None,
    datetime_start=None,
    datetime_end=None,
    description=None,
    call_sid=None,
    client_name=None,
    client_phone=None,
    client_email=None,
    confirmed=False,
    **_kwargs,
):
    owned = None
    started = time.perf_counter()
    try:
        from app.appointments import service as appointments_service
        from app.appointments.idempotency import build_appointment_idempotency_key

        datetime_start = _parse_dt(datetime_start)
        datetime_end = _parse_dt(datetime_end)
        if not summary or datetime_start is None or datetime_end is None:
            return {
                "success": False,
                "error": "summary, datetime_start, and datetime_end are required",
            }

        if not _as_bool(confirmed):
            duration_min = int((datetime_end - datetime_start).total_seconds() // 60)
            prompt = (
                f"I can book '{summary}' on {_format_local(datetime_start)} "
                f"for {duration_min} minutes"
            )
            if client_name:
                prompt += f" for {client_name}"
            prompt += ". Would you like me to book it?"
            return {
                "success": False,
                "needs_confirmation": True,
                "confirmation_prompt": prompt,
                "pending": {
                    "summary": summary,
                    "datetime_start": datetime_start.isoformat(),
                    "datetime_end": datetime_end.isoformat(),
                    "client_name": client_name,
                },
            }

        calendar_service, owned, timezone_name, calendar_id = _resolve_service()
        ctx = current_call_context.get()
        user_id = ctx.user_id if ctx is not None else voice_user_id.get()
        if user_id is None:
            raise ValueError("user_id is required for calendar tools")
        effective_call_sid = call_sid or (ctx.call_sid if ctx is not None else None)

        key = build_appointment_idempotency_key(
            user_id=user_id,
            calendar_id=calendar_id,
            start_utc=datetime_start,
            end_utc=datetime_end,
            summary=summary,
            call_sid=effective_call_sid,
        )
        existing = appointments_service.get_by_idempotency_key(calendar_service.db, key)
        if existing is not None and existing.user_id == user_id:
            return {
                "success": True,
                "idempotent": True,
                "appointment_id": existing.id,
                "event_id": existing.google_calendar_event_id,
                "html_link": existing.google_calendar_link,
                "summary": existing.summary,
                "start_time": existing.start_datetime.isoformat(),
                "end_time": existing.end_datetime.isoformat(),
                "message": "Appointment already exists (idempotent replay)",
            }

        event = calendar_service.create_event(
            summary=summary,
            datetime_start=datetime_start.isoformat(),
            datetime_end=datetime_end.isoformat(),
            description=description or f"Appointment: {summary}",
            timezone=timezone_name,
            calendar_id=calendar_id,
        )
        appointment = appointments_service.create_appointment(
            calendar_service.db,
            user_id,
            summary=summary,
            start_datetime=datetime_start,
            end_datetime=datetime_end,
            timezone=timezone_name,
            description=description,
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            calendar_id=calendar_id,
            call_sid=effective_call_sid,
            idempotency_key=key,
            google_calendar_event_id=event.get("id"),
            google_calendar_link=event.get("htmlLink"),
            status="confirmed",
        )
        from app.core.cache import invalidate_user_calendar_caches

        invalidate_user_calendar_caches(user_id)
        return {
            "success": True,
            "idempotent": False,
            "appointment_id": appointment.id,
            "event_id": event.get("id"),
            "html_link": event.get("htmlLink"),
            "summary": event.get("summary"),
            "start_time": event["start"].get("dateTime"),
            "end_time": event["end"].get("dateTime"),
            "message": "Appointment created and saved",
        }
    except Exception as e:
        logging.error("Error creating calendar event: %s", e.__class__.__name__)
        if owned is not None:
            owned.rollback()
        return {"error": f"Failed to create appointment: {str(e)}", "success": False}
    finally:
        _record_calendar_latency("create", started)
        if owned is not None:
            owned.close()


def reschedule_appointment(
    event_id=None,
    new_datetime_start=None,
    new_datetime_end=None,
    reason=None,
    confirmed=False,
    **_kwargs,
):
    """Reschedule by verified event_id only. Rejects approximate first-match flows."""
    owned = None
    try:
        if _kwargs.get("original_datetime") and not event_id:
            return {
                "success": False,
                "error": (
                    "Reschedule by approximate timestamp is not allowed. "
                    "Call find_appointments, pick an event_id, then reschedule."
                ),
            }
        if not event_id:
            return {"success": False, "error": "event_id is required"}

        new_datetime_start = _parse_dt(new_datetime_start)
        new_datetime_end = _parse_dt(new_datetime_end)
        if new_datetime_start is None or new_datetime_end is None:
            return {
                "success": False,
                "error": "new_datetime_start and new_datetime_end are required",
            }

        calendar_service, owned, timezone_name, calendar_id = _resolve_service()
        existing = (
            calendar_service.service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
        summary = existing.get("summary", "Appointment")
        old_start = existing["start"].get("dateTime") or existing["start"].get("date")

        if not _as_bool(confirmed):
            return {
                "success": False,
                "needs_confirmation": True,
                "confirmation_prompt": (
                    f"I can move '{summary}' (event_id={event_id}) from {old_start} "
                    f"to {_format_local(new_datetime_start)}. Should I reschedule it?"
                ),
                "pending": {
                    "event_id": event_id,
                    "summary": summary,
                    "new_datetime_start": new_datetime_start.isoformat(),
                    "new_datetime_end": new_datetime_end.isoformat(),
                },
            }

        updated_event = calendar_service.update_event(
            event_id=event_id,
            datetime_start=new_datetime_start.isoformat(),
            datetime_end=new_datetime_end.isoformat(),
            timezone=timezone_name,
            calendar_id=calendar_id,
        )
        if reason:
            current_description = updated_event.get("description", "") or ""
            calendar_service.update_event(
                event_id=event_id,
                description=f"{current_description}\n\nRescheduled: {reason}".strip(),
                calendar_id=calendar_id,
            )

        _sync_local_appointment(
            calendar_service.db,
            event_id=event_id,
            start=new_datetime_start,
            end=new_datetime_end,
            status="confirmed",
        )
        from app.core.cache import invalidate_user_calendar_caches
        from app.voice.context import current_call_context as _ctx

        c = _ctx.get()
        if c is not None:
            invalidate_user_calendar_caches(c.user_id)
        return {
            "success": True,
            "event_id": updated_event.get("id"),
            "original_time": old_start,
            "new_time": new_datetime_start.isoformat(),
            "message": "Appointment successfully rescheduled",
        }
    except Exception as e:
        logging.error("Error rescheduling appointment: %s", e)
        return {
            "error": f"Failed to reschedule appointment: {str(e)}",
            "success": False,
        }
    finally:
        if owned is not None:
            owned.close()


def cancel_appointment(event_id=None, reason=None, confirmed=False, **_kwargs):
    """Cancel by verified event_id only. Never picks the closest timestamp match."""
    owned = None
    try:
        if _kwargs.get("datetime_start") and not event_id:
            return {
                "success": False,
                "error": (
                    "Cancel by approximate timestamp is not allowed. "
                    "Call find_appointments, pick an event_id, then cancel."
                ),
            }
        if not event_id:
            return {"success": False, "error": "event_id is required"}

        calendar_service, owned, _timezone, calendar_id = _resolve_service()
        existing = (
            calendar_service.service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
        summary = existing.get("summary", "Unknown appointment")
        start = existing["start"].get("dateTime") or existing["start"].get("date")

        if not _as_bool(confirmed):
            return {
                "success": False,
                "needs_confirmation": True,
                "confirmation_prompt": (
                    f"I found '{summary}' at {start} (event_id={event_id}). "
                    "Should I cancel it?"
                ),
                "pending": {
                    "event_id": event_id,
                    "summary": summary,
                    "start_time": start,
                },
            }

        success = calendar_service.delete_event(event_id, calendar_id=calendar_id)
        if not success:
            return {
                "success": False,
                "error": "Failed to cancel the appointment",
                "appointment": summary,
            }

        _sync_local_appointment(
            calendar_service.db,
            event_id=event_id,
            status="cancelled",
        )
        from app.core.cache import invalidate_user_calendar_caches
        from app.voice.context import current_call_context as _ctx

        c = _ctx.get()
        if c is not None:
            invalidate_user_calendar_caches(c.user_id)
        result = {
            "success": True,
            "event_id": event_id,
            "cancelled_appointment": summary,
            "original_time": start,
            "message": f"Appointment '{summary}' has been successfully cancelled",
        }
        if reason:
            result["cancellation_reason"] = reason
            result["message"] += f". Reason: {reason}"
        return result
    except Exception as e:
        logging.error("Error cancelling appointment: %s", e)
        return {
            "error": f"Failed to cancel appointment: {str(e)}",
            "success": False,
        }
    finally:
        if owned is not None:
            owned.close()


def _sync_local_appointment(
    db: Session,
    *,
    event_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    status: str | None = None,
) -> None:
    row = db.scalar(
        select(Appointment).where(Appointment.google_calendar_event_id == event_id)
    )
    if row is None:
        return
    if start is not None:
        row.start_datetime = start
    if end is not None:
        row.end_datetime = end
    if status is not None:
        row.status = status
    db.commit()


def generate_alternative_slots(
    original_start,
    original_end,
    calendar_service,
    num_alternatives=3,
    *,
    calendar_id: str = "primary",
):
    """Fetch busy once, then evaluate candidates locally (Phase 9.2)."""
    try:
        duration = original_end - original_start
        offsets = [1, 2, 3, -1, -2, 24]
        candidates = []
        for hours_offset in offsets:
            alternative_start = original_start + timedelta(hours=hours_offset)
            alternative_end = alternative_start + duration
            candidates.append((alternative_start, alternative_end))

        window_start = min(c[0] for c in candidates).isoformat()
        window_end = max(c[1] for c in candidates).isoformat()
        busy = calendar_service.get_busy_intervals(
            window_start, window_end, calendar_id=calendar_id
        )

        def _free(start: datetime, end: datetime) -> bool:
            from app.calendars.providers.google import _overlaps

            s, e = start.isoformat(), end.isoformat()
            return not any(_overlaps(s, e, b["start"], b["end"]) for b in busy)

        alternatives = []
        for alternative_start, alternative_end in candidates:
            if not _free(alternative_start, alternative_end):
                continue
            alternatives.append(
                {
                    "start": alternative_start.isoformat(),
                    "end": alternative_end.isoformat(),
                    "message": f"Available at {alternative_start.strftime('%I:%M %p')}",
                }
            )
            if len(alternatives) >= num_alternatives:
                break
        return alternatives
    except Exception as e:
        logging.error("Error generating alternative slots: %s", e)
        return []


FUNCTION_MAP: dict[str, Callable[..., dict[str, Any]]] = {
    "check_calendar_availability": check_calendar_availability,
    "find_appointments": find_appointments,
    "create_calendar_event": create_calendar_event,
    "reschedule_appointment": reschedule_appointment,
    "cancel_appointment": cancel_appointment,
    "get_appointment_details": get_appointment_details,
}

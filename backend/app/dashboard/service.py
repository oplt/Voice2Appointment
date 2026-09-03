"""Dashboard summary from DB (no Google round-trips required)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calendars.service import calendar_status
from app.db.models import Appointment, CallSession


def dashboard_summary(db: Session, user_id: int) -> dict[str, Any]:
    from app.core.cache import cache_get, cache_set

    cache_key = f"dashboard:summary:{user_id}"
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    week_end = today_start + timedelta(days=7)

    appointments_today = (
        db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.user_id == user_id,
                Appointment.start_datetime >= today_start,
                Appointment.start_datetime < today_end,
            )
        )
        or 0
    )
    appointments_week = (
        db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.user_id == user_id,
                Appointment.start_datetime >= today_start,
                Appointment.start_datetime < week_end,
            )
        )
        or 0
    )
    recent_calls = (
        db.scalar(
            select(func.count())
            .select_from(CallSession)
            .where(
                CallSession.user_id == user_id,
                CallSession.started_at >= today_start - timedelta(days=7),
            )
        )
        or 0
    )

    upcoming_rows = list(
        db.scalars(
            select(Appointment)
            .where(
                Appointment.user_id == user_id,
                Appointment.start_datetime >= now,
                Appointment.status != "cancelled",
            )
            .order_by(Appointment.start_datetime.asc())
            .limit(10)
        ).all()
    )
    upcoming = [
        {
            "id": a.id,
            "summary": a.summary,
            "start_datetime": a.start_datetime.isoformat(),
            "end_datetime": a.end_datetime.isoformat(),
            "status": a.status,
            "client_name": a.client_name,
        }
        for a in upcoming_rows
    ]

    cal = calendar_status(db, user_id)
    payload = {
        "appointments_today": int(appointments_today),
        "appointments_week": int(appointments_week),
        "upcoming": upcoming,
        "calendar_connected": bool(cal.get("connected")),
        "recent_calls": int(recent_calls),
        "call_statistics": {"recent_calls": int(recent_calls)},
    }
    cache_set(cache_key, payload, ttl_seconds=45)
    return payload

"""Operational dashboard KPIs (P5-01) from CallSession + Appointment lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.calendars.service import calendar_status, get_auth_record
from app.core.config import settings
from app.db.models import Appointment, CallSession, User

_ACTIVE_APPOINTMENT = Appointment.status.notin_(("cancelled", "canceled", "failed"))

# Terminal outcomes that count toward completion (answered + clean end).
_COMPLETED_OUTCOMES = frozenset({"completed", "booked"})
# Attention / failure bucket (no sensitive provider text).
_ATTENTION_OUTCOMES = frozenset({"failed", "expired", "rejected"})
_ATTENTION_STATUSES = frozenset({"provider_error", "expired", "rejected"})
# Rejected before engagement are excluded from completion denominator.
_EXCLUDE_FROM_COMPLETION = frozenset({"rejected"})


def _tenant_zone(db: Session, user_id: int) -> ZoneInfo:
    auth = get_auth_record(db, user_id)
    name = (
        (auth.time_zone if auth and auth.time_zone else None)
        or settings.default_timezone
        or "UTC"
    )
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _kpi(
    *,
    value: Any,
    definition: str,
    window: str,
    timezone_name: str,
    drill_down: str,
    exclusions: str,
    numerator: int | None = None,
    denominator: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "value": value,
        "definition": definition,
        "window": window,
        "timezone": timezone_name,
        "drill_down": drill_down,
        "exclusions": exclusions,
    }
    if numerator is not None:
        payload["numerator"] = numerator
    if denominator is not None:
        payload["denominator"] = denominator
    return payload


def dashboard_summary(
    db: Session, user_id: int, *, now: datetime | None = None
) -> dict[str, Any]:
    from app.core.cache import (
        CACHE_TTL_DASHBOARD,
        cache_get,
        cache_set,
        durable_versioned_key,
    )

    cache_key = durable_versioned_key(db, user_id, "dashboard", "summary")
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    zone = _tenant_zone(db, user_id)
    tz_name = str(zone)
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(zone)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = local_midnight.astimezone(timezone.utc)
    today_end = (local_midnight + timedelta(days=1)).astimezone(timezone.utc)
    week_end = (local_midnight + timedelta(days=7)).astimezone(timezone.utc)
    calls_start = today_start - timedelta(days=7)

    start_counts = db.execute(
        select(
            func.count().filter(Appointment.start_datetime < today_end).label("today"),
            func.count().label("week"),
        )
        .select_from(Appointment)
        .where(
            Appointment.user_id == user_id,
            Appointment.start_datetime >= today_start,
            Appointment.start_datetime < week_end,
            _ACTIVE_APPOINTMENT,
        )
    ).one()
    booked_today = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.user_id == user_id,
            Appointment.created_at >= today_start,
            Appointment.created_at < today_end,
            Appointment.status.in_(("pending", "confirmed", "completed")),
        )
    ) or 0

    call_stats = db.execute(
        select(
            func.count().label("calls_today"),
            func.coalesce(
                func.sum(
                    case(
                        (CallSession.outcome.in_(tuple(_COMPLETED_OUTCOMES)), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("completed_today"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            CallSession.outcome.is_not(None)
                            & CallSession.outcome.notin_(tuple(_EXCLUDE_FROM_COMPLETION)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("completion_denom"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            CallSession.outcome.in_(tuple(_ATTENTION_OUTCOMES))
                            | CallSession.status.in_(tuple(_ATTENTION_STATUSES)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("attention_today"),
        )
        .select_from(CallSession)
        .where(
            CallSession.user_id == user_id,
            CallSession.started_at >= today_start,
            CallSession.started_at < today_end,
        )
    ).one()

    recent_calls = (
        db.scalar(
            select(func.count())
            .select_from(CallSession)
            .where(
                CallSession.user_id == user_id,
                CallSession.started_at >= calls_start,
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
                _ACTIVE_APPOINTMENT,
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
    user = db.get(User, user_id)
    calls_today = int(call_stats.calls_today or 0)
    completed_today = int(call_stats.completed_today or 0)
    completion_denom = int(call_stats.completion_denom or 0)
    attention_today = int(call_stats.attention_today or 0)
    completion_rate = (
        round(completed_today / completion_denom, 4) if completion_denom else None
    )

    provider_status = {
        "twilio": bool(user and user.twilio_account_sid and user.twilio_auth_token),
        "deepgram": bool((settings.deepgram_api_key or "").strip()),
        "calendar": bool(cal.get("connected")),
    }
    twilio_synced = (
        user.twilio_last_synced_at.isoformat()
        if user and user.twilio_last_synced_at
        else None
    )

    operational = {
        "calls_today": _kpi(
            value=calls_today,
            definition="Count of CallSession rows whose started_at falls in the tenant-local calendar day.",
            window="local_day",
            timezone_name=tz_name,
            drill_down="/calls",
            exclusions="None; rejected pre-connect calls still count as started.",
        ),
        "completion_rate": _kpi(
            value=completion_rate,
            numerator=completed_today,
            denominator=completion_denom,
            definition="Share of today's calls with outcome in {completed, booked} among calls that have a non-null outcome other than rejected.",
            window="local_day",
            timezone_name=tz_name,
            drill_down="/calls",
            exclusions="outcome=rejected excluded from denominator; null outcome excluded until lifecycle closes.",
        ),
        "appointments_booked_today": _kpi(
            value=int(booked_today),
            definition="Appointments created today (tenant-local) with status pending/confirmed/completed.",
            window="local_day",
            timezone_name=tz_name,
            drill_down="/appointments",
            exclusions="cancelled/failed creations excluded.",
        ),
        "attention_needed": _kpi(
            value=attention_today,
            definition="Today's calls with outcome in {failed, expired, rejected} or status in {provider_error, expired, rejected}.",
            window="local_day",
            timezone_name=tz_name,
            drill_down="/calls",
            exclusions="No transcript/provider error text is exposed—counts only.",
        ),
        "upcoming_appointments": _kpi(
            value=len(upcoming),
            definition="Next active appointments with start_datetime >= now (capped list of 10).",
            window="forward",
            timezone_name=tz_name,
            drill_down="/appointments",
            exclusions="cancelled/canceled/failed statuses excluded.",
        ),
        "appointments_today": _kpi(
            value=int(start_counts.today),
            definition="Active appointments whose start falls in the tenant-local day.",
            window="local_day",
            timezone_name=tz_name,
            drill_down="/appointments",
            exclusions="cancelled/canceled/failed excluded.",
        ),
    }

    payload = {
        "appointments_today": int(start_counts.today),
        "appointments_week": int(start_counts.week),
        "upcoming": upcoming,
        "calendar_connected": bool(cal.get("connected")),
        "recent_calls": int(recent_calls),
        "call_statistics": {
            "recent_calls": int(recent_calls),
            "calls_today": calls_today,
            "completed_today": completed_today,
            "attention_today": attention_today,
            "completion_rate": completion_rate,
        },
        "provider_status": provider_status,
        "integrations": {
            **provider_status,
            "twilio_last_synced_at": twilio_synced,
            "calendar_account": cal.get("account_email"),
        },
        "operational": operational,
        "timezone": tz_name,
        "generated_at": now.isoformat(),
        "freshness": {
            "generated_at": now.isoformat(),
            "source_synced_at": twilio_synced,
            "stale": bool(
                user
                and user.twilio_last_synced_at
                and (now - user.twilio_last_synced_at) > timedelta(hours=48)
            )
            if user and user.twilio_last_synced_at
            else (provider_status["twilio"] and twilio_synced is None),
        },
    }
    cache_set(cache_key, payload, ttl_seconds=CACHE_TTL_DASHBOARD)
    return payload

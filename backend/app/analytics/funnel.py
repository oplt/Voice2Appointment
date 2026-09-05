"""Call booking-funnel aggregation from CallSession + Appointment (P5-02/P5-V06)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Appointment, BookingFunnelEvent, CallSession

# Ordered funnel stages — each call counted at most once per stage.
FUNNEL_STAGES = (
    "started",
    "engaged",
    "booking_attempted",
    "booked",
    "rescheduled",
    "cancelled",
    "failed",
    "unknown",
)

_ENGAGED_OUTCOMES = frozenset(
    {"completed", "booked", "failed", "disconnected", "expired"}
)
_ENGAGED_STATUSES = frozenset(
    {"connected", "completed", "disconnected", "provider_error", "expired"}
)
_FAILED_OUTCOMES = frozenset({"failed", "expired", "rejected"})
_FAILED_STATUSES = frozenset({"provider_error", "expired", "rejected"})
_BOOKED_APPT = frozenset({"pending", "confirmed", "completed"})
_CANCELLED_APPT = frozenset({"cancelled", "canceled"})
_PUBLIC_FAILURE_CODES = frozenset({"failed", "expired", "rejected", "provider_error"})


def _inclusive_start(start: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc)


def _exclusive_end(end: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(
        timezone.utc
    )


def _failure_category(terminal_reason: str | None, outcome: str | None) -> str:
    if outcome in _PUBLIC_FAILURE_CODES:
        return outcome
    return "unknown"


def record_funnel_event(
    db: Session,
    *,
    user_id: int,
    call_session_id: int | None,
    stage: str,
    idempotency_key: str,
    reason_code: str = "unknown",
) -> None:
    """Append one public, idempotent event in the caller transaction."""
    if stage not in FUNNEL_STAGES:
        raise ValueError("invalid funnel stage")
    public_reason = reason_code if reason_code in _PUBLIC_FAILURE_CODES else "unknown"
    try:
        with db.begin_nested():
            db.add(
                BookingFunnelEvent(
                    user_id=user_id,
                    call_session_id=call_session_id,
                    stage=stage,
                    reason_code=public_reason,
                    idempotency_key=idempotency_key,
                )
            )
    except IntegrityError:
        pass


def link_call_session_on_book(
    db: Session,
    *,
    user_id: int,
    call_sid: str | None,
    appointment: Appointment,
) -> None:
    """Attach appointment to CallSession and mark outcome booked (idempotent)."""
    if not call_sid or appointment.callsession_id:
        return
    cs = db.scalar(
        select(CallSession).where(
            CallSession.user_id == user_id,
            CallSession.call_sid == call_sid,
        )
    )
    if cs is None:
        return
    appointment.callsession_id = cs.id
    if cs.outcome in (None, "completed", "unknown", ""):
        cs.outcome = "booked"
    record_funnel_event(
        db,
        user_id=user_id,
        call_session_id=cs.id,
        stage="booking_attempted",
        idempotency_key=f"book-attempt:{appointment.id}",
    )
    record_funnel_event(
        db,
        user_id=user_id,
        call_session_id=cs.id,
        stage="booked",
        idempotency_key=f"booked:{appointment.id}",
    )


def funnel_summary(
    db: Session,
    user_id: int,
    *,
    start: date,
    end: date,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    """SQL-aggregated funnel counts for CallSessions started in [start, end]."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"

    bound_start = _inclusive_start(start, zone)
    bound_end = _exclusive_end(end, zone)

    # Prefer durable BookingFunnelEvent counts when events exist for the window.
    event_rows = db.execute(
        select(BookingFunnelEvent.stage, func.count().label("n"))
        .where(
            BookingFunnelEvent.user_id == user_id,
            BookingFunnelEvent.occurred_at >= bound_start,
            BookingFunnelEvent.occurred_at < bound_end,
            BookingFunnelEvent.stage.in_(
                ("booking_attempted", "booked", "rescheduled", "cancelled", "failed")
            ),
        )
        .group_by(BookingFunnelEvent.stage)
    ).all()
    event_counts = {str(r.stage): int(r.n) for r in event_rows}
    use_events = bool(event_counts)

    appt = Appointment
    cs = CallSession
    engaged = case(
        (
            cs.outcome.in_(tuple(_ENGAGED_OUTCOMES))
            | cs.status.in_(tuple(_ENGAGED_STATUSES))
            | (func.coalesce(cs.duration_seconds, 0) > 0)
            | appt.id.is_not(None),
            1,
        ),
        else_=0,
    )
    booking_attempted = case(
        (appt.id.is_not(None) | (cs.outcome == "booked"), 1),
        else_=0,
    )
    booked = case(
        (
            (
                appt.status.in_(tuple(_BOOKED_APPT))
                & ~appt.status.in_(tuple(_CANCELLED_APPT))
            )
            | (cs.outcome == "booked"),
            1,
        ),
        else_=0,
    )
    cancelled = case((appt.status.in_(tuple(_CANCELLED_APPT)), 1), else_=0)
    failed = case(
        (
            cs.outcome.in_(tuple(_FAILED_OUTCOMES))
            | cs.status.in_(tuple(_FAILED_STATUSES)),
            1,
        ),
        else_=0,
    )
    unknown = case(
        (
            (
                cs.outcome.is_(None)
                & appt.id.is_(None)
                & (
                    cs.status.is_(None)
                    | cs.status.in_(("active", "connected"))
                )
            )
            | (cs.outcome.is_(None) & (engaged == 0)),
            1,
        ),
        else_=0,
    )

    agg = db.execute(
        select(
            func.count(cs.id).label("started"),
            func.coalesce(func.sum(engaged), 0).label("engaged"),
            func.coalesce(func.sum(booking_attempted), 0).label("booking_attempted"),
            func.coalesce(func.sum(booked), 0).label("booked"),
            func.coalesce(func.sum(cancelled), 0).label("cancelled"),
            func.coalesce(func.sum(failed), 0).label("failed"),
            func.coalesce(func.sum(unknown), 0).label("unknown"),
        )
        .select_from(cs)
        .outerjoin(appt, appt.callsession_id == cs.id)
        .where(
            cs.user_id == user_id,
            cs.started_at >= bound_start,
            cs.started_at < bound_end,
        )
    ).one()

    counts = {
        "started": int(agg.started or 0),
        "engaged": int(agg.engaged or 0),
        "booking_attempted": int(agg.booking_attempted or 0),
        "booked": int(agg.booked or 0),
        "rescheduled": int(event_counts.get("rescheduled", 0)) if use_events else 0,
        "cancelled": int(agg.cancelled or 0),
        "failed": int(agg.failed or 0),
        "unknown": int(agg.unknown or 0),
    }
    if use_events:
        for stage in ("booking_attempted", "booked", "cancelled", "failed"):
            if stage in event_counts:
                counts[stage] = max(counts[stage], event_counts[stage])

    failure_rows = db.execute(
        select(cs.outcome, func.count().label("n"))
        .where(
            cs.user_id == user_id,
            cs.started_at >= bound_start,
            cs.started_at < bound_end,
            cs.outcome.in_(tuple(_PUBLIC_FAILURE_CODES)),
        )
        .group_by(cs.outcome)
    ).all()
    failure_buckets = {
        _failure_category(None, str(r.outcome)): int(r.n) for r in failure_rows
    }

    stages = [
        {
            "id": stage,
            "label": stage.replace("_", " ").title(),
            "count": counts[stage],
        }
        for stage in FUNNEL_STAGES
        if stage != "unknown"
    ]
    stages.append({"id": "unknown", "label": "Unknown", "count": counts["unknown"]})

    failures = [
        {"code": code, "count": n}
        for code, n in sorted(failure_buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "stages": stages,
        "failure_categories": failures,
        "timezone": timezone_name,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "definitions": {
            "started": "Every CallSession with started_at in range (one row per call).",
            "engaged": "Connected/completed/disconnected/failed/expired, duration>0, or linked appointment.",
            "booking_attempted": "Call linked to an Appointment or outcome=booked (idempotent link).",
            "booked": "Linked appointment pending/confirmed/completed, or outcome=booked.",
            "cancelled": "Linked appointment cancelled/canceled.",
            "failed": "outcome/status in failed/expired/rejected/provider_error.",
            "unknown": "No durable outcome and not engaged.",
        },
        "source": "sql_aggregate",
    }

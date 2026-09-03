"""Call booking-funnel aggregation from CallSession + Appointment (P5-02)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Appointment, CallSession

# Ordered funnel stages — each call counted at most once per stage.
FUNNEL_STAGES = (
    "started",
    "engaged",
    "booking_attempted",
    "booked",
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


def _inclusive_start(start: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc)


def _exclusive_end(end: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(
        timezone.utc
    )


def _failure_category(terminal_reason: str | None, outcome: str | None) -> str:
    if terminal_reason:
        prefix = terminal_reason.split(":", 1)[0].strip().lower()
        if prefix:
            return prefix[:32]
    if outcome in _FAILED_OUTCOMES:
        return outcome
    return "unknown"


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


def funnel_summary(
    db: Session,
    user_id: int,
    *,
    start: date,
    end: date,
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    """Aggregate funnel counts for CallSessions started in [start, end] local dates."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"

    bound_start = _inclusive_start(start, zone)
    bound_end = _exclusive_end(end, zone)

    stmt = (
        select(
            CallSession.id,
            CallSession.outcome,
            CallSession.status,
            CallSession.terminal_reason,
            CallSession.duration_seconds,
            Appointment.status.label("appt_status"),
            Appointment.id.label("appt_id"),
        )
        .select_from(CallSession)
        .outerjoin(Appointment, Appointment.callsession_id == CallSession.id)
        .where(
            CallSession.user_id == user_id,
            CallSession.started_at >= bound_start,
            CallSession.started_at < bound_end,
        )
    )
    rows = list(db.execute(stmt).all())

    counts = {stage: 0 for stage in FUNNEL_STAGES}
    failure_buckets: dict[str, int] = {}

    for row in rows:
        counts["started"] += 1
        outcome = (row.outcome or "").strip() or None
        status = (row.status or "").strip() or None
        appt_status = (row.appt_status or "").strip() or None
        has_appt = row.appt_id is not None
        duration = row.duration_seconds or 0

        engaged = (
            outcome in _ENGAGED_OUTCOMES
            or status in _ENGAGED_STATUSES
            or duration > 0
            or has_appt
        )
        if engaged:
            counts["engaged"] += 1

        booking_attempted = has_appt or outcome == "booked"
        if booking_attempted:
            counts["booking_attempted"] += 1

        booked = (appt_status in _BOOKED_APPT) or outcome == "booked"
        if booked and appt_status not in _CANCELLED_APPT:
            counts["booked"] += 1

        if appt_status in _CANCELLED_APPT:
            counts["cancelled"] += 1

        failed = outcome in _FAILED_OUTCOMES or status in _FAILED_STATUSES
        if failed:
            counts["failed"] += 1
            cat = _failure_category(row.terminal_reason, outcome)
            failure_buckets[cat] = failure_buckets.get(cat, 0) + 1

        if outcome is None and not has_appt and status in (None, "active", "connected"):
            counts["unknown"] += 1
        elif outcome is None and not engaged:
            counts["unknown"] += 1

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
            "failed": "outcome in {failed,expired,rejected} or status provider_error/expired/rejected.",
            "unknown": "No outcome yet and not engaged; historical rows without lifecycle data.",
            "attribution": "Appointment.callsession_id unique — retries reuse the same appointment via idempotency_key.",
        },
    }

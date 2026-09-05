"""CallSession lifecycle transitions (P2-01)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CallSession

logger = logging.getLogger(__name__)

STATUS_ACTIVE = "active"
STATUS_CONNECTED = "connected"
STATUS_COMPLETED = "completed"
STATUS_DISCONNECTED = "disconnected"
STATUS_REJECTED = "rejected"
STATUS_PROVIDER_ERROR = "provider_error"
STATUS_EXPIRED = "expired"

TERMINAL_STATUSES = frozenset(
    {
        STATUS_COMPLETED,
        STATUS_DISCONNECTED,
        STATUS_REJECTED,
        STATUS_PROVIDER_ERROR,
        STATUS_EXPIRED,
    }
)

_ALLOWED: dict[str, frozenset[str]] = {
    STATUS_ACTIVE: frozenset(
        {
            STATUS_CONNECTED,
            STATUS_REJECTED,
            STATUS_EXPIRED,
            STATUS_DISCONNECTED,
            STATUS_PROVIDER_ERROR,
            STATUS_COMPLETED,
        }
    ),
    STATUS_CONNECTED: frozenset(
        {
            STATUS_COMPLETED,
            STATUS_DISCONNECTED,
            STATUS_PROVIDER_ERROR,
            STATUS_EXPIRED,
        }
    ),
    # A provider error is the strongest terminal outcome. It may supersede a
    # generic clean/disconnected/expired result that raced it, but cannot be
    # erased by a later success callback.
    STATUS_DISCONNECTED: frozenset(
        {STATUS_COMPLETED, STATUS_DISCONNECTED, STATUS_PROVIDER_ERROR}
    ),
    STATUS_COMPLETED: frozenset({STATUS_COMPLETED, STATUS_PROVIDER_ERROR}),
    STATUS_REJECTED: frozenset({STATUS_REJECTED}),
    STATUS_PROVIDER_ERROR: frozenset({STATUS_PROVIDER_ERROR}),
    STATUS_EXPIRED: frozenset(
        {STATUS_EXPIRED, STATUS_COMPLETED, STATUS_PROVIDER_ERROR}
    ),
}

_MAX_TRANSCRIPT_CHARS = 32_000

_TWILIO_STATUS_MAP = {
    "completed": (STATUS_COMPLETED, "completed"),
    "busy": (STATUS_COMPLETED, "busy"),
    "no-answer": (STATUS_COMPLETED, "no_answer"),
    "failed": (STATUS_PROVIDER_ERROR, "failed"),
    "canceled": (STATUS_DISCONNECTED, "cancelled"),
    "cancelled": (STATUS_DISCONNECTED, "cancelled"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_terminal(status: str | None) -> bool:
    return (status or "") in TERMINAL_STATUSES


def _bound_transcript(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    if len(cleaned) > _MAX_TRANSCRIPT_CHARS:
        return cleaned[:_MAX_TRANSCRIPT_CHARS] + "\n…[truncated]"
    return cleaned


def transition_call_session(
    db: Session,
    *,
    call_sid: str,
    user_id: int | None = None,
    new_status: str,
    terminal_reason: str | None = None,
    outcome: str | None = None,
    transcript: str | None = None,
    duration_seconds: int | None = None,
    ended_at: datetime | None = None,
    extra_data: dict[str, Any] | None = None,
) -> CallSession | None:
    """Idempotent, serialized lifecycle transition.

    ``user_id`` scopes externally initiated transitions to their authenticated
    tenant.  The lock makes state validation and the resulting write one
    critical section on PostgreSQL.
    """
    query = select(CallSession).where(CallSession.call_sid == call_sid)
    if user_id is not None:
        query = query.where(CallSession.user_id == user_id)
    cs = db.scalar(query.with_for_update())
    if cs is None:
        return None

    current = cs.status or STATUS_ACTIVE
    if new_status == current and is_terminal(current):
        # Harmless replay — optionally fill missing fields.
        changed = False
        if transcript and not cs.transcript:
            cs.transcript = _bound_transcript(transcript)
            changed = True
        if outcome and not cs.outcome:
            cs.outcome = outcome
            changed = True
        if duration_seconds is not None and cs.duration_seconds is None:
            cs.duration_seconds = max(0, int(duration_seconds))
            changed = True
        if extra_data:
            merged = dict(cs.data or {})
            merged.update(extra_data)
            if merged != (cs.data or {}):
                cs.data = merged
                changed = True
        if changed:
            db.commit()
            db.refresh(cs)
        return cs

    allowed = _ALLOWED.get(current, frozenset())
    if new_status not in allowed:
        logger.info(
            "Ignoring call lifecycle transition call_sid=%s %s -> %s",
            call_sid,
            current,
            new_status,
        )
        return cs

    cs.status = new_status
    if terminal_reason:
        cs.terminal_reason = terminal_reason[:64]
    if outcome:
        cs.outcome = outcome[:32]
    if transcript is not None:
        cs.transcript = _bound_transcript(transcript)
    if is_terminal(new_status):
        end = ended_at or _utcnow()
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        cs.ended_at = end
        if duration_seconds is not None:
            cs.duration_seconds = max(0, int(duration_seconds))
        elif cs.started_at is not None:
            started = cs.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            cs.duration_seconds = max(0, int((end - started).total_seconds()))
    if extra_data:
        merged = dict(cs.data or {})
        merged.update(extra_data)
        cs.data = merged
    db.add(cs)
    db.commit()
    db.refresh(cs)
    try:
        from app.core.metrics import metrics

        metrics.incr("call_transitions", labels={"status": new_status})
    except Exception:  # noqa: BLE001
        pass
    return cs


def mark_connected(db: Session, call_sid: str) -> CallSession | None:
    return transition_call_session(db, call_sid=call_sid, new_status=STATUS_CONNECTED)


def finalize_voice_session(
    db: Session,
    *,
    call_sid: str,
    status: str,
    terminal_reason: str,
    transcript: str | None = None,
    transcript_metadata: dict[str, Any] | None = None,
    outcome: str | None = None,
) -> CallSession | None:
    return transition_call_session(
        db,
        call_sid=call_sid,
        new_status=status,
        terminal_reason=terminal_reason,
        transcript=transcript,
        outcome=outcome or "unknown",
        extra_data=(
            {"transcript_capture": transcript_metadata}
            if transcript_metadata is not None
            else None
        ),
    )


def apply_twilio_status_callback(
    db: Session,
    payload: dict[str, str],
    *,
    user_id: int,
) -> dict[str, Any]:
    call_sid = (payload.get("CallSid") or "").strip()
    if not call_sid:
        return {"ok": False, "error": "missing CallSid"}
    raw_status = (payload.get("CallStatus") or "").strip().lower()
    mapped_status = _TWILIO_STATUS_MAP.get(raw_status)
    if mapped_status is None:
        return {"ok": True, "ignored": True, "status": raw_status}

    duration_raw = payload.get("CallDuration") or payload.get("Duration")
    duration: int | None = None
    if duration_raw:
        try:
            duration = max(0, int(duration_raw))
        except ValueError:
            duration = None

    status, outcome = mapped_status
    cs = transition_call_session(
        db,
        call_sid=call_sid,
        user_id=user_id,
        new_status=status,
        terminal_reason=f"twilio:{raw_status}",
        outcome=outcome,
        duration_seconds=duration,
        extra_data={"twilio_call_status": raw_status},
    )
    if cs is None:
        return {"ok": False, "error": "unknown call"}
    return {"ok": True, "status": cs.status}


def reconcile_expired_calls(db: Session, *, limit: int = 100) -> dict[str, Any]:
    """Mark stale nonterminal CallSessions as expired."""
    now = _utcnow()
    rows = list(
        db.scalars(
            select(CallSession)
            .where(
                CallSession.status.notin_(tuple(TERMINAL_STATUSES)),
                CallSession.expires_at.is_not(None),
                CallSession.expires_at < now,
            )
            .limit(limit)
        ).all()
    )
    marked = 0
    for row in rows:
        transition_call_session(
            db,
            call_sid=row.call_sid,
            new_status=STATUS_EXPIRED,
            terminal_reason="reconcile:expired",
            outcome="expired",
        )
        marked += 1
    return {"ok": True, "marked": marked}

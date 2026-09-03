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
    # Terminal states only accept identical re-entry (idempotent) or completed
    # after disconnected when Twilio reports a clean hangup.
    STATUS_DISCONNECTED: frozenset({STATUS_COMPLETED, STATUS_DISCONNECTED}),
    STATUS_COMPLETED: frozenset({STATUS_COMPLETED}),
    STATUS_REJECTED: frozenset({STATUS_REJECTED}),
    STATUS_PROVIDER_ERROR: frozenset({STATUS_PROVIDER_ERROR, STATUS_COMPLETED}),
    STATUS_EXPIRED: frozenset({STATUS_EXPIRED, STATUS_COMPLETED}),
}

_MAX_TRANSCRIPT_CHARS = 32_000

_TWILIO_STATUS_MAP = {
    "completed": STATUS_COMPLETED,
    "busy": STATUS_COMPLETED,
    "no-answer": STATUS_COMPLETED,
    "failed": STATUS_PROVIDER_ERROR,
    "canceled": STATUS_DISCONNECTED,
    "cancelled": STATUS_DISCONNECTED,
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
    new_status: str,
    terminal_reason: str | None = None,
    outcome: str | None = None,
    transcript: str | None = None,
    duration_seconds: int | None = None,
    ended_at: datetime | None = None,
    extra_data: dict[str, Any] | None = None,
) -> CallSession | None:
    """Idempotent lifecycle transition. Returns None if CallSession missing."""
    cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
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
    outcome: str | None = None,
) -> CallSession | None:
    return transition_call_session(
        db,
        call_sid=call_sid,
        new_status=status,
        terminal_reason=terminal_reason,
        transcript=transcript,
        outcome=outcome or "unknown",
    )


def apply_twilio_status_callback(
    db: Session,
    payload: dict[str, str],
) -> dict[str, Any]:
    call_sid = (payload.get("CallSid") or "").strip()
    if not call_sid:
        return {"ok": False, "error": "missing CallSid"}
    raw_status = (payload.get("CallStatus") or "").strip().lower()
    mapped = _TWILIO_STATUS_MAP.get(raw_status)
    if mapped is None:
        return {"ok": True, "ignored": True, "status": raw_status}

    duration_raw = payload.get("CallDuration") or payload.get("Duration")
    duration: int | None = None
    if duration_raw:
        try:
            duration = max(0, int(duration_raw))
        except ValueError:
            duration = None

    cs = transition_call_session(
        db,
        call_sid=call_sid,
        new_status=mapped,
        terminal_reason=f"twilio:{raw_status}",
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

"""Tenant call-session listing (P4-03)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CallSession


def _encode_cursor(started_at: datetime, call_id: int) -> str:
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    raw = f"{started_at.isoformat()}|{call_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, id_str = raw.rsplit("|", 1)
        started = datetime.fromisoformat(ts)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return started, int(id_str)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid cursor") from exc


def list_call_sessions(
    db: Session,
    user_id: int,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[CallSession], str | None]:
    limit = max(1, min(100, limit))
    stmt = (
        select(CallSession)
        .where(CallSession.user_id == user_id)
        .order_by(CallSession.started_at.desc(), CallSession.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        started, call_id = _decode_cursor(cursor)
        stmt = stmt.where(
            (CallSession.started_at < started)
            | ((CallSession.started_at == started) & (CallSession.id < call_id))
        )
    rows = list(db.scalars(stmt).all())
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        rows = rows[:limit]
        if last.started_at is not None:
            next_cursor = _encode_cursor(last.started_at, last.id)
    return rows, next_cursor


def get_call_session(
    db: Session, user_id: int, call_id: int
) -> CallSession | None:
    row = db.get(CallSession, call_id)
    if row is None or row.user_id != user_id:
        return None
    return row


def to_detail_item(row: CallSession) -> dict:
    return {
        "id": row.id,
        "call_sid": row.call_sid,
        "from_number": row.from_number,
        "to_number": row.to_number,
        "status": row.status,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_seconds": row.duration_seconds,
        "outcome": row.outcome,
        "terminal_reason": row.terminal_reason,
        "has_transcript": bool((row.transcript or "").strip()),
    }


def to_list_item(row: CallSession) -> dict:
    transcript_available = bool((row.transcript or "").strip()) and row.content_purged_at is None
    return {
        "id": row.id,
        "call_sid": row.call_sid,
        "status": row.status,
        "started_at": row.started_at,
        "duration_seconds": row.duration_seconds,
        "outcome": row.outcome,
        "direction": str((row.data or {}).get("direction") or "unknown"),
        "summary": str(row.outcome or row.terminal_reason or row.status)[:120],
        "transcript_available": transcript_available,
        "transcript_purged": row.content_purged_at is not None,
    }

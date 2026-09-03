"""Opaque single-use stream tokens binding Twilio media WS to CallSession."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CallSession


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_stream_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_stream_token(db: Session, call_session: CallSession) -> str:
    """Mint a new single-use token for this CallSession; returns raw token."""
    raw = secrets.token_urlsafe(32)
    call_session.stream_token_hash = hash_stream_token(raw)
    call_session.stream_token_expires_at = _utcnow() + timedelta(
        seconds=settings.stream_token_ttl_seconds
    )
    call_session.stream_token_consumed_at = None
    db.add(call_session)
    db.commit()
    db.refresh(call_session)
    return raw


def consume_stream_token(
    db: Session,
    *,
    call_sid: str,
    raw_token: str,
) -> CallSession:
    """Verify and consume a stream token. Raises ValueError on failure."""
    call_sid = (call_sid or "").strip()
    raw_token = (raw_token or "").strip()
    if not call_sid or not raw_token:
        raise ValueError("call_sid and stream_token are required")

    cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
    if cs is None:
        raise ValueError("unknown call")
    if not cs.stream_token_hash:
        raise ValueError("no stream token issued")
    if cs.stream_token_consumed_at is not None:
        raise ValueError("stream token already used")
    expires = _as_aware(cs.stream_token_expires_at)
    if expires is None or expires < _utcnow():
        raise ValueError("stream token expired")
    if not secrets.compare_digest(cs.stream_token_hash, hash_stream_token(raw_token)):
        raise ValueError("invalid stream token")

    cs.stream_token_consumed_at = _utcnow()
    db.add(cs)
    db.commit()
    db.refresh(cs)
    return cs

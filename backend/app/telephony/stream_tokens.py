"""Opaque single-use stream tokens binding Twilio media WS to CallSession."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
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
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_stream_token(db: Session, call_session: CallSession) -> str:
    """Mint a new single-use token for this CallSession; returns raw token."""
    raw = secrets.token_urlsafe(32)
    call_session.stream_token_hash = hash_stream_token(raw)
    call_session.stream_token_ciphertext = raw
    call_session.stream_token_expires_at = _utcnow() + timedelta(
        seconds=settings.stream_token_ttl_seconds
    )
    call_session.stream_token_consumed_at = None
    db.add(call_session)
    db.commit()
    db.refresh(call_session)
    return raw


def get_or_issue_stream_token(db: Session, call_session: CallSession) -> str:
    """Return the current replay-safe token, rotating only an unused expired token."""
    raw = call_session.stream_token_ciphertext
    expires = _as_aware(call_session.stream_token_expires_at)
    if raw and call_session.stream_token_hash:
        digest_matches = secrets.compare_digest(
            call_session.stream_token_hash,
            hash_stream_token(raw),
        )
        if digest_matches and (
            call_session.stream_token_consumed_at is not None
            or (expires is not None and expires >= _utcnow())
        ):
            return raw
    if call_session.stream_token_consumed_at is not None:
        raise ValueError("media stream already started")
    return issue_stream_token(db, call_session)


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

    now = _utcnow()
    consumed_id = db.execute(
        update(CallSession)
        .where(
            CallSession.call_sid == call_sid,
            CallSession.stream_token_hash == hash_stream_token(raw_token),
            CallSession.stream_token_consumed_at.is_(None),
            CallSession.stream_token_expires_at.is_not(None),
            CallSession.stream_token_expires_at >= now,
        )
        .values(stream_token_consumed_at=now)
        .returning(CallSession.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if consumed_id is None:
        db.rollback()
        cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
        if cs is None:
            raise ValueError("unknown call")
        if not cs.stream_token_hash:
            raise ValueError("no stream token issued")
        if cs.stream_token_consumed_at is not None:
            raise ValueError("stream token already used")
        expires = _as_aware(cs.stream_token_expires_at)
        if expires is None or expires < now:
            raise ValueError("stream token expired")
        raise ValueError("invalid stream token")

    db.commit()
    cs = db.get(CallSession, consumed_id)
    if cs is None:  # pragma: no cover - protected by UPDATE target
        raise ValueError("unknown call")
    return cs

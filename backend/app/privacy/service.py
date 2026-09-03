"""Retention and transcript/recording purge (P6-02)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Appointment, CallSession, User
from app.users.product_prefs import load_product_prefs

logger = logging.getLogger(__name__)


def purge_call_content(
    db: Session,
    cs: CallSession,
    *,
    reason: str = "retention",
) -> dict[str, Any]:
    """Remove transcript/recording references; audit via content_purged_at only."""
    if cs.content_purged_at is not None:
        return {"ok": True, "idempotent": True, "call_id": cs.id}

    path = cs.recording_path
    if path:
        try:
            p = Path(path)
            if p.is_file():
                p.unlink()
        except OSError as exc:
            logger.warning(
                "recording_unlink_failed call_id=%s err=%s", cs.id, type(exc).__name__
            )

    cs.transcript = None
    cs.recording_path = None
    cs.recording_url = None
    cs.content_purged_at = datetime.now(timezone.utc)
    # Keep opaque reason in data blob without content.
    data = dict(cs.data or {})
    data["purge_reason"] = reason[:64]
    cs.data = data
    db.add(cs)
    db.commit()
    logger.info("call_content_purged call_id=%s reason=%s", cs.id, reason)
    return {"ok": True, "idempotent": False, "call_id": cs.id}


def purge_appointment_transcript(
    db: Session,
    appt: Appointment,
    *,
    reason: str = "retention",
) -> dict[str, Any]:
    if appt.transcript_purged_at is not None and not appt.transcript:
        return {"ok": True, "idempotent": True, "appointment_id": appt.id}
    appt.transcript = None
    appt.audio_data = None
    appt.transcript_purged_at = datetime.now(timezone.utc)
    db.add(appt)
    db.commit()
    logger.info(
        "appointment_transcript_purged appointment_id=%s reason=%s",
        appt.id,
        reason,
    )
    return {"ok": True, "idempotent": False, "appointment_id": appt.id}


def run_retention_purge(db: Session, *, limit: int = 200) -> dict[str, Any]:
    """Purge aged content for tenants without legal hold."""
    now = datetime.now(timezone.utc)
    users = list(db.scalars(select(User)).all())
    purged_calls = purged_appts = skipped_hold = 0

    for user in users:
        prefs = load_product_prefs(user.config_json).retention
        if prefs.legal_hold:
            skipped_hold += 1
            continue
        call_cutoff = now - timedelta(days=prefs.transcript_days)
        recording_cutoff = now - timedelta(days=prefs.recording_days)
        cutoff = min(call_cutoff, recording_cutoff)

        calls = list(
            db.scalars(
                select(CallSession)
                .where(
                    CallSession.user_id == user.id,
                    CallSession.content_purged_at.is_(None),
                    CallSession.started_at < cutoff,
                    (
                        CallSession.transcript.is_not(None)
                        | CallSession.recording_path.is_not(None)
                        | CallSession.recording_url.is_not(None)
                    ),
                )
                .limit(limit)
            ).all()
        )
        for cs in calls:
            started = cs.started_at
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started is None:
                continue
            # Use class-specific cutoffs
            age_ok_transcript = started < call_cutoff and cs.transcript
            age_ok_recording = started < recording_cutoff and (
                cs.recording_path or cs.recording_url
            )
            if age_ok_transcript or age_ok_recording:
                purge_call_content(db, cs, reason="retention_auto")
                purged_calls += 1

        appts = list(
            db.scalars(
                select(Appointment)
                .where(
                    Appointment.user_id == user.id,
                    Appointment.transcript_purged_at.is_(None),
                    Appointment.transcript.is_not(None),
                    Appointment.created_at < call_cutoff,
                )
                .limit(limit)
            ).all()
        )
        for appt in appts:
            purge_appointment_transcript(db, appt, reason="retention_auto")
            purged_appts += 1

    return {
        "ok": True,
        "purged_calls": purged_calls,
        "purged_appointments": purged_appts,
        "tenants_on_legal_hold": skipped_hold,
    }


def delete_call_content_for_user(
    db: Session, user_id: int, call_id: int
) -> dict[str, Any]:
    cs = db.get(CallSession, call_id)
    if cs is None or cs.user_id != user_id:
        raise LookupError("call not found")
    prefs = load_product_prefs(db.get(User, user_id).config_json).retention  # type: ignore[union-attr]
    if prefs.legal_hold:
        raise PermissionError("legal_hold_active")
    return purge_call_content(db, cs, reason="user_delete")

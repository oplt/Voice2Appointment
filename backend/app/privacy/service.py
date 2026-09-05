"""Retention and transcript/recording purge (P6-02 / P6-V02)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Appointment, CallSession, User
from app.users.product_prefs import load_product_prefs, prefs_policy_valid

logger = logging.getLogger(__name__)


def _recording_root() -> Path:
    root = os.environ.get("RECORDING_STORAGE_DIR") or "recordings"
    return Path(root).resolve()


def _safe_unlink(path_str: str | None) -> tuple[bool, str | None]:
    """Unlink only if path is under configured recording root. Fail closed on error."""
    if not path_str:
        return True, None
    try:
        path = Path(path_str).resolve()
        root = _recording_root()
        if root not in path.parents and path != root:
            logger.warning("recording_path_outside_root path=%s", path_str[:80])
            return False, "path_outside_root"
        if path.is_file():
            path.unlink()
        return True, None
    except OSError as exc:
        logger.warning(
            "recording_unlink_failed err=%s",
            type(exc).__name__,
        )
        return False, type(exc).__name__


def purge_call_content(
    db: Session,
    cs: CallSession,
    *,
    reason: str = "retention",
    purge_transcript: bool = True,
    purge_recording: bool = True,
) -> dict[str, Any]:
    """Remove selected content stores; clear DB pointers only after successful delete."""
    if cs.content_purged_at is not None and not cs.transcript and not cs.recording_path and not cs.recording_url:
        return {"ok": True, "idempotent": True, "call_id": cs.id}

    errors: list[str] = []
    if purge_recording and cs.recording_path:
        ok, err = _safe_unlink(cs.recording_path)
        if not ok:
            errors.append(err or "unlink_failed")
        else:
            cs.recording_path = None
            cs.recording_url = None
    elif purge_recording and cs.recording_url:
        # Provider copy not deleted here — retain URL until provider deletion job exists.
        # Do not clear URL on local-only success path without provider confirm.
        errors.append("provider_recording_pending")

    if purge_transcript and cs.transcript is not None:
        cs.transcript = None

    fully_clear = (
        cs.transcript is None
        and cs.recording_path is None
        and (cs.recording_url is None or not purge_recording)
        and not errors
    )
    if fully_clear or (
        cs.transcript is None
        and cs.recording_path is None
        and not errors
        and purge_transcript
        and not purge_recording
    ):
        if cs.transcript is None and cs.recording_path is None and cs.recording_url is None:
            cs.content_purged_at = datetime.now(timezone.utc)

    data = dict(cs.data or {})
    data["purge_reason"] = reason[:64]
    if errors:
        data["purge_errors"] = errors[:5]
    cs.data = data
    db.add(cs)
    db.commit()
    if errors:
        logger.warning("call_content_purge_partial call_id=%s errors=%s", cs.id, errors)
        return {"ok": False, "idempotent": False, "call_id": cs.id, "errors": errors}
    logger.info("call_content_purged call_id=%s reason=%s", cs.id, reason)
    return {"ok": True, "idempotent": False, "call_id": cs.id}


def purge_appointment_transcript(
    db: Session,
    appt: Appointment,
    *,
    reason: str = "retention",
) -> dict[str, Any]:
    if (
        appt.transcript_purged_at is not None
        and not appt.transcript
        and not appt.audio_data
        and not appt.stored_filename
        and not appt.mime_type
    ):
        return {"ok": True, "idempotent": True, "appointment_id": appt.id}
    appt.transcript = None
    appt.audio_data = None
    # Clear the metadata describing the deleted audio blob too — retaining
    # filename/MIME type after the bytes are gone is a residual content leak.
    appt.stored_filename = None
    appt.mime_type = None
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
    """Purge aged content with independent transcript/recording cutoffs."""
    now = datetime.now(timezone.utc)
    users = list(db.scalars(select(User)).all())
    purged_calls = purged_appts = skipped_hold = fail_closed = 0

    for user in users:
        if not prefs_policy_valid(user.config_json):
            fail_closed += 1
            logger.error("retention_fail_closed user_id=%s reason=invalid_prefs", user.id)
            continue
        prefs = load_product_prefs(user.config_json).retention
        if prefs.legal_hold:
            skipped_hold += 1
            continue

        transcript_cutoff = now - timedelta(days=prefs.transcript_days)
        recording_cutoff = now - timedelta(days=prefs.recording_days)

        # Transcript-aged calls (independent of recording cutoff).
        transcript_calls = list(
            db.scalars(
                select(CallSession)
                .where(
                    CallSession.user_id == user.id,
                    CallSession.started_at < transcript_cutoff,
                    CallSession.transcript.is_not(None),
                )
                .limit(limit)
            ).all()
        )
        for cs in transcript_calls:
            result = purge_call_content(
                db, cs, reason="retention_transcript", purge_transcript=True, purge_recording=False
            )
            if result.get("ok"):
                purged_calls += 1

        # Recording-aged calls (independent of transcript cutoff).
        recording_calls = list(
            db.scalars(
                select(CallSession)
                .where(
                    CallSession.user_id == user.id,
                    CallSession.started_at < recording_cutoff,
                    or_(
                        CallSession.recording_path.is_not(None),
                        CallSession.recording_url.is_not(None),
                    ),
                )
                .limit(limit)
            ).all()
        )
        for cs in recording_calls:
            result = purge_call_content(
                db, cs, reason="retention_recording", purge_transcript=False, purge_recording=True
            )
            if result.get("ok"):
                purged_calls += 1

        # Appointments: transcript OR audio_data
        appts = list(
            db.scalars(
                select(Appointment)
                .where(
                    Appointment.user_id == user.id,
                    Appointment.transcript_purged_at.is_(None),
                    Appointment.created_at < transcript_cutoff,
                    or_(
                        Appointment.transcript.is_not(None),
                        Appointment.audio_data.is_not(None),
                    ),
                )
                .limit(limit)
            ).all()
        )
        for appt in appts:
            purge_appointment_transcript(db, appt, reason="retention_auto")
            purged_appts += 1

    return {
        "ok": fail_closed == 0,
        "purged_calls": purged_calls,
        "purged_appointments": purged_appts,
        "tenants_on_legal_hold": skipped_hold,
        "tenants_fail_closed": fail_closed,
    }


def delete_call_content_for_user(
    db: Session, user_id: int, call_id: int
) -> dict[str, Any]:
    cs = db.get(CallSession, call_id)
    if cs is None or cs.user_id != user_id:
        raise LookupError("call not found")
    user = db.get(User, user_id)
    if user is None or not prefs_policy_valid(user.config_json):
        raise PermissionError("retention_policy_invalid")
    prefs = load_product_prefs(user.config_json).retention
    if prefs.legal_hold:
        raise PermissionError("legal_hold_active")
    return purge_call_content(db, cs, reason="user_delete")

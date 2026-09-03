"""Background tasks (no Flask). Phase 10: Twilio sync + recording + reminders."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Appointment, CallSession, User
from app.db.session import SessionLocal
from app.telephony.security import (
    assert_valid_twilio_sid,
    is_allowed_twilio_media_host,
    twilio_recording_api_url,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

RECORDING_DIR = Path(os.environ.get("RECORDING_DIR", "/tmp/voice_recordings"))
_AUDIO_MIME_PREFIXES = ("audio/", "application/octet-stream")


def _safe_recording_path(recording_sid: str) -> Path:
    """Resolve final path under RECORDING_DIR; reject traversal."""
    assert_valid_twilio_sid(recording_sid, prefix="RE")
    final = (RECORDING_DIR / f"{recording_sid}.mp3").resolve()
    base = RECORDING_DIR.resolve()
    if not str(final).startswith(str(base) + os.sep) and final != base:
        raise ValueError("recording path escapes archive directory")
    return final


@celery_app.task(name="send_password_reset_email")
def send_password_reset_email(email: str, token: str) -> dict:
    """Deliver password-reset mail off the request path (P3-07)."""
    from app.auth.service import _send_reset_email

    _send_reset_email(email, token)
    return {"ok": True}


@celery_app.task(
    name="download_and_archive_recording",
    bind=True,
    autoretry_for=(requests.RequestException, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def download_and_archive_recording(
    self,
    recording_sid: str,
    recording_url: str,
    call_sid: str,
    account_sid: str | None = None,
    user_id: int | None = None,
):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    if not recording_sid or not call_sid:
        return {"ok": False, "error": "missing arguments"}

    db = SessionLocal()
    temp_path: str | None = None
    try:
        recording_sid = assert_valid_twilio_sid(recording_sid, prefix="RE")
        call_sid = assert_valid_twilio_sid(call_sid, prefix="CA")

        cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
        if cs is None:
            return {"ok": False, "error": "call session not found"}
        if user_id is not None and cs.user_id != user_id:
            return {"ok": False, "error": "ownership mismatch"}

        user = db.get(User, cs.user_id)
        if user is None:
            return {"ok": False, "error": "user not found"}
        if not user.twilio_account_sid or not user.twilio_auth_token:
            return {"ok": False, "error": "twilio credentials missing"}

        effective_account = account_sid or user.twilio_account_sid
        effective_account = assert_valid_twilio_sid(effective_account, prefix="AC")
        if effective_account != user.twilio_account_sid:
            return {"ok": False, "error": "account mismatch"}

        # Reconstruct URL; ignore untrusted hosts from webhook.
        audio_url = twilio_recording_api_url(
            account_sid=effective_account, recording_sid=recording_sid
        )
        # Allow legacy callers that already passed the reconstructed URL.
        if recording_url and recording_url.rstrip("/") != audio_url.rstrip("/"):
            parsed = urlparse(recording_url)
            if parsed.scheme != "https" or not is_allowed_twilio_media_host(
                parsed.hostname or ""
            ):
                return {"ok": False, "error": "disallowed recording host"}

        parsed_audio = urlparse(audio_url)
        if parsed_audio.scheme != "https" or not is_allowed_twilio_media_host(
            parsed_audio.hostname or ""
        ):
            return {"ok": False, "error": "disallowed recording host"}

        resp = requests.get(
            audio_url,
            auth=(user.twilio_account_sid, user.twilio_auth_token),
            timeout=settings.recording_download_timeout_seconds,
            stream=True,
            allow_redirects=False,
        )
        if resp.is_redirect or resp.status_code in {301, 302, 303, 307, 308}:
            resp.close()
            return {"ok": False, "error": "redirect refused"}
        resp.raise_for_status()

        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type and not any(
            content_type.startswith(p) for p in _AUDIO_MIME_PREFIXES
        ):
            resp.close()
            return {"ok": False, "error": "unexpected content type"}

        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        final_path = _safe_recording_path(recording_sid)
        max_bytes = settings.recording_max_bytes

        with tempfile.NamedTemporaryFile(
            dir=RECORDING_DIR, suffix=".partial", delete=False
        ) as tmp:
            temp_path = tmp.name
            written = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError("recording exceeds size limit")
                tmp.write(chunk)
            tmp.flush()
            os.fsync(tmp.fileno())

        os.replace(temp_path, final_path)
        temp_path = None

        cs.update(
            session=db,
            recording_path=str(final_path),
            recording_downloaded_at=datetime.now(timezone.utc),
        )
        return {"ok": True, "path": str(final_path)}
    except Exception:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                logger.exception("Failed to clean partial recording %s", temp_path)
        raise
    finally:
        db.close()


@celery_app.task(name="sync_twilio_for_user")
def sync_twilio_for_user(user_id: int) -> dict:
    """Incremental Twilio sync for one tenant."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.analytics.service import fetch_and_store_twilio
    from app.core.config import settings as app_settings

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return {"ok": False, "error": "user not found"}
        account_sid = user.twilio_account_sid or app_settings.twilio_account_sid
        auth_token = user.twilio_auth_token or app_settings.twilio_auth_token
        if not account_sid or not auth_token:
            return {"ok": False, "error": "twilio credentials missing"}
        metrics = fetch_and_store_twilio(
            db,
            user_id=user.id,
            account_sid=account_sid,
            auth_token=auth_token,
        )
        return {"ok": True, "user_id": user_id, "metrics": metrics}
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_twilio_for_user failed user_id=%s", user_id)
        return {"ok": False, "user_id": user_id, "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="sync_all_twilio_analytics")
def sync_all_twilio_analytics() -> dict:
    """Beat entrypoint: enqueue incremental sync for every tenant with Twilio."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        users = list(
            db.scalars(
                select(User).where(
                    User.twilio_account_sid.is_not(None),
                    User.twilio_auth_token.is_not(None),
                )
            ).all()
        )
        queued = 0
        for user in users:
            sync_twilio_for_user.delay(user.id)
            queued += 1
        return {"ok": True, "queued": queued}
    finally:
        db.close()


@celery_app.task(name="send_appointment_reminders")
def send_appointment_reminders() -> dict:
    """Send due appointment reminders (consent/quiet-hours aware)."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.notifications.service import process_due_reminders

    db = SessionLocal()
    try:
        return process_due_reminders(db)
    finally:
        db.close()


@celery_app.task(name="send_appointment_confirmation")
def send_appointment_confirmation(appointment_id: int) -> dict:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.db.models import Appointment
    from app.notifications.service import KIND_CONFIRMATION, deliver_notification

    db = SessionLocal()
    try:
        appt = db.get(Appointment, appointment_id)
        if appt is None:
            return {"ok": False, "error": "not_found"}
        return deliver_notification(db, appt, kind=KIND_CONFIRMATION)
    finally:
        db.close()


@celery_app.task(name="purge_expired_retained_content")
def purge_expired_retained_content(*, limit: int = 200) -> dict:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.privacy import service as privacy_service

    db = SessionLocal()
    try:
        return privacy_service.run_retention_purge(db, limit=limit)
    finally:
        db.close()


@celery_app.task(name="reconcile_expired_call_sessions")
def reconcile_expired_call_sessions(*, limit: int = 100) -> dict:
    """Mark CallSessions past expires_at as expired when callbacks never arrived (P2-01)."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.telephony.lifecycle import reconcile_expired_calls

    db = SessionLocal()
    try:
        return reconcile_expired_calls(db, limit=limit)
    finally:
        db.close()


@celery_app.task(name="reconcile_pending_appointments")
def reconcile_pending_appointments(*, max_age_minutes: int = 15, limit: int = 50) -> dict:
    """Retry/finalize appointments stuck in pending_provider (P0-08)."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.appointments import booking as booking_service

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        rows = list(
            db.scalars(
                select(Appointment)
                .where(
                    Appointment.provider_sync_status == "pending_provider",
                    Appointment.created_at <= cutoff,
                )
                .limit(limit)
            ).all()
        )
        results = []
        for row in rows:
            results.append(booking_service.reconcile_pending_appointment(db, row))
        return {"ok": True, "processed": len(results), "results": results}
    finally:
        db.close()


@celery_app.task(name="precompute_analytics_summaries")
def precompute_analytics_summaries() -> dict:
    """Warm analytics cache for tenants with Twilio credentials."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.analytics.service import analytics_summary

    db = SessionLocal()
    try:
        users = list(
            db.scalars(
                select(User).where(User.twilio_account_sid.is_not(None))
            ).all()
        )
        warmed = 0
        for user in users:
            analytics_summary(db, user.id)
            warmed += 1
        return {"ok": True, "warmed": warmed}
    finally:
        db.close()

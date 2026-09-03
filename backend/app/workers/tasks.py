"""Background tasks (no Flask). Phase 10: Twilio sync + recording + reminders."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from sqlalchemy import select

from app.db.models import Appointment, CallSession, User
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

RECORDING_DIR = Path(os.environ.get("RECORDING_DIR", "/tmp/voice_recordings"))


@celery_app.task(
    name="download_and_archive_recording",
    bind=True,
    autoretry_for=(requests.RequestException, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def download_and_archive_recording(
    self, recording_sid: str, recording_url: str, call_sid: str
):
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    if not recording_sid or not recording_url or not call_sid:
        return {"ok": False, "error": "missing arguments"}

    db = SessionLocal()
    temp_path: str | None = None
    try:
        cs = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
        if cs is None:
            return {"ok": False, "error": "call session not found"}

        user = db.get(User, cs.user_id)
        if user is None:
            return {"ok": False, "error": "user not found"}
        if not user.twilio_account_sid or not user.twilio_auth_token:
            return {"ok": False, "error": "twilio credentials missing"}

        audio_url = f"{recording_url}.mp3?Download=true"
        resp = requests.get(
            audio_url,
            auth=(user.twilio_account_sid, user.twilio_auth_token),
            timeout=30,
            stream=True,
        )
        resp.raise_for_status()

        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        final_path = RECORDING_DIR / f"{recording_sid}.mp3"

        # Atomic write: temp file in same directory, then replace.
        with tempfile.NamedTemporaryFile(
            dir=RECORDING_DIR, suffix=".partial", delete=False
        ) as tmp:
            temp_path = tmp.name
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
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
    from app.core.config import settings

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return {"ok": False, "error": "user not found"}
        account_sid = user.twilio_account_sid or settings.twilio_account_sid
        auth_token = user.twilio_auth_token or settings.twilio_auth_token
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
    """Mark due appointment reminders (email send can plug in later)."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=24)
        rows = list(
            db.scalars(
                select(Appointment).where(
                    Appointment.reminder_sent.is_(False),
                    Appointment.status != "cancelled",
                    Appointment.start_datetime >= now,
                    Appointment.start_datetime <= window_end,
                )
            ).all()
        )
        for row in rows:
            row.reminder_sent = True
            logger.info(
                "Reminder due appointment_id=%s user_id=%s start=%s",
                row.id,
                row.user_id,
                row.start_datetime,
            )
        db.commit()
        return {"ok": True, "marked": len(rows)}
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

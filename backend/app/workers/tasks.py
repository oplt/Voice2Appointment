"""Background tasks (no Flask). Phase 10: Twilio sync + recording + reminders."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import or_, select

from app.db.models import Appointment, User
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(
    name="process_password_reset_request",
    autoretry_for=(OSError, smtplib.SMTPException),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def process_password_reset_request(email: str, token: str | None = None) -> dict:
    """Deliver one persisted reset token; retries reuse the same token."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    from app.auth.service import process_queued_password_reset

    db = SessionLocal()
    try:
        return process_queued_password_reset(db, email, token)
    finally:
        db.close()


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
    from app.workers.recordings import process_recording_download

    return process_recording_download(
        recording_sid=recording_sid,
        recording_url=recording_url,
        call_sid=call_sid,
        account_sid=account_sid,
        user_id=user_id,
        session_factory=SessionLocal,
    )


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
        if metrics.get("has_more"):
            sync_twilio_for_user.apply_async(args=[user_id], countdown=1)
            metrics["continuation_enqueued"] = True
        return {"ok": True, "user_id": user_id, "metrics": metrics}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "sync_twilio_for_user failed user_id=%s error_type=%s",
            user_id,
            type(exc).__name__,
        )
        return {"ok": False, "user_id": user_id, "error_code": "provider_unavailable"}
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


@celery_app.task(name="retry_pending_notifications")
def retry_pending_notifications(*, limit: int = 200) -> dict:
    """Sweep scheduled/failed outbox rows: quiet-hours reschedule, failure
    retry, and broker/enqueue-outage recovery (P6-V01)."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.notifications.service import retry_pending_notifications as _retry

    db = SessionLocal()
    try:
        return _retry(db, limit=limit)
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
    from app.calendars.service import booking_provider_hooks

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        rows = list(
            db.scalars(
                select(Appointment)
                .where(
                    Appointment.provider_sync_status == "pending_provider",
                    or_(
                        Appointment.provider_next_retry_at <= datetime.now(timezone.utc),
                        (
                            Appointment.provider_next_retry_at.is_(None)
                            & (Appointment.created_at <= cutoff)
                        ),
                    ),
                )
                .limit(limit)
            ).all()
        )
        results = []
        for row in rows:
            hooks = booking_provider_hooks(db, row.user_id)
            results.append(
                booking_service.reconcile_pending_appointment(
                    db,
                    row,
                    provider_create=hooks.create_event,
                    provider_update=hooks.update_event,
                    provider_delete=hooks.delete_event,
                )
            )
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

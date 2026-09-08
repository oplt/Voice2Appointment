"""Background tasks (no Flask). Phase 10: Twilio sync + recording + reminders."""

from __future__ import annotations

import json
import logging
import random
import smtplib
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import requests
from sqlalchemy import or_, select
from twilio.base.exceptions import TwilioRestException

from app.core.metrics import metrics
from app.db.models import Appointment, User
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TwilioFailureKind = Literal["permanent", "transient"]


def _http_status(exc: BaseException) -> int | None:
    value = getattr(exc, "status", None)
    if value is None:
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def classify_twilio_sync_failure(exc: BaseException) -> tuple[TwilioFailureKind, str]:
    """Classify provider failures without relying on vendor response text."""
    status = _http_status(exc)
    if status in {401, 403}:
        return "permanent", "twilio_auth"
    if status == 429 or (status is not None and status >= 500):
        return "transient", "twilio_provider_retryable"
    if status is not None and 400 <= status < 500:
        return "permanent", "twilio_invalid_request"
    if isinstance(exc, (requests.Timeout, requests.ConnectionError, TimeoutError, ConnectionError, OSError)):
        return "transient", "twilio_provider_unavailable"
    if isinstance(exc, TwilioRestException):
        # SDK exceptions without a status are not safe to call permanent.
        return "transient", "twilio_provider_unavailable"
    return "transient", "twilio_provider_unavailable"


def _set_twilio_sync_health(
    db,
    user: User,
    *,
    status: Literal["healthy", "permanent_failure"],
    error_code: str | None = None,
) -> None:
    """Persist bounded integration health without overwriting malformed config."""
    try:
        data = json.loads(user.config_json or "{}")
        if not isinstance(data, dict):
            return
        health = data.get("integration_health")
        if not isinstance(health, dict):
            health = {}
        health["twilio_sync"] = {
            "status": status,
            "error_code": error_code,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data["integration_health"] = health
        user.config_json = json.dumps(data, separators=(",", ":"), sort_keys=True)
        db.add(user)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Unable to record Twilio sync integration health")


def _twilio_retry_countdown(retries: int) -> int:
    ceiling = min(300, 2 ** max(0, retries))
    return max(1, int(random.uniform(ceiling / 2, ceiling)))


def _sync_chain_key(user_id: int) -> str:
    return f"twilio-sync-chain:{user_id}"


def _claim_sync_chain(user_id: int) -> bool:
    """Coalesce scheduler fan-out; the durable DB lease remains the backstop."""
    from app.core.cache_backend import redis_client
    from app.core.config import settings

    client = redis_client()
    if client is None:
        return True
    try:
        return bool(
            client.set(
                _sync_chain_key(user_id),
                "1",
                nx=True,
                ex=max(60, settings.twilio_sync_lease_seconds * 3),
            )
        )
    except Exception:  # noqa: BLE001
        return True


def _release_sync_chain(user_id: int) -> None:
    from app.core.cache_backend import redis_client

    client = redis_client()
    if client is None:
        return
    try:
        client.delete(_sync_chain_key(user_id))
    except Exception:  # noqa: BLE001
        pass

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


@celery_app.task(name="sync_twilio_for_user", bind=True)
def sync_twilio_for_user(self, user_id: int) -> dict:
    """Incremental Twilio sync for one tenant."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.analytics.service import fetch_and_store_twilio
    from app.core.config import settings as app_settings

    db = SessionLocal()
    retain_chain = False
    sync_started = time.perf_counter()
    try:
        user = db.get(User, user_id)
        if user is None:
            metrics.incr("twilio_sync", labels={"result": "invalid_tenant"})
            return {"ok": False, "error_code": "invalid_tenant"}
        account_sid = user.twilio_account_sid or app_settings.twilio_account_sid
        auth_token = user.twilio_auth_token or app_settings.twilio_auth_token
        if not account_sid or not auth_token:
            _set_twilio_sync_health(
                db, user, status="permanent_failure", error_code="twilio_not_configured"
            )
            metrics.incr("twilio_sync", labels={"result": "twilio_not_configured"})
            return {"ok": False, "user_id": user_id, "error_code": "twilio_not_configured"}
        sync_metrics = fetch_and_store_twilio(
            db,
            user_id=user.id,
            account_sid=account_sid,
            auth_token=auth_token,
        )
        _set_twilio_sync_health(db, user, status="healthy")
        if sync_metrics.get("has_more"):
            sync_twilio_for_user.apply_async(args=[user_id], countdown=1)
            sync_metrics["continuation_enqueued"] = True
            retain_chain = True
        metrics.incr("twilio_sync", labels={"result": "success"})
        metrics.observe(
            "twilio_sync_duration_ms",
            (time.perf_counter() - sync_started) * 1000.0,
            labels={"result": "success"},
        )
        return {"ok": True, "user_id": user_id, "metrics": sync_metrics}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        kind, error_code = classify_twilio_sync_failure(exc)
        logger.warning(
            "sync_twilio_for_user failed user_id=%s error_type=%s classification=%s",
            user_id,
            type(exc).__name__,
            kind,
        )
        metrics.incr("twilio_sync", labels={"result": error_code})
        metrics.observe(
            "twilio_sync_duration_ms",
            (time.perf_counter() - sync_started) * 1000.0,
            labels={"result": error_code[:32]},
        )
        metrics.incr(
            "provider_errors",
            labels={
                "provider": "twilio",
                "operation": "sync",
                "category": kind[:32],
            },
        )
        if kind == "permanent":
            user = db.get(User, user_id)
            if user is not None:
                _set_twilio_sync_health(
                    db, user, status="permanent_failure", error_code=error_code
                )
            return {"ok": False, "user_id": user_id, "error_code": error_code}
        retain_chain = True
        return self.retry(
            exc=exc,
            countdown=_twilio_retry_countdown(self.request.retries),
            max_retries=5,
        )
    finally:
        db.close()
        if not retain_chain:
            _release_sync_chain(user_id)


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
        coalesced = 0
        for user in users:
            if not _claim_sync_chain(user.id):
                coalesced += 1
                continue
            sync_twilio_for_user.delay(user.id)
            queued += 1
        return {"ok": True, "queued": queued, "coalesced": coalesced}
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


@celery_app.task(name="expire_reservation_holds")
def expire_reservation_holds(*, limit: int = 100) -> dict:
    """Release capacity from expired reservation holds."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.reservations.service import expire_stale_holds

    db = SessionLocal()
    try:
        expired = expire_stale_holds(db, limit=limit)
        return {"ok": True, "expired": expired}
    finally:
        db.close()


@celery_app.task(name="finalize_pending_reservations")
def finalize_pending_reservations_task(*, limit: int = 50) -> dict:
    """Retry external-provider finalize for committed reservations."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")

    from app.calendars.service import booking_provider_hooks
    from app.reservations.service import finalize_pending_reservations

    db = SessionLocal()
    try:
        def provider_create_for_user(user_id: int):
            hooks = booking_provider_hooks(db, user_id)
            return hooks.create_event

        results = finalize_pending_reservations(
            db, provider_create_for_user=provider_create_for_user, limit=limit
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

"""Celery application for background jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "voice_assistant",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Single default queue (P8-02). Do not enable task_routes until
    # docs/phase8-decisions.md contention threshold is met.
    task_default_queue="celery",
    beat_schedule={
        # Phase 10.4 — periodic Twilio incremental sync (not real-time voice).
        "sync-all-twilio-analytics": {
            "task": "sync_all_twilio_analytics",
            "schedule": crontab(minute="*/15"),
        },
        "send-appointment-reminders": {
            "task": "send_appointment_reminders",
            "schedule": crontab(minute="*/30"),
        },
        "purge-expired-retained-content": {
            "task": "purge_expired_retained_content",
            "schedule": crontab(minute=20, hour="*/6"),
        },
        "reconcile-pending-appointments": {
            "task": "reconcile_pending_appointments",
            "schedule": crontab(minute="*/10"),
        },
        "reconcile-expired-call-sessions": {
            "task": "reconcile_expired_call_sessions",
            "schedule": crontab(minute="*/5"),
        },
        "precompute-analytics-summaries": {
            "task": "precompute_analytics_summaries",
            "schedule": crontab(minute=5),
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

from app.workers.instrumentation import register_celery_metrics  # noqa: E402

register_celery_metrics(celery_app)

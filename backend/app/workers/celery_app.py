"""Celery application for background jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

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
    task_default_queue="maintenance",
    task_queues=(
        Queue("critical"),
        Queue("notifications"),
        Queue("provider_sync"),
        Queue("media"),
        Queue("maintenance"),
    ),
    task_routes={
        "reconcile_pending_appointments": {"queue": "critical"},
        "expire_reservation_holds": {"queue": "critical"},
        "finalize_pending_reservations": {"queue": "critical"},
        "reconcile_expired_call_sessions": {"queue": "critical"},
        "send_appointment_confirmation": {"queue": "notifications"},
        "send_appointment_reminders": {"queue": "notifications"},
        "retry_pending_notifications": {"queue": "notifications"},
        "process_password_reset_request": {"queue": "notifications"},
        "sync_twilio_for_user": {"queue": "provider_sync"},
        "sync_all_twilio_analytics": {"queue": "provider_sync"},
        "download_and_archive_recording": {"queue": "media"},
        "purge_expired_retained_content": {"queue": "maintenance"},
        "precompute_analytics_summaries": {"queue": "maintenance"},
    },
    worker_prefetch_multiplier=1,
    task_soft_time_limit=120,
    task_time_limit=150,
    task_acks_late=False,
    task_annotations={
        "sync_twilio_for_user": {"acks_late": True},
        "reconcile_pending_appointments": {"acks_late": True},
        "expire_reservation_holds": {"acks_late": True},
        "finalize_pending_reservations": {"acks_late": True},
        "reconcile_expired_call_sessions": {"acks_late": True},
        "retry_pending_notifications": {"acks_late": True},
        "download_and_archive_recording": {"acks_late": True},
        "purge_expired_retained_content": {"acks_late": True},
        "precompute_analytics_summaries": {"acks_late": True},
    },
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
        "retry-pending-notifications": {
            "task": "retry_pending_notifications",
            "schedule": crontab(minute="*/5"),
        },
        "purge-expired-retained-content": {
            "task": "purge_expired_retained_content",
            "schedule": crontab(minute=20, hour="*/6"),
        },
        "reconcile-pending-appointments": {
            "task": "reconcile_pending_appointments",
            "schedule": crontab(minute="*/10"),
        },
        "expire-reservation-holds": {
            "task": "expire_reservation_holds",
            "schedule": crontab(minute="*/1"),
        },
        "finalize-pending-reservations": {
            "task": "finalize_pending_reservations",
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

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
        "precompute-analytics-summaries": {
            "task": "precompute_analytics_summaries",
            "schedule": crontab(minute=5),
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

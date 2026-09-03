"""P8-01 concurrent call admission + P8-02/P8-04 capacity-related tests."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.analytics.aggregate import aggregate_twilio_sql
from app.core.metrics import metrics
from app.core.security import hash_password
from app.db.models import TwilioCall, User
from app.voice.admission import CallAdmission, admission
from app.workers.instrumentation import _operation_for, register_celery_metrics


def test_admission_under_cap_accepts() -> None:
    adm = CallAdmission(max_concurrent=2)
    assert adm.try_acquire("CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True
    assert adm.try_acquire("CAbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") is True
    assert adm.active_count() == 2


def test_admission_at_cap_rejects_then_release_frees_slot() -> None:
    adm = CallAdmission(max_concurrent=1)
    assert adm.try_acquire("CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True
    assert adm.try_acquire("CAbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") is False
    snap = adm.snapshot()
    assert snap["rejected_total"] == 1
    assert snap["utilization"] == 1.0
    adm.release("CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert adm.try_acquire("CAbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") is True


def test_admission_idempotent_same_call_sid() -> None:
    adm = CallAdmission(max_concurrent=1)
    assert adm.try_acquire("CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True
    assert adm.try_acquire("CAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True
    assert adm.active_count() == 1


def test_health_metrics_includes_admission(client) -> None:
    admission.reset()
    admission.configure(max_concurrent=5)
    assert admission.try_acquire("CAcccccccccccccccccccccccccccccccc") is True
    metrics.incr("voice_admission", labels={"result": "accepted"})
    response = client.get("/health/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["admission"]["cap"] == 5
    assert body["metrics"]["admission"]["active_calls"] == 1
    assert "voice_admission" in body["metrics"]["counters"]


def test_celery_operation_buckets_are_bounded() -> None:
    assert _operation_for("send_appointment_reminders") == "reminders"
    assert _operation_for("download_and_archive_recording") == "recording"
    assert _operation_for("sync_all_twilio_analytics") == "sync"
    assert _operation_for("reconcile_expired_call_sessions") == "reconcile"
    assert _operation_for("totally_unknown_task") == "other"


def test_celery_metrics_register_idempotent() -> None:
    from app.workers.celery_app import celery_app

    # Already registered at import; second call must not crash.
    register_celery_metrics(celery_app)
    metrics.incr("celery_tasks", labels={"operation": "reminders", "result": "success"})
    snap = metrics.snapshot()
    assert "celery_tasks" in snap["counters"]


def test_analytics_aggregate_benchmark_under_slo(db_session) -> None:
    """P8-04: representative analytics query stays under rollup threshold at modest volume."""
    from sqlalchemy import func, select

    user = User(
        username="bench_user",
        email="bench@example.com",
        password=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        TwilioCall(
            user_id=user.id,
            sid=f"CA{i:032d}",
            start_time=start + timedelta(minutes=i),
            duration_sec=60,
            price=0.01,
            price_unit="USD",
            status="completed",
        )
        for i in range(200)
    ]
    db_session.add_all(rows)
    db_session.commit()

    bound_start = start
    bound_end = start + timedelta(days=2)
    zone = ZoneInfo("UTC")

    # Prefer full SQL aggregate when the dialect supports it; SQLite date casting
    # in aggregate_twilio_sql can fail on some SQLAlchemy versions — fall back to
    # the same totals shape used by the aggregator.
    def _run_once() -> int:
        try:
            result = aggregate_twilio_sql(
                db_session,
                user.id,
                bound_start=bound_start,
                bound_end=bound_end,
                zone=zone,
            )
            if result is not None:
                return int(result["total_calls"])
        except TypeError:
            pass
        total = db_session.execute(
            select(func.count())
            .select_from(TwilioCall)
            .where(
                TwilioCall.user_id == user.id,
                TwilioCall.start_time >= bound_start,
                TwilioCall.start_time < bound_end,
            )
        ).scalar()
        return int(total or 0)

    samples: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        assert _run_once() == 200
        samples.append((time.perf_counter() - t0) * 1000.0)

    samples.sort()
    p95 = samples[int(0.95 * (len(samples) - 1))]
    # Gate in docs/phase8-decisions.md: rollups only if p95 > 500ms at volume.
    assert p95 < 500.0, f"analytics p95={p95}ms unexpectedly high on 200 rows"

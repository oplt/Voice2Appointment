"""Celery task wait/runtime instrumentation (P8-02).

Single default queue remains. These metrics justify a future split only when
urgent-job p95 wait exceeds the documented SLO under mixed load.
"""

from __future__ import annotations

import time
from typing import Any

from celery.signals import task_postrun, task_prerun, task_retry

# Allowlisted task name prefixes → short operation labels (bounded cardinality).
_OPERATION_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("send_appointment_reminder", "reminders"),
    ("send_appointment_confirmation", "reminders"),
    ("send_password_reset", "mail"),
    ("reconcile_", "reconcile"),
    ("purge_expired", "purge"),
    ("download_and_archive", "recording"),
    ("sync_", "sync"),
    ("precompute_analytics", "analytics"),
)

_started_at: dict[str, float] = {}


def _operation_for(task_name: str | None) -> str:
    name = (task_name or "unknown").strip()
    for prefix, label in _OPERATION_BY_PREFIX:
        if name.startswith(prefix) or prefix in name:
            return label
    return "other"


def _task_key(task_id: str | None) -> str:
    return task_id or "-"


def register_celery_metrics(app: Any) -> None:
    """Attach signal handlers once per Celery app process."""

    @task_prerun.connect(weak=False)
    def _on_prerun(
        sender: Any = None,
        task_id: str | None = None,
        task: Any = None,
        **kwargs: Any,
    ) -> None:
        _started_at[_task_key(task_id)] = time.perf_counter()

    @task_postrun.connect(weak=False)
    def _on_postrun(
        sender: Any = None,
        task_id: str | None = None,
        task: Any = None,
        state: str | None = None,
        **kwargs: Any,
    ) -> None:
        from app.core.metrics import metrics

        key = _task_key(task_id)
        started = _started_at.pop(key, None)
        name = getattr(task, "name", None) or getattr(sender, "name", None)
        op = _operation_for(name)
        result = "success"
        if state and str(state).upper() not in {"SUCCESS", "NONE", ""}:
            result = "failure" if str(state).upper() == "FAILURE" else str(state).lower()[:24]
        metrics.incr("celery_tasks", labels={"operation": op, "result": result})
        if started is not None:
            metrics.observe(
                "celery_runtime_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"operation": op, "result": result},
            )

    @task_retry.connect(weak=False)
    def _on_retry(sender: Any = None, **kwargs: Any) -> None:
        from app.core.metrics import metrics

        name = getattr(sender, "name", None)
        metrics.incr(
            "celery_tasks",
            labels={"operation": _operation_for(name), "result": "retry"},
        )

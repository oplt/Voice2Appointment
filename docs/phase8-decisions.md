# Phase 8 decisions (gated scale work)

Measurement-first. Do **not** add operational complexity until the threshold
column is met with evidence from a non-production soak.

| Item | Status | Threshold to implement | Current evidence |
| --- | --- | --- | --- |
| **P8-01** capacity + admission | **Done** | N/A | `VOICE_MAX_CONCURRENT_CALLS`, harness, [capacity.md](./capacity.md) |
| **P8-02** Celery queue split | **Deferred** | Urgent job (reminders/reconcile) p95 **wait** > 30s under mixed load while recording/sync occupy the worker | Instrumentation only: `celery_tasks` / `celery_runtime_ms` |
| **P8-03** durable object storage | **Deferred** | Explicit retention/compliance need for multi-AZ media **and** cost model + scope approval for a new external service | Local `RECORDING_DIR` + P6-02 purge (14d recordings / 30d transcripts) |
| **P8-04** analytics rollups | **Deferred** | Permitted-range analytics p95 wall time **> 500 ms** at representative volume after cache miss | SQL aggregates (P5-06) + cache; see benchmark in `test_phase8_capacity.py` |

## P8-02 — future routing sketch (not enabled)

If the wait SLO fails, route latency-sensitive tasks to `urgent` and heavy I/O
to `bulk` with separate worker concurrency — without losing idempotency:

```python
# NOT active — document only
task_routes = {
    "send_appointment_reminders": {"queue": "urgent"},
    "send_appointment_confirmation": {"queue": "urgent"},
    "reconcile_expired_call_sessions": {"queue": "urgent"},
    "download_and_archive_recording": {"queue": "bulk"},
    "sync_all_twilio_analytics": {"queue": "bulk"},
}
```

Compose continues to run **one** generic worker until this gate opens. Dead-letter
/ manual recovery remains: inspect failed task payloads (no PII dumps), retry
idempotent tasks, escalate via [runbooks/reconciliation-backlog.md](./runbooks/reconciliation-backlog.md).

## P8-03 — storage

Short-lived local archives under `RECORDING_DIR` (default `/tmp/voice_recordings`)
are purged by `purge_expired_retained_content`. Moving to encrypted tenant-scoped
object storage requires:

1. Stakeholder approval for retained media durability beyond local disk
2. Cost/region/lifecycle design
3. Explicit implementation task (new adapter + access API + tests)

Until then: **no** storage adapter, **no** public buckets, keep purge + legal hold.

## P8-04 — rollups

Raw SQL aggregation + versioned cache remain authoritative. Rollup tables would
add timezone/late-data correction complexity; introduce only after the 500 ms
threshold fails with a recorded benchmark and a reconciler against raw totals.

## Rollback posture

Every future component must document: idempotency key, recovery steps, retention,
cost owner, and how to disable the feature flag / route without data loss.

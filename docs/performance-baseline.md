# Performance baseline

This is the Phase 0 baseline for the checked-in Docker configuration. It records
what is configured, the only safe local measurement taken, and the procedure for
collecting comparable end-to-end results. It is not a production capacity claim.

## Architecture

| Component | Current responsibility and boundary |
| --- | --- |
| HTTP process | `backend/asgi.py` creates `create_app(include_api=True, include_voice=False)`. Docker starts it as the backend image's default Gunicorn/Uvicorn-worker command on port 8000. API routes, Twilio webhooks, and health endpoints run here; voice WebSockets do not. |
| Voice WebSocket process | `backend/voice_asgi.py` creates `create_app(include_api=False, include_voice=True)`. Compose starts one Uvicorn process on port 8001 with access logging disabled. `/ws/voice/...` authenticates the Twilio stream, bridges Twilio media to Deepgram, and moves synchronous tool/DB work off the event loop. |
| Celery worker | `worker` runs `app.workers.celery_app.celery_app` with the default `celery` queue. It handles mail, recordings, reminders, reconciliation, and Twilio sync jobs. |
| Celery beat | `beat` is a separate scheduler process. It publishes periodic sync, reminder, retry, cleanup, reconciliation, and analytics tasks; it does not execute them. |
| PostgreSQL | Shared authoritative SQLAlchemy database for application state, appointments, call sessions, OAuth metadata, and durable cache versions. The migration container upgrades it before runtime containers start. |
| Redis | Used by the bounded application cache and as Celery broker/result backend. It is not the source of truth for bookings. |
| Twilio | Signed HTTP webhooks reach the HTTP process. A Twilio media stream reaches only the voice process. The REST client is used for sync and controlled live-call updates. |
| Deepgram | The voice process opens an outbound Deepgram Agent WebSocket for an admitted call. No startup/readiness probe contacts Deepgram. |
| Google Calendar | OAuth credentials and calendar metadata are stored in PostgreSQL. HTTP and voice tools use the synchronous Google client; voice invokes that work through `asyncio.to_thread`. |

## Concurrency boundaries

| Boundary | Current value / behavior |
| --- | --- |
| Gunicorn workers | The backend image and `Procfile.production` start Gunicorn with `--workers 2`, so Compose has **2 HTTP workers** per `web` container. Deployment replicas are outside this repository. |
| Voice processes | Compose runs one Uvicorn process and specifies no `--workers`; this is **1 voice process** per `voice` container. |
| Voice admission | `VOICE_MAX_CONCURRENT_CALLS` defaults to **25** and is enforced per voice process, not cluster-wide. |
| Python executor | `asyncio.to_thread` uses asyncio's lazily-created default `ThreadPoolExecutor`; no executor size is configured here. In Python 3.12 its maximum is `min(32, os.cpu_count() + 4)`. Voice authentication, persistence, fallback, configuration, and synchronous tools share that executor in the voice process. |
| SQLAlchemy pool | PostgreSQL uses the existing QueuePool defaults: pool size **5**, max overflow **10**, timeout **30 seconds**. Phase 0 adds observation only; it does not set a connection budget. SQLite keeps its dialect default pool. |
| Redis pool | The application cache uses `BlockingConnectionPool(max_connections=20, timeout=0.5s)`. Health checks create a short-lived independent client. |
| Celery concurrency | The worker command has no `--concurrency`; Celery's prefork default is the detected CPU count. Beat is a single scheduler process. |

## Phase 12 — correlation and percentiles

Cross-boundary `correlation_id` links:

| Hop | Source |
| --- | --- |
| HTTP | `X-Correlation-ID` or `X-Request-ID` |
| Voice WS | `call:{CallSid}` once Twilio start arrives |
| Voice tools | ContextVars copied into tool worker threads |
| Google / Twilio REST | logs inherit active correlation |
| Celery | `va_correlation_id` / `va_request_id` / `va_call_sid` headers |

`GET /health/metrics` histograms now include `p50_ms` / `p95_ms` / `p99_ms`
from a bounded ring buffer (256 samples/series).

Additional / clarified metrics:

| Metric | Meaning |
| --- | --- |
| `voice_first_response_ms` | TTS-first (else LLM) latency for a call |
| `voice_tool_queue_wait_ms` / `voice_tool_execution_ms` | Tool admission → start → finish |
| `calendar_lookup_latency_ms` / `calendar_create_latency_ms` | Google freebusy/list vs create/update |
| `booking_lock_wait_ms` | Advisory lock wait |
| `db_pool_checked_out` / `db_pool_wait_ms` / `db_transaction_duration_ms` | Pool utilization + tx duration |
| `redis_latency_ms` | Cache command latency |
| `celery_queue_wait_ms` | Publish → start delay |
| `twilio_sync_duration_ms` | Incremental Twilio sync runtime |
| `provider_retries` / `provider_errors` | Retry counts and error categories |

### Synthetic before/after load

```bash
PYTHONPATH=backend python backend/scripts/observability_load.py \
  --concurrency 8 --iterations 40 \
  --json-out /tmp/obs-before.json

# change code / config, then:
PYTHONPATH=backend python backend/scripts/observability_load.py \
  --concurrency 8 --iterations 40 \
  --compare-with /tmp/obs-before.json \
  --json-out /tmp/obs-after.json
```

HTTP booking scenarios still use `performance_baseline.py` with
`--compare-with` for p95 deltas against a disposable target. Do not declare
success from unit tests alone — inspect p95 deltas and error counts.

---

## Metrics added or confirmed

`GET /health/metrics` exposes bounded, process-local aggregates. They have no
tenant, call, phone-number, transcript, token, or request-payload labels.

| Metric | Meaning |
| --- | --- |
| `db_pool_checked_out` | Current checked-out PostgreSQL QueuePool connections (gauge). |
| `db_pool_wait_ms` | Time spent acquiring a PostgreSQL pool connection, including exhaustion wait. |
| `db_transaction_duration_ms` | Transaction lifetime to commit or rollback. |
| `google_request_latency_ms` / `google_requests` | Google Calendar request durations and success/failure count by bounded operation. |
| `twilio_request_latency_ms` / `twilio_requests` | Twilio REST request durations and success/failure count by bounded operation. |
| `voice_tool_queue_wait_ms` | Time between scheduling a sync tool with `asyncio.to_thread` and starting it in the executor. |
| `voice_tool_execution_ms` | Tool execution time after an executor thread starts. |
| `celery_queue_wait_ms` | Publish-to-task-start delay, already carried in a Celery header. |
| `redis_latency_ms` | Cache connect/get/set/delete command duration and outcome. |
| `booking_lock_wait_ms` | PostgreSQL advisory-lock acquisition time for a booking mutation. |

Metrics are intentionally per process. Compare each process's snapshot, or
scrape/aggregate it externally, before making a cluster-wide conclusion.

## Measurements

No PostgreSQL, Redis, Google, Twilio, Deepgram, or authenticated HTTP target was
available in this workspace, so no synthetic provider or API latency has been
recorded. Inventing those numbers would make this baseline misleading.

The safe in-process voice-admission check was run on 2026-09-08 with Python 3.12,
`--cap 25`, `--workers 32`, and unique CallSIDs:

| Concurrent attempts | Accepted | Rejected | Admission p95 |
| ---: | ---: | ---: | ---: |
| 10 | 10 | 0 | 0.0022 ms |
| 25 | 25 | 0 | 0.0019 ms |
| 100 | 25 | 75 | 0.0016 ms |

This measures only the in-memory admission lock, not WebSocket, executor,
database, or provider capacity. It confirms the configured per-process cap is
enforced under concurrent acquire attempts.

## Load-test scaffold

`backend/scripts/performance_baseline.py` is dependency-free and executes named
scenarios from a local JSON file. The checked-in
`backend/scripts/performance-baseline.example.json` covers:

1. concurrent dashboard requests;
2. concurrent availability requests;
3. simultaneous bookings for one tenant;
4. simultaneous bookings for different tenants;
5. voice-function fixtures through a non-production test endpoint; and
6. provider-timeout fixtures through a non-production fake provider.

Copy the example outside version control, replace every `REPLACE` value with
authenticated non-production requests, and use unique idempotency keys for every
booking attempt. Point the final two scenarios only at a test endpoint/fake that
never reaches live Twilio or Google services.

```bash
PYTHONPATH=backend python backend/scripts/performance_baseline.py \
  --config /secure/path/performance-baseline.json \
  --confirm-target http://127.0.0.1:8000 \
  --json-out /tmp/performance-baseline-report.json
curl http://127.0.0.1:8000/health/metrics
curl http://127.0.0.1:8001/health/metrics
```

Run at fixed concurrency levels (for example 1, 5, 10, 25), capture the JSON
report and both process metric snapshots, then record p50/p95/p99, error counts,
pool utilization, lock wait, and queue delay. Do not run booking scenarios against
production.

## Discovered bottlenecks and assumptions

* A single tenant's booking mutations serialize on a PostgreSQL advisory lock.
  The current booking flow can perform calendar availability/create work while
  that lock/transaction is held; Phase 2 must address this before optimization.
* The default executor has no voice-tool-specific limit. Tool work shares it with
  other `asyncio.to_thread` calls, so queue wait is now the primary saturation
  signal.
* Database capacity is multiplied by web, voice, worker, and deployment replica
  counts; no repository-level connection budget exists yet.
* Celery uses one queue for urgent and maintenance work, so queue delay must be
  measured under mixed traffic before routes/concurrency are changed.
* Provider timeouts are configuration/client-library dependent. Google currently
  creates `httplib2.Http(timeout=30)`; this baseline does not change retry or
  timeout policy.
* Results assume provider fakes and a disposable database. Authentication,
  seeded tenant configuration, and external network variance otherwise dominate
  the endpoint measurements.

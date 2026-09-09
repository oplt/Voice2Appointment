# Performance baseline (Phase 14)

Living document for measured latency under disposable targets. Numbers below
are real local harness runs unless marked **scaffold / not run**.

Architecture and pool math: see `docs/phase3-connection-budget.md`.
Voice tool runtime: bounded `VoiceToolRuntime` + `asyncio.wrap_future` (not
default `asyncio.to_thread`). Celery: isolated queues in
`Procfile.production` (`critical`, `notifications`, `provider_sync`, `media`,
`maintenance`).

## How to run Phase 14

One-shot aggregator (capacity + observability + E2E load + optional HTTP
baseline):

```bash
chmod +x backend/scripts/run_phase14_baseline.sh
BASE_URL=http://127.0.0.1:8000 ./backend/scripts/run_phase14_baseline.sh
# writes /tmp/phase14-baseline.json
```

Optional env overrides:

| Variable | Default | Meaning |
| --- | --- | --- |
| `STAGES` | `1,5,10,25` | Concurrency stages |
| `BASE_URL` | `http://127.0.0.1:8000` | Health / performance_baseline target |
| `AGGREGATE` | `/tmp/phase14-baseline.json` | Combined report path |
| `PERF_CONFIG` | auto health-only stand-in | HTTP scenario file (`--confirm-target` must match) |

Individual scripts:

```bash
PYTHONPATH=backend python backend/scripts/voice_capacity_harness.py \
  --stages 1,5,10,25 --json-out /tmp/phase14-voice-capacity.json

PYTHONPATH=backend python backend/scripts/observability_load.py \
  --concurrency 4 --iterations 10 --json-out /tmp/phase14-observability-load.json

PYTHONPATH=backend python backend/scripts/voice_e2e_load.py \
  --stages 1,5,10,25 --json-out /tmp/phase14-voice-e2e-load.json \
  [--base-url http://127.0.0.1:8000] \
  [--inject busy-tools] [--inject redis-down]
```

`voice_e2e_load.py` measures in-process tool runtime + `CallAdmission`, optional
`/health`, and optional Deepgram WS connect/disconnect when `DEEPGRAM_API_KEY`
is set. It does **not** place live Twilio calls (even with `--live-twilio`).

If `/health` is not live, the aggregator skips `performance_baseline.py` and
records a note in the JSON report. When health is live and `PERF_CONFIG` is
unset, the aggregator synthesizes a disposable health-only scenario file
(required scenario names) so `--confirm-target` matches `BASE_URL`.

### Local Phase 14 aggregator run (2026-09-09)

Disposable uvicorn on `:8765` + `/tmp/phase14-baseline.json` (not production p95):

| Probe | Result |
| --- | --- |
| Admission stages 1/5/10/25 | all acquired correctly |
| Tool runtime @25 | 20 ok / 5 busy (default workers+queue bounds) |
| HTTP `/health` | ~16 ms |
| Deepgram WS connect/disconnect | ~0.5–0.7 s connect (no audio) |
| `performance_baseline` | 6× health stand-in scenarios, all 10/10 |

## Process layout (current)

| Component | Boundary |
| --- | --- |
| HTTP | `asgi.py` — Gunicorn 2 workers, no voice WS |
| Voice | `voice_asgi.py` — 1 Uvicorn, `/ws/voice` |
| Celery | Prefork children per queue concurrency; smaller `DB_POOL_SIZE=2` |
| Postgres / Redis | Shared; Redis = cache + broker |
| Providers | Twilio / Deepgram / Google — credentials backend-only |

## Metrics catalog

`GET /health/metrics` — process-local histograms with `p50_ms` / `p95_ms` /
`p99_ms` (ring buffer). Key series:

| Metric | Meaning |
| --- | --- |
| `voice_first_response_ms` | First TTS/LLM response |
| `voice_tool_queue_wait_ms` / `voice_tool_execution_ms` | Tool admission → finish |
| `calendar_lookup_latency_ms` / `calendar_create_latency_ms` | Google freebusy vs write |
| `booking_lock_wait_ms` | Reservation advisory lock wait |
| `db_pool_checked_out` / `db_pool_wait_ms` / `db_transaction_duration_ms` | Pool + tx |
| `redis_latency_ms` | Cache command latency |
| `celery_queue_wait_ms` | Publish → start |
| `twilio_sync_duration_ms` | Incremental Twilio sync |

## Local measurements (2026-09-09)

### Voice admission lock (in-process)

`PYTHONPATH=backend python backend/scripts/voice_capacity_harness.py`

| Concurrent attempts | Accepted | Rejected | Admission p95 |
| ---: | ---: | ---: | ---: |
| 10 | 10 | 0 | 0.0016 ms |
| 25 | 25 | 0 | ~0.002 ms |
| 100 | 25 | 75 | 0.0014 ms |

Measures **only** the in-memory admission semaphore — not WS/DB/providers.

### Voice E2E / load harness (2026-09-09)

`PYTHONPATH=backend python backend/scripts/voice_e2e_load.py --stages 1,5,10,25`

| Stage | Tool ok / busy | Tool p95 | Admission acquired |
| ---: | --- | ---: | ---: |
| 1 | 1 / 0 | ~98 ms (cold+DB touch) | 1 |
| 5 | 5 / 0 | ~9.5 ms | 5 |
| 10 | 10 / 0 | ~17 ms | 10 |
| 25 | 20 / 5 | ~31 ms | 25 |

Busy rejects at 25 reflect default `VOICE_TOOL_WORKERS` + `VOICE_TOOL_QUEUE_SIZE`
saturation — expected. Deepgram connect/disconnect probed when key present;
Twilio live calls not placed.

### Observability synthetic load (2026-09-09)

```bash
PYTHONPATH=backend python backend/scripts/observability_load.py \
  --concurrency 4 --iterations 10 \
  --json-out /tmp/obs-baseline.json
```

Recorded synthetic (in-process, not disposable E2E):

| Series | p95 |
| --- | ---: |
| end_to_end_ms (harness loop) | 1.16 ms |
| voice_tool_queue_wait_ms | 2.4 ms |
| voice_tool_execution_ms | 5.0 ms |

**Not** a substitute for disposable-env E2E voice load with Twilio/Deepgram/Postgres.

### HTTP scenario scaffold

```bash
PYTHONPATH=backend python backend/scripts/performance_baseline.py \
  --config /secure/path/performance-baseline.json \
  --confirm-target http://127.0.0.1:8000 \
  --json-out /tmp/performance-baseline-report.json
```

Copy `backend/scripts/performance-baseline.example.json`, replace `REPLACE`
values, use unique idempotency keys. Run at concurrency **1 / 5 / 10 / 25**.

Capture both:

```bash
curl http://127.0.0.1:8000/health/metrics
curl http://127.0.0.1:8001/health/metrics
```

## Required E2E scenarios (disposable env — status)

| Scenario | Status |
| --- | --- |
| Voice first response @ 1/5/10/25 calls | **Not run** — needs Twilio + Deepgram disposable |
| Tool queue wait under load | Partial via `observability_load.py` |
| Google freebusy / create | **Not run** |
| DB pool wait / tx time | Requires live Postgres under load |
| Redis latency | Requires live Redis |
| Celery queue delay | Requires broker + workers |
| Reservation lock wait | Requires Postgres advisory locks |

## Failure injection checklist (disposable env)

| Fault | Expected signal | Status |
| --- | --- | --- |
| Google 500 / timeout | `provider_errors`, calendar latency spike | Not run |
| Twilio 429 | bounded concurrency + retry metrics | Not run |
| Redis down | cache miss / degrade path | Not run |
| Celery down | outbox stays scheduled | Not run |
| Postgres pool exhaustion | `db_pool_wait_ms` ↑, 503/busy | Not run |
| Deepgram disconnect | voice reconnect path | Not run |
| Voice reconnect during mutation | idempotent lifecycle ops | Not run |
| Worker restart mid-reservation | hold expiry / reconcile | Not run |

## Bottlenecks (current code — refreshed)

* Booking mutations serialize on org/resource advisory locks — measure
  `booking_lock_wait_ms` under contention.
* Voice tools use dedicated bounded executor (`VOICE_TOOL_WORKERS` /
  `VOICE_TOOL_QUEUE_SIZE`); admission rejects with busy when saturated.
* Postgres budget must count Celery **prefork children**, not parent workers.
* Provider timeouts/retries are configured (`GOOGLE_HTTP_TIMEOUT_SECONDS`,
  Twilio client bounds) — verify under injected faults before claiming p95.

Do **not** publish production p95/p99 claims until disposable-env rows above
are filled with real numbers and error rates.

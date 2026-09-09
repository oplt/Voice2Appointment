# Production acceptance

Checklist before enabling the product-domain architecture for **all** tenants.
This document reflects the **repository state as of the Phase A–Q closure pass**.

## Gate summary

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Backend typecheck (mypy) | ✅ local | `cd backend && mypy` — clean |
| 2 | Frontend Vitest | ✅ local | `npm test` — 50 passed |
| 3 | Focused backend unit tests | ✅ local | phase7/8/9, customer dedup, clinic hooks, combos, deposits, tenancy RBAC |
| 4 | Reservation concurrency design | ✅ code | `resource_scheduling_locks` by resource id; PG tests in `test_postgres_integration.py` (require PG CI) |
| 5 | Reservation lifecycle + notifications | ✅ code | cancel/reschedule/party/resources + outbox staging |
| 6 | Product HTTP APIs | ✅ code | catalog/pricing/resources/customers/reservations/payments/tenancy/industries; hold/commit/detail/pagination |
| 7 | Tenancy/RBAC | ✅ code | `resources.read/write`, `agent.manage`, `locations.write`; org switcher wired |
| 8 | Customer dedup | ✅ code | E.164/email normalize + unique indexes + merge/history |
| 9 | Agent instructions runtime | ✅ code | Knowledge `instructions` below immutable safety in `build_system_prompt` |
| 10 | Clinic Google sync path | ✅ code | `booking_provider_hooks` passed into `book_reservation` |
| 11 | Connection budget | ✅ | Celery `DB_POOL_SIZE=2`; `docs/phase3-connection-budget.md` |
| 12 | Voice executor | ✅ | `asyncio.wrap_future` + submit failure releases semaphore |
| 13 | Perf harness @ 1/5/10/25 | 🟡 | `run_phase14_baseline.sh` → `/tmp/phase14-baseline.json`; Deepgram connect probe; busy-tools inject. Full Twilio media soak + live Google freebusy still optional disposable-env |
| 14 | Alembic head | ✅ | Current head **`o1c2d3e4f5a6`** (customer dedup). Org backfill revision id **`g9b0c1d2e3f4`** lives in file `e6f7a8b9c0d1_backfill_organizations.py` |
| 15 | Full GitHub CI (migrations/PG/Playwright/Docker) | ⬜ verify on next push | Must pass after this closure; do not claim green until Actions confirms |

## Feature flags (kill switches)

| Variable | Production default | Non-prod default |
| --- | --- | --- |
| `ENABLE_CATALOG_DOMAIN` | `false` | `true` |
| `ENABLE_RESERVATION_DOMAIN` | `false` | `true` |
| `ENABLE_INDUSTRY_VOICE_TOOLS` | `false` | `true` |

```bash
curl -s http://127.0.0.1:8000/health/features
```

## Rollback

1. Set all three `ENABLE_*` to `false` on HTTP **and** voice; restart.
2. Confirm `/health/features` all `false`.
3. Do **not** reverse org backfill (`g9b0c1d2e3f4`) in production without a DB snapshot.
4. Stop Celery reservation maintenance tasks if a bad path shipped while flags were on.
5. Legacy calendar/voice booking tools remain available while product-domain flags are off.

## Migration chain (relevant)

```text
… → b0c1d2e3f4a5 (industry)
  → g9b0c1d2e3f4 (org backfill; file e6f7a8b9c0d1_*)
  → h0c1… → … → n1c2… (adjacency/payments)
  → o1c2d3e4f5a6 (customer dedup)   ← HEAD
```

## Load / latency

Track voice latency and HTTP enqueue latency before flipping product-domain flags for all tenants.

```bash
bash backend/scripts/run_phase14_baseline.sh
PYTHONPATH=backend python backend/scripts/voice_e2e_load.py \
  --stages 1,5,10,25 --inject busy-tools --json-out /tmp/phase14-busy.json
```

Synthetic + Deepgram connect/disconnect is **not** a full production voice p95 claim. Disposable Twilio media soak remains recommended before go-live.

## Critical section rule

1. Acquire resource advisory locks (sorted resource ids).
2. Persist durable reservation intent.
3. Commit / release lock.
4. Provider `complete_create` **outside** the lock.
5. Reconcile pending provider state asynchronously if needed.

## Honest gaps remaining for true production p95

* Live Google freebusy/create under load (disposable creds)
* Postgres pool exhaustion + Redis/Celery down drills against real services
* Full Twilio media WebSocket soak
* GitHub Actions confirmation of migrations / PG integration / Playwright / Docker after push

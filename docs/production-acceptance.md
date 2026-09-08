# Production acceptance (Phase 13)

Checklist before enabling the new product-domain architecture for **all** tenants.

## Gate summary

| # | Criterion | Evidence |
| --- | --- | --- |
| 1 | Existing appointment workflow passes tests | `test_phase2_provider_io`, `test_phase13_*` booking |
| 2 | Existing voice booking still works | ToolRegistry legacy defaults + phase 7 tests |
| 3 | Google Calendar behavior compatible | Provider I/O outside lock; google metrics |
| 4 | Twilio behavior compatible | Sync lease + no open TX during fetch |
| 5 | Frontend routes remain functional | `frontend` vitest + Playwright a11y |
| 6 | Legacy tenants migrated automatically | Alembic org backfill + `create_organization_for_user` on register |
| 7 | Rollback path exists | Kill switches below |
| 8 | Catalog/reservation behind flags + entitlements | `ENABLE_*` + `FeatureEntitlement` / industry profile |
| 9 | Load-test voice latency | Synth before/after (`observability_load.py`); live voice load still required for go-live |
| 10 | No provider network in long DB critical section | Booking + reservation commit: `complete_create` **after** `scheduling_lock` |

## Feature flags (kill switches)

Set in environment (see `.env.example`):

| Variable | Production default | Non-prod default |
| --- | --- | --- |
| `ENABLE_CATALOG_DOMAIN` | `false` | `true` |
| `ENABLE_RESERVATION_DOMAIN` | `false` | `true` |
| `ENABLE_INDUSTRY_VOICE_TOOLS` | `false` | `true` |

When off:

- Voice exposes **legacy calendar tools only** (no industry/catalog/reservation tools).
- `create_catalog_item` / reservation hold-commit raise `FeatureDisabledError`.
- Classic `book_appointment` continues to work (JSON booking policy).

Inspect live flags:

```bash
curl -s http://127.0.0.1:8000/health/features
```

Per-organization tool entitlements still apply when flags are on (industry profile assignment).

## Rollback

1. Set all three `ENABLE_*` flags to `false` on HTTP **and** voice processes; restart.
2. Confirm `/health/features` shows all `false`.
3. Confirm voice Deepgram function list is legacy calendar set only (no `book_table`, etc.).
4. Do **not** reverse Alembic org backfill in production unless restoring a full DB snapshot — organization rows are additive and safe to leave.
5. If a bad reservation path shipped while flags were on, stop Celery reservation tasks (`expire_reservation_holds`, `finalize_pending_reservations`) until flags are off.
6. Calendar/Twilio credentials and appointment rows remain authoritative; no data wipe required for flag rollback.

## Migration

- `e6f7a8b9c0d1` / `g9b0c1d2e3f4` backfill creates one `organization` + owner membership per legacy user.
- New registrations call `create_organization_for_user` so tenants never lack an org id.

## Load / latency

```bash
PYTHONPATH=backend python backend/scripts/observability_load.py \
  --concurrency 8 --iterations 40 \
  --json-out /tmp/obs-before.json
# … deploy candidate …
PYTHONPATH=backend python backend/scripts/observability_load.py \
  --compare-with /tmp/obs-before.json \
  --json-out /tmp/obs-after.json
```

Synthetic load is **not** a substitute for a disposable-environment voice WebSocket load test before declaring production voice latency non-regressing.

## Critical section rule

Justified pattern (already implemented):

1. Acquire advisory lock.
2. Persist durable booking/reservation intent.
3. Commit / release lock.
4. Call Google (or other provider) via `complete_create` **outside** the lock.
5. Reconcile pending provider state asynchronously if the request crashes after step 3.

Any new code that performs provider HTTP while holding `scheduling_lock` or an open write transaction must document an explicit exception in this file and add a regression test.

## Acceptance command

```bash
PYTHONPATH=backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  pytest -p timeout \
  backend/tests/test_phase13_production_acceptance.py \
  backend/tests/test_phase1_reliability.py \
  backend/tests/test_phase2_provider_io.py \
  backend/tests/test_phase7_tool_registry.py \
  -q

cd frontend && npm test && npm run build
```

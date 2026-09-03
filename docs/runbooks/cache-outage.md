# Runbook: Cache / Redis outage

**Impact:** Readiness fails; rate limits fall back to process-local; cache misses.

## Detect

- `/health/ready` redis check not `ok`
- Logs: Redis rate-limit / cache unavailable warnings

## Diagnose

1. Ping Redis from the app network namespace.
2. Confirm `REDIS_URL` and memory/eviction pressure.
3. Note auth still fail-opens to local limiter — watch multi-replica fairness.

## Mitigate

- Restore Redis; prefer failover over disabling readiness long-term.
- If prolonged outage: scale single-process carefully; monitor 429s.

## Verify

- `/health/ready` returns ready.
- Cache hit metrics recover; no secret material in cache keys.

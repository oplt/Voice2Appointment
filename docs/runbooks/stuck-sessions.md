# Runbook: Stuck call sessions

**Impact:** Sessions remain `active`/`connected` without teardown; capacity leak.

## Detect

- DB: non-terminal `CallSession` older than stream TTL / expected call length
- Reconcile job logs for expired sessions

## Diagnose

1. Inspect `CallSession.status`, `ended_at`, stream token consumption.
2. Confirm Twilio status callbacks and Celery reconcile task run.
3. Check voice gateway process liveness.

## Mitigate

- Run reconcile for aged sessions (safe terminal transition).
- Restart stuck voice workers after draining.
- Do not delete rows; transition to `expired`/`disconnected` with reason.

## Verify

- Aged sessions reach a terminal status.
- New calls still create sessions and complete.

# Runbook: Calendar sync lag

**Impact:** Dashboard/calendar UI missing or stale events.

## Detect

- Worker sync lag logs; dashboard freshness timestamps stale
- Cache version not bumping after mutations

## Diagnose

1. Confirm Google OAuth tokens valid for the tenant (status API).
2. Check Celery sync task errors (no token bodies in logs).
3. Verify Redis cache invalidation path.

## Mitigate

- Re-auth calendar for the affected tenant.
- Clear tenant calendar cache keys via existing invalidation helpers.
- Replay sync from last good cursor if documented; never invent events.

## Verify

- Calendar status connected; events list refreshes within SLA.
- Freshness timestamp updates on dashboard/analytics.

# Runbook: Booking divergence

**Impact:** Double bookings, missing calendar events, or false conflicts.

## Detect

- `bookings{result=conflict}` vs created ratio anomaly
- Appointments `provider_sync_status` stuck pending
- Customer report of duplicate calendar events

## Diagnose

1. Compare appointment row vs provider event id for one tenant.
2. Confirm advisory lock path on PostgreSQL (integration tests).
3. Check idempotency key reuse on retries.

## Mitigate

- Stop automated retries that create without idempotency key.
- Repair divergent rows manually with audit note; prefer soft-cancel.
- Do not wipe appointments.

## Verify

- Re-book same slot idempotently returns same appointment.
- Conflict on true overlap still raises.

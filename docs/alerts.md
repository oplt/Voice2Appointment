# Alerts and SLOs (P7-07)

Symptom-based alerts derived from `/health/*`, structured logs (`request_id`,
`call_sid`), and `/health/metrics` counters. Thresholds start conservative;
tune from baseline.

| Alert | User impact | Signal | Owner | First response |
| --- | --- | --- | --- | --- |
| API not ready | Owners cannot sign in / manage bookings | `/health/ready` ≠ ready for 5m | Platform | [runbooks/cache-outage.md](runbooks/cache-outage.md) / DB |
| Elevated HTTP 5xx | Dashboard/API errors | `http_requests{status=5xx}` rate > 5% for 10m | Platform | Check logs by `request_id`; rollback last deploy |
| Call failure spike | Callers cannot complete bookings | `call_transitions{status=provider_error}` or `disconnected` elevated vs 1h baseline | Voice | [runbooks/provider-outage.md](runbooks/provider-outage.md) |
| Stuck active sessions | Media left open; cost / capacity | Active `CallSession` older than TTL without terminal status | Voice | [runbooks/stuck-sessions.md](runbooks/stuck-sessions.md) |
| Booking conflict surge | Legitimate slots rejected | `bookings{result=conflict}` spike with flat traffic | Product | Policy/hours check; [runbooks/booking-divergence.md](runbooks/booking-divergence.md) |
| Calendar sync lag | Events missing from UI | Sync job lag / cursor age (worker logs) | Integrations | [runbooks/sync-lag.md](runbooks/sync-lag.md) |
| Migration failure | Deploy blocked / app crash loop | Alembic job non-zero / startup migrate error | Platform | [runbooks/migration-failure.md](runbooks/migration-failure.md) |
| Reconciliation backlog | Stale call outcomes | Celery reconcile queue depth / age | Voice | [runbooks/reconciliation-backlog.md](runbooks/reconciliation-backlog.md) |

Drill checklist: induce a synthetic readiness failure in staging, confirm alert
fires, follow the matching runbook, verify recovery signal.

# Dashboard & analytics contracts (Phase 5)

## Dashboard operational KPIs

Returned under `GET /api/v1/dashboard/summary` → `operational` (plus legacy top-level fields).

| KPI | Formula | Window | Exclusions | Drill-down |
| --- | --- | --- | --- | --- |
| `calls_today` | Count `CallSession` with `started_at` in tenant-local day | local day | none (rejected still count as started) | `/calls` |
| `completion_rate` | `outcome ∈ {completed,booked}` / non-null outcomes excluding `rejected` | local day | null outcomes; `rejected` | `/calls` |
| `appointments_booked_today` | Appointments with `created_at` in local day and status pending/confirmed/completed | local day | cancelled/failed | `/appointments` |
| `attention_needed` | `outcome ∈ {failed,expired,rejected}` or `status ∈ {provider_error,expired,rejected}` | local day | counts only (no provider text) | `/calls` |
| `upcoming_appointments` | Active appointments with `start_datetime ≥ now` (list capped at 10) | forward | cancelled/canceled/failed | `/appointments` |

Timezone is the calendar auth timezone, else `DEFAULT_TIMEZONE`, else UTC. `freshness.generated_at` is always set; `stale` when Twilio sync is missing or older than 48h.

## Booking funnel

`GET /api/v1/analytics/summary` includes `funnel` for the same applied local date range.

Stages (each call ≤ once per stage): started → engaged → booking_attempted → booked; plus cancelled, failed, unknown.

Attribution: voice booking sets `Appointment.callsession_id` and may set `CallSession.outcome=booked`. Retries reuse `idempotency_key` so totals do not inflate. Historical rows without outcome stay **unknown** (never inferred).

Failure categories use the prefix of `terminal_reason` (e.g. `deepgram`) — never raw provider error text.

## Analytics privacy & freshness

- `top_numbers` labels are masked (`***` + last 4 digits).
- Monetary totals expose `currency` / `reporting_currency` and `totals_by_currency`.
- `generated_at`, `source_synced_at`, and `stale` are always present on the summary DTO.
- Filters are applied only on explicit Apply; draft edits do not fetch. Optional `compare=true` adds an equal-length prior-period delta for `total_calls` and `total_duration`.

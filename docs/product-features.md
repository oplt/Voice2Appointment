# Product features (Phase 6)

## Notifications (P6-01)

- Channel: **email** only (SMTP via existing `EMAIL_USER` / `EMAIL_PASSWORD`).
- Tenant prefs: `GET/PUT /api/v1/users/me/product-prefs` → `notifications`.
- Enabling confirmations/reminders records `consent_at`.
- Quiet hours use tenant calendar timezone; deliveries skip with `quiet_hours`.
- Idempotency: `notification_delivery.idempotency_key = kind:appointment_id:start_iso`.
- Audit stores status/error_code only — **no message body**.
- Booking create/reschedule enqueues confirmation; cancel skips pending rows.
- Celery: `send_appointment_confirmation`, `send_appointment_reminders` (every 30m).

## Retention (P6-02)

Defaults: transcripts **30** days, recordings **14** days (tenant-overridable).

| Class | Stored | Purge |
| --- | --- | --- |
| Call transcript / recording path | `CallSession` | `content_purged_at` + unlink file |
| Appointment transcript / audio | `Appointment` | `transcript_purged_at` |

- Legal hold pauses automatic purge and blocks `DELETE /api/v1/calls/{id}/content`.
- Celery: `purge_expired_retained_content` every 6h.
- Deletion logs reason codes without retaining content.
- **Durable object storage (P8-03)** is not enabled. Media stays on local
  `RECORDING_DIR` with short retention until a cost/compliance decision opens
  that gate — see [phase8-decisions.md](./phase8-decisions.md).

## Human handoff (P6-03)

- Voice tool `request_human_handoff` (confirmed=true after caller agrees).
- Transfers once per call (`transfer_attempted_at`); outcome `transferred` / `transfer_failed`.
- Redacted summary: reason category + masked caller + call_sid suffix — **no transcript**.
- Destination from product prefs; optional business-hours gate.

## Setup readiness (P6-04)

- `GET /api/v1/users/me/readiness` — checklist from live config.
- Settings → **Setup** tab; required vs optional items with Fix links.
- Test-call hint warns against production bookings during verification.

## Multilingual (P6-05) — gated

Not enabled. See [multilingual-gate.md](./multilingual-gate.md).

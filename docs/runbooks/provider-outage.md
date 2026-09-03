# Runbook: Provider auth / outage

**Impact:** Inbound calls fail to connect media or tools fail mid-call.

## Detect

- `call_transitions` with `provider_error` elevated
- Logs: `operation` containing voice/Deepgram/Twilio; never expect API keys in logs
- Twilio/Deepgram status pages

## Diagnose

1. Confirm `/health/live` ok and `/health/ready` ok (local deps).
2. Grep logs for one `call_sid` / `request_id` across webhook → WS → tool.
3. Verify env `TWILIO_AUTH_TOKEN`, `DEEPGRAM_API_KEY` present (do not print values).

## Mitigate

- Fail closed on forged webhooks; do not disable signature checks.
- If Deepgram outage: communicate degraded mode; do not invent hybrid fallbacks.
- Rotate compromised tokens via secret store; restart workers.

## Verify

- Synthetic signed voice webhook returns TwiML with stream URL.
- New call reaches `connected` then a terminal status.

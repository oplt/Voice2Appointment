# Observability (P7-06)

## Correlation

Every HTTP request gets an opaque `X-Request-ID` (accepted if supplied, else
generated). Structured logs include `request_id`, `call_sid`, `user_id`, and
`operation` via contextvars (`app.core.logging`).

Voice/media paths should bind `call_sid` when known. Jobs should pass the same
opaque IDs explicitly into worker payloads — do not rely on thread-local
inheritance alone.

## Metrics

`GET /health/metrics` returns a bounded in-process snapshot:

- counters such as `http_requests`, `bookings`, `call_transitions`
- latency histograms such as `http_latency_ms`

Label keys are allowlisted (`status`, `outcome`, `provider`, `operation`,
`result`, `cache`, `queue`). Series per metric are capped; excess folds into
`overflow=1`. Transcripts, phones, tokens, and free text must never appear as
labels.

## Redaction

`sanitize_for_log` / `mask_phone` strip secrets and mask phone numbers before
structured log extras are emitted.

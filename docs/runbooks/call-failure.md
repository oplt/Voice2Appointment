# Runbook: Elevated call failure / latency

**Impact:** Callers hear silence, drop early, or bookings do not complete.

## Detect

- `http_latency_ms` / voice media metrics in logs (`voice_audio_forward_stats`)
- Spike in non-completed terminal statuses

## Diagnose

1. Pick one failing `call_sid`; follow structured logs end-to-end.
2. Check queue depth / sequence gap fields in media metrics.
3. Confirm Celery workers and Redis are healthy.

## Mitigate

- Scale voice workers if queue high watermark is elevated.
- Rollback recent voice/telephony deploy if correlated.
- Pause outbound reconcile-heavy jobs if they starve call handling.

## Verify

- P95 first-enqueue lag returns to baseline.
- Booking success (`bookings{result=created}`) recovers.

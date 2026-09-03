# Runbook: Reconciliation backlog

**Impact:** Call outcomes lag Twilio truth; analytics under-count completions.

## Detect

- Celery queue depth / age for reconcile tasks
- Sessions stuck until reconcile (see stuck-sessions)

## Diagnose

1. Inspect worker concurrency and broker connectivity.
2. Sample oldest pending reconcile payload (no PII dumps).
3. Confirm Twilio status webhook delivery.

## Mitigate

- Scale workers; clear poison messages after quarantine.
- Temporarily raise reconcile frequency only with rate limits.

## Verify

- Queue age returns under SLO.
- Terminal statuses match Twilio for sampled `call_sid`s.

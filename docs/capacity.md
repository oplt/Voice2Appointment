# Capacity budgets (P8-01)

Per-process media admission protects event-loop and memory. Scale to higher
concurrency by adding voice gateway instances — not by raising one node to
1,000 sessions.

## Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `VOICE_MAX_CONCURRENT_CALLS` | `25` | Max simultaneous `/ws/voice` sessions per process |
| `VOICE_AUDIO_QUEUE_MAXSIZE` | `50` | Bounded Twilio→Deepgram frame queue (~1s at 20 ms frames) |

Admission runs after stream-token verification and before `websocket.accept()`.
Saturation closes the socket with code **1013** (Try Again Later) and increments
`voice_admission{result=rejected}`.

Signals (autoscaling / alerts):

- `/health/metrics` → `admission.active_calls`, `admission.cap`, `admission.utilization`
- Reject rate from `voice_admission` counters

## Staged budgets

| Concurrent calls | Guidance |
| --- | --- |
| **10** | Comfortable single-instance soak; validate CPU, event-loop lag, Redis/DB pools |
| **100** | Requires **≥4** instances at cap 25 (or raise cap only after measured headroom) |
| **1,000** | Horizontal only: **≥40** instances at cap 25; also bound by **provider quotas** |

Harness (content-free acquire/release, no audio):

```bash
PYTHONPATH=backend python backend/scripts/voice_capacity_harness.py --stages 10,25,100 --cap 25
```

Record p50/p95/p99 acquire latency and reject rate per stage in non-production.
A stage with `reject_rate > 0` at `target <= cap` indicates a harness bug; at
`target > cap`, rejects are expected and prove admission.

## Provider quotas (external hard limits)

Capacity math must include:

- **Twilio** concurrent call / media stream limits for the account
- **Deepgram** Agent concurrent session and rate limits for the API key
- DB connection pool size and Redis connections per instance

When provider quotas are lower than `instances × VOICE_MAX_CONCURRENT_CALLS`,
the provider limit is the real ceiling.

## Memory / queue sketch

Rough per-call working set (order-of-magnitude, measure under load):

- Audio queue: `VOICE_AUDIO_QUEUE_MAXSIZE` × ~160 B μ-law frame ≈ tens of KB
- Reconnect buffer: `VOICE_RECONNECT_BUFFER_FRAMES` frames
- Transcript lines capped in session; never use as metric labels

Saturation symptoms: rising `voice_audio_forward_stats` queue age, elevated
HTTP/voice latency histograms, admission rejects.

## Related

- [phase8-decisions.md](./phase8-decisions.md) — queue split / storage / rollups gates
- [alerts.md](./alerts.md) — call failure and stuck-session runbooks

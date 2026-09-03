# Deepgram Flux benchmark (Phase 8.3)

Production voice still uses **Nova-3** (`DEEPGRAM_MODEL=nova-3`).

## Goal

Compare Nova-3 vs Flux multilingual on real Voice2Appointment call audio before any
model swap, especially for:

- English, Dutch, French, German, Turkish
- Names, dates, times, addresses, appointment vocabulary

## How to run

```bash
export DEEPGRAM_API_KEY=...
python backend/scripts/benchmark_deepgram_flux.py /path/to/recording.wav
```

Results land in `deepgram_flux_benchmark_results.json` (gitignored locally if desired).

## Decision rule

Do **not** change the default model unless Flux is clearly better on latency and
appointment-term accuracy across the languages above. Until then keep Nova-3.

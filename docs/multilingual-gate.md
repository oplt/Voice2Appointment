# Multilingual calls gate (P6-05)

Multilingual voice support is **not** product-enabled.

## Required before enablement

1. Select 1–2 demanded languages beyond English.
2. Build a consented, redacted evaluation corpus per language.
3. Benchmark ASR accuracy, tool-call success, latency, and voice quality against published thresholds.
4. Localize prompts, date/time/number confirmation, and safety messages.
5. Ship per-tenant language setting behind a feature flag with instant fallback to English.

## Current behavior

- `ProductPrefs.languages` is forced to `primary=en`, `enabled=["en"]` on save.
- Settings UI states the gate explicitly.
- Unsupported language requests must continue in English (no silent partial localization).

Until thresholds pass, do not expand Deepgram/prompt language paths in production.

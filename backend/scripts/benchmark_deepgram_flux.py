#!/usr/bin/env python3
"""Benchmark Deepgram Nova-3 vs Flux on Voice2Appointment sample audio (Phase 8.3).

Does NOT change production model selection. Default remains nova-3 until results
justify a swap (see docs/deepgram-flux-benchmark.md).

Usage:
  export DEEPGRAM_API_KEY=...
  python backend/scripts/benchmark_deepgram_flux.py /path/to/recording.wav

Requires: deepgram-sdk (optional; falls back to REST via httpx/requests).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

MODELS = (
    ("nova-3", {"model": "nova-3", "language": "en"}),
    ("flux-multilingual", {"model": "flux-general-en", "language": "multi"}),
)

# Appointment-vocabulary spot checks (extend per language corpus).
SPOT_TERMS = (
    "appointment",
    "calendar",
    "reschedule",
    "cancel",
    "Monday",
    "Tuesday",
    "o'clock",
    "am",
    "pm",
)


def _transcribe_rest(api_key: str, audio_path: Path, params: dict) -> tuple[str, float]:
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode(params)
    url = f"https://api.deepgram.com/v1/listen?{query}"
    data = audio_path.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/wav",
        },
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - started
    alt = (
        payload.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
    )
    transcript = alt.get("transcript") or ""
    return transcript, elapsed


def _score_spot_terms(transcript: str) -> dict[str, bool]:
    lower = transcript.lower()
    return {term: term.lower() in lower for term in SPOT_TERMS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="WAV/MP3 recording path")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("deepgram_flux_benchmark_results.json"),
        help="Write JSON results here",
    )
    args = parser.parse_args()
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        print("DEEPGRAM_API_KEY is required", file=sys.stderr)
        return 2
    if not args.audio.is_file():
        print(f"Audio not found: {args.audio}", file=sys.stderr)
        return 2

    results = []
    for label, params in MODELS:
        try:
            transcript, elapsed = _transcribe_rest(api_key, args.audio, params)
            results.append(
                {
                    "label": label,
                    "params": params,
                    "elapsed_sec": round(elapsed, 3),
                    "chars": len(transcript),
                    "spot_terms": _score_spot_terms(transcript),
                    "transcript_preview": transcript[:500],
                    "error": None,
                }
            )
            print(f"{label}: {elapsed:.2f}s chars={len(transcript)}")
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "label": label,
                    "params": params,
                    "error": str(exc),
                }
            )
            print(f"{label}: ERROR {exc}", file=sys.stderr)

    payload = {
        "audio": str(args.audio),
        "recommendation": (
            "Keep DEEPGRAM_MODEL=nova-3 until Flux wins on appointment vocabulary "
            "across EN/NL/FR/DE/TR on production call recordings."
        ),
        "results": results,
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

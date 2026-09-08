#!/usr/bin/env python3
"""Phase 12 in-process observability load + before/after comparison.

Runs synthetic metric/correlation work without live Twilio/Google/Deepgram.
Use alongside ``performance_baseline.py`` when a disposable HTTP target exists.

Usage:
  PYTHONPATH=backend python backend/scripts/observability_load.py \
    --json-out /tmp/observability-load.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextvars
import json
import statistics
import time
from pathlib import Path
from typing import Any

from app.core.correlation import (
    bind_correlation,
    celery_correlation_headers,
    get_correlation_id,
    reset_correlation,
)
from app.core.metrics import metrics
from app.voice.latency import LatencyTracker


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _extract_hist(snap: dict[str, Any], name: str) -> dict[str, Any]:
    series = (snap.get("histograms") or {}).get(name) or {}
    if not series:
        return {}
    return series.get("_") or next(iter(series.values()))


def _tool_body(index: int) -> dict[str, Any]:
    time.sleep(0.001)
    metrics.observe("voice_tool_queue_wait_ms", 0.4 + (index % 3), labels={"operation": "load_probe"})
    metrics.observe(
        "voice_tool_execution_ms",
        1.0 + (index % 5),
        labels={"operation": "load_probe", "result": "success"},
    )
    metrics.observe("booking_lock_wait_ms", 0.5, labels={"result": "acquired"})
    metrics.observe("db_transaction_duration_ms", 1.2, labels={"result": "commit"})
    metrics.observe("redis_latency_ms", 0.8, labels={"operation": "get", "result": "success"})
    metrics.observe(
        "celery_queue_wait_ms",
        2.0,
        labels={"operation": "sync", "queue": "provider_sync"},
    )
    metrics.observe(
        "calendar_lookup_latency_ms",
        5.0 + (index % 7),
        labels={"operation": "freebusy", "result": "success"},
    )
    metrics.observe(
        "calendar_create_latency_ms",
        8.0 + (index % 5),
        labels={"operation": "create_event", "result": "success"},
    )
    metrics.observe("twilio_sync_duration_ms", 12.0, labels={"result": "success"})
    return {"ok": True, "correlation_id": get_correlation_id()}


def run_synthetic_load(*, concurrency: int, iterations: int) -> dict[str, Any]:
    end_to_end: list[float] = []
    first_responses: list[float] = []

    def one(index: int) -> tuple[float, float | None]:
        started = time.perf_counter()
        tokens = bind_correlation(
            call_sid=f"CA{index:08d}load",
            request_id=f"req{index:08d}",
            operation="observability_load",
        )
        try:
            cid = get_correlation_id() or ""
            headers = celery_correlation_headers()
            assert headers.get("va_correlation_id")
            assert cid.startswith("call:")

            tracker = LatencyTracker()
            tracker.note_twilio_audio()
            tracker.note_audio_enqueued()
            tracker.note_stt_final()
            tracker.note_llm_response()
            tracker.note_tts_first_audio()
            tracker.emit_summary()
            first = tracker.snapshot()["latencies_ms"].get("tts_first_audio_ms")

            # Propagate correlation into a worker-like context (voice tools).
            ctx = contextvars.copy_context()
            result = ctx.run(_tool_body, index)
            assert result.get("ok") is True
            assert result.get("correlation_id") == cid
            return (time.perf_counter() - started) * 1000.0, (
                float(first) if first is not None else None
            )
        finally:
            reset_correlation(tokens)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one, i) for i in range(iterations)]
        for fut in concurrent.futures.as_completed(futures):
            ms, first = fut.result()
            end_to_end.append(ms)
            if first is not None:
                first_responses.append(first)

    return {
        "iterations": iterations,
        "concurrency": concurrency,
        "end_to_end_ms": {
            "p50": round(_percentile(end_to_end, 50), 3),
            "p95": round(_percentile(end_to_end, 95), 3),
            "p99": round(_percentile(end_to_end, 99), 3),
            "mean": round(statistics.fmean(end_to_end), 3) if end_to_end else 0.0,
        },
        "voice_first_response_samples": len(first_responses),
        "voice_first_response_p95_ms": round(_percentile(first_responses, 95), 3),
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    names = sorted(
        set((before.get("histograms") or {})) | set((after.get("histograms") or {}))
    )
    deltas: dict[str, Any] = {}
    for name in names:
        b = _extract_hist(before, name)
        a = _extract_hist(after, name)
        if not a and not b:
            continue
        deltas[name] = {
            "before_p95_ms": b.get("p95_ms"),
            "after_p95_ms": a.get("p95_ms"),
            "before_count": b.get("count"),
            "after_count": a.get("count"),
            "count_delta": (a.get("count") or 0) - (b.get("count") or 0),
        }
    return deltas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--json-out", default="")
    parser.add_argument(
        "--compare-with",
        default="",
        help="Optional prior report JSON for before/after delta",
    )
    args = parser.parse_args()

    before = metrics.snapshot()
    load = run_synthetic_load(concurrency=args.concurrency, iterations=args.iterations)
    after = metrics.snapshot()
    report: dict[str, Any] = {
        "kind": "observability_load",
        "started_at_epoch": time.time(),
        "load": load,
        "before": before,
        "after": after,
        "delta": compare(before, after),
        "notes": [
            "Synthetic only — not a production capacity claim.",
            "Compare voice_first_response_ms / voice_tool_* / calendar_* / redis / celery histograms.",
            "HTTP booking load requires performance_baseline.py against a disposable target.",
        ],
    }
    if args.compare_with:
        prior = json.loads(Path(args.compare_with).read_text(encoding="utf-8"))
        report["vs_prior_file"] = args.compare_with
        report["vs_prior_delta"] = compare(prior.get("after") or prior, after)

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

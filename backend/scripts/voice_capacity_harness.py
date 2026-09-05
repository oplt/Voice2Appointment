#!/usr/bin/env python3
"""Voice admission harness (P8-01 / P8-V01).

Modes:
  * ``admission`` (default) — concurrent in-process acquire/release microbenchmark.
    Unique SIDs only. Not a capacity proof for media pipelines.
  * Documented separately: media soak requires non-production gateway + fakes.

Usage (from repo root):
  PYTHONPATH=backend python backend/scripts/voice_capacity_harness.py --stages 10,25,100
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.voice.admission import CallAdmission  # noqa: E402


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _unique_sid(i: int) -> str:
    # Twilio CallSid shape: CA + 32 hex; keep unique across 1k+ attempts.
    return f"CA{uuid.uuid4().hex}"


def run_stage(target: int, *, cap: int, workers: int) -> dict:
    """Concurrent acquire attempts with unique SIDs against a shared registry."""
    adm = CallAdmission(max_concurrent=cap)
    latencies_ms: list[float] = []
    acquired: list[str] = []
    rejected = 0
    lock_stats = {"acquired": 0, "rejected": 0}

    def attempt(i: int) -> tuple[bool, float, str]:
        sid = _unique_sid(i)
        t0 = time.perf_counter()
        ok = adm.try_acquire(sid)
        ms = (time.perf_counter() - t0) * 1000.0
        return ok, ms, sid

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(attempt, i) for i in range(target)]
        for fut in concurrent.futures.as_completed(futures):
            ok, ms, sid = fut.result()
            latencies_ms.append(ms)
            if ok:
                acquired.append(sid)
                lock_stats["acquired"] += 1
            else:
                rejected += 1
                lock_stats["rejected"] += 1

    for sid in acquired:
        adm.release(sid)

    latencies_ms.sort()
    expected_acquired = min(target, cap)
    return {
        "mode": "admission_unit_benchmark",
        "stage_target": target,
        "cap": cap,
        "workers": workers,
        "unique_sids": True,
        "acquired": len(acquired),
        "rejected": rejected,
        "reject_rate": round(rejected / target, 4) if target else 0.0,
        "expected_acquired": expected_acquired,
        "admission_correct": len(acquired) == expected_acquired,
        "p50_ms": round(_percentile(latencies_ms, 50), 4),
        "p95_ms": round(_percentile(latencies_ms, 95), 4),
        "p99_ms": round(_percentile(latencies_ms, 99), 4),
        "mean_ms": round(statistics.fmean(latencies_ms), 4) if latencies_ms else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice admission capacity harness")
    parser.add_argument(
        "--stages",
        default="10,25,100",
        help="Comma-separated concurrency targets",
    )
    parser.add_argument("--cap", type=int, default=25)
    parser.add_argument(
        "--workers",
        type=int,
        default=32,
        help="Thread pool size for concurrent acquire attempts",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path to write the stage report JSON",
    )
    args = parser.parse_args()
    stages = [int(x.strip()) for x in args.stages.split(",") if x.strip()]
    report = {
        "mode": "admission_unit_benchmark",
        "note": (
            "Not a media-pipeline capacity proof. Unique SIDs + concurrent actors. "
            "For 10/100/1000 media soaks use non-production gateway + provider fakes."
        ),
        "stages": [
            run_stage(target, cap=args.cap, workers=args.workers) for target in stages
        ],
    }
    print(json.dumps(report, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    ok = all(stage["admission_correct"] for stage in report["stages"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

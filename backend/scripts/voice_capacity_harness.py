#!/usr/bin/env python3
"""Content-free voice admission load harness (P8-01).

Does not open Twilio/Deepgram sockets or send audio. Measures acquire/release
latency and reject rate at staged concurrency against the in-process admission
registry.

Usage (from repo root):
  PYTHONPATH=backend python backend/scripts/voice_capacity_harness.py --stages 10,25,100
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
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


def run_stage(target: int, *, cap: int) -> dict:
    """Attempt to hold `target` concurrent slots against a registry capped at `cap`."""
    adm = CallAdmission(max_concurrent=cap)
    latencies_ms: list[float] = []
    acquired: list[str] = []
    rejected = 0

    for i in range(target):
        sid = f"CA{'x' * 30}{i:02d}"[:34]
        t0 = time.perf_counter()
        ok = adm.try_acquire(sid)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if ok:
            acquired.append(sid)
        else:
            rejected += 1

    for sid in acquired:
        adm.release(sid)

    latencies_ms.sort()
    return {
        "stage_target": target,
        "cap": cap,
        "acquired": len(acquired),
        "rejected": rejected,
        "reject_rate": round(rejected / target, 4) if target else 0.0,
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
        help="Comma-separated concurrency targets (1000 is multi-instance math only)",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=25,
        help="Per-instance admission cap (default 25)",
    )
    args = parser.parse_args()
    stages = [int(x.strip()) for x in args.stages.split(",") if x.strip()]
    print(f"per_instance_cap={args.cap}")
    for stage in stages:
        if stage > args.cap * 40:
            # Documented: do not pretend one node holds 1000 sessions.
            instances_needed = (stage + args.cap - 1) // args.cap
            print(
                f"stage={stage} note=horizontal_only "
                f"instances_needed>={instances_needed} "
                f"(not run as single-process acquire)"
            )
            continue
        result = run_stage(stage, cap=args.cap)
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 6 — record before/after-style performance evidence for offload & batching.

Writes artifacts/phase6-performance-evidence.json (repo root).
Does not claim production SLOs; measures local micro-benchmarks only.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "phase6-performance-evidence.json"


def _bench_thread_offload() -> dict:
    from app.core.thread_db import to_thread_db

    def slow(_db, delay: float) -> float:
        time.sleep(delay)
        return delay

    async def sequential() -> float:
        started = time.perf_counter()
        await to_thread_db(slow, 0.08)
        await to_thread_db(slow, 0.08)
        return time.perf_counter() - started

    async def parallel() -> float:
        started = time.perf_counter()
        await asyncio.gather(to_thread_db(slow, 0.08), to_thread_db(slow, 0.08))
        return time.perf_counter() - started

    seq = asyncio.run(sequential())
    par = asyncio.run(parallel())
    return {
        "name": "to_thread_db_parallel_vs_sequential",
        "sequential_s": round(seq, 4),
        "parallel_s": round(par, 4),
        "speedup_x": round(seq / par, 2) if par > 0 else None,
        "pass": par < seq * 0.85 and par < 0.14,
        "notes": "Simulates concurrent webhook/DB work off the event loop (Phase 2).",
    }


def _bench_voice_read_batch_contract() -> dict:
    """Evidence that the batching barrier exists; timing comes from unit test semantics."""
    from app.voice import session as voice_session
    import inspect

    src = inspect.getsource(voice_session)
    has_batch = "asyncio.gather" in src
    return {
        "name": "voice_read_tool_batching_present",
        "batching_symbols_present": has_batch,
        "pass": has_batch,
        "notes": (
            "Sequential vs concurrent latency is covered by "
            "test_voice_read_calls_are_batched_with_mutation_barrier; "
            "this check records that the production path retains asyncio.gather batching."
        ),
    }


def _bundle_artifact() -> dict:
    path = ROOT / "frontend" / "artifacts" / "bundle-size.json"
    if not path.is_file():
        return {
            "name": "frontend_bundle_report",
            "pass": False,
            "error": "frontend/artifacts/bundle-size.json missing — run npm run build && npm run bundle:report",
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "name": "frontend_bundle_report",
        "pass": True,
        "totalJsBytes": data.get("totalJsBytes"),
        "initialJsBytes": data.get("initialJsBytes"),
        "routeJsBytes": data.get("routeJsBytes"),
        "lazyVisualizationJsBytes": data.get("lazyVisualizationJsBytes"),
        "largestChunk": data.get("largestChunk"),
        "notes": "Analytics charts are lazy-split (Phase 5.8); inspect lazyVisualizationJsBytes.",
    }


def _analytics_refresh_contract() -> dict:
    from app.analytics import router as analytics_router
    import inspect

    src = inspect.getsource(analytics_router)
    returns_202 = "202" in src and "fetch" in src.lower()
    uses_thread = "to_thread_db" in src
    return {
        "name": "analytics_manual_refresh_enqueue",
        "returns_accepted_pattern": returns_202,
        "offloads_enqueue": uses_thread,
        "pass": returns_202 and uses_thread,
        "notes": "test_fetch_twilio_returns_202_and_enqueues proves quick return after enqueue.",
    }


def main() -> int:
    results = [
        _bench_thread_offload(),
        _bench_voice_read_batch_contract(),
        _analytics_refresh_contract(),
        _bundle_artifact(),
    ]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Local micro-benchmarks and static contracts — not production load tests. "
            "Do not claim SLOs from these numbers alone."
        ),
        "results": results,
        "allPassed": all(bool(r.get("pass")) for r in results),
        "pool_metrics": {
            "notes": (
                "DB/Redis pool gauges are exposed via MetricsRegistry "
                "(db_pool_checked_out, db_pool_wait_ms); see test_performance_metrics."
            )
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["allPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

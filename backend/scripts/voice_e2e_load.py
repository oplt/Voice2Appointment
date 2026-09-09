#!/usr/bin/env python3
"""Disposable Phase 14 voice E2E / load harness (stages 1,5,10,25).

Measures in-process voice tool runtime queue+exec, CallAdmission per stage,
optional HTTP health, and optional Deepgram WS connect/disconnect latency.
Does **not** place live Twilio calls unless ``--live-twilio`` is passed
(still a stub flag — live placement is out of scope for this harness).

Usage (repo root):
  PYTHONPATH=backend python backend/scripts/voice_e2e_load.py \\
    --stages 1,5,10,25 --json-out /tmp/voice-e2e-load.json
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Load dotenv without printing secrets.
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO / ".env")
    load_dotenv(_BACKEND / ".env", override=True)
except Exception:  # noqa: BLE001
    pass

from app.core.config import settings  # noqa: E402
from app.voice.admission import CallAdmission  # noqa: E402
from app.voice.tool_runtime import (  # noqa: E402
    VoiceToolBusyError,
    get_voice_tool_runtime,
    shutdown_voice_tool_runtime,
)


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


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "mean_ms": 0.0}
    return {
        "p50_ms": round(_percentile(values, 50), 4),
        "p95_ms": round(_percentile(values, 95), 4),
        "p99_ms": round(_percentile(values, 99), 4),
        "mean_ms": round(statistics.fmean(values), 4),
    }


def _noop_tool() -> dict[str, Any]:
    # Lightweight sync work (no secrets); optional DB touch when DATABASE_URL set.
    touch = {"ok": True}
    db_url = (settings.database_url or "").strip()
    if db_url and "://" in db_url:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(db_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            touch["db"] = "ok"
            engine.dispose()
        except Exception as exc:  # noqa: BLE001
            touch["db"] = type(exc).__name__
    else:
        touch["db"] = "skipped"
    return touch


async def _run_tool_once(runtime: Any, operation: str) -> tuple[float, float, str]:
    queued_at = time.perf_counter()
    try:
        await runtime.run(operation, _noop_tool)
        total_ms = (time.perf_counter() - queued_at) * 1000.0
        return total_ms, total_ms, "ok"
    except VoiceToolBusyError:
        return (time.perf_counter() - queued_at) * 1000.0, 0.0, "busy"
    except Exception as exc:  # noqa: BLE001
        return (time.perf_counter() - queued_at) * 1000.0, 0.0, type(exc).__name__


def run_tool_stage(
    concurrency: int,
    *,
    inject_busy: bool,
) -> dict[str, Any]:
    """Measure voice tool runtime under concurrent noop/db-touch load."""
    # Fresh runtime so busy injection can saturate a known small executor.
    shutdown_voice_tool_runtime()
    if inject_busy:
        os.environ["VOICE_TOOL_WORKERS"] = "1"
        os.environ["VOICE_TOOL_QUEUE_SIZE"] = "1"
        # Settings already loaded — rebuild runtime with tiny bounds.
        from app.voice import tool_runtime as tr

        tr._runtime = tr.VoiceToolRuntime(workers=1, queue_size=1)
        runtime = tr._runtime
        # Saturate: hold workers with long sleep, then probe.
        hold = concurrent.futures.Future()

        def blocker() -> dict[str, Any]:
            time.sleep(0.35)
            return {"blocked": True}

        async def saturate_and_probe() -> dict[str, Any]:
            # Fill workers+queue so later submits are busy.
            fillers = [
                asyncio.create_task(runtime.run(f"fill-{i}", blocker))
                for i in range(2)
            ]
            await asyncio.sleep(0.02)
            probe_latencies: list[float] = []
            results: list[str] = []
            for _ in range(concurrency):
                t0 = time.perf_counter()
                try:
                    await runtime.run("probe", _noop_tool)
                    results.append("ok")
                except VoiceToolBusyError:
                    results.append("busy")
                except Exception as exc:  # noqa: BLE001
                    results.append(type(exc).__name__)
                probe_latencies.append((time.perf_counter() - t0) * 1000.0)
            await asyncio.gather(*fillers, return_exceptions=True)
            hold.set_result(True)
            return {
                "latencies_ms": probe_latencies,
                "results": results,
            }

        outcome = asyncio.run(saturate_and_probe())
        shutdown_voice_tool_runtime()
        busy_count = sum(1 for r in outcome["results"] if r == "busy")
        return {
            "stage": concurrency,
            "mode": "busy_tools_injection",
            "attempts": concurrency,
            "busy": busy_count,
            "ok": sum(1 for r in outcome["results"] if r == "ok"),
            "tool_total_ms": _stats(outcome["latencies_ms"]),
            "note": "Saturated VoiceToolRuntime (workers=1, queue=1); expect busy rejects",
        }

    runtime = get_voice_tool_runtime()

    async def stage() -> dict[str, Any]:
        tasks = [
            _run_tool_once(runtime, f"e2e-noop-{i}") for i in range(concurrency)
        ]
        rows = await asyncio.gather(*tasks)
        totals = [r[0] for r in rows]
        statuses = [r[2] for r in rows]
        return {
            "totals": totals,
            "statuses": statuses,
        }

    outcome = asyncio.run(stage())
    shutdown_voice_tool_runtime()
    return {
        "stage": concurrency,
        "mode": "tool_runtime",
        "attempts": concurrency,
        "ok": sum(1 for s in outcome["statuses"] if s == "ok"),
        "busy": sum(1 for s in outcome["statuses"] if s == "busy"),
        "errors": [
            s for s in outcome["statuses"] if s not in {"ok", "busy"}
        ],
        "tool_total_ms": _stats(outcome["totals"]),
    }


def run_admission_stage(concurrency: int, *, cap: int) -> dict[str, Any]:
    adm = CallAdmission(max_concurrent=cap)
    latencies: list[float] = []
    acquired: list[str] = []
    rejected = 0

    def attempt(i: int) -> tuple[bool, float, str]:
        sid = f"CA{uuid.uuid4().hex}"
        t0 = time.perf_counter()
        ok = adm.try_acquire(sid)
        return ok, (time.perf_counter() - t0) * 1000.0, sid

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, concurrency)
    ) as pool:
        futures = [pool.submit(attempt, i) for i in range(concurrency)]
        for fut in concurrent.futures.as_completed(futures):
            ok, ms, sid = fut.result()
            latencies.append(ms)
            if ok:
                acquired.append(sid)
            else:
                rejected += 1
    for sid in acquired:
        adm.release(sid)
    return {
        "stage": concurrency,
        "cap": cap,
        "acquired": len(acquired),
        "rejected": rejected,
        "admission_ms": _stats(latencies),
    }


def probe_health(base_url: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/health"
    t0 = time.perf_counter()
    try:
        with urlopen(url, timeout=5) as resp:
            body = resp.read(256)
            status = int(getattr(resp, "status", 200) or 200)
        return {
            "ok": 200 <= status < 400,
            "status": status,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "bytes": len(body),
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }


def probe_deepgram_ws() -> dict[str, Any]:
    """Connect/disconnect latency only — no audio, no Twilio."""
    api_key = (os.getenv("DEEPGRAM_API_KEY") or settings.deepgram_api_key or "").strip()
    if not api_key:
        return {"skipped": True, "reason": "DEEPGRAM_API_KEY not set"}

    async def _ping() -> dict[str, Any]:
        try:
            import websockets
            from websockets.typing import Subprotocol
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"websockets_import:{type(exc).__name__}"}

        endpoint = (settings.deepgram_agent_url or "").strip() or (
            "wss://agent.deepgram.com/v1/agent/converse"
        )
        t0 = time.perf_counter()
        try:
            async with websockets.connect(
                endpoint,
                subprotocols=[Subprotocol("token"), Subprotocol(api_key)],
                open_timeout=10,
                close_timeout=5,
            ):
                connect_ms = (time.perf_counter() - t0) * 1000.0
            total_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "ok": True,
                "connect_ms": round(connect_ms, 3),
                "connect_disconnect_ms": round(total_ms, 3),
                "endpoint_host": endpoint.split("/")[2] if "://" in endpoint else "redacted",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": type(exc).__name__,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }

    return asyncio.run(_ping())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", default="1,5,10,25")
    parser.add_argument("--cap", type=int, default=25)
    parser.add_argument("--base-url", default="", help="Optional HTTP base for /health")
    parser.add_argument(
        "--inject",
        action="append",
        default=[],
        help="Failure injection: redis-down | busy-tools (repeatable)",
    )
    parser.add_argument(
        "--live-twilio",
        action="store_true",
        help="Reserved; this harness never places live Twilio calls",
    )
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    stages = [int(x.strip()) for x in args.stages.split(",") if x.strip()]
    inject = {str(x).strip().lower() for x in (args.inject or [])}

    notes: list[str] = []
    if args.live_twilio:
        notes.append(
            "live-twilio flag set but harness does not place Twilio calls "
            "(connect probes only)."
        )
    if "redis-down" in inject:
        notes.append(
            "inject=redis-down: skipped (no Redis client forced down in this harness)."
        )

    tool_stages = [
        run_tool_stage(n, inject_busy=("busy-tools" in inject)) for n in stages
    ]
    admission_stages = [run_admission_stage(n, cap=args.cap) for n in stages]

    health: dict[str, Any] | None = None
    if args.base_url.strip():
        health = probe_health(args.base_url.strip())
    else:
        health = {"skipped": True, "reason": "no --base-url"}

    deepgram = probe_deepgram_ws()

    report = {
        "kind": "voice_e2e_load",
        "stages": stages,
        "inject": sorted(inject),
        "notes": notes,
        "tool_runtime": tool_stages,
        "call_admission": admission_stages,
        "http_health": health,
        "deepgram_ws_ping": deepgram,
        "live_twilio": False,
        "synthetic": True,
        "disclaimer": (
            "Not a production p95 claim. Tool/admission stages are in-process; "
            "Deepgram probe is connect/disconnect only."
        ),
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

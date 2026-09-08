#!/usr/bin/env python3
"""Run repeatable Phase 0 HTTP load scenarios against a non-production target.

The scenario file deliberately supplies paths, headers and payloads instead of
embedding product credentials or mutating production data.  A fake Google/Twilio
provider can be selected in the target environment for the timeout scenario.

Usage:
  PYTHONPATH=backend python backend/scripts/performance_baseline.py \
    --config backend/scripts/performance-baseline.example.json \
    --confirm-target http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _request(base_url: str, spec: dict[str, Any]) -> tuple[bool, float, str]:
    path = str(spec.get("path", ""))
    url = path if path.startswith(("http://", "https://")) else base_url + path
    method = str(spec.get("method", "GET")).upper()
    payload = spec.get("json")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {str(key): str(value) for key, value in (spec.get("headers") or {}).items()}
    if body is not None:
        headers.setdefault("Content-Type", "application/json")
    started = time.perf_counter()
    try:
        with urlopen(
            Request(url, data=body, headers=headers, method=method),
            timeout=float(spec.get("timeout_seconds", 10)),
        ) as response:
            response.read()
            return 200 <= response.status < 400, (time.perf_counter() - started) * 1000, str(response.status)
    except HTTPError as exc:
        return False, (time.perf_counter() - started) * 1000, str(exc.code)
    except (URLError, TimeoutError) as exc:
        return False, (time.perf_counter() - started) * 1000, type(exc).__name__


def run_scenario(base_url: str, name: str, scenario: dict[str, Any]) -> dict[str, Any]:
    """Issue declared requests concurrently; request ordering is never implied."""
    requests = scenario.get("requests") or []
    if not isinstance(requests, list) or not requests:
        raise ValueError(f"scenario {name!r} needs at least one request")
    iterations = int(scenario.get("iterations", len(requests)))
    concurrency = int(scenario.get("concurrency", min(iterations, 10)))
    if iterations < 1 or concurrency < 1:
        raise ValueError(f"scenario {name!r} iterations and concurrency must be positive")

    latencies: list[float] = []
    statuses: dict[str, int] = {}
    succeeded = 0

    def perform(index: int) -> tuple[bool, float, str]:
        return _request(base_url, requests[index % len(requests)])

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(perform, index) for index in range(iterations)]
        for future in concurrent.futures.as_completed(futures):
            ok, latency_ms, status = future.result()
            latencies.append(latency_ms)
            statuses[status] = statuses.get(status, 0) + 1
            succeeded += int(ok)

    return {
        "scenario": name,
        "iterations": iterations,
        "concurrency": concurrency,
        "successes": succeeded,
        "failures": iterations - succeeded,
        "status_counts": statuses,
        "p50_ms": round(_percentile(latencies, 50), 3),
        "p95_ms": round(_percentile(latencies, 95), 3),
        "p99_ms": round(_percentile(latencies, 99), 3),
        "mean_ms": round(statistics.fmean(latencies), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Scenario JSON file")
    parser.add_argument(
        "--confirm-target",
        required=True,
        help="Exact base_url from the scenario file; prevents accidental execution",
    )
    parser.add_argument("--json-out", default="", help="Optional report JSON path")
    parser.add_argument(
        "--compare-with",
        default="",
        help="Optional prior baseline JSON; emit scenario p95 deltas",
    )
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    base_url = str(config.get("base_url", "")).rstrip("/")
    if not base_url or args.confirm_target.rstrip("/") != base_url:
        parser.error("--confirm-target must exactly match config base_url")
    scenarios = config.get("scenarios") or {}
    required = {
        "dashboard",
        "availability",
        "booking_one_tenant",
        "booking_different_tenants",
        "voice_function_calls",
        "provider_timeouts",
    }
    missing = required.difference(scenarios)
    if missing:
        parser.error(f"scenario file is missing: {', '.join(sorted(missing))}")

    report = {
        "base_url": base_url,
        "started_at_epoch": time.time(),
        "scenarios": [
            run_scenario(base_url, name, scenarios[name]) for name in sorted(required)
        ],
    }
    if args.compare_with:
        prior = json.loads(Path(args.compare_with).read_text(encoding="utf-8"))
        prior_by_name = {
            row["scenario"]: row for row in (prior.get("scenarios") or []) if "scenario" in row
        }
        deltas = []
        for row in report["scenarios"]:
            prev = prior_by_name.get(row["scenario"]) or {}
            deltas.append(
                {
                    "scenario": row["scenario"],
                    "p95_before_ms": prev.get("p95_ms"),
                    "p95_after_ms": row.get("p95_ms"),
                    "p95_delta_ms": (
                        None
                        if prev.get("p95_ms") is None
                        else round(float(row["p95_ms"]) - float(prev["p95_ms"]), 3)
                    ),
                    "failures_before": prev.get("failures"),
                    "failures_after": row.get("failures"),
                }
            )
        report["compare_with"] = args.compare_with
        report["p95_deltas"] = deltas
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

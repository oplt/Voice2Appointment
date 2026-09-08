"""Phase 12 — correlation, percentiles, and observability load."""

from __future__ import annotations

import contextvars
import json
from pathlib import Path

from app.core.correlation import (
    bind_correlation,
    celery_correlation_headers,
    get_correlation_id,
    reset_correlation,
    resolve_correlation_id,
)
from app.core.metrics import MetricsRegistry
from app.voice.latency import LatencyTracker


def test_correlation_prefers_call_sid() -> None:
    tokens = bind_correlation(request_id="abc", call_sid="CAdeadbeef")
    try:
        assert get_correlation_id() == "call:CAdeadbeef"
        headers = celery_correlation_headers()
        assert headers["va_correlation_id"] == "call:CAdeadbeef"
        assert headers["va_call_sid"] == "CAdeadbeef"
        assert headers["va_request_id"] == "abc"
    finally:
        reset_correlation(tokens)


def test_correlation_propagates_into_copied_context() -> None:
    tokens = bind_correlation(call_sid="CA123", operation="voice_tool")
    try:
        outer = get_correlation_id()

        def worker() -> str | None:
            return get_correlation_id()

        ctx = contextvars.copy_context()
        assert ctx.run(worker) == outer
    finally:
        reset_correlation(tokens)


def test_resolve_correlation_explicit_wins() -> None:
    assert resolve_correlation_id(explicit="custom-id", call_sid="CA1") == "custom-id"


def test_metrics_snapshot_includes_percentiles() -> None:
    registry = MetricsRegistry()
    for value in (10.0, 20.0, 30.0, 40.0, 100.0):
        registry.observe("voice_tool_execution_ms", value, labels={"operation": "x", "result": "success"})
    snap = registry.snapshot()
    series = snap["histograms"]["voice_tool_execution_ms"]["operation=x,result=success"]
    assert series["count"] == 5
    assert series["p50_ms"] == 30.0
    assert series["p95_ms"] >= 40.0
    assert series["p99_ms"] >= 40.0
    assert "samples" in series


def test_latency_tracker_emits_first_response_metric() -> None:
    registry = MetricsRegistry()
    # Patch module singleton temporarily via attribute swap on observe path
    from app.core import metrics as metrics_mod

    previous = metrics_mod.metrics
    metrics_mod.metrics = registry
    try:
        tracker = LatencyTracker()
        tracker.note_stt_final()
        tracker.note_llm_response()
        tracker.note_tts_first_audio()
        tracker.emit_summary()
        hist = registry.snapshot()["histograms"]
        assert "voice_first_response_ms" in hist
        assert hist["voice_first_response_ms"]["_"]["count"] == 1
    finally:
        metrics_mod.metrics = previous


def test_observability_load_script_runs(tmp_path: Path) -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "observability_load.py"
    spec = importlib.util.spec_from_file_location("observability_load", path)
    assert spec and spec.loader
    load_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load_mod)

    before = load_mod.metrics.snapshot()
    result = load_mod.run_synthetic_load(concurrency=4, iterations=8)
    after = load_mod.metrics.snapshot()
    assert result["iterations"] == 8
    assert result["end_to_end_ms"]["p95"] >= 0
    delta = load_mod.compare(before, after)
    assert "voice_first_response_ms" in delta or "voice_tool_queue_wait_ms" in delta
    out = tmp_path / "report.json"
    out.write_text(json.dumps({"after": after}) + "\n", encoding="utf-8")
    assert out.exists()

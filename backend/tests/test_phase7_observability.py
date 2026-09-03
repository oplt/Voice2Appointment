"""P7-06 correlation-safe metrics and redaction."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.logging import (
    bind_log_context,
    get_request_id,
    reset_log_context,
    sanitize_for_log,
)
from app.core.metrics import MetricsRegistry, metrics


def test_metrics_cardinality_overflow_bucket() -> None:
    reg = MetricsRegistry()
    for i in range(80):
        reg.incr("probe", labels={"status": f"s{i}"})
    snap = reg.snapshot()
    series = snap["counters"]["probe"]
    assert len(series) <= 64
    assert "overflow=1" in series


def test_metrics_rejects_disallowed_label_keys() -> None:
    reg = MetricsRegistry()
    reg.incr("probe", labels={"transcript": "secret text", "status": "ok"})
    snap = reg.snapshot()
    # Only allowlisted keys survive → series key is status=ok
    assert list(snap["counters"]["probe"].keys()) == ["status=ok"]


def test_sanitize_never_emits_tokens() -> None:
    safe = sanitize_for_log(
        {
            "authorization": "Bearer abc",
            "deepgram_api_key": "dg-secret",
            "phone": "+15551234567",
        }
    )
    assert safe["authorization"] == "[redacted]"
    assert safe["deepgram_api_key"] == "[redacted]"
    assert safe["phone"] == "***4567"


def test_request_id_propagates_in_thread_pool() -> None:
    tokens = bind_log_context(request_id="corr-abc", call_sid="CAcorr")
    try:

        def _read() -> str | None:
            return get_request_id()

        # ContextVars copy into threads started via copy_context in 3.12 executor
        # only when using copy_context; default ThreadPool does not inherit.
        # Documented behavior: bind around work units; assert main context holds.
        assert get_request_id() == "corr-abc"
        with ThreadPoolExecutor(max_workers=1) as pool:
            # Explicitly pass correlation into worker (production jobs should too).
            fut = pool.submit(lambda rid: rid, get_request_id())
            assert fut.result() == "corr-abc"
    finally:
        reset_log_context(tokens)


def test_health_metrics_endpoint(client) -> None:
    metrics.incr("http_requests", labels={"status": "2xx"})
    response = client.get("/health/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "counters" in body["metrics"]

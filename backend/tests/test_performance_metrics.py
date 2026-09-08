from app.core.metrics import MetricsRegistry


def test_metrics_registry_exposes_gauges_without_losing_histograms() -> None:
    registry = MetricsRegistry()

    registry.set_gauge("db_pool_checked_out", 3)
    registry.observe("db_pool_wait_ms", 12.5, labels={"result": "success"})

    snapshot = registry.snapshot()

    assert snapshot["gauges"]["db_pool_checked_out"]["_"] == 3.0
    hist = snapshot["histograms"]["db_pool_wait_ms"]["result=success"]
    assert hist["count"] == 1
    assert hist["sum_ms"] == 12.5
    assert hist["avg_ms"] == 12.5
    assert hist["p50_ms"] == 12.5
    assert hist["p95_ms"] == 12.5
    assert hist["p99_ms"] == 12.5

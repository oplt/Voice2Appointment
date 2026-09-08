"""Bounded in-process metrics for SLO-oriented observability (P7-06 / Phase 12).

Cardinality is deliberately low: only allowlisted label keys/values.
Never attach transcripts, phone numbers, tokens, or free-text as labels.

Histograms keep a ring buffer of recent samples so snapshots can report
p50/p95/p99 without unbounded memory growth.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any

_ALLOWED_LABEL_KEYS = frozenset(
    {
        "status",
        "outcome",
        "provider",
        "operation",
        "result",
        "cache",
        "queue",
        "category",
        "stage",
    }
)

# Cap distinct label combinations per metric name.
_MAX_SERIES_PER_METRIC = 64
# Recent samples retained per series for percentile estimates.
_MAX_SAMPLES_PER_SERIES = 256


def _percentile(ordered: list[float], percentile: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


class MetricsRegistry:
    """Process-local counters and latency observations with percentile samples."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._hist_sum: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._hist_count: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._hist_samples: dict[str, dict[str, deque[float]]] = defaultdict(dict)
        self._gauges: dict[str, dict[str, float]] = defaultdict(dict)
        self._started_at = time.time()

    @staticmethod
    def _series_key(labels: dict[str, str] | None) -> str:
        if not labels:
            return ""
        from app.core.logging import redact_phones

        parts: list[str] = []
        for key in sorted(labels):
            if key not in _ALLOWED_LABEL_KEYS:
                continue
            value = redact_phones(str(labels[key]))[:48]
            parts.append(f"{key}={value}")
        return ",".join(parts)

    def incr(
        self,
        name: str,
        *,
        amount: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        key = self._series_key(labels)
        with self._lock:
            series = self._counters[name]
            if key not in series:
                if key != "overflow=1" and len(series) >= _MAX_SERIES_PER_METRIC - 1:
                    key = "overflow=1"
            series[key] += amount

    def observe(
        self,
        name: str,
        value_ms: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        key = self._series_key(labels)
        sample = float(value_ms)
        with self._lock:
            sums = self._hist_sum[name]
            counts = self._hist_count[name]
            samples = self._hist_samples[name]
            if key not in sums:
                if key != "overflow=1" and len(sums) >= _MAX_SERIES_PER_METRIC - 1:
                    key = "overflow=1"
            sums[key] += sample
            counts[key] += 1.0
            bucket = samples.get(key)
            if bucket is None:
                bucket = deque(maxlen=_MAX_SAMPLES_PER_SERIES)
                samples[key] = bucket
            bucket.append(sample)

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a low-cardinality instantaneous measurement."""
        key = self._series_key(labels)
        with self._lock:
            series = self._gauges[name]
            if key not in series:
                if key != "overflow=1" and len(series) >= _MAX_SERIES_PER_METRIC - 1:
                    key = "overflow=1"
            series[key] = float(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = {
                name: dict(series) for name, series in self._counters.items()
            }
            histograms: dict[str, dict[str, Any]] = {}
            for name, sums in self._hist_sum.items():
                histograms[name] = {}
                for key, total in sums.items():
                    count = self._hist_count[name].get(key, 0.0)
                    sample_values = list(self._hist_samples[name].get(key, ()))
                    ordered = sorted(sample_values)
                    histograms[name][key or "_"] = {
                        "count": int(count),
                        "sum_ms": round(total, 3),
                        "avg_ms": round(total / count, 3) if count else 0.0,
                        "p50_ms": round(_percentile(ordered, 50), 3),
                        "p95_ms": round(_percentile(ordered, 95), 3),
                        "p99_ms": round(_percentile(ordered, 99), 3),
                        "samples": len(ordered),
                    }
            return {
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "counters": counters,
                "gauges": {
                    name: {key or "_": round(value, 3) for key, value in series.items()}
                    for name, series in self._gauges.items()
                },
                "histograms": histograms,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._hist_sum.clear()
            self._hist_count.clear()
            self._hist_samples.clear()
            self._started_at = time.time()


metrics = MetricsRegistry()

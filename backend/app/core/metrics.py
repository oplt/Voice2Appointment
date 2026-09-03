"""Bounded in-process metrics for SLO-oriented observability (P7-06).

Cardinality is deliberately low: only allowlisted label keys/values.
Never attach transcripts, phone numbers, tokens, or free-text as labels.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
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
    }
)

# Cap distinct label combinations per metric name.
_MAX_SERIES_PER_METRIC = 64


class MetricsRegistry:
    """Process-local counters and simple latency observations."""

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
        self._started_at = time.time()

    @staticmethod
    def _series_key(labels: dict[str, str] | None) -> str:
        if not labels:
            return ""
        parts: list[str] = []
        for key in sorted(labels):
            if key not in _ALLOWED_LABEL_KEYS:
                continue
            value = str(labels[key])[:48]
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
                # Reserve one slot for the overflow bucket.
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
        with self._lock:
            sums = self._hist_sum[name]
            counts = self._hist_count[name]
            if key not in sums:
                if key != "overflow=1" and len(sums) >= _MAX_SERIES_PER_METRIC - 1:
                    key = "overflow=1"
            sums[key] += float(value_ms)
            counts[key] += 1.0

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
                    histograms[name][key or "_"] = {
                        "count": int(count),
                        "sum_ms": round(total, 3),
                        "avg_ms": round(total / count, 3) if count else 0.0,
                    }
            return {
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "counters": counters,
                "histograms": histograms,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._hist_sum.clear()
            self._hist_count.clear()
            self._started_at = time.time()


metrics = MetricsRegistry()

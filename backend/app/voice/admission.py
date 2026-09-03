"""Per-instance concurrent call admission (P8-01).

Process-local only: each voice gateway process enforces its own cap.
Scale-out is horizontal (N instances × cap), never 1,000 on one node by assumption.
"""

from __future__ import annotations

import threading
from typing import Any


class CallAdmission:
    """Track active media sessions and reject when at capacity."""

    def __init__(self, *, max_concurrent: int = 25) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._max_concurrent = max(1, int(max_concurrent))
        self._rejected_total = 0
        self._accepted_total = 0

    @property
    def cap(self) -> int:
        return self._max_concurrent

    def configure(self, max_concurrent: int) -> None:
        with self._lock:
            self._max_concurrent = max(1, int(max_concurrent))

    def try_acquire(self, call_sid: str) -> bool:
        sid = (call_sid or "").strip()
        if not sid:
            return False
        with self._lock:
            if sid in self._active:
                # Idempotent re-acquire for the same call (reconnect path).
                self._accepted_total += 1
                return True
            if len(self._active) >= self._max_concurrent:
                self._rejected_total += 1
                return False
            self._active.add(sid)
            self._accepted_total += 1
            return True

    def release(self, call_sid: str) -> None:
        sid = (call_sid or "").strip()
        if not sid:
            return
        with self._lock:
            self._active.discard(sid)

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = len(self._active)
            return {
                "active_calls": active,
                "cap": self._max_concurrent,
                "utilization": round(active / self._max_concurrent, 4)
                if self._max_concurrent
                else 0.0,
                "accepted_total": self._accepted_total,
                "rejected_total": self._rejected_total,
            }

    def reset(self) -> None:
        """Test helper — clear active set and counters."""
        with self._lock:
            self._active.clear()
            self._rejected_total = 0
            self._accepted_total = 0


def _default_cap() -> int:
    try:
        from app.core.config import settings

        return int(settings.voice_max_concurrent_calls)
    except Exception:  # noqa: BLE001
        return 25


admission = CallAdmission(max_concurrent=_default_cap())

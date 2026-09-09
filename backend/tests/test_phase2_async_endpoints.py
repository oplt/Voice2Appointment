"""Phase 2.1 — thread offload for sync endpoint workloads."""

from __future__ import annotations

import asyncio
import time

from app.core.thread_db import to_thread_db


def test_to_thread_db_allows_parallel_sync_work() -> None:
    def slow_db(_db, delay: float) -> float:
        time.sleep(delay)
        return delay

    async def run_case() -> tuple[list[float], float]:
        started = time.perf_counter()
        results = await asyncio.gather(
            to_thread_db(slow_db, 0.15),
            to_thread_db(slow_db, 0.15),
        )
        return list(results), time.perf_counter() - started

    results, elapsed = asyncio.run(run_case())
    assert results == [0.15, 0.15]
    assert elapsed < 0.30

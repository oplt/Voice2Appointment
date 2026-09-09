"""Bounded executor for blocking voice tools.

Tool functions create their own database session inside the worker; this runtime
only owns admission and threads, never SQLAlchemy state or provider clients.
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from threading import BoundedSemaphore
from typing import Any, Callable

from app.core.config import settings
from app.core.metrics import metrics


class ToolKind(StrEnum):
    READ = "read"
    MUTATION = "mutation"


@dataclass(frozen=True)
class ToolMetadata:
    kind: ToolKind
    capabilities: frozenset[str]


def _metadata_from_registry() -> dict[str, ToolMetadata]:
    from app.voice.registry.core import get_tool_registry

    out: dict[str, ToolMetadata] = {}
    for name, (kind, capabilities) in get_tool_registry().metadata_by_name().items():
        out[name] = ToolMetadata(kind=ToolKind(kind.value), capabilities=capabilities)
    return out


# Lazy-populated so importing this module does not force registry init cycles.
TOOL_METADATA: dict[str, ToolMetadata] = {}


def get_tool_metadata(name: str) -> ToolMetadata | None:
    global TOOL_METADATA
    if not TOOL_METADATA:
        TOOL_METADATA = _metadata_from_registry()
    return TOOL_METADATA.get(name)


class VoiceToolBusyError(RuntimeError):
    pass


class VoiceToolRuntime:
    def __init__(self, *, workers: int, queue_size: int) -> None:
        self._workers = workers
        self._queue_size = queue_size
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="voice-tool")
        self._admission = BoundedSemaphore(workers + queue_size)
        self._closed = False

    async def run(
        self,
        operation: str,
        func: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if self._closed or not self._admission.acquire(blocking=False):
            metrics.incr("voice_tool_admission", labels={"result": "rejected"})
            raise VoiceToolBusyError("voice tools are busy")
        queued_at = time.perf_counter()
        # Propagate request/call/correlation ContextVars into the worker thread.
        ctx = contextvars.copy_context()

        def invoke() -> dict[str, Any]:
            started = time.perf_counter()
            metrics.observe(
                "voice_tool_queue_wait_ms",
                (started - queued_at) * 1000.0,
                labels={"operation": operation},
            )
            result = "success"
            try:
                return ctx.run(func)
            except Exception:  # noqa: BLE001
                result = "failure"
                raise
            finally:
                self._admission.release()
                metrics.observe(
                    "voice_tool_execution_ms",
                    (time.perf_counter() - started) * 1000.0,
                    labels={"operation": operation, "result": result},
                )

        try:
            submitted = self._executor.submit(invoke)
        except Exception:
            # Admission was taken before submit; release if the executor rejects work.
            self._admission.release()
            metrics.incr("voice_tool_admission", labels={"result": "submit_failed"})
            raise
        # Prefer wrap_future over 1ms polling — fewer event-loop wakeups.
        return await asyncio.wrap_future(submitted)

    def shutdown(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)


_runtime: VoiceToolRuntime | None = None


def get_voice_tool_runtime() -> VoiceToolRuntime:
    global _runtime
    if _runtime is None or _runtime._closed:
        _runtime = VoiceToolRuntime(
            workers=settings.voice_tool_workers,
            queue_size=settings.voice_tool_queue_size,
        )
    return _runtime


def shutdown_voice_tool_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.shutdown()
        _runtime = None

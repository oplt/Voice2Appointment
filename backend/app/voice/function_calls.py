"""Function-call execution with read batching and mutation barriers."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

from app.core.logging import log_event, sanitize_for_log
from app.voice.context import CallContext
from app.voice.latency import LatencyTracker
from app.voice.tool_runtime import ToolKind, get_tool_metadata, get_voice_tool_runtime


def _func_identity(function_call: dict[str, Any]) -> tuple[str | None, str | None, str, str]:
    raw_id = function_call.get("id") if isinstance(function_call, dict) else None
    raw_name = function_call.get("name") if isinstance(function_call, dict) else None
    func_id = raw_id if isinstance(raw_id, str) and raw_id else None
    func_name = raw_name if isinstance(raw_name, str) and raw_name else None
    return func_id, func_name, func_id or "unknown", func_name or "unknown"


async def handle_function_call_request(
    decoded: dict[str, Any],
    sts_ws: Any,
    *,
    ctx: CallContext,
    latency: LatencyTracker,
    run_tool_in_thread: Callable[[str, dict[str, Any], CallContext], dict[str, Any]],
    create_response: Callable[[str, str, dict[str, Any]], dict[str, Any]],
    logger: Any,
    tool_results: dict[str, dict] | None = None,
    inflight_tool_ids: set[str] | None = None,
) -> None:
    async def _execute_one(function_call: dict[str, Any]) -> dict[str, Any] | None:
        func_id, func_name, response_id, response_name = _func_identity(function_call)
        if func_id and tool_results is not None and func_id in tool_results:
            return tool_results[func_id]
        if func_id and inflight_tool_ids is not None and func_id in inflight_tool_ids:
            return None
        if func_id and inflight_tool_ids is not None:
            inflight_tool_ids.add(func_id)

        started = time.perf_counter()
        try:
            if func_name is None:
                raise ValueError("function name is required")
            raw_arguments = function_call.get("arguments")
            if not isinstance(raw_arguments, str):
                raise ValueError("function arguments must be JSON")
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError("function arguments must be an object")
            log_event(
                logger,
                "function_call",
                operation=func_name,
                func_id=response_id,
                arguments=sanitize_for_log(arguments),
            )
            result = await get_voice_tool_runtime().run(
                func_name, lambda: run_tool_in_thread(func_name, arguments, ctx)
            )
            latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
            if "availability" in func_name or "find_" in func_name:
                latency.record_ms("calendar_lookup_ms", latency_ms)
            elif "create_" in func_name:
                latency.record_ms("calendar_create_ms", latency_ms)
            function_result = create_response(response_id, func_name, result)
            log_event(
                logger,
                "function_call_sent",
                operation=func_name,
                func_id=response_id,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "function_call_failed operation=%s error_type=%s",
                response_name,
                type(exc).__name__,
            )
            function_result = create_response(
                response_id,
                response_name,
                {"error": f"Function call failed with: {type(exc).__name__}"},
            )
        finally:
            if func_id and inflight_tool_ids is not None:
                inflight_tool_ids.discard(func_id)

        if func_id and tool_results is not None:
            tool_results[func_id] = function_result
        return function_result

    function_calls = [fc for fc in (decoded.get("functions") or []) if isinstance(fc, dict)]
    idx = 0
    while idx < len(function_calls):
        current = function_calls[idx]
        _, current_name, _, _ = _func_identity(current)
        current_meta = get_tool_metadata(current_name or "") if current_name else None
        if current_meta is None or current_meta.kind != ToolKind.READ:
            payload = await _execute_one(current)
            if payload is not None:
                await sts_ws.send(json.dumps(payload))
            idx += 1
            continue

        batch: list[dict[str, Any]] = []
        j = idx
        while j < len(function_calls):
            _, name, _, _ = _func_identity(function_calls[j])
            meta = get_tool_metadata(name or "") if name else None
            if meta is None or meta.kind != ToolKind.READ:
                break
            batch.append(function_calls[j])
            j += 1

        if len(batch) == 1:
            payload = await _execute_one(batch[0])
            if payload is not None:
                await sts_ws.send(json.dumps(payload))
        else:
            for payload in await asyncio.gather(*(_execute_one(fc) for fc in batch)):
                if payload is not None:
                    await sts_ws.send(json.dumps(payload))
        idx = j

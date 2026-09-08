"""Voice tool surface backed by the capability-aware ToolRegistry."""

from __future__ import annotations

from typing import Any, Callable

from app.voice.registry.core import get_tool_registry

FUNCTION_MAP: dict[str, Callable[..., dict[str, Any]]] = get_tool_registry().as_function_map()

__all__ = ["FUNCTION_MAP", "get_function_map"]


def get_function_map() -> dict[str, Callable[..., dict[str, Any]]]:
    return get_tool_registry().as_function_map()

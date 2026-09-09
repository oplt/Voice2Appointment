"""Server-side argument validation for voice tool calls."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.voice.registry.types import ToolDefinition

_INVALID = "invalid_arguments"


def _schema_properties(definition: ToolDefinition) -> dict[str, Any]:
    params = definition.schema.get("parameters") or {}
    if not isinstance(params, dict):
        return {}
    props = params.get("properties") or {}
    return props if isinstance(props, dict) else {}


def _schema_required(definition: ToolDefinition) -> list[str]:
    params = definition.schema.get("parameters") or {}
    if not isinstance(params, dict):
        return []
    required = params.get("required") or []
    return [str(item) for item in required] if isinstance(required, list) else []


def _coerce_value(value: Any, schema: dict[str, Any]) -> Any:
    expected = schema.get("type")
    if expected == "integer":
        if isinstance(value, bool):
            raise ValueError("expected integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        raise ValueError("expected integer")
    if expected == "number":
        if isinstance(value, bool):
            raise ValueError("expected number")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value.strip())
        raise ValueError("expected number")
    if expected == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().casefold()
            if lowered in {"1", "true", "yes", "y"}:
                return True
            if lowered in {"0", "false", "no", "n"}:
                return False
        raise ValueError("expected boolean")
    if expected == "string":
        if value is None:
            return value
        return str(value)
    if expected == "array":
        if isinstance(value, list):
            return value
        raise ValueError("expected array")
    if expected == "object":
        if isinstance(value, dict):
            return value
        raise ValueError("expected object")
    return value


def _validation_error_payload(exc: ValidationError | ValueError | TypeError) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {
            "success": False,
            "error": _INVALID,
            "details": exc.errors(include_url=False),
        }
    return {
        "success": False,
        "error": _INVALID,
        "details": [{"msg": str(exc), "type": type(exc).__name__}],
    }


def _validate_against_schema(
    definition: ToolDefinition, arguments: dict[str, Any]
) -> dict[str, Any]:
    properties = _schema_properties(definition)
    required = _schema_required(definition)
    # Drop unknown keys rather than rejecting — LLM tool calls often include extras.
    cleaned: dict[str, Any] = {}
    if properties:
        for key, value in arguments.items():
            if key not in properties:
                continue
            cleaned[key] = _coerce_value(value, properties[key] or {})
    else:
        cleaned = dict(arguments)

    missing = [key for key in required if key not in cleaned or cleaned[key] is None]
    if missing:
        return {
            "success": False,
            "error": _INVALID,
            "details": [
                {
                    "type": "missing",
                    "loc": [key],
                    "msg": "Field required",
                    "input": arguments.get(key),
                }
                for key in missing
            ],
        }
    return cleaned


def validate_tool_arguments(
    definition: ToolDefinition, arguments: dict[str, Any] | None
) -> dict[str, Any]:
    """Return validated kwargs, or an invalid_arguments error payload."""
    raw = dict(arguments or {})
    if definition.args_model is not None:
        try:
            model = definition.args_model.model_validate(raw)
            return model.model_dump(exclude_unset=False)
        except ValidationError as exc:
            return _validation_error_payload(exc)
    try:
        return _validate_against_schema(definition, raw)
    except (ValueError, TypeError) as exc:
        return _validation_error_payload(exc)


def is_invalid_arguments_result(payload: dict[str, Any]) -> bool:
    return payload.get("success") is False and payload.get("error") == _INVALID

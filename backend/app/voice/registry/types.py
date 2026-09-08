"""Typed voice tool definition contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Literal

ToolHandler = Callable[..., dict[str, Any]]


class ToolKind(StrEnum):
    READ = "read"
    MUTATION = "mutation"


@dataclass(frozen=True)
class TimeoutPolicy:
    soft_seconds: float = 8.0
    hard_seconds: float = 15.0


@dataclass(frozen=True)
class IdempotencyPolicy:
    """How duplicate/replayed tool calls should behave."""

    mode: Literal["none", "by_func_id", "confirmed_gate"] = "none"


@dataclass(frozen=True)
class RedactionPolicy:
    redact_argument_keys: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"client_phone", "client_email", "email", "phone", "transcript"}
        )
    )
    redact_result_keys: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"client_phone", "client_email", "email", "phone", "transcript", "ehr_payload"}
        )
    )
    clinic_medical_redact: bool = False


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: ToolHandler
    kind: ToolKind
    capability: str
    required_feature: str | None
    schema: dict[str, Any]
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    idempotency: IdempotencyPolicy = field(default_factory=IdempotencyPolicy)
    redaction: RedactionPolicy = field(default_factory=RedactionPolicy)
    legacy_names: tuple[str, ...] = ()

    def deepgram_schema(self) -> dict[str, Any]:
        payload = dict(self.schema)
        payload["name"] = self.name
        return payload

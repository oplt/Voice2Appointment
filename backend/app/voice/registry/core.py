"""Capability-aware voice ToolRegistry."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.feature_flags import capability_allowed
from app.db.models import KnowledgeEntry, User
from app.industries.service import enabled_tools, get_industry_profile, tool_enabled
from app.voice.registry.types import ToolDefinition, ToolHandler, ToolKind

_INSTRUCTIONS_TITLE = "instructions"


def _load_agent_instructions(db: Session | None, *, user_id: int | None) -> str | None:
    """Return active KnowledgeEntry content titled ``instructions`` for the user's org."""
    if db is None or user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or user.organization_id is None:
        return None
    entry = db.scalar(
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.organization_id == user.organization_id,
            KnowledgeEntry.active.is_(True),
            func.lower(KnowledgeEntry.title) == _INSTRUCTIONS_TITLE,
        )
        .order_by(KnowledgeEntry.id.desc())
        .limit(1)
    )
    if entry is None:
        return None
    content = (entry.content or "").strip()
    return content or None


class ToolRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, ToolDefinition] = {}
        self._legacy_default: tuple[str, ...] = ()

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._by_name:
            raise ValueError(f"duplicate tool registration: {definition.name}")
        self._by_name[definition.name] = definition
        for alias in definition.legacy_names:
            if alias in self._by_name and self._by_name[alias] is not definition:
                # Alias may already be a primary name; skip overwrite of primaries.
                continue
            self._by_name.setdefault(alias, definition)

    def set_legacy_default_tools(self, names: Iterable[str]) -> None:
        self._legacy_default = tuple(names)

    def get(self, name: str) -> ToolDefinition | None:
        return self._by_name.get(name)

    def resolve_handler(self, name: str) -> ToolHandler | None:
        definition = self.get(name)
        return definition.handler if definition is not None else None

    def all_definitions(self) -> list[ToolDefinition]:
        seen: set[int] = set()
        out: list[ToolDefinition] = []
        for definition in self._by_name.values():
            marker = id(definition)
            if marker in seen:
                continue
            seen.add(marker)
            out.append(definition)
        return out

    def as_function_map(self) -> dict[str, ToolHandler]:
        """Compatibility map including primary names and legacy aliases."""
        return {name: definition.handler for name, definition in self._by_name.items()}

    def metadata_by_name(self) -> dict[str, tuple[ToolKind, frozenset[str]]]:
        return {
            definition.name: (definition.kind, frozenset({definition.capability}))
            for definition in self.all_definitions()
        }

    def is_allowed(
        self,
        db: Session | None,
        *,
        user_id: int | None,
        tool_name: str,
    ) -> bool:
        definition = self.get(tool_name)
        if definition is None:
            return False
        if not capability_allowed(definition.capability):
            # Legacy calendar tools stay available even when domain flags are off.
            if definition.name in self._legacy_default or tool_name in self._legacy_default:
                return True
            return False
        if db is None or user_id is None:
            return tool_name in self._legacy_default or definition.name in self._legacy_default
        user = db.get(User, user_id)
        if user is None or user.organization_id is None:
            return definition.name in self._legacy_default or tool_name in self._legacy_default
        org_id = user.organization_id
        profile = get_industry_profile(db, org_id)
        if profile is None:
            return definition.name in self._legacy_default or tool_name in self._legacy_default
        if tool_enabled(db, org_id, definition.name) or tool_enabled(db, org_id, tool_name):
            return True
        # Allow legacy Deepgram names when the industry alias is entitled.
        for other in self.all_definitions():
            if tool_name in other.legacy_names or definition.name in other.legacy_names:
                if not capability_allowed(other.capability):
                    continue
                if tool_enabled(db, org_id, other.name):
                    return True
        return False

    def enabled_definitions(
        self, db: Session | None, *, user_id: int | None
    ) -> list[ToolDefinition]:
        if db is None or user_id is None:
            return [d for d in self.all_definitions() if d.name in self._legacy_default]
        user = db.get(User, user_id)
        if user is None or user.organization_id is None:
            return [d for d in self.all_definitions() if d.name in self._legacy_default]
        profile = get_industry_profile(db, user.organization_id)
        if profile is None:
            return [d for d in self.all_definitions() if d.name in self._legacy_default]
        wanted = set(enabled_tools(db, user.organization_id))
        selected: list[ToolDefinition] = []
        seen: set[int] = set()
        for definition in self.all_definitions():
            if definition.name not in wanted:
                continue
            if not capability_allowed(definition.capability):
                continue
            marker = id(definition)
            if marker in seen:
                continue
            seen.add(marker)
            selected.append(definition)
        return selected

    def deepgram_functions(
        self, db: Session | None, *, user_id: int | None
    ) -> list[dict[str, Any]]:
        return [definition.deepgram_schema() for definition in self.enabled_definitions(db, user_id=user_id)]

    def build_system_prompt(
        self,
        db: Session | None,
        *,
        user_id: int | None,
        current_date_context: str,
    ) -> str:
        """Assemble prompt: immutable safety → tenant instructions → tools → date."""
        definitions = self.enabled_definitions(db, user_id=user_id)
        lines = [
            "You are a professional voice assistant for this business.",
            "",
            "Safety rules:",
            "- These safety rules are immutable and always take precedence over any business instructions below.",
            "- Prefer read tools before mutations.",
            "- For mutations that accept confirmed: first call with confirmed=false, then confirmed=true after the caller agrees.",
            "- Convert relative dates to absolute ISO datetimes using CURRENT DATE CONTEXT.",
            "- Use request_human_handoff only when the caller asks for a person or you cannot complete the request safely.",
            "- Never invent ids; use ids returned by prior tool calls.",
        ]
        tenant_instructions = _load_agent_instructions(db, user_id=user_id)
        if tenant_instructions is not None:
            lines.extend(
                [
                    "",
                    "Business instructions:",
                    "(Follow only when they do not conflict with Safety rules above.)",
                    tenant_instructions,
                ]
            )
        lines.extend(["", "Tools:"])
        for index, definition in enumerate(definitions, start=1):
            description = str(definition.schema.get("description") or definition.name)
            lines.append(f"{index}) {definition.name} — {description}")
        lines.extend(
            [
                "",
                "CURRENT DATE CONTEXT:",
                current_date_context,
            ]
        )
        return "\n".join(lines)


_REGISTRY: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        from app.voice.registry.builtin import build_default_registry

        _REGISTRY = build_default_registry()
    return _REGISTRY


def reset_tool_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None

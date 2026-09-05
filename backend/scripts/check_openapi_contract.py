#!/usr/bin/env python3
"""P7-04: fail when frontend fixtures/types drift from the backend OpenAPI contract.

The backend analytics/dashboard routes declare Pydantic ``response_model``s, so
FastAPI's generated OpenAPI schema is *derived from*, not merely inspired by,
those models. This script uses that OpenAPI schema as the single source of
truth and checks that every backend-required field is still declared on the
corresponding hand-maintained frontend TypeScript type. A backend response
shape change that silently drops the field from the frontend types (or that
adds a new required field the frontend forgot) fails this check.

This intentionally does not attempt full structural TS<->JSON-schema
equivalence (frontend types add optional UI-only chrome). It targets what the
Phase 7 audit called out: required-field drift going unnoticed.

Usage:
    PYTHONPATH=backend python backend/scripts/check_openapi_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_REPO_ROOT = _BACKEND.parent
_FRONTEND_TYPES = _REPO_ROOT / "frontend" / "src" / "types" / "index.ts"

# Maps an OpenAPI component schema name to the frontend TypeScript type that
# must declare (at least) every one of that schema's required fields.
_CONTRACTS: tuple[tuple[str, str], ...] = (
    ("AnalyticsSummaryResponse", "AnalyticsSummary"),
    ("DashboardSummaryResponse", "DashboardSummary"),
)

_FIELD_NAME_RE = re.compile(r"^\s*(?:/\*\*.*?\*/\s*)?([A-Za-z_][A-Za-z0-9_]*)\??\s*:", re.MULTILINE)


def _load_openapi_schema() -> dict:
    from app.main import app

    return app.openapi()


def _frontend_type_fields(type_name: str) -> set[str]:
    text = _FRONTEND_TYPES.read_text(encoding="utf-8")
    match = re.search(rf"export type {re.escape(type_name)}\s*=\s*\{{", text)
    if match is None:
        raise ValueError(f"frontend type {type_name!r} not found in {_FRONTEND_TYPES}")
    depth = 0
    start = match.end() - 1
    end = start
    for idx in range(start, len(text)):
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                end = idx
                break
    body = text[start + 1 : end]
    return {m.group(1) for m in _FIELD_NAME_RE.finditer(body)}


def check_contracts() -> list[str]:
    """Return a list of human-readable drift errors (empty when contracts match)."""
    schema = _load_openapi_schema()
    schemas = schema.get("components", {}).get("schemas", {})
    errors: list[str] = []
    for backend_name, frontend_name in _CONTRACTS:
        backend_schema = schemas.get(backend_name)
        if backend_schema is None:
            errors.append(
                f"backend OpenAPI schema is missing component {backend_name!r}; "
                "is response_model still declared on its route?"
            )
            continue
        required = set(backend_schema.get("required", []))
        try:
            frontend_fields = _frontend_type_fields(frontend_name)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        missing = sorted(required - frontend_fields)
        if missing:
            errors.append(
                f"{frontend_name} (frontend) is missing required backend fields "
                f"from {backend_name}: {missing}"
            )
    return errors


def main() -> int:
    errors = check_contracts()
    if errors:
        for error in errors:
            print(f"CONTRACT DRIFT: {error}", file=sys.stderr)
        return 1
    print("OpenAPI/frontend contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

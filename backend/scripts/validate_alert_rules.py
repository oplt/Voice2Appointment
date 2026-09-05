#!/usr/bin/env python3
"""P7-07: validate docs/alerts.yaml against emitted metrics and runbook files.

Turns alert prose into a minimally executable operational control: every
alert rule must name a real owner and user impact, and any metric it cites
must be a metric name this codebase actually emits (scanned from
``metrics.incr``/``metrics.observe`` call sites, not hand-copied), and any
runbook path must exist.

Usage:
    PYTHONPATH=backend python backend/scripts/validate_alert_rules.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

_BACKEND = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND.parent
_ALERTS_YAML = _REPO_ROOT / "docs" / "alerts.yaml"
_RUNBOOKS_DIR = _REPO_ROOT / "docs" / "runbooks"
_APP_DIR = _BACKEND / "app"

_METRIC_CALL_RE = re.compile(r'metrics\.(?:incr|observe)\(\s*"([^"]+)"')


def emitted_metric_names() -> set[str]:
    """Every metric name actually passed to metrics.incr/observe in app/."""
    names: set[str] = set()
    for path in _APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        names.update(_METRIC_CALL_RE.findall(text))
    return names


def load_alerts() -> list[dict[str, Any]]:
    data = yaml.safe_load(_ALERTS_YAML.read_text(encoding="utf-8"))
    alerts = data.get("alerts") if isinstance(data, dict) else None
    if not isinstance(alerts, list) or not alerts:
        raise ValueError(f"{_ALERTS_YAML} must define a non-empty 'alerts' list")
    return alerts


def validate_alerts() -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    emitted = emitted_metric_names()
    alerts = load_alerts()
    seen_names: set[str] = set()

    for alert in alerts:
        name = alert.get("name")
        if not name:
            errors.append(f"alert missing 'name': {alert!r}")
            continue
        if name in seen_names:
            errors.append(f"duplicate alert name: {name!r}")
        seen_names.add(name)

        for field in ("owner", "user_impact", "condition", "signal_type"):
            if not (alert.get(field) or "").strip():
                errors.append(f"{name}: missing required field '{field}'")

        signal_type = alert.get("signal_type")
        if signal_type == "metric":
            metric = alert.get("metric")
            if not metric:
                errors.append(f"{name}: signal_type=metric requires 'metric'")
            elif metric not in emitted:
                errors.append(
                    f"{name}: metric {metric!r} is not emitted anywhere in "
                    f"app/ (known emitted metrics: {sorted(emitted)})"
                )
        elif signal_type in ("endpoint", "query"):
            if not (alert.get("signal") or "").strip():
                errors.append(f"{name}: signal_type={signal_type} requires 'signal'")
        else:
            errors.append(f"{name}: unknown signal_type {signal_type!r}")

        runbook = alert.get("runbook")
        if runbook:
            runbook_path = _REPO_ROOT / "docs" / runbook
            if not runbook_path.is_file():
                errors.append(f"{name}: runbook path does not exist: {runbook}")

    return errors


def main() -> int:
    try:
        errors = validate_alerts()
    except Exception as exc:  # noqa: BLE001
        print(f"ALERT CONFIG INVALID: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ALERT CONFIG INVALID: {error}", file=sys.stderr)
        return 1
    print("Alert rule config valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""PHASE 11: analytics JSON charts without pandas/matplotlib/GeoJSON."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from app.analytics.service import process_twilio_data


def test_process_twilio_data_has_no_call_details_by_default() -> None:
    calls = [
        {
            "sid": "CA1",
            "from": "+32470123456",
            "to": "+32470999999",
            "start_time": "2026-09-01T10:00:00Z",
            "duration_sec": 90,
            "price": 0.02,
        },
        {
            "sid": "CA2",
            "from": "+4915112345678",
            "to": "+32470999999",
            "start_time": "2026-09-01T15:00:00Z",
            "duration_sec": 30,
            "price": 0.01,
        },
    ]
    result = process_twilio_data(calls, date(2026, 9, 1), date(2026, 9, 1))
    assert result is not None
    assert "call_details" not in result
    assert result["total_calls"] == 2
    assert result["calls_over_time"]["labels"] == ["2026-09-01"]
    assert result["calls_over_time"]["values"] == [2]
    assert result["cost_over_time"]["values"][0] == 0.03
    assert result["duration_distribution"]["labels"]
    assert result["peak_hours_days"]["matrix"][1][10] == 1  # Tuesday 10:00
    assert result["top_countries"]
    assert all("iso3" in c for c in result["geo_country_counts"])


def test_process_twilio_data_optional_details() -> None:
    calls = [
        {
            "sid": "CA1",
            "from": "+10000000001",
            "to": "+10000000002",
            "start_time": "2026-09-02T12:00:00Z",
            "duration_sec": 60,
            "price": 0.01,
        }
    ]
    result = process_twilio_data(
        calls, None, None, include_call_details=True
    )
    assert result is not None
    assert len(result["call_details"]) == 1


def test_analytics_service_has_no_heavy_deps() -> None:
    source = Path(__file__).resolve().parents[1] / "app" / "analytics" / "service.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "pandas" not in imported
    assert "matplotlib" not in imported
    assert "folium" not in imported
    assert "numpy" not in imported


def test_requirements_drop_unused_analytics_libs() -> None:
    req = (
        Path(__file__).resolve().parents[1] / "requirements.txt"
    ).read_text(encoding="utf-8").lower()
    assert "pandas" not in req
    assert "matplotlib" not in req
    assert "folium" not in req
    assert "numpy" not in req
    assert "xlsxwriter" not in req

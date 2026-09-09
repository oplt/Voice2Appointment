"""PHASE 14 — FHIR adapter HTTP wiring (honest, not a compliance claim)."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from app.industries.fhir import FhirEHRAdapter, IntegrationError


class _FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_fhir_adapter_disabled_returns_none() -> None:
    adapter = FhirEHRAdapter(
        base_url="https://fhir.example.test/r4",
        bearer_token="secret-token",
        enabled=False,
    )
    assert adapter.connected is False
    assert (
        adapter.lookup_patient(organization_id=1, phone="+15551212", email=None) is None
    )
    assert (
        adapter.push_appointment(
            organization_id=1,
            patient=None,
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc),
            visit_type="checkup",
        )
        is None
    )


def test_fhir_adapter_enabled_mock_http_returns_patient(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "pat-42",
                    "name": [{"text": "Ada Lovelace"}],
                }
            }
        ],
    }
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float = 15) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        auth = request.headers.get("Authorization") or request.get_header("Authorization")
        assert auth == "Bearer test-token"
        # Ensure token is not accidentally written into exception messages here.
        assert "test-token" not in str(request.full_url)
        return _FakeResponse(json.dumps(bundle).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = FhirEHRAdapter(
        base_url="https://fhir.example.test/r4",
        bearer_token="test-token",
        enabled=True,
        timeout_seconds=9,
    )
    assert adapter.connected is True
    ref = adapter.lookup_patient(organization_id=7, phone="+15550100", email=None)
    assert ref is not None
    assert ref.external_id == "pat-42"
    assert ref.display_name == "Ada Lovelace"
    assert "Patient" in captured["url"]
    assert "telecom=" in captured["url"]
    assert captured["timeout"] == 9.0


def test_fhir_adapter_http_error_raises_integration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float = 15) -> Any:
        raise HTTPError(
            request.full_url,
            503,
            "Unavailable",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b""),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = FhirEHRAdapter(
        base_url="https://fhir.example.test/r4",
        bearer_token="secret",
        enabled=True,
    )
    with pytest.raises(IntegrationError) as excinfo:
        adapter.lookup_patient(organization_id=1, phone="+1", email=None)
    assert excinfo.value.status == 503
    assert "secret" not in str(excinfo.value)


def test_fhir_adapter_transport_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float = 15) -> Any:
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = FhirEHRAdapter(
        base_url="https://fhir.example.test/r4",
        enabled=True,
        bearer_token=None,
    )
    with pytest.raises(IntegrationError):
        adapter.lookup_patient(organization_id=1, phone="+1", email=None)


def test_fhir_push_appointment_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.industries.ehr import EHRPatientRef

    def fake_urlopen(request: Any, timeout: float = 15) -> _FakeResponse:
        assert request.get_method() == "POST"
        body = json.loads(request.data.decode("utf-8"))
        assert body["resourceType"] == "Appointment"
        return _FakeResponse(
            json.dumps(
                {"resourceType": "Appointment", "id": "appt-9", "status": "booked"}
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = FhirEHRAdapter(
        base_url="https://fhir.example.test/r4",
        bearer_token="tok",
        enabled=True,
    )
    start = datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, 14, 30, tzinfo=timezone.utc)
    ref = adapter.push_appointment(
        organization_id=1,
        patient=EHRPatientRef(external_id="pat-1", display_name="Ada"),
        start=start,
        end=end,
        visit_type="checkup",
    )
    assert ref is not None
    assert ref.external_id == "appt-9"
    assert ref.status == "booked"

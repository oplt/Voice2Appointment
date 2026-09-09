"""FHIR R4 EHR adapter (opt-in HTTP).

Not a compliance claim and not a regulatory certification. Enable only after
security/regulatory review. Default remains ``NullEHRAdapter`` until
``FHIR_ENABLED`` + ``FHIR_BASE_URL`` are set at process startup.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from app.industries.ehr import EHRAppointmentRef, EHRPatientRef

logger = logging.getLogger(__name__)


class IntegrationError(Exception):
    """External FHIR integration failed — callers must not treat as success."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        self.status = status
        super().__init__(message)


class FhirEHRAdapter:
    """HTTP FHIR R4 adapter — disabled until enabled + base_url are set."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        bearer_token: str | None = None,
        enabled: bool = False,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._bearer_token = bearer_token
        self._enabled = bool(enabled and self._base_url)
        self._timeout = max(1.0, float(timeout_seconds))

    @property
    def connected(self) -> bool:
        return self._enabled

    def lookup_patient(
        self, *, organization_id: int, phone: str | None, email: str | None
    ) -> EHRPatientRef | None:
        if not self._enabled:
            return None
        telecom = (phone or email or "").strip()
        if not telecom:
            return None
        query = urllib.parse.urlencode({"telecom": telecom})
        url = f"{self._base_url}/Patient?{query}"
        try:
            payload = self._request_json("GET", url)
        except IntegrationError as exc:
            if exc.status == 404:
                return None
            raise
        ref = _parse_patient_ref(payload)
        logger.info(
            "fhir_patient_lookup org=%s found=%s",
            organization_id,
            ref is not None,
        )
        return ref

    def push_appointment(
        self,
        *,
        organization_id: int,
        patient: EHRPatientRef | None,
        start: datetime,
        end: datetime,
        visit_type: str,
        practitioner_external_id: str | None = None,
    ) -> EHRAppointmentRef | None:
        if not self._enabled:
            return None
        if patient is None:
            return None
        body = self.appointment_bundle_stub(
            patient_external_id=patient.external_id,
            start=start,
            end=end,
            visit_type=visit_type,
        )
        if practitioner_external_id:
            body.setdefault("participant", []).append(
                {
                    "actor": {
                        "reference": f"Practitioner/{practitioner_external_id}"
                    },
                    "status": "accepted",
                }
            )
        url = f"{self._base_url}/Appointment"
        payload = self._request_json("POST", url, body=body)
        ref = _parse_appointment_ref(payload)
        if ref is None:
            raise IntegrationError("FHIR Appointment response missing id")
        logger.info(
            "fhir_appointment_push org=%s ok=1",
            organization_id,
        )
        return ref

    def appointment_bundle_stub(
        self,
        *,
        patient_external_id: str,
        start: datetime,
        end: datetime,
        visit_type: str,
    ) -> dict[str, Any]:
        """Appointment resource shape for POST /Appointment."""
        return {
            "resourceType": "Appointment",
            "status": "booked",
            "description": visit_type,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "participant": [
                {
                    "actor": {"reference": f"Patient/{patient_external_id}"},
                    "status": "accepted",
                }
            ],
        }

    def _request_json(
        self, method: str, url: str, *, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/fhir+json, application/json",
        }
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/fhir+json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200) or 200)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            # Never log Authorization or clinical body — status only.
            logger.warning(
                "fhir_http_error method=%s status=%s path=%s",
                method,
                status,
                urllib.parse.urlparse(url).path,
            )
            raise IntegrationError(
                f"FHIR HTTP {status}",
                status=status,
            ) from None
        except urllib.error.URLError as exc:
            logger.warning(
                "fhir_transport_error method=%s path=%s err=%s",
                method,
                urllib.parse.urlparse(url).path,
                type(exc.reason).__name__
                if hasattr(exc, "reason")
                else type(exc).__name__,
            )
            raise IntegrationError("FHIR transport error") from None
        except TimeoutError as exc:
            logger.warning(
                "fhir_timeout method=%s path=%s",
                method,
                urllib.parse.urlparse(url).path,
            )
            raise IntegrationError("FHIR request timed out") from exc

        if status >= 400:
            raise IntegrationError(f"FHIR HTTP {status}", status=status)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrationError("FHIR response was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise IntegrationError("FHIR response was not a JSON object")
        # Never log bearer tokens or clinical payloads (status/path only above).
        return parsed


def _display_name(resource: dict[str, Any]) -> str | None:
    names = resource.get("name")
    if isinstance(names, list) and names:
        first = names[0]
        if isinstance(first, dict):
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            given = first.get("given")
            family = first.get("family")
            parts: list[str] = []
            if isinstance(given, list):
                parts.extend(str(g) for g in given if g)
            if family:
                parts.append(str(family))
            if parts:
                return " ".join(parts)
    return None


def _parse_patient_ref(payload: dict[str, Any]) -> EHRPatientRef | None:
    resource: dict[str, Any] | None = None
    if payload.get("resourceType") == "Patient":
        resource = payload
    elif payload.get("resourceType") == "Bundle":
        entries = payload.get("entry") or []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                candidate = entry.get("resource")
                if isinstance(candidate, dict) and candidate.get("resourceType") == "Patient":
                    resource = candidate
                    break
    if resource is None:
        return None
    external_id = resource.get("id")
    if not external_id:
        return None
    return EHRPatientRef(
        external_id=str(external_id),
        display_name=_display_name(resource),
    )


def _parse_appointment_ref(payload: dict[str, Any]) -> EHRAppointmentRef | None:
    if payload.get("resourceType") != "Appointment":
        return None
    external_id = payload.get("id")
    if not external_id:
        return None
    status = str(payload.get("status") or "scheduled")
    return EHRAppointmentRef(external_id=str(external_id), status=status)

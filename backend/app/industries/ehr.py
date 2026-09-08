"""EHR integration port — adapters stay outside the reservation domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class EHRPatientRef:
    external_id: str
    display_name: str | None = None


@dataclass(frozen=True)
class EHRAppointmentRef:
    external_id: str
    status: str = "scheduled"


class EHRPort(Protocol):
    """Future FHIR/HL7 adapters implement this; core booking never imports vendors."""

    def lookup_patient(
        self, *, organization_id: int, phone: str | None, email: str | None
    ) -> EHRPatientRef | None: ...

    def push_appointment(
        self,
        *,
        organization_id: int,
        patient: EHRPatientRef | None,
        start: datetime,
        end: datetime,
        visit_type: str,
        practitioner_external_id: str | None = None,
    ) -> EHRAppointmentRef | None: ...


class NullEHRAdapter:
    """Default no-op adapter — no compliance claim, no clinical payload."""

    def lookup_patient(
        self, *, organization_id: int, phone: str | None, email: str | None
    ) -> EHRPatientRef | None:
        return None

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
        return None


_default_ehr: EHRPort = NullEHRAdapter()


def get_ehr_adapter() -> EHRPort:
    return _default_ehr


def set_ehr_adapter(adapter: EHRPort) -> None:
    global _default_ehr
    _default_ehr = adapter

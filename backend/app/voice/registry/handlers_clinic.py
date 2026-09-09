"""Clinic vertical voice tool handlers."""

from __future__ import annotations

from typing import Any

from app.calendars.service import booking_provider_hooks
from app.calendars.tools import create_calendar_event
from app.customers.service import get_or_create_customer
from app.industries.clinic import (
    ClinicSafetyError,
    emergency_safety_gate,
    list_practitioners,
    list_visit_types,
)
from app.industries.ehr import get_ehr_adapter
from app.industries.service import sync_calendar_for_org
from app.reservations.service import book_reservation
from app.voice.registry.handlers_common import (
    _as_bool,
    _find_bookable_catalog_item,
    _org_context,
    _parse_dt,
)


def find_visit_types_tool(
    *, specialty: str | None = None, utterance: str | None = None, **_: Any
) -> dict[str, Any]:
    if utterance:
        try:
            gate = emergency_safety_gate(utterance)
        except ClinicSafetyError as exc:
            return {"success": False, "error": "safety_gate", "message": str(exc)}
        if not gate["allowed"]:
            return {"success": False, **gate}
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    items = list_visit_types(db, organization_id, specialty=specialty)
    return {
        "success": True,
        "visit_types": [
            {
                "id": item.id,
                "name": item.name,
                "duration_minutes": item.duration_minutes,
                "requires_referral": bool((item.metadata_json or {}).get("requires_referral")),
                "specialty": (item.metadata_json or {}).get("specialty"),
            }
            for item in items
        ],
    }

def find_practitioners_tool(
    *, location_id: int | None = None, capability: str | None = None, **_: Any
) -> dict[str, Any]:
    ctx = _org_context()
    if isinstance(ctx, dict):
        return ctx
    db, organization_id, _user_id = ctx
    rows = list_practitioners(
        db, organization_id, location_id=location_id, capability=capability
    )
    return {
        "success": True,
        "practitioners": [
            {"id": row.id, "name": row.name, "location_id": row.location_id} for row in rows
        ],
    }

def book_appointment_tool(**kwargs: Any) -> dict[str, Any]:
    return create_calendar_event(**kwargs)

def create_appointment_tool(**kwargs: Any) -> dict[str, Any]:
    utterance = kwargs.get("summary") or kwargs.get("utterance")
    if isinstance(utterance, str) and utterance:
        try:
            gate = emergency_safety_gate(utterance)
            if not gate["allowed"]:
                return {"success": False, **gate}
        except ClinicSafetyError as exc:
            return {"success": False, "error": "safety_gate", "message": str(exc)}

    ctx = _org_context()
    if isinstance(ctx, dict):
        return create_calendar_event(**kwargs)
    db, organization_id, user_id = ctx

    catalog_item = _find_bookable_catalog_item(
        db,
        organization_id,
        catalog_item_id=kwargs.get("catalog_item_id"),
        summary=kwargs.get("summary"),
    )
    if catalog_item is None:
        return create_calendar_event(**kwargs)

    if not _as_bool(kwargs.get("confirmed")):
        return create_calendar_event(**kwargs)

    start = _parse_dt(kwargs.get("datetime_start"))
    end = _parse_dt(kwargs.get("datetime_end"))
    if start is None:
        return {"success": False, "error": "datetime_start_required"}

    customer = None
    if kwargs.get("client_name") or kwargs.get("client_phone") or kwargs.get("client_email"):
        customer = get_or_create_customer(
            db,
            organization_id=organization_id,
            name=kwargs.get("client_name"),
            phone=kwargs.get("client_phone"),
            email=kwargs.get("client_email"),
        )
        db.flush()

    preferred: tuple[int, ...] = ()
    practitioner_id = kwargs.get("practitioner_id")
    if isinstance(practitioner_id, int):
        preferred = (practitioner_id,)

    duration = None
    if end is not None:
        duration = max(1, int((end - start).total_seconds() // 60))
    elif catalog_item.duration_minutes:
        duration = int(catalog_item.duration_minutes)

    # Same Google Calendar hooks as HTTP reservations API; no-op when disconnected.
    hooks = booking_provider_hooks(db, user_id)
    try:
        reservation = book_reservation(
            db,
            organization_id=organization_id,
            catalog_item_id=catalog_item.id,
            start_datetime=start,
            end_datetime=end,
            location_id=kwargs.get("location_id"),
            customer_id=customer.id if customer is not None else None,
            preferred_resource_ids=preferred,
            scheduling_mode="single_resource",
            duration_minutes=duration,
            owner_user_id=user_id,
            sync_calendar=sync_calendar_for_org(db, organization_id),
            provider_create=hooks.create_event,
            calendar_id=hooks.calendar_id,
        )
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}

    ehr = get_ehr_adapter()
    ehr_ref = None
    ehr_error: str | None = None
    try:
        patient = ehr.lookup_patient(
            organization_id=organization_id,
            phone=kwargs.get("client_phone"),
            email=kwargs.get("client_email"),
        )
        ehr_ref = ehr.push_appointment(
            organization_id=organization_id,
            patient=patient,
            start=reservation.start_datetime,
            end=reservation.end_datetime,
            visit_type=catalog_item.name,
            practitioner_external_id=str(practitioner_id) if practitioner_id else None,
        )
    except Exception as exc:  # noqa: BLE001 — IntegrationError or transport
        from app.industries.fhir import IntegrationError

        if isinstance(exc, IntegrationError):
            ehr_error = exc.__class__.__name__
        else:
            raise
    payload: dict[str, Any] = {
        "success": True,
        "reservation_id": reservation.id,
        "status": reservation.status,
        "catalog_item_id": catalog_item.id,
        "appointment_id": reservation.appointment_id,
        "start": reservation.start_datetime.isoformat(),
        "end": reservation.end_datetime.isoformat(),
        "path": "reservation",
    }
    if ehr_ref is not None:
        payload["ehr_external_id"] = ehr_ref.external_id
        payload["ehr_status"] = ehr_ref.status
    if ehr_error is not None:
        payload["ehr_error"] = ehr_error

    from app.industries.compliance import record_clinic_audit, require_consent_flag
    from app.industries.service import get_industry_profile

    profile = get_industry_profile(db, organization_id)
    if profile is not None and profile.industry_type == "clinic":
        consent_ok = require_consent_flag(customer, "scheduling", default=True)
        record_clinic_audit(
            db,
            organization_id,
            actor_user_id=user_id,
            action="create_appointment",
            entity_type="reservation",
            entity_id=str(reservation.id),
            data={
                "catalog_item_id": catalog_item.id,
                "customer_id": customer.id if customer is not None else None,
                "consent_ok": consent_ok,
                "ehr_pushed": ehr_ref is not None,
            },
        )
        payload["consent_ok"] = consent_ok
    return payload


"""Register legacy calendar tools + industry capability tools."""

from __future__ import annotations

from typing import Any

from app.calendars import tools as calendar_tools
from app.calendars.tool_schemas import VOICE_TOOL_DEFINITIONS
from app.voice.registry import handlers_industry as industry
from app.voice.registry import handlers_restaurant as restaurant
from app.voice.registry import handlers_salon as salon
from app.voice.registry.args_models import (
    BookSalonServiceArgs,
    CancelReservationArgs,
    CheckOrderStatusArgs,
    CreateAppointmentArgs,
    CreateReservationArgs,
    ModifyReservationArgs,
    ModifySalonBookingArgs,
    PromoteWaitlistArgs,
    SendSecureLinkArgs,
)
from app.voice.registry.core import ToolRegistry
from app.voice.registry.types import (
    IdempotencyPolicy,
    RedactionPolicy,
    TimeoutPolicy,
    ToolDefinition,
    ToolKind,
)


def _schema_by_name() -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in VOICE_TOOL_DEFINITIONS}


def _dt_prop(description: str) -> dict[str, Any]:
    return {"type": "string", "format": "date-time", "description": description}


def _tool(
    *,
    name: str,
    handler,
    kind: ToolKind,
    capability: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
    required_feature: str | None = None,
    legacy_names: tuple[str, ...] = (),
    mutation_confirm: bool = False,
    clinic_redact: bool = False,
    timeout: TimeoutPolicy | None = None,
    args_model: type | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        handler=handler,
        kind=kind,
        capability=capability,
        required_feature=required_feature or f"tool:{name}",
        schema={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
        timeout=timeout or TimeoutPolicy(),
        idempotency=IdempotencyPolicy(
            mode="confirmed_gate" if mutation_confirm else "by_func_id"
        ),
        redaction=RedactionPolicy(clinic_medical_redact=clinic_redact),
        legacy_names=legacy_names,
        args_model=args_model,
    )


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    legacy = _schema_by_name()

    # --- Legacy Deepgram calendar tools (names preserved) ---
    for name, handler, kind, capability in (
        ("check_calendar_availability", calendar_tools.check_calendar_availability, ToolKind.READ, "calendar"),
        ("find_appointments", calendar_tools.find_appointments, ToolKind.READ, "calendar"),
        ("get_appointment_details", calendar_tools.get_appointment_details, ToolKind.READ, "calendar"),
        ("create_calendar_event", calendar_tools.create_calendar_event, ToolKind.MUTATION, "reservation"),
        ("reschedule_appointment", calendar_tools.reschedule_appointment, ToolKind.MUTATION, "reservation"),
        ("cancel_appointment", calendar_tools.cancel_appointment, ToolKind.MUTATION, "reservation"),
        ("request_human_handoff", calendar_tools.request_human_handoff, ToolKind.MUTATION, "handoff"),
    ):
        schema = legacy.get(name)
        if schema is None and name == "get_appointment_details":
            schema = {
                "name": name,
                "description": "Get details for a known appointment event_id",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                    },
                    "required": ["event_id"],
                },
            }
        assert schema is not None
        registry.register(
            ToolDefinition(
                name=name,
                handler=handler,
                kind=kind,
                capability=capability,
                required_feature=f"tool:{name}",
                schema=schema,
                idempotency=IdempotencyPolicy(
                    mode="confirmed_gate" if kind is ToolKind.MUTATION else "by_func_id"
                ),
                redaction=RedactionPolicy(),
            )
        )

    registry.set_legacy_default_tools(
        (
            "check_calendar_availability",
            "find_appointments",
            "create_calendar_event",
            "reschedule_appointment",
            "cancel_appointment",
            "request_human_handoff",
        )
    )

    # --- Industry tools (Phase 6 names exposed to Deepgram when entitled) ---
    registry.register(
        _tool(
            name="catalog_search",
            handler=industry.catalog_search,
            kind=ToolKind.READ,
            capability="catalog",
            description="Search the business catalog for services or products",
            properties={"query": {"type": "string"}},
        )
    )
    registry.register(
        _tool(
            name="search_catalog",
            handler=industry.search_catalog_tool,
            kind=ToolKind.READ,
            capability="catalog",
            description="Search catalog items for a general business",
            properties={"query": {"type": "string"}},
        )
    )
    registry.register(
        _tool(
            name="find_visit_types",
            handler=industry.find_visit_types_tool,
            kind=ToolKind.READ,
            capability="clinic",
            description="List administrative visit types; never provides diagnosis",
            properties={
                "specialty": {"type": "string"},
                "utterance": {"type": "string"},
            },
            clinic_redact=True,
        )
    )
    registry.register(
        _tool(
            name="find_practitioners",
            handler=industry.find_practitioners_tool,
            kind=ToolKind.READ,
            capability="clinic",
            description="List practitioners optionally filtered by capability",
            properties={
                "location_id": {"type": "integer"},
                "capability": {"type": "string"},
            },
            clinic_redact=True,
        )
    )
    registry.register(
        _tool(
            name="appointment_availability",
            handler=industry.appointment_availability,
            kind=ToolKind.READ,
            capability="calendar",
            description="Check appointment availability for a time slot",
            properties={
                "datetime_start": _dt_prop("Slot start ISO-8601"),
                "datetime_end": _dt_prop("Slot end ISO-8601"),
            },
            required=["datetime_start", "datetime_end"],
            legacy_names=("check_calendar_availability",),
        )
    )
    registry.register(
        _tool(
            name="restaurant_availability",
            handler=industry.restaurant_availability_tool,
            kind=ToolKind.READ,
            capability="reservation",
            description="Find restaurant capacity slots for a party size",
            properties={
                "catalog_item_id": {"type": "integer"},
                "datetime_start": _dt_prop("Window start"),
                "datetime_end": _dt_prop("Window end"),
                "party_size": {"type": "integer"},
                "location_id": {"type": "integer"},
                "seating_preference": {"type": "string"},
            },
            required=["datetime_start"],
        )
    )
    registry.register(
        _tool(
            name="create_reservation",
            handler=restaurant.create_reservation_tool,
            kind=ToolKind.MUTATION,
            capability="reservation",
            description="Create a restaurant reservation using capacity allocation",
            properties={
                "catalog_item_id": {"type": "integer"},
                "datetime_start": _dt_prop("Start"),
                "party_size": {"type": "integer"},
                "location_id": {"type": "integer"},
                "client_name": {"type": "string"},
                "client_phone": {"type": "string"},
                "seating_preference": {"type": "string"},
                "dietary_notes": {"type": "string"},
                "accessibility_notes": {"type": "string"},
                "special_occasion": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            required=["catalog_item_id", "datetime_start", "party_size"],
            mutation_confirm=True,
            args_model=CreateReservationArgs,
        )
    )
    registry.register(
        _tool(
            name="modify_reservation",
            handler=restaurant.modify_reservation_tool,
            kind=ToolKind.MUTATION,
            capability="reservation",
            description="Modify party size and/or reschedule a restaurant reservation",
            properties={
                "reservation_id": {"type": "integer"},
                "party_size": {"type": "integer"},
                "datetime_start": _dt_prop("New start time"),
                "confirmed": {"type": "boolean"},
            },
            required=["reservation_id"],
            mutation_confirm=True,
            args_model=ModifyReservationArgs,
        )
    )
    registry.register(
        _tool(
            name="cancel_reservation",
            handler=industry.cancel_reservation_tool,
            kind=ToolKind.MUTATION,
            capability="reservation",
            description="Cancel a restaurant reservation by id",
            properties={
                "reservation_id": {"type": "integer"},
                "confirmed": {"type": "boolean"},
            },
            required=["reservation_id"],
            mutation_confirm=True,
            args_model=CancelReservationArgs,
        )
    )
    registry.register(
        _tool(
            name="join_waitlist",
            handler=industry.join_waitlist_tool,
            kind=ToolKind.MUTATION,
            capability="waitlist",
            description="Join the waitlist for a location or service",
            properties={
                "party_size": {"type": "integer"},
                "location_id": {"type": "integer"},
                "catalog_item_id": {"type": "integer"},
                "client_name": {"type": "string"},
                "client_phone": {"type": "string"},
                "preferred_start": _dt_prop("Preferred start"),
                "seating_preference": {"type": "string"},
            },
        )
    )
    registry.register(
        _tool(
            name="promote_waitlist",
            handler=restaurant.promote_waitlist_tool,
            kind=ToolKind.MUTATION,
            capability="waitlist",
            description="Promote a waitlist entry when a table becomes available",
            properties={
                "waitlist_id": {"type": "integer"},
                "confirmed": {"type": "boolean"},
            },
            required=["waitlist_id"],
            mutation_confirm=True,
            args_model=PromoteWaitlistArgs,
        )
    )
    registry.register(
        _tool(
            name="find_salon_services",
            handler=salon.find_salon_services,
            kind=ToolKind.READ,
            capability="salon",
            description="List salon services from the catalog",
            properties={"query": {"type": "string"}},
        )
    )
    registry.register(
        _tool(
            name="find_available_staff",
            handler=salon.find_available_staff,
            kind=ToolKind.READ,
            capability="salon",
            description="List salon staff optionally filtered by skill",
            properties={
                "skill": {"type": "string"},
                "location_id": {"type": "integer"},
            },
        )
    )
    registry.register(
        _tool(
            name="find_salon_availability",
            handler=salon.find_salon_availability,
            kind=ToolKind.READ,
            capability="salon",
            description="Find multi-resource salon availability slots",
            properties={
                "catalog_item_id": {"type": "integer"},
                "datetime_start": _dt_prop("Window start"),
                "datetime_end": _dt_prop("Window end"),
                "location_id": {"type": "integer"},
                "preferred_staff_id": {"type": "integer"},
                "required_capability": {"type": "string"},
            },
            required=["catalog_item_id", "datetime_start"],
        )
    )
    registry.register(
        _tool(
            name="estimate_service_price",
            handler=salon.estimate_service_price,
            kind=ToolKind.READ,
            capability="salon",
            description="Estimate salon service price including add-ons",
            properties={
                "catalog_item_id": {"type": "integer"},
                "addon_item_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "location_id": {"type": "integer"},
            },
            required=["catalog_item_id"],
        )
    )
    registry.register(
        _tool(
            name="book_salon_service",
            handler=salon.book_salon_service,
            kind=ToolKind.MUTATION,
            capability="salon",
            description="Book a salon service with optional staff and add-ons",
            properties={
                "catalog_item_id": {"type": "integer"},
                "datetime_start": _dt_prop("Appointment start"),
                "addon_item_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "preferred_staff_id": {"type": "integer"},
                "required_capability": {"type": "string"},
                "location_id": {"type": "integer"},
                "client_name": {"type": "string"},
                "client_phone": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            required=["catalog_item_id", "datetime_start"],
            mutation_confirm=True,
            args_model=BookSalonServiceArgs,
        )
    )
    registry.register(
        _tool(
            name="modify_salon_booking",
            handler=salon.modify_salon_booking,
            kind=ToolKind.MUTATION,
            capability="salon",
            description="Reschedule a salon booking and/or change preferred staff",
            properties={
                "reservation_id": {"type": "integer"},
                "datetime_start": _dt_prop("New start time"),
                "preferred_staff_id": {"type": "integer"},
                "confirmed": {"type": "boolean"},
            },
            required=["reservation_id"],
            mutation_confirm=True,
            args_model=ModifySalonBookingArgs,
        )
    )
    create_appointment_props = dict(legacy["create_calendar_event"]["parameters"]["properties"])
    create_appointment_props.update(
        {
            "catalog_item_id": {"type": "integer"},
            "practitioner_id": {"type": "integer"},
            "location_id": {"type": "integer"},
            "utterance": {"type": "string"},
        }
    )
    registry.register(
        _tool(
            name="create_appointment",
            handler=industry.create_appointment_tool,
            kind=ToolKind.MUTATION,
            capability="reservation",
            description="Create an administrative appointment after confirmation",
            properties=create_appointment_props,
            required=list(legacy["create_calendar_event"]["parameters"]["required"]),
            mutation_confirm=True,
            clinic_redact=True,
            legacy_names=("create_calendar_event",),
            args_model=CreateAppointmentArgs,
        )
    )
    registry.register(
        _tool(
            name="book_appointment",
            handler=industry.book_appointment_tool,
            kind=ToolKind.MUTATION,
            capability="reservation",
            description="Book an appointment for a general business",
            properties=legacy["create_calendar_event"]["parameters"]["properties"],
            required=list(legacy["create_calendar_event"]["parameters"]["required"]),
            mutation_confirm=True,
            legacy_names=("create_calendar_event",),
        )
    )
    registry.register(
        _tool(
            name="get_price",
            handler=industry.get_price_tool,
            kind=ToolKind.READ,
            capability="pricing",
            description="Look up a catalog item price in minor units",
            properties={"catalog_item_id": {"type": "integer"}},
            required=["catalog_item_id"],
        )
    )
    registry.register(
        _tool(
            name="create_quote_request",
            handler=industry.create_quote_request_tool,
            kind=ToolKind.MUTATION,
            capability="lead",
            description="Capture a quote request",
            properties={
                "details": {"type": "string"},
                "catalog_item_id": {"type": "integer"},
            },
        )
    )
    registry.register(
        _tool(
            name="take_message",
            handler=industry.take_message_tool,
            kind=ToolKind.MUTATION,
            capability="lead",
            description="Take a message for the business",
            properties={
                "message": {"type": "string"},
                "client_name": {"type": "string"},
                "client_phone": {"type": "string"},
            },
            required=["message"],
        )
    )
    registry.register(
        _tool(
            name="answer_faq",
            handler=industry.answer_faq_tool,
            kind=ToolKind.READ,
            capability="knowledge",
            description="Answer from organization knowledge entries",
            properties={"query": {"type": "string"}},
            required=["query"],
        )
    )
    registry.register(
        _tool(
            name="provide_product_information",
            handler=industry.provide_product_information,
            kind=ToolKind.READ,
            capability="catalog",
            description="Provide product information from the catalog",
            properties={"query": {"type": "string"}},
        )
    )
    registry.register(
        _tool(
            name="send_secure_link",
            handler=industry.send_secure_link_tool,
            kind=ToolKind.MUTATION,
            capability="payments",
            description="Queue a secure payment or product link",
            properties={
                "purpose": {"type": "string"},
                "client_phone": {"type": "string"},
                "client_email": {"type": "string"},
                "client_name": {"type": "string"},
            },
            args_model=SendSecureLinkArgs,
        )
    )
    registry.register(
        _tool(
            name="check_order_status",
            handler=industry.check_order_status_tool,
            kind=ToolKind.READ,
            capability="orders",
            description="Check order status when connected",
            properties={"order_id": {"type": "string"}},
            required=["order_id"],
            args_model=CheckOrderStatusArgs,
        )
    )
    return registry

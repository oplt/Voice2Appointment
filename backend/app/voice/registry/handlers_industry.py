"""Shared industry voice helpers + registry-facing re-exports."""

from __future__ import annotations

from app.calendars.tools import (
    cancel_appointment as calendar_cancel_appointment,
)
from app.calendars.tools import (
    check_calendar_availability,
    request_human_handoff,
    reschedule_appointment,
)
from app.voice.registry.handlers_clinic import (
    book_appointment_tool,
    create_appointment_tool,
    find_practitioners_tool,
    find_visit_types_tool,
)
from app.voice.registry.handlers_common import (
    _as_bool,
    _find_bookable_catalog_item,
    _org_context,
    _parse_dt,
)
from app.voice.registry.handlers_general import (
    answer_faq_tool,
    catalog_search,
    check_order_status_tool,
    create_quote_request_tool,
    get_price_tool,
    provide_product_information,
    search_catalog_tool,
    send_secure_link_tool,
    take_message_tool,
)
from app.voice.registry.handlers_restaurant import (
    cancel_reservation_tool,
    join_waitlist_tool,
    restaurant_availability_tool,
)

appointment_availability = check_calendar_availability
cancel_appointment_tool = calendar_cancel_appointment
reschedule_appointment_tool = reschedule_appointment
request_human_handoff_tool = request_human_handoff

__all__ = [
    "_as_bool",
    "_find_bookable_catalog_item",
    "_org_context",
    "_parse_dt",
    "answer_faq_tool",
    "appointment_availability",
    "book_appointment_tool",
    "cancel_appointment_tool",
    "cancel_reservation_tool",
    "catalog_search",
    "check_order_status_tool",
    "create_appointment_tool",
    "create_quote_request_tool",
    "find_practitioners_tool",
    "find_visit_types_tool",
    "get_price_tool",
    "join_waitlist_tool",
    "provide_product_information",
    "request_human_handoff_tool",
    "reschedule_appointment_tool",
    "restaurant_availability_tool",
    "search_catalog_tool",
    "send_secure_link_tool",
    "take_message_tool",
]

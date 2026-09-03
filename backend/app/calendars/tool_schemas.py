"""Single source of truth for Deepgram/OpenAI voice tool schemas.

Must match Python callables in ``app.calendars.tools.FUNCTION_MAP``.
"""

from __future__ import annotations

from typing import Any

AGENT_SYSTEM_PROMPT = """You are a professional appointment scheduling assistant.

Tools:
1) check_calendar_availability — check a time slot
2) find_appointments — list candidate events with event_id (required before cancel/reschedule)
3) create_calendar_event — book only after the caller confirms (confirmed=true)
4) reschedule_appointment — reschedule by verified event_id only after confirmation
5) cancel_appointment — cancel by verified event_id only after confirmation

Safety rules:
- Never cancel or reschedule by guessing the closest time. Always call find_appointments first.
- If find_appointments returns 0 results: ask the caller for a clearer time/title.
- If it returns 1 result: read it back and ask for confirmation, then mutate with that event_id and confirmed=true.
- If it returns multiple results: ask the caller which event_id / which appointment.
- For create/reschedule/cancel: first call with confirmed=false (or omit confirmed) to get a confirmation prompt; only call again with confirmed=true after the caller agrees.
- Always convert relative dates (today, tomorrow, next Friday, this evening) to absolute ISO datetimes using CURRENT DATE CONTEXT before tool calls.
- Confirm critical details (title, date, time, duration) before mutations.
- Use request_human_handoff only when the caller asks for a person or you cannot complete the request safely; require confirmed=true after they agree.

CURRENT DATE CONTEXT:
{current_date_context}
"""


def _dt_prop(description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "format": "date-time",
        "description": description,
    }


VOICE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "check_calendar_availability",
        "description": "Check if a specific time slot is available on the calendar",
        "parameters": {
            "type": "object",
            "properties": {
                "datetime_start": _dt_prop("Slot start in ISO-8601"),
                "datetime_end": _dt_prop("Slot end in ISO-8601"),
            },
            "required": ["datetime_start", "datetime_end"],
        },
    },
    {
        "name": "find_appointments",
        "description": (
            "Find candidate appointments in a time range. "
            "Returns event_id values required for cancel/reschedule."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "datetime_start": _dt_prop("Search window start ISO-8601"),
                "datetime_end": _dt_prop("Search window end ISO-8601"),
                "summary_contains": {
                    "type": "string",
                    "description": "Optional case-insensitive title filter",
                },
            },
            "required": ["datetime_start", "datetime_end"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Create a calendar appointment. Call first with confirmed=false to get a "
            "confirmation prompt; call again with confirmed=true only after the caller agrees."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Appointment title"},
                "datetime_start": _dt_prop("Start ISO-8601"),
                "datetime_end": _dt_prop("End ISO-8601"),
                "description": {"type": "string"},
                "client_name": {"type": "string"},
                "client_phone": {"type": "string"},
                "client_email": {"type": "string"},
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true to perform the booking",
                },
            },
            "required": ["summary", "datetime_start", "datetime_end"],
        },
    },
    {
        "name": "reschedule_appointment",
        "description": (
            "Reschedule an appointment by verified Google event_id. "
            "Requires confirmed=true after the caller agrees."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Exact Google Calendar event id from find_appointments",
                },
                "new_datetime_start": _dt_prop("New start ISO-8601"),
                "new_datetime_end": _dt_prop("New end ISO-8601"),
                "reason": {"type": "string"},
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true to perform the reschedule",
                },
            },
            "required": ["event_id", "new_datetime_start", "new_datetime_end"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": (
            "Cancel an appointment by verified Google event_id. "
            "Requires confirmed=true after the caller agrees."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Exact Google Calendar event id from find_appointments",
                },
                "reason": {"type": "string"},
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true to perform the cancellation",
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "request_human_handoff",
        "description": (
            "Transfer the live call to a human when the caller asks or the assistant "
            "cannot safely continue. Call first with confirmed=false; only confirmed=true "
            "after the caller agrees. Never include transcript content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short category, e.g. billing, complex_request, caller_request",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true to perform the transfer",
                },
            },
            "required": [],
        },
    },
]

import logging
from datetime import datetime, timedelta
from flaskapp.calendar.calendar import GoogleCalendarService

DEFAULT_USER_ID = 1

def check_calendar_availability(datetime_start=None, datetime_end=None):
    """
    Check if a specific time slot is available on Google Calendar
    """
    # user_id = user_id or DEFAULT_USER_ID

    try:
        # Convert to proper datetime format if needed
        if isinstance(datetime_start, str):
            datetime_start = datetime.fromisoformat(datetime_start.replace('Z', '+00:00'))
        if isinstance(datetime_end, str):
            datetime_end = datetime.fromisoformat(datetime_end.replace('Z', '+00:00'))

        # Format for Google Calendar API
        start_iso = datetime_start.isoformat()
        end_iso = datetime_end.isoformat()

        logging.info(f"Checking calendar availability from {start_iso} to {end_iso}")

        # Initialize calendar service with user_id
        # calendar_service = GoogleCalendarService(user_id)
        calendar_service = GoogleCalendarService()

        # Check availability
        is_available, conflicting_events = calendar_service.check_availability(start_iso, end_iso)

        if is_available:
            return {
                "available": True,
                "message": "Time slot is available",
                "suggested_alternatives": []
            }
        else:
            # Suggest alternative times
            alternatives = generate_alternative_slots(datetime_start, datetime_end, calendar_service)

            return {
                "available": False,
                "message": "Time slot is not available",
                "conflicting_events": [event.get('summary', 'Unknown event') for event in conflicting_events],
                "suggested_alternatives": alternatives
            }

    except Exception as e:
        logging.error(f"Error checking calendar availability: {e}")
        return {
            "error": f"Failed to check availability: {str(e)}",
            "available": False
        }

def create_calendar_event(summary=None, datetime_start=None, datetime_end=None, description=None, attendees=None):
    """
    Create a new calendar event for an appointment on Google Calendar
    """
    # user_id = user_id or DEFAULT_USER_ID

    try:
        # Convert to proper datetime format if needed
        if isinstance(datetime_start, str):
            datetime_start = datetime.fromisoformat(datetime_start.replace('Z', '+00:00'))
        if isinstance(datetime_end, str):
            datetime_end = datetime.fromisoformat(datetime_end.replace('Z', '+00:00'))

        # Format for Google Calendar API
        start_iso = datetime_start.isoformat()
        end_iso = datetime_end.isoformat()

        logging.info(f"Creating calendar event: {summary} from {start_iso} to {end_iso}")

        # Initialize calendar service with user_id
        # calendar_service = GoogleCalendarService(user_id)
        calendar_service = GoogleCalendarService()

        # Create the event
        event = calendar_service.create_event(
            summary=summary,
            datetime_start=start_iso,
            datetime_end=end_iso,
            description=description or f"Appointment: {summary}",
            timezone="UTC"
        )

        return {
            "success": True,
            "event_id": event.get('id'),
            "html_link": event.get('htmlLink'),
            "summary": event.get('summary'),
            "start_time": event['start'].get('dateTime'),
            "end_time": event['end'].get('dateTime'),
            "message": "Appointment successfully created on Google Calendar"
        }

    except Exception as e:
        logging.error(f"Error creating calendar event: {e}")
        return {
            "error": f"Failed to create appointment: {str(e)}",
            "success": False
        }

def reschedule_appointment(original_datetime=None, new_datetime_start=None, new_datetime_end=None, reason=None):
    """
    Reschedule an existing appointment on Google Calendar
    """
    # user_id = user_id or DEFAULT_USER_ID

    try:
        # Convert to proper datetime format
        if isinstance(original_datetime, str):
            original_datetime = datetime.fromisoformat(original_datetime.replace('Z', '+00:00'))
        if isinstance(new_datetime_start, str):
            new_datetime_start = datetime.fromisoformat(new_datetime_start.replace('Z', '+00:00'))
        if isinstance(new_datetime_end, str):
            new_datetime_end = datetime.fromisoformat(new_datetime_end.replace('Z', '+00:00'))

        # Initialize calendar service with user_id
        # calendar_service = GoogleCalendarService(user_id)
        calendar_service = GoogleCalendarService()

        # Find the event at the original time
        original_start_iso = original_datetime.isoformat()
        original_end_iso = (original_datetime + timedelta(hours=1)).isoformat()  # Assume 1-hour appointment

        # Get events in the original time range
        events_result = calendar_service.service.events().list(
            calendarId='primary',
            timeMin=original_start_iso,
            timeMax=original_end_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "success": False,
                "error": "No appointment found at the specified time"
            }

        # Update the first event found (assuming it's the correct one)
        event = events[0]
        event_id = event['id']

        # Update the event
        updated_event = calendar_service.update_event(
            event_id=event_id,
            datetime_start=new_datetime_start.isoformat(),
            datetime_end=new_datetime_end.isoformat()
        )

        # Add reschedule reason to description if provided
        if reason:
            current_description = updated_event.get('description', '')
            new_description = f"{current_description}\n\nRescheduled: {reason}"
            calendar_service.update_event(
                event_id=event_id,
                description=new_description
            )

        return {
            "success": True,
            "event_id": updated_event.get('id'),
            "original_time": original_datetime.isoformat(),
            "new_time": new_datetime_start.isoformat(),
            "message": "Appointment successfully rescheduled"
        }

    except Exception as e:
        logging.error(f"Error rescheduling appointment: {e}")
        return {
            "error": f"Failed to reschedule appointment: {str(e)}",
            "success": False
        }

def cancel_appointment(datetime_start=None, reason=None):
    """
    Cancel an existing appointment on Google Calendar by finding and deleting the event
    """
    # user_id = user_id or DEFAULT_USER_ID

    try:
        # Convert to proper datetime format if needed
        if isinstance(datetime_start, str):
            datetime_start = datetime.fromisoformat(datetime_start.replace('Z', '+00:00'))

        logging.info(f"Cancelling appointment at {datetime_start.isoformat()}")

        # Initialize calendar service with user_id
        # calendar_service = GoogleCalendarService(user_id)
        calendar_service = GoogleCalendarService()

        # Create a time window to search for the appointment (30 minutes before and after)
        search_start = (datetime_start - timedelta(minutes=30)).isoformat()
        search_end = (datetime_start + timedelta(minutes=30)).isoformat()

        # Search for events in the time window
        events_result = calendar_service.service.events().list(
            calendarId='primary',
            timeMin=search_start,
            timeMax=search_end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "success": False,
                "error": "No appointment found around the specified time",
                "suggestions": "Please check the exact time of your appointment"
            }

        # Find the closest event to the requested time
        closest_event = None
        min_time_diff = float('inf')

        for event in events:
            event_start_str = event['start'].get('dateTime') or event['start'].get('date')
            if event_start_str:
                event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                time_diff = abs((event_start - datetime_start).total_seconds())

                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_event = event

        if not closest_event:
            return {
                "success": False,
                "error": "Could not find a valid appointment to cancel"
            }

        # Get event details
        event_id = closest_event['id']
        event_summary = closest_event.get('summary', 'Unknown appointment')
        event_start = closest_event['start'].get('dateTime') or closest_event['start'].get('date')

        # Delete the event
        success = calendar_service.delete_event(event_id)

        if success:
            result = {
                "success": True,
                "cancelled_appointment": event_summary,
                "original_time": event_start,
                "message": f"Appointment '{event_summary}' has been successfully cancelled"
            }

            # Add reason if provided
            if reason:
                result["cancellation_reason"] = reason
                result["message"] += f". Reason: {reason}"

            return result
        else:
            return {
                "success": False,
                "error": "Failed to cancel the appointment",
                "appointment": event_summary
            }

    except Exception as e:
        logging.error(f"Error cancelling appointment: {e}")
        return {
            "error": f"Failed to cancel appointment: {str(e)}",
            "success": False
        }

def get_appointment_details(datetime_start=None, datetime_end=None, attendee=None):
    """
    Get details about appointments in a time range from Google Calendar
    """
    # user_id = user_id or DEFAULT_USER_ID

    try:
        if isinstance(datetime_start, str):
            datetime_start = datetime.fromisoformat(datetime_start.replace('Z', '+00:00'))
        if isinstance(datetime_end, str):
            datetime_end = datetime.fromisoformat(datetime_end.replace('Z', '+00:00'))

        # Initialize calendar service with user_id
        # calendar_service = GoogleCalendarService(user_id)
        calendar_service = GoogleCalendarService()

        start_iso = datetime_start.isoformat()
        end_iso = datetime_end.isoformat()

        # Get events in the time range
        events_result = calendar_service.service.events().list(
            calendarId='primary',
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Filter by attendee if specified
        if attendee:
            events = [
                event for event in events
                if any(attendee.lower() in attendee_email.get('email', '').lower()
                      or attendee.lower() in attendee_email.get('displayName', '').lower()
                      for attendee_email in event.get('attendees', []))
            ]

        # Format the response
        appointment_details = []
        for event in events:
            appointment_details.append({
                "id": event.get('id'),
                "summary": event.get('summary'),
                "description": event.get('description'),
                "start_time": event['start'].get('dateTime'),
                "end_time": event['end'].get('dateTime'),
                "status": event.get('status'),
                "attendees": [
                    {
                        "email": att.get('email'),
                        "name": att.get('displayName')
                    } for att in event.get('attendees', [])
                ]
            })

        return {
            "success": True,
            "appointments": appointment_details,
            "count": len(appointment_details),
            "time_range": {
                "start": start_iso,
                "end": end_iso
            }
        }

    except Exception as e:
        logging.error(f"Error getting appointment details: {e}")
        return {
            "error": f"Failed to get appointment details: {str(e)}",
            "success": False
        }

def generate_alternative_slots(original_start, original_end, calendar_service, num_alternatives=3):
    """
    Generate alternative time slots when the requested time is not available
    """

    try:
        duration = original_end - original_start
        alternatives = []

        # Try same day, different times
        for hours_offset in [1, 2, 3, -1, -2]:  # Try before and after
            alternative_start = original_start + timedelta(hours=hours_offset)
            alternative_end = alternative_start + duration

            # Check if this alternative is available
            is_available, _ = calendar_service.check_availability(
                alternative_start.isoformat(),
                alternative_end.isoformat()
            )

            if is_available:
                alternatives.append({
                    "start": alternative_start.isoformat(),
                    "end": alternative_end.isoformat(),
                    "message": f"Available at {alternative_start.strftime('%I:%M %p')}"
                })

                if len(alternatives) >= num_alternatives:
                    break

        # If not enough alternatives, try next day
        if len(alternatives) < num_alternatives:
            next_day_start = original_start + timedelta(days=1)
            next_day_end = next_day_start + duration

            is_available, _ = calendar_service.check_availability(
                next_day_start.isoformat(),
                next_day_end.isoformat()
            )

            if is_available:
                alternatives.append({
                    "start": next_day_start.isoformat(),
                    "end": next_day_end.isoformat(),
                    "message": f"Available tomorrow at {next_day_start.strftime('%I:%M %p')}"
                })

        return alternatives

    except Exception as e:
        logging.error(f"Error generating alternative slots: {e}")
        return []

FUNCTION_MAP = {
    "check_calendar_availability": check_calendar_availability,
    "create_calendar_event": create_calendar_event,
    "reschedule_appointment": reschedule_appointment,
    "cancel_appointment": cancel_appointment,
    "get_appointment_details": get_appointment_details
}
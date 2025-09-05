from flask import render_template, request, Blueprint, jsonify
from flask_login import current_user, login_required
from functools import lru_cache
from flaskapp.database.models import GoogleCalendarAuth
from flaskapp.calendar.calendar import  authenticate_google_calendar
from datetime import datetime, timedelta
import pytz
import logging
from flaskapp.calendar.calendar import GoogleCalendarService


calendar_bp = Blueprint('calendar_bp', __name__)


@lru_cache
def get_user_timezone(user_id):
    """Get the user's timezone from GoogleCalendarAuth table"""
    try:
        auth_record = GoogleCalendarAuth.query.filter_by(user_id=user_id).first()
        if auth_record and auth_record.time_zone:
            return auth_record.time_zone
        else:
            # Default to Europe/Brussels if no timezone is set
            return 'Europe/Brussels'
    except Exception:
        # Fallback to Europe/Brussels if there's an error
        return 'Europe/Brussels'


@calendar_bp.route('/calendar/embed/<view_type>')
@login_required
def get_calendar_embed(view_type):
    """Get Google Calendar embed URL for different view types"""
    try:
        # Get user's calendar ID (primary calendar)
        service = authenticate_google_calendar()

        # Get calendar list to find primary calendar
        calendar_list = service.calendarList().list().execute()
        primary_calendar = None

        for calendar in calendar_list.get('items', []):
            if calendar.get('primary'):
                primary_calendar = calendar
                break

        if not primary_calendar:
            return jsonify({'ok': False, 'message': 'Primary calendar not found'}), 404

        calendar_id = primary_calendar['id']
        timezone=GoogleCalendarAuth.query.filter_by(user_id=current_user.id).first().time_zone

        # Create Google Calendar embed URLs that work with proper authentication
        # Using embed URLs with proper parameters to avoid 403 errors and popups
        if view_type == 'week':
            embed_url = f"https://calendar.google.com/calendar/embed?src={calendar_id}&ctz={timezone}&mode=WEEK&showTitle=0&showNav=1&showDate=1&showPrint=0&showTabs=1&showCalendars=0&showTz=0&hl=en&bgcolor=%23ffffff&color=%23000000"
        elif view_type == 'month':
            embed_url = f"https://calendar.google.com/calendar/embed?src={calendar_id}&ctz={timezone}&mode=MONTH&showTitle=0&showNav=1&showDate=1&showPrint=0&showTabs=1&showCalendars=0&showTz=0&hl=en&bgcolor=%23ffffff&color=%23000000"
        elif view_type == 'agenda':
            embed_url = f"https://calendar.google.com/calendar/embed?src={calendar_id}&ctz={timezone}&mode=AGENDA&showTitle=0&showNav=1&showDate=1&showPrint=0&showTabs=1&showCalendars=0&showTz=0&hl=en&bgcolor=%23ffffff&color=%23000000"
        else:
            return jsonify({'ok': False, 'message': 'Invalid view type'}), 400

        return jsonify({
            'ok': True,
            'embed_url': embed_url,
            'view_type': view_type,
            'calendar_id': calendar_id
        })

    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@calendar_bp.route('/calendar/events')
@login_required
def get_google_calendar_events():
    """Get Google Calendar events for the current user"""
    try:
        # Get query parameters
        time_min = request.args.get('timeMin')
        time_max = request.args.get('timeMax')
        timezone_str = request.args.get('timezone', 'Europe/Brussels')

        if not time_min or not time_max:
            return jsonify({'error': 'timeMin and timeMax parameters are required'}), 400

        # Parse and validate dates
        try:
            # Parse the incoming dates (they should be in ISO format from FullCalendar)
            from datetime import datetime
            import pytz

            # Parse the dates - FullCalendar may send dates with or without timezone info
            if 'Z' in time_min or '+' in time_min or '-' in time_min[-6:]:
                # Date has timezone info (e.g., 2025-08-30T23:34:22.535Z)
                start_date = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
                end_date = datetime.fromisoformat(time_max.replace('Z', '+00:00'))

                # Convert to the user's timezone
                user_tz = pytz.timezone(timezone_str)
                start_date = start_date.astimezone(user_tz)
                end_date = end_date.astimezone(user_tz)
            else:
                # Date has no timezone info (e.g., 2025-07-27T00:00:00)
                start_date = datetime.fromisoformat(time_min)
                end_date = datetime.fromisoformat(time_max)

                # Localize the dates to the user's timezone
                user_tz = pytz.timezone(timezone_str)
                start_date = user_tz.localize(start_date)
                end_date = user_tz.localize(end_date)

            # Format for Google Calendar API (RFC 3339 format)
            time_min_formatted = start_date.isoformat()
            time_max_formatted = end_date.isoformat()

            logging.info(f"Date range: {time_min_formatted} to {time_max_formatted}")

        except ValueError as e:
            logging.error(f"Invalid date format: {e}")
            return jsonify({'error': f'Invalid date format: {str(e)}'}), 400

        # Get user's Google Calendar service
        from flaskapp.calendar.calendar import GoogleCalendarService
        calendar_service = GoogleCalendarService.authenticate()

        # Get events from Google Calendar with proper error handling
        try:
            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=time_min_formatted,
                timeMax=time_max_formatted,
                singleEvents=True,
                orderBy='startTime',
                maxResults=100  # Limit results to avoid overwhelming responses
            ).execute()

            events = events_result.get('items', [])
            logging.info(f"Retrieved {len(events)} events from Google Calendar")

        except Exception as api_error:
            logging.error(f"Google Calendar API error: {api_error}")
            # Return empty events list instead of failing completely
            events = []

        # Format events for FullCalendar
        formatted_events = []
        for event in events:
            try:
                start = event['start'].get('dateTime') or event['start'].get('date')
                end = event['end'].get('dateTime') or event['end'].get('date')

                # Ensure dates are in proper format for FullCalendar
                if start:
                    if 'T' in start:  # Has time component
                        # Convert to user's timezone if it's a datetime
                        try:
                            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                            start_dt = start_dt.astimezone(user_tz)
                            start = start_dt.isoformat()
                        except:
                            pass  # Keep original if conversion fails
                    else:
                        # All-day event, keep as is
                        pass

                if end:
                    if 'T' in end:  # Has time component
                        try:
                            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                            end_dt = end_dt.astimezone(user_tz)
                            end = end_dt.isoformat()
                        except:
                            pass

                formatted_event = {
                    'id': event.get('id', f'event_{len(formatted_events)}'),
                    'title': event.get('summary', 'No Title'),
                    'start': start,
                    'description': event.get('description', ''),
                    'location': event.get('location', ''),
                    'attendees': [
                        {
                            'email': att.get('email', ''),
                            'name': att.get('displayName', att.get('email', ''))
                        } for att in event.get('attendees', [])
                    ]
                }

                # Only add end time if it's different from start time
                if end and end != start:
                    formatted_event['end'] = end

                # Set allDay flag
                formatted_event['allDay'] = 'date' in event['start']

                # Add URL if available
                if event.get('htmlLink'):
                    formatted_event['url'] = event['htmlLink']

                formatted_events.append(formatted_event)

            except Exception as event_error:
                logging.error(f"Error formatting event {event.get('id', 'unknown')}: {event_error}")
                continue  # Skip this event and continue with others

        logging.info(f"Returning {len(formatted_events)} formatted events")
        return jsonify(formatted_events)

    except Exception as e:
        logging.error(f"Error fetching Google Calendar events: {e}")
        return jsonify({'error': f'Failed to fetch events: {str(e)}'}), 500


@calendar_bp.route('/google/counts')
@login_required
def get_google_calendar_counts():
    try:
        # Get user's timezone
        timezone = get_user_timezone(current_user.id)
        now = datetime.now(pytz.timezone(timezone))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        week_end = today_start + timedelta(days=7)

        # Get user's Google Calendar service
        calendar_service = GoogleCalendarService.authenticate(current_user)

        # Get today's events
        today_events = calendar_service.events().list(
            calendarId='primary',
            timeMin=today_start.isoformat(),
            timeMax=today_end.isoformat(),
            singleEvents=True
        ).execute()

        # Get this week's events
        week_events = calendar_service.events().list(
            calendarId='primary',
            timeMin=today_start.isoformat(),
            timeMax=week_end.isoformat(),
            singleEvents=True
        ).execute()

        return jsonify({
            'today': len(today_events.get('items', [])),
            'week': len(week_events.get('items', [])),
        })

    except Exception as e:
        logging.error(f"Error getting Google Calendar counts: {e}")
        return jsonify({'error': f'Failed to get counts: {str(e)}'}), 500


@calendar_bp.route('/google/auth-status')
@login_required
def google_auth_status():
    is_connected = GoogleCalendarService.authenticate(current_user) is not None
    return jsonify({'connected': is_connected})


@calendar_bp.route('/google/upcoming-events')
@login_required
def get_upcoming_appointments():
    """Get upcoming appointments for the sidebar"""
    try:
        timezone = get_user_timezone(user_id=current_user.id)
        now = datetime.now(pytz.timezone(timezone))
        end_date = now + timedelta(days=7)

        calendar_service = GoogleCalendarService.authenticate(current_user)
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=10
        ).execute()

        events = events_result.get('items', [])

        # Format upcoming events
        upcoming = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))

            if 'dateTime' in event['start']:
                # This is a datetime event
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = pytz.timezone(timezone).localize(start_dt)
            else:
                # This is an all-day event
                start_dt = datetime.strptime(start, '%Y-%m-%d')
                start_dt = pytz.timezone(timezone).localize(start_dt)

            upcoming.append({
                'id': event['id'],
                'title': event.get('summary', 'No Title'),
                'start': start_dt.strftime('%I:%M %p'),
                'date': start_dt.strftime('%b %d'),
                'is_today': start_dt.date() == now.date(),
                'htmlLink': event.get('htmlLink', '#')
            })

        return jsonify({
            'ok': True,
            'upcoming': upcoming
        })

    except Exception as e:
        logging.error(f"Error fetching upcoming events: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500

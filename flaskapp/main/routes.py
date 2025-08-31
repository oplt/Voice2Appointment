from flask import render_template, request, Blueprint, jsonify
from flask_login import current_user, login_required
from numba.cuda.cudadrv.devicearray import lru_cache
from flaskapp.database.models import GoogleCalendarAuth
from flaskapp.utils.calendar import  authenticate_google_calendar
from datetime import datetime, timedelta
import pytz
from flaskapp import db
import logging



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

main = Blueprint('main', __name__)


@main.route("/")
@main.route("/home")
def home():
    return render_template('home.html')


@main.route("/dashboard")
@login_required
def dashboard():
    return render_template('dashboard.html')



@main.route('/dashboard/stats')
@login_required
def get_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    try:
        from flaskapp.database.models import User
        total_users = User.query.count()

        try:
            timezone = get_user_timezone(user_id=current_user.id if current_user.is_authenticated else None)
            now = datetime.now(pytz.timezone(timezone))
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            week_end = today_start + timedelta(days=7)
            
            # Only try to authenticate if user is logged in
            if current_user.is_authenticated:
                try:
                    service = authenticate_google_calendar()
                    
                    # Today's events
                    today_events = service.events().list(
                        calendarId='primary',
                        timeMin=today_start.isoformat(),
                        timeMax=today_end.isoformat(),
                        singleEvents=True
                    ).execute()
                    
                    # This week's events
                    week_events = service.events().list(
                        calendarId='primary',
                        timeMin=today_start.isoformat(),
                        timeMax=week_end.isoformat(),
                        singleEvents=True
                    ).execute()
                    
                    # Count voice-scheduled appointments
                    voice_count = len([e for e in week_events.get('items', []) 
                                      if 'voice' in e.get('summary', '').lower() or 
                                         'voice' in e.get('description', '').lower()])
                    
                    calendar_stats = {
                        'today': len(today_events.get('items', [])),
                        'week': len(week_events.get('items', [])),
                        'voice': voice_count
                    }
                except Exception as cal_error:
                    # If calendar fails, use default values
                    calendar_stats = {
                        'today': 0,
                        'week': 0,
                        'voice': 0
                    }
            else:
                # No authenticated user, use default values
                calendar_stats = {
                    'today': 0,
                    'week': 0,
                    'voice': 0
                }
        
        except Exception as cal_error:
            # If calendar fails, use default values
            calendar_stats = {
                'today': 0,
                'week': 0,
                'voice': 0
            }
        
        return jsonify({
            'ok': True,
            'stats': {
                'today': calendar_stats['today'],
                'week': calendar_stats['week'],
                'voice': calendar_stats['voice'],
                'totalUsers': total_users
            }
        })
        
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@main.route('/calendar/events')
@login_required
def get_calendar_events():
    """Fetch calendar events for the current user"""
    try:
        timezone = get_user_timezone(user_id=current_user.id if current_user.is_authenticated else None)
        now = datetime.now(pytz.timezone(timezone))
        end_date = now + timedelta(days=30)
        
        service = authenticate_google_calendar()
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Format events for frontend
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            formatted_events.append({
                'id': event['id'],
                'title': event['summary'],
                'start': start,
                'end': end,
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'htmlLink': event.get('htmlLink', '')
            })
        
        return jsonify({
            'ok': True,
            'events': formatted_events,
            'count': len(formatted_events)
        })
        
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@main.route('/calendar/upcoming')
@login_required
def get_upcoming_appointments():
    """Get upcoming appointments for the sidebar"""
    try:

        timezone = get_user_timezone(user_id=current_user.id if current_user.is_authenticated else None)
        now = datetime.now(pytz.timezone(timezone))
        end_date = now + timedelta(days=7)
        
        service = authenticate_google_calendar()
        events_result = service.events().list(
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
            if isinstance(start, str):
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = pytz.timezone(timezone).localize(start_dt)
            else:
                start_dt = start
                
            upcoming.append({
                'id': event['id'],
                'title': event['summary'],
                'start': start_dt.strftime('%I:%M %p'),
                'date': start_dt.strftime('%b %d'),
                'is_today': start_dt.date() == now.date(),
                'htmlLink': event.get('htmlLink', '')
            })
        
        return jsonify({
            'ok': True,
            'upcoming': upcoming
        })
        
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@main.route('/calendar/embed/<view_type>')
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





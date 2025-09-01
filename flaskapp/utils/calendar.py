# calendar.py (updated)
import os
import tempfile
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from flaskapp.database.models import GoogleCalendarAuth
from flaskapp import db


class GoogleCalendarService:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.service = None
        self.authenticate()

    def authenticate(self):
        """Authenticate with Google Calendar"""
        try:
            # if self.user_id is None:
            #     raise ValueError("No user ID provided")

            # Get credentials from database
            # auth_record = GoogleCalendarAuth.query.filter_by(user_id=self.user_id).first()
            auth_record = GoogleCalendarAuth.query.first()
            if not auth_record:
                raise ValueError(f"No Google Calendar authentication found for user {self.user_id}")

            credentials_json = auth_record.credentials_json
            token_json = auth_record.token_json

            if not credentials_json:
                raise ValueError("No credentials found in database")

            creds = None
            SCOPES = ['https://www.googleapis.com/auth/calendar']

            # If we have a token, try to use it
            if token_json:
                try:
                    # Parse the token JSON from database
                    token_data = json.loads(token_json)
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Error parsing token: {e}")
                    creds = None

            # If no valid credentials, try to refresh or get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        # Update the token in database
                        auth_record.token_json = creds.to_json()
                        db.session.commit()
                    except Exception as e:
                        print(f"Error refreshing token: {e}")
                        creds = None

                # If still no valid credentials, need to re-authenticate
                if not creds:
                    # Create a temporary credentials file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_creds:
                        temp_creds.write(credentials_json)
                        temp_creds_path = temp_creds.name

                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(temp_creds_path, SCOPES)
                        creds = flow.run_local_server(port=0)

                        # Save the new token to database
                        auth_record.token_json = creds.to_json()
                        db.session.commit()
                    finally:
                        # Clean up temporary file
                        try:
                            os.unlink(temp_creds_path)
                        except:
                            pass

            if not creds:
                raise ValueError("Failed to obtain valid Google Calendar credentials")

            self.service = build('calendar', 'v3', credentials=creds)
            return self.service

        except Exception as e:
            print(f"Error in Google Calendar authentication: {e}")
            raise

    def check_availability(self, datetime_start, datetime_end, calendar_id='primary'):
        """Check if a time slot is available"""
        try:
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=datetime_start,
                timeMax=datetime_end,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            return len(events) == 0, events

        except HttpError as error:
            print(f"An error occurred: {error}")
            raise

    def create_event(self, summary, datetime_start, datetime_end,
                     description="", timezone="UTC", calendar_id='primary'):
        """Create a new calendar event"""
        try:
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': datetime_start,
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': datetime_end,
                    'timeZone': timezone,
                },
            }

            event = self.service.events().insert(calendarId=calendar_id, body=event).execute()
            return event

        except HttpError as error:
            print(f"An error occurred: {error}")
            raise

    def update_event(self, event_id, summary=None, datetime_start=None, datetime_end=None,
                     description=None, timezone="UTC", calendar_id='primary'):
        """Update an existing calendar event"""
        try:
            # First get the existing event
            event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            
            # Update only the fields that are provided
            if summary:
                event['summary'] = summary
            if datetime_start:
                event['start']['dateTime'] = datetime_start
                event['start']['timeZone'] = timezone
            if datetime_end:
                event['end']['dateTime'] = datetime_end
                event['end']['timeZone'] = timezone
            if description:
                event['description'] = description

            updated_event = self.service.events().update(
                calendarId=calendar_id, 
                eventId=event_id, 
                body=event
            ).execute()
            
            return updated_event

        except HttpError as error:
            print(f"An error occurred: {error}")
            raise

    def delete_event(self, event_id, calendar_id='primary'):
        """Delete a calendar event"""
        try:
            self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            return True
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise

    def get_available_slots(self, date, duration_minutes=30, start_hour=9, end_hour=17, calendar_id='primary'):
        """Get available time slots for a specific date"""
        try:
            from datetime import datetime, timedelta
            import pytz
            
            # Set timezone (default to UTC if not specified)
            tz = pytz.UTC
            
            # Create start and end of day
            start_of_day = datetime.combine(date, datetime.min.time()).replace(tzinfo=tz)
            end_of_day = datetime.combine(date, datetime.max.time()).replace(tzinfo=tz)
            
            # Get working hours
            working_start = start_of_day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            working_end = start_of_day.replace(hour=end_hour, minute=0, second=0, microsecond=0)
            
            # Get existing events for the day
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=working_start.isoformat(),
                timeMax=working_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Generate available slots
            available_slots = []
            current_time = working_start
            
            while current_time + timedelta(minutes=duration_minutes) <= working_end:
                slot_end = current_time + timedelta(minutes=duration_minutes)
                
                # Check if this slot conflicts with any existing events
                slot_available = True
                for event in events:
                    event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')))
                    event_end = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date')))
                    
                    if event_start < slot_end and event_end > current_time:
                        slot_available = False
                        break
                
                if slot_available:
                    available_slots.append({
                        'start': current_time.isoformat(),
                        'end': slot_end.isoformat()
                    })
                
                current_time += timedelta(minutes=duration_minutes)
            
            return available_slots
            
        except Exception as e:
            print(f"Error getting available slots: {e}")
            return []


# Backward compatibility function
def authenticate_google_calendar():
    """Legacy function for backward compatibility"""
    # if user_id is None:
    #     raise ValueError("user_id is required for Google Calendar authentication")
    service = GoogleCalendarService()
    return service.service
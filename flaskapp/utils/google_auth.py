import os
import tempfile
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from flask_login import current_user
from db.models import GoogleCalendarAuth
from flaskapp import db


def authenticate_google_calendar(user_id=None):
    """Authenticate with Google Calendar using database credentials"""
    try:
        if user_id is None and current_user.is_authenticated:
            user_id = current_user.id
        
        if user_id is None:
            raise ValueError("No user ID provided and no authenticated user")
        
        # Get credentials from database
        auth_record = GoogleCalendarAuth.query.filter_by(user_id=user_id).first()
        if not auth_record:
            raise ValueError(f"No Google Calendar authentication found for user {user_id}")
        
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
        
        return build('calendar', 'v3', credentials=creds)
        
    except Exception as e:
        print(f"Error in Google Calendar authentication: {e}")
        raise

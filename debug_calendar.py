#!/usr/bin/env python3
"""
Debug script for Google Calendar authentication
Run this script to check your calendar authentication status
"""

import os
import sys
import json
import logging
from datetime import datetime

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug_calendar.log')
    ]
)
logger = logging.getLogger(__name__)

def check_environment():
    """Check if required environment is set up"""
    logger.info("=== Environment Check ===")
    print("=== Environment Check ===")
    
    # Check Python path
    logger.debug(f"Python path: {sys.path[:3]}...")
    print(f"Python path: {sys.path[:3]}...")
    
    # Check if we can import required modules
    try:
        from backend.core.ai_processor import CalendarManager
        logger.info("Successfully imported CalendarManager")
        print("✅ Successfully imported CalendarManager")
    except ImportError as e:
        logger.error(f"Failed to import CalendarManager: {e}")
        print(f"❌ Failed to import CalendarManager: {e}")
        return False
    
    try:
        from db.models import GoogleCalendarAuth
        logger.info("Successfully imported GoogleCalendarAuth model")
        print("✅ Successfully imported GoogleCalendarAuth model")
    except ImportError as e:
        logger.error(f"Failed to import GoogleCalendarAuth: {e}")
        print(f"❌ Failed to import GoogleCalendarAuth: {e}")
        return False
    
    return True

def check_local_files():
    """Check local credential files"""
    logger.info("=== Local Files Check ===")
    print("\n=== Local Files Check ===")
    
    credentials_file = 'credentials.json'
    token_file = 'token.json'
    
    if os.path.exists(credentials_file):
        logger.info(f"Credentials file exists: {credentials_file}")
        print(f"✅ Credentials file exists: {credentials_file}")
        try:
            with open(credentials_file, 'r') as f:
                creds_data = json.load(f)
                creds_type = creds_data.get('type', 'unknown')
                logger.debug(f"Credentials type: {creds_type}")
                print(f"   Type: {creds_type}")
                if creds_type == 'service_account':
                    project_id = creds_data.get('project_id', 'N/A')
                    logger.debug(f"Project ID: {project_id}")
                    print(f"   Project ID: {project_id}")
                else:
                    client_id = creds_data.get('client_id', 'N/A')[:20]
                    logger.debug(f"Client ID: {client_id}...")
                    print(f"   Client ID: {client_id}...")
        except Exception as e:
            logger.error(f"Error reading credentials: {e}")
            print(f"   ❌ Error reading credentials: {e}")
    else:
        logger.warning(f"Credentials file not found: {credentials_file}")
        print(f"❌ Credentials file not found: {credentials_file}")
    
    if os.path.exists(token_file):
        logger.info(f"Token file exists: {token_file}")
        print(f"✅ Token file exists: {token_file}")
        try:
            with open(token_file, 'r') as f:
                token_data = json.load(f)
                has_refresh = 'refresh_token' in token_data
                logger.debug(f"Has refresh token: {has_refresh}")
                print(f"   Has refresh token: {has_refresh}")
                if has_refresh:
                    token_type = token_data.get('token_type', 'N/A')
                    logger.debug(f"Token type: {token_type}")
                    print(f"   Token type: {token_type}")
        except Exception as e:
            logger.error(f"Error reading token: {e}")
            print(f"   ❌ Error reading token: {e}")
    else:
        logger.warning(f"Token file not found: {token_file}")
        print(f"❌ Token file not found: {token_file}")

def check_database_credentials():
    """Check database credentials (if possible)"""
    print("\n=== Database Credentials Check ===")
    
    try:
        # Try to set up Flask context
        from flask import Flask
        from flaskapp import create_app, db
        
        app = create_app()
        with app.app_context():
            # Check if we can query the database
            try:
                auth_records = GoogleCalendarAuth.query.all()
                print(f"✅ Database connection successful")
                print(f"   Total auth records: {len(auth_records)}")
                
                for i, record in enumerate(auth_records):
                    print(f"   Record {i+1}:")
                    print(f"     User ID: {record.user_id}")
                    print(f"     Account Email: {record.account_email}")
                    print(f"     Status: {record.status}")
                    print(f"     Has Credentials: {bool(record.credentials_json)}")
                    print(f"     Has Token: {bool(record.token_json)}")
                    
                    if record.credentials_json:
                        try:
                            creds_data = json.loads(record.credentials_json)
                            creds_type = creds_data.get('type', 'unknown')
                            print(f"     Credentials Type: {creds_type}")
                            if creds_type == 'service_account':
                                print(f"     Project ID: {creds_data.get('project_id', 'N/A')}")
                            else:
                                print(f"     Client ID: {creds_data.get('client_id', 'N/A')[:20]}...")
                                print(f"     Has Client Secret: {'client_secret' in creds_data}")
                                print(f"     Has Refresh Token: {'refresh_token' in creds_data}")
                        except Exception as e:
                            print(f"     ❌ Error parsing credentials: {e}")
                    
                    if record.last_error:
                        print(f"     Last Error: {record.last_error}")
                        
            except Exception as db_error:
                print(f"❌ Database query failed: {db_error}")
                
    except Exception as e:
        print(f"❌ Failed to set up Flask context: {e}")

def test_calendar_manager():
    """Test the CalendarManager directly"""
    print("\n=== Calendar Manager Test ===")
    
    try:
        from backend.core.ai_processor import CalendarManager
        
        calendar_manager = CalendarManager()
        print("✅ CalendarManager created successfully")
        
        # Test debug authentication
        debug_info = calendar_manager.debug_authentication()
        print("✅ Debug authentication successful")
        print("Debug info:")
        print(json.dumps(debug_info, indent=2, default=str))
        
        # Try to authenticate
        print("\n--- Testing Authentication ---")
        try:
            service = calendar_manager.authenticate()
            print("✅ Authentication successful!")
            print(f"   Service type: {type(service)}")
            
            # Test a simple calendar operation
            try:
                calendar_list = service.calendarList().list().execute()
                calendars = calendar_list.get('items', [])
                print(f"   Available calendars: {len(calendars)}")
                for cal in calendars[:3]:  # Show first 3
                    print(f"     - {cal.get('summary', 'N/A')} ({cal.get('id', 'N/A')})")
            except Exception as cal_error:
                print(f"   ❌ Calendar operation failed: {cal_error}")
                
        except Exception as auth_error:
            print(f"❌ Authentication failed: {auth_error}")
            
    except Exception as e:
        print(f"❌ CalendarManager test failed: {e}")

def main():
    """Main debug function"""
    logger.info("Starting Google Calendar Authentication Debug Tool")
    print("Google Calendar Authentication Debug Tool")
    print("=" * 50)
    print(f"Time: {datetime.now()}")
    print(f"Working Directory: {os.getcwd()}")
    
    # Run checks
    if not check_environment():
        logger.error("Environment check failed. Cannot continue.")
        print("\n❌ Environment check failed. Cannot continue.")
        return
    
    check_local_files()
    check_database_credentials()
    test_calendar_manager()
    
    logger.info("Debug completed successfully")
    print("\n" + "=" * 50)
    print("Debug completed!")

if __name__ == "__main__":
    main()

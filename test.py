# test.py
import sys
import os
import json
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Mock Flask and database dependencies for testing
class MockCurrentUser:
    def __init__(self, user_id=1):
        self.id = user_id
        self.is_authenticated = True

class MockFlaskApp:
    def app_context(self):
        return MockAppContext()

class MockAppContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

# Mock GoogleCalendarService
class MockGoogleCalendarService:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.service = MockCalendarService()

    def check_availability(self, datetime_start, datetime_end, calendar_id='primary'):
        # Simulate some availability logic
        test_busy_times = [
            ('2024-01-15T10:00:00+00:00', '2024-01-15T11:00:00+00:00'),
            ('2024-01-15T14:00:00+00:00', '2024-01-15T15:00:00+00:00')
        ]

        for busy_start, busy_end in test_busy_times:
            if (datetime_start < busy_end and datetime_end > busy_start):
                return False, [{'summary': 'Test Meeting', 'start': {'dateTime': busy_start}, 'end': {'dateTime': busy_end}}]

        return True, []

    def create_event(self, summary, datetime_start, datetime_end, description="", timezone="UTC", calendar_id='primary'):
        return {
            'id': 'test_event_123',
            'htmlLink': 'https://calendar.google.com/event?eid=test',
            'summary': summary,
            'start': {'dateTime': datetime_start},
            'end': {'dateTime': datetime_end},
            'description': description
        }

    def update_event(self, event_id, summary=None, datetime_start=None, datetime_end=None,
                     description=None, timezone="UTC", calendar_id='primary'):
        return {
            'id': event_id,
            'summary': summary or 'Updated Event',
            'start': {'dateTime': datetime_start or '2024-01-15T10:00:00+00:00'},
            'end': {'dateTime': datetime_end or '2024-01-15T11:00:00+00:00'},
            'description': description or 'Updated description'
        }

    def delete_event(self, event_id, calendar_id='primary'):
        return True

    def service(self):
        return self.service

class MockCalendarService:
    def events(self):
        return self

    def list(self, calendarId, timeMin, timeMax, singleEvents, orderBy):
        return MockEventsRequest()

    def get(self, calendarId, eventId):
        return MockEventRequest()

    def insert(self, calendarId, body):
        return MockEventInsertRequest(body)

    def update(self, calendarId, eventId, body):
        return MockEventUpdateRequest(body)

    def delete(self, calendarId, eventId):
        return MockEventDeleteRequest()

class MockEventsRequest:
    def execute(self):
        return {'items': []}

class MockEventRequest:
    def execute(self):
        return {
            'id': 'test_event_123',
            'summary': 'Test Event',
            'start': {'dateTime': '2024-01-15T10:00:00+00:00'},
            'end': {'dateTime': '2024-01-15T11:00:00+00:00'},
            'description': 'Test description'
        }

class MockEventInsertRequest:
    def __init__(self, body):
        self.body = body

    def execute(self):
        return {
            'id': 'new_event_456',
            'htmlLink': 'https://calendar.google.com/event?eid=new',
            'summary': self.body.get('summary', 'New Event'),
            'start': self.body['start'],
            'end': self.body['end'],
            'description': self.body.get('description', '')
        }

class MockEventUpdateRequest:
    def __init__(self, body):
        self.body = body

    def execute(self):
        return self.body

class MockEventDeleteRequest:
    def execute(self):
        return None

# Mock the actual imports
sys.modules['flaskapp.utils.calendar'] = type(sys)('mock_calendar')
sys.modules['flaskapp.utils.calendar'].GoogleCalendarService = MockGoogleCalendarService

sys.modules['flask'] = type(sys)('mock_flask')
sys.modules['flask'].has_request_context = lambda: False
sys.modules['flask'].current_app = MockFlaskApp()

sys.modules['flask_login'] = type(sys)('mock_flask_login')
sys.modules['flask_login'].current_user = MockCurrentUser()

# Now import the functions to test
from flaskapp.utils.functions_map import (
    check_calendar_availability,
    create_calendar_event,
    reschedule_appointment,
    cancel_appointment,
    get_appointment_details,
    generate_alternative_slots,
    FUNCTION_MAP
)

def test_check_calendar_availability():
    print("=" * 60)
    print("Testing check_calendar_availability")
    print("=" * 60)

    # Test available time slot
    print("\n1. Testing available time slot:")
    result = check_calendar_availability(
        datetime_start='2024-01-15T12:00:00+00:00',
        datetime_end='2024-01-15T13:00:00+00:00',
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

    # Test busy time slot
    print("\n2. Testing busy time slot:")
    result = check_calendar_availability(
        datetime_start='2024-01-15T10:30:00+00:00',
        datetime_end='2024-01-15T11:30:00+00:00',
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

    # Test without user_id
    print("\n3. Testing without user_id:")
    result = check_calendar_availability(
        datetime_start='2024-01-15T12:00:00+00:00',
        datetime_end='2024-01-15T13:00:00+00:00'
    )
    print(f"Result: {json.dumps(result, indent=2)}")

def test_create_calendar_event():
    print("\n" + "=" * 60)
    print("Testing create_calendar_event")
    print("=" * 60)

    # Test successful event creation
    print("\n1. Testing successful event creation:")
    result = create_calendar_event(
        summary="Test Meeting",
        datetime_start='2024-01-15T12:00:00+00:00',
        datetime_end='2024-01-15T13:00:00+00:00',
        description="This is a test meeting",
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

    # Test with string datetime
    print("\n2. Testing with string datetime:")
    result = create_calendar_event(
        summary="String DateTime Test",
        datetime_start='2024-01-15T14:00:00+00:00',
        datetime_end='2024-01-15T15:00:00+00:00',
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

def test_reschedule_appointment():
    print("\n" + "=" * 60)
    print("Testing reschedule_appointment")
    print("=" * 60)

    # Test rescheduling
    print("\n1. Testing rescheduling:")
    result = reschedule_appointment(
        original_datetime='2024-01-15T10:00:00+00:00',
        new_datetime_start='2024-01-15T16:00:00+00:00',
        new_datetime_end='2024-01-15T17:00:00+00:00',
        reason="Conflict with another meeting",
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

def test_cancel_appointment():
    print("\n" + "=" * 60)
    print("Testing cancel_appointment")
    print("=" * 60)

    # Test cancellation
    print("\n1. Testing cancellation:")
    result = cancel_appointment(
        datetime_start='2024-01-15T10:00:00+00:00',
        reason="No longer needed",
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

    # Test cancellation with string datetime
    print("\n2. Testing cancellation with string datetime:")
    result = cancel_appointment(
        datetime_start='2024-01-15T10:00:00+00:00',
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

def test_get_appointment_details():
    print("\n" + "=" * 60)
    print("Testing get_appointment_details")
    print("=" * 60)

    # Test getting appointment details
    print("\n1. Testing appointment details:")
    result = get_appointment_details(
        datetime_start='2024-01-15T00:00:00+00:00',
        datetime_end='2024-01-15T23:59:59+00:00',
        user_id=1
    )
    print(f"Result: {json.dumps(result, indent=2)}")

def test_generate_alternative_slots():
    print("\n" + "=" * 60)
    print("Testing generate_alternative_slots")
    print("=" * 60)

    # Mock calendar service
    calendar_service = MockGoogleCalendarService(1)

    # Test generating alternatives
    print("\n1. Testing alternative slot generation:")
    original_start = datetime(2024, 1, 15, 10, 30)
    original_end = datetime(2024, 1, 15, 11, 30)

    alternatives = generate_alternative_slots(original_start, original_end, calendar_service)
    print(f"Alternatives: {json.dumps(alternatives, indent=2, default=str)}")

def test_function_map():
    print("\n" + "=" * 60)
    print("Testing FUNCTION_MAP direct calls")
    print("=" * 60)

    # Test each function through FUNCTION_MAP
    test_cases = [
        {
            'name': 'check_calendar_availability',
            'args': {
                'datetime_start': '2024-01-15T09:00:00+00:00',
                'datetime_end': '2024-01-15T10:00:00+00:00',
                'user_id': 1
            }
        },
        {
            'name': 'create_calendar_event',
            'args': {
                'summary': 'FUNCTION_MAP Test',
                'datetime_start': '2024-01-16T14:00:00+00:00',
                'datetime_end': '2024-01-16T15:00:00+00:00',
                'user_id': 1
            }
        }
    ]

    for test_case in test_cases:
        print(f"\nTesting {test_case['name']}:")
        try:
            result = FUNCTION_MAP[test_case['name']](**test_case['args'])
            print(f"Result: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")

def test_error_cases():
    print("\n" + "=" * 60)
    print("Testing Error Cases")
    print("=" * 60)

    # Test invalid datetime format
    print("\n1. Testing invalid datetime format:")
    try:
        result = check_calendar_availability(
            datetime_start='invalid-date',
            datetime_end='invalid-date',
            user_id=1
        )
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Expected error: {e}")

    # Test without required parameters
    print("\n2. Testing without required parameters:")
    try:
        result = create_calendar_event(
            summary="Test",
            user_id=1
        )
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Expected error: {e}")

if __name__ == "__main__":
    print("Starting Calendar Functions Test Suite")
    print("=" * 60)

    # Run all tests
    test_check_calendar_availability()
    test_create_calendar_event()
    test_reschedule_appointment()
    test_cancel_appointment()
    test_get_appointment_details()
    test_generate_alternative_slots()
    test_function_map()
    test_error_cases()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
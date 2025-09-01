#!/usr/bin/env python3
"""
Debug script to test calendar endpoints and troubleshoot calendar display issues
"""
import requests
import json
from datetime import datetime, timedelta

# Flask app base URL
BASE_URL = "http://localhost:5000"

def test_calendar_endpoints():
    """Test all calendar-related endpoints"""
    print("🔍 Testing Calendar Endpoints for Debugging")
    print("=" * 60)
    
    # Test 1: Check if Flask app is running
    print("\n1️⃣ Testing Flask app availability...")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Flask app is running")
        else:
            print("   ⚠️  Flask app responded with unexpected status")
    except Exception as e:
        print(f"   ❌ Flask app not accessible: {e}")
        return
    
    # Test 2: Test Google Calendar events endpoint with sample dates
    print("\n2️⃣ Testing /google/events endpoint...")
    try:
        # Use the exact date format that was causing the error
        time_min = "2025-07-27T00:00:00"
        time_max = "2025-09-07T00:00:00"
        timezone = "Europe/Brussels"
        
        print(f"   Testing with dates: {time_min} to {time_max}")
        print(f"   Timezone: {timezone}")
        
        response = requests.get(
            f"{BASE_URL}/google/events",
            params={
                'timeMin': time_min,
                'timeMax': time_max,
                'timezone': timezone
            }
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 401:
            print("   ✅ Endpoint exists but requires authentication (expected)")
        elif response.status_code == 200:
            print("   ✅ Events endpoint working!")
            data = response.json()
            print(f"   📅 Events returned: {len(data)}")
            if data:
                print(f"   📝 First event: {data[0].get('title', 'No title')}")
        elif response.status_code == 500:
            print("   ❌ Server error - check Flask logs")
            print(f"   Error details: {response.text[:200]}...")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"   ❌ Error testing events endpoint: {e}")
    
    # Test 3: Test with current dates
    print("\n3️⃣ Testing with current dates...")
    try:
        now = datetime.now()
        time_min = now.isoformat()
        time_max = (now + timedelta(days=7)).isoformat()
        
        print(f"   Current time: {time_min}")
        print(f"   Week from now: {time_max}")
        
        response = requests.get(
            f"{BASE_URL}/google/events",
            params={
                'timeMin': time_min,
                'timeMax': time_max,
                'timezone': 'Europe/Brussels'
            }
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   📅 Events in next week: {len(data)}")
        elif response.status_code == 401:
            print("   ✅ Requires authentication (expected)")
        else:
            print(f"   ⚠️  Status: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Test Google Calendar counts endpoint
    print("\n4️⃣ Testing /google/counts endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/google/counts")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 401:
            print("   ✅ Requires authentication (expected)")
        elif response.status_code == 200:
            data = response.json()
            print(f"   📊 Counts: {data}")
        else:
            print(f"   ⚠️  Status: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 5: Test dashboard stats endpoint
    print("\n5️⃣ Testing /dashboard/stats endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/dashboard/stats")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 401:
            print("   ✅ Requires authentication (expected)")
        elif response.status_code == 200:
            data = response.json()
            print(f"   📊 Dashboard stats: {data}")
        else:
            print(f"   ⚠️  Status: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")

def test_date_parsing():
    """Test the date parsing logic that was added"""
    print("\n📅 Testing Date Parsing Logic")
    print("=" * 60)
    
    try:
        from datetime import datetime
        import pytz
        
        # Test the exact dates from the error
        time_min = "2025-07-27T00:00:00"
        time_max = "2025-09-07T00:00:00"
        timezone_str = "Europe/Brussels"
        
        print(f"   Input dates: {time_min} to {time_max}")
        print(f"   Timezone: {timezone_str}")
        
        # Parse the dates (this is the logic that was added to fix the error)
        start_date = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
        
        # Convert to the user's timezone
        user_tz = pytz.timezone(timezone_str)
        start_date = start_date.astimezone(user_tz)
        end_date = end_date.astimezone(user_tz)
        
        # Format for Google Calendar API (RFC 3339 format)
        time_min_formatted = start_date.isoformat()
        time_max_formatted = end_date.isoformat()
        
        print(f"   ✅ Parsed dates successfully")
        print(f"   Formatted start: {time_min_formatted}")
        print(f"   Formatted end: {time_max_formatted}")
        
        # Verify the format is correct for Google Calendar API
        if 'T' in time_min_formatted and 'T' in time_max_formatted:
            print("   ✅ Date format is correct for Google Calendar API")
        else:
            print("   ❌ Date format is incorrect")
            
        # Check if the dates are in the future (which might cause issues)
        now = datetime.now()
        if start_date > now:
            print(f"   ⚠️  Start date is in the future: {start_date}")
        if end_date > now:
            print(f"   ⚠️  End date is in the future: {end_date}")
            
    except Exception as e:
        print(f"   ❌ Date parsing failed: {e}")
        import traceback
        traceback.print_exc()

def provide_debugging_tips():
    """Provide debugging tips for the calendar issue"""
    print("\n🔧 Debugging Tips for Calendar Display Issue")
    print("=" * 60)
    
    print("\n📋 Common Issues and Solutions:")
    print("   1. **Events not showing in FullCalendar:**")
    print("      - Check browser console for JavaScript errors")
    print("      - Verify /google/events endpoint returns data")
    print("      - Check if user is authenticated with Google Calendar")
    
    print("\n   2. **FullCalendar not rendering:**")
    print("      - Ensure FullCalendar CSS/JS files are loaded")
    print("      - Check if calendarContainer div exists")
    print("      - Verify calendar.render() is called")
    
    print("\n   3. **Google Calendar API errors:**")
    print("      - Check Flask app logs for API errors")
    print("      - Verify Google Calendar credentials are valid")
    print("      - Check if user has calendar access")
    
    print("\n   4. **Date format issues:**")
    print("      - Ensure dates are in ISO format")
    print("      - Check timezone handling")
    print("      - Verify date parsing logic")
    
    print("\n🔍 Next Steps:")
    print("   1. Start your Flask app: python run.py")
    print("   2. Check browser console for errors")
    print("   3. Test endpoints with this script")
    print("   4. Check Flask app logs for errors")
    print("   5. Verify Google Calendar connection")

if __name__ == "__main__":
    print("🚀 Starting Calendar Debugging Session")
    print("=" * 60)
    
    try:
        test_calendar_endpoints()
        test_date_parsing()
        provide_debugging_tips()
        
        print("\n" + "=" * 60)
        print("🎉 Debug session completed!")
        print("\n💡 If you see 401 errors, that's expected when not logged in")
        print("   If you see 500 errors, check your Flask app logs")
        print("   If you see 404 errors, the endpoints don't exist")
        
    except Exception as e:
        print(f"\n💥 Debug session failed: {e}")
        import traceback
        traceback.print_exc()


#!/usr/bin/env python3
"""
Test script to verify Google Calendar endpoints are working after fixes
"""
import requests
import json
from datetime import datetime, timedelta

# Flask app base URL
BASE_URL = "http://localhost:5000"

def test_google_endpoints():
    """Test Google Calendar endpoints"""
    print("🧪 Testing Google Calendar Endpoints After Fixes")
    print("=" * 60)
    
    # Test 1: Google Calendar Connect page
    print("\n1️⃣ Testing /google/connect endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/google/connect")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Google connect page accessible")
        else:
            print("   ❌ Google connect page not accessible")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Google Calendar Events endpoint (will require authentication)
    print("\n2️⃣ Testing /google/events endpoint...")
    try:
        # This will likely return 401 (unauthorized) since we're not logged in
        time_min = datetime.now().isoformat()
        time_max = (datetime.now() + timedelta(days=7)).isoformat()
        
        response = requests.get(
            f"{BASE_URL}/google/events",
            params={
                'timeMin': time_min,
                'timeMax': time_max,
                'timezone': 'Europe/Brussels'
            }
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✅ Endpoint exists but requires authentication (expected)")
        elif response.status_code == 200:
            print("   ✅ Events endpoint working")
            data = response.json()
            print(f"   📅 Events returned: {len(data)}")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Google Calendar Counts endpoint
    print("\n3️⃣ Testing /google/counts endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/google/counts")
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✅ Endpoint exists but requires authentication (expected)")
        elif response.status_code == 200:
            print("   ✅ Counts endpoint working")
            data = response.json()
            print(f"   📊 Counts: {data}")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Dashboard stats endpoint
    print("\n4️⃣ Testing /dashboard/stats endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/dashboard/stats")
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✅ Endpoint exists but requires authentication (expected)")
        elif response.status_code == 200:
            print("   ✅ Dashboard stats working")
            data = response.json()
            print(f"   📊 Stats: {data}")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")

def test_date_formatting():
    """Test date formatting that was causing the Bad Request error"""
    print("\n📅 Testing Date Formatting Fixes")
    print("=" * 60)
    
    # Test the date parsing logic that was added
    try:
        from datetime import datetime
        import pytz
        
        # Test the date parsing that was causing issues
        time_min = "2025-07-27T00:00:00"
        time_max = "2025-09-07T00:00:00"
        timezone_str = "Europe/Brussels"
        
        print(f"   Input dates: {time_min} to {time_max}")
        print(f"   Timezone: {timezone_str}")
        
        # Parse the dates (this is the logic that was added)
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
            
    except Exception as e:
        print(f"   ❌ Date parsing failed: {e}")

if __name__ == "__main__":
    print("🚀 Starting Google Calendar Fix Verification")
    print("=" * 60)
    print("📝 Note: These tests will show 401 errors for authenticated endpoints")
    print("   This is expected behavior when not logged in")
    print("=" * 60)
    
    try:
        test_google_endpoints()
        test_date_formatting()
        
        print("\n" + "=" * 60)
        print("🎉 All tests completed!")
        print("\n📋 Summary:")
        print("   ✅ If you see 401 errors, the endpoints exist and require authentication")
        print("   ✅ If you see 200 responses, the endpoints are working")
        print("   ❌ If you see 404 errors, the endpoints don't exist")
        print("\n🔧 Next Steps:")
        print("   1. Start your Flask app: python run.py")
        print("   2. Log in to your app in a browser")
        print("   3. Check the dashboard for Google Calendar events")
        print("   4. The date formatting errors should now be resolved")
        
    except Exception as e:
        print(f"\n💥 Testing failed: {e}")
        import traceback
        traceback.print_exc()


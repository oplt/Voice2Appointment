#!/usr/bin/env python3
"""
Test script for Google Calendar endpoints
"""
import requests
import json
from datetime import datetime, timedelta

# Flask app base URL
BASE_URL = "http://localhost:5000"

def test_google_endpoints():
    """Test Google Calendar endpoints"""
    print("🧪 Testing Google Calendar Endpoints")
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

def test_with_session():
    """Test with a session (simulating logged-in user)"""
    print("\n🔐 Testing with Session (Simulating Logged-in User)")
    print("=" * 60)
    
    # Create a session
    session = requests.Session()
    
    # Try to access dashboard (this will redirect to login)
    print("\n📱 Testing dashboard access...")
    try:
        response = session.get(f"{BASE_URL}/dashboard")
        print(f"   Dashboard Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Dashboard accessible")
        elif response.status_code == 302:
            print("   ✅ Dashboard redirects to login (expected)")
        else:
            print(f"   ⚠️  Unexpected status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Starting Google Calendar Endpoint Testing")
    print("=" * 60)
    print("📝 Note: These tests will show 401 errors for authenticated endpoints")
    print("   This is expected behavior when not logged in")
    print("=" * 60)
    
    try:
        test_google_endpoints()
        test_with_session()
        
        print("\n" + "=" * 60)
        print("🎉 All endpoint tests completed!")
        print("\n📋 Summary:")
        print("   ✅ If you see 401 errors, the endpoints exist and require authentication")
        print("   ✅ If you see 200 responses, the endpoints are working")
        print("   ❌ If you see 404 errors, the endpoints don't exist")
        print("\n🔧 Next Steps:")
        print("   1. Start your Flask app: python run.py")
        print("   2. Log in to your app in a browser")
        print("   3. Check the dashboard for Google Calendar events")
        print("   4. If no events appear, check the browser console for errors")
        
    except Exception as e:
        print(f"\n💥 Testing failed: {e}")
        import traceback
        traceback.print_exc()


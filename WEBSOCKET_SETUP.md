# WebSocket Integration with User Authentication

This document explains how the WebSocket system has been integrated with user authentication to pass `current_user.id` from Flask to the `functions_map.py` for instantiating `GoogleCalendarService`.

## Architecture Overview

```
Flask App (Port 5000) → WebSocket Server (Port 5001) → functions_map.py → GoogleCalendarService
     ↓
current_user.id → /phone/websocket → ws://localhost:5001/ws/{user_id} → user_id parameter
```

## How It Works

### 1. User Authentication Flow
- User logs into Flask app
- Dashboard loads and calls `/phone/websocket` endpoint
- Flask route returns user's WebSocket connection URL with their user ID
- JavaScript connects to `ws://localhost:5001/ws/{user_id}`

### 2. WebSocket Connection
- WebSocket server extracts user_id from the URL path
- Passes user_id to `twilio_handler` function
- All function calls now include the user_id parameter

### 3. Function Execution
- When a function is called, `execute_function_call` adds user_id to the arguments
- `GoogleCalendarService` is instantiated with the correct user_id
- Calendar operations are performed for the authenticated user

## Files Modified

### 1. `flaskapp/utils/functions_map.py`
- All calendar functions now accept `user_id` as first parameter
- `GoogleCalendarService(user_id)` is called with the authenticated user's ID
- Removed undefined `DEFAULT_USER_ID` variable

### 2. `flaskapp/utils/websocket_handler.py`
- Modified to accept and store `user_id` parameter
- `execute_function_call` automatically adds user_id to calendar function calls
- All handler functions propagate user_id through the call chain

### 3. `run.py`
- Added WebSocket server with user authentication
- Extracts user_id from WebSocket URL path (`/ws/{user_id}`)
- Routes connections to appropriate handlers

### 4. `flaskapp/phone/routes.py`
- Added `/phone/websocket` endpoint for authenticated users
- Returns WebSocket connection information with user_id

### 5. `flaskapp/static/js/dashboard.js`
- Added WebSocket connection logic
- Automatically connects when dashboard loads
- Shows connection status and handles reconnection

### 6. `flaskapp/templates/dashboard.html`
- Added WebSocket status indicator
- Added results display area for voice assistant responses

## Usage

### 1. Start the Application
```bash
python run.py
```

This starts:
- Flask app on port 5000
- WebSocket server on port 5001

### 2. User Login
- User logs into Flask app
- Dashboard automatically establishes WebSocket connection

### 3. Voice Assistant Functions
All calendar functions now work with the authenticated user:
- `check_calendar_availability(user_id, ...)`
- `create_calendar_event(user_id, ...)`
- `reschedule_appointment(user_id, ...)`
- `cancel_appointment(user_id, ...)`
- `get_appointment_details(user_id, ...)`

### 4. Testing
Use the test script to verify WebSocket connections:
```bash
python test_websocket.py
```

## Security Features

1. **Authentication Required**: `/phone/websocket` endpoint requires user login
2. **User Isolation**: Each WebSocket connection is tied to a specific user
3. **Path Validation**: WebSocket server validates user_id format
4. **Session Management**: Uses Flask-Login for user authentication

## Troubleshooting

### WebSocket Connection Issues
1. Check if WebSocket server is running on port 5001
2. Verify user is authenticated in Flask app
3. Check browser console for connection errors
4. Ensure firewall allows WebSocket connections

### Function Call Issues
1. Verify user_id is being passed correctly
2. Check if user has Google Calendar authentication set up
3. Review logs for authentication errors

### Port Conflicts
- Flask app: Port 5000
- WebSocket server: Port 5001
- Ensure both ports are available

## Future Enhancements

1. **Real-time Updates**: Push calendar changes to connected clients
2. **Multi-user Support**: Handle multiple simultaneous connections
3. **Connection Pooling**: Manage WebSocket connections efficiently
4. **Error Recovery**: Implement robust reconnection logic
5. **Message Queuing**: Handle messages when user is offline

## API Reference

### WebSocket Endpoint
- **URL**: `ws://localhost:5001/ws/{user_id}`
- **Authentication**: User must be logged into Flask app
- **Protocol**: WebSocket

### Flask Endpoint
- **URL**: `/phone/websocket`
- **Method**: GET
- **Authentication**: Required (login_required)
- **Response**: JSON with WebSocket connection details

### Function Parameters
All calendar functions now require `user_id` as the first parameter:
```python
def check_calendar_availability(user_id, datetime_start, datetime_end):
    calendar_service = GoogleCalendarService(user_id)
    # ... rest of function
```


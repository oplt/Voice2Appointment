from flask import Blueprint, request, jsonify, Response
from flask_login import login_required
import logging
from flaskapp.database.models import CallSession, Appointment
# from flaskapp.utils.websocket_handler import WebSocketHandler
import asyncio
import json

# Create phone blueprint
phone_bp = Blueprint('phone', __name__, url_prefix='/phone')

@phone_bp.route('/twilio', methods=['GET'])
def twilio_info():
    """Provide information about available Twilio endpoints"""
    return jsonify({
        'message': 'Voice Assistant Twilio Integration',
        'status': 'active',
        'available_endpoints': {
            'webhook': {
                'url': '/phone/webhook',
                'method': 'POST',
                'description': 'Handle incoming Twilio calls',
                'parameters': ['CallSid', 'From', 'To', 'CallStatus']
            },
            'gather': {
                'url': '/phone/gather',
                'method': 'POST',
                'description': 'Process speech input from calls',
                'parameters': ['CallSid', 'SpeechResult', 'From', 'To']
            },
            'check_availability': {
                'url': '/phone/check_availability',
                'method': 'POST',
                'description': 'Check calendar availability',
                'parameters': ['CallSid']
            },
            'confirm_appointment': {
                'url': '/phone/confirm_appointment',
                'method': 'POST',
                'description': 'Confirm appointment scheduling',
                'parameters': ['CallSid', 'Digits']
            },
            'status': {
                'url': '/phone/status',
                'method': 'POST',
                'description': 'Handle call status updates',
                'parameters': ['CallSid', 'CallStatus', 'CallDuration']
            },
            'stream': {
                'url': '/phone/stream/<call_sid>',
                'method': 'GET',
                'description': 'WebSocket endpoint for real-time audio',
                'parameters': ['call_sid (in URL)']
            }
        },
        'websocket_server': {
            'port': 5000,
            'status': 'running',
            'description': 'Real-time audio streaming with Deepgram',
            'connection_url': 'wss://0c4283781de3.ngrok-free.app:5000'
        },
        'testing': {
            'webhook_test': 'curl -X POST /phone/webhook -d "CallSid=test123&CallStatus=ringing"',
            'gather_test': 'curl -X POST /phone/gather -d "CallSid=test123&SpeechResult=test"'
        },
        'twillo_bin_setup': {
            'correct_url': 'wss://0c4283781de3.ngrok-free.app:5000',
            'current_url': 'wss://0c4283781de3.ngrok-free.app/twilio',
            'note': 'Remove /twilio path and use port 5000 directly'
        }
    })

@phone_bp.route('/test_websocket', methods=['GET'])
def test_websocket():
    """Test WebSocket server connectivity"""
    return jsonify({
        'message': 'WebSocket Test Endpoint',
        'websocket_server': {
            'port': 5000,
            'status': 'should be running',
            'connection_test': 'Use a WebSocket client to connect to ws://localhost:5000'
        },
        'twilio_stream': {
            'correct_url': 'wss://0c4283781de3.ngrok-free.app:5000',
            'note': 'This should connect to your WebSocket server'
        },
        'testing': {
            'websocket_test': 'Use a WebSocket client to test ws://localhost:5000',
            'twilio_test': 'Call your Twilio number to test the Stream connection'
        }
    })

@phone_bp.route('/webhook', methods=['POST'])
def webhook():
    """Handle Twilio webhook requests for incoming calls"""
    try:
        call_sid = request.form.get('CallSid')
        from_number = request.form.get('From')
        to_number = request.form.get('To')
        call_status = request.form.get('CallStatus')

        logging.info(f"Twilio webhook received: CallSid={call_sid}, From={from_number}, To={to_number}, Status={call_status}")

        if call_status == 'ringing':
            # Call is ringing, start the appointment scheduling flow
            response = f'''<?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Gather input="speech" action="/phone/gather" method="POST" speechTimeout="auto" language="en-US">
                        <Say>Welcome to our appointment scheduling service. Please tell me when you'd like to schedule an appointment.</Say>
                    </Gather>
                </Response>'''
        else:
            # Handle other call statuses
            response = f'''<?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Say>Thank you for calling. Goodbye.</Say>
                </Response>'''

        return response, 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        logging.error(f"Error in webhook: {e}")
        return str(e), 500

@phone_bp.route('/gather', methods=['POST'])
def gather():
    """Handle speech input from user"""
    try:
        speech_result = request.form.get('SpeechResult', '')
        call_sid = request.form.get('CallSid')
        from_number = request.form.get('From')
        to_number = request.form.get('To')

        logging.info(f"Speech input received: {speech_result}")

        # Create or get call session
        session = CallSession.query.filter_by(call_sid=call_sid).first()
        if not session:
            session = CallSession.create(
                call_sid=call_sid,
                from_number=from_number,
                to_number=to_number,
                data={'speech_input': speech_result}
            )

        # For now, provide a simple response
        # In a real implementation, you'd process the speech and check calendar availability
        response = f'''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>I heard you say: {speech_result}. I'm processing your appointment request.</Say>
                <Pause length="1"/>
                <Say>Please wait while I check our calendar availability.</Say>
                <Redirect>/phone/check_availability</Redirect>
            </Response>'''

        return response, 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        logging.error(f"Error in gather: {e}")
        return str(e), 500

@phone_bp.route('/check_availability', methods=['POST'])
def check_availability():
    """Check calendar availability and provide options"""
    try:
        call_sid = request.form.get('CallSid')
        
        # In a real implementation, you'd:
        # 1. Parse the speech input for date/time
        # 2. Check Google Calendar availability
        # 3. Provide available time slots
        
        response = f'''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>I'm checking our calendar for available time slots.</Say>
                <Pause length="2"/>
                <Say>Based on your request, I found some available times. Please confirm if you'd like to proceed.</Say>
                <Gather input="dtmf" action="/phone/confirm_appointment" method="POST" numDigits="1">
                    <Say>Press 1 to confirm the appointment, or 2 to choose a different time.</Say>
                </Gather>
            </Response>'''

        return response, 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        logging.error(f"Error in check_availability: {e}")
        return str(e), 500

@phone_bp.route('/confirm_appointment', methods=['POST'])
def confirm_appointment():
    """Handle appointment confirmation"""
    try:
        digits = request.form.get('Digits', '')
        call_sid = request.form.get('CallSid')
        
        if digits == '1':
            # User confirmed appointment
            response = f'''<?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Say>Great! I've confirmed your appointment. You'll receive a confirmation email shortly.</Say>
                    <Pause length="1"/>
                    <Say>Thank you for using our appointment scheduling service. Goodbye!</Say>
                    <Hangup/>
                </Response>'''
        else:
            # User wants different time
            response = f'''<?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Say>No problem. Let me help you find another available time.</Say>
                    <Redirect>/phone/check_availability</Redirect>
                </Response>'''

        return response, 200, {'Content-Type': 'text/xml'}

    except Exception as e:
        logging.error(f"Error in confirm_appointment: {e}")
        return str(e), 500

@phone_bp.route('/stream/<call_sid>', methods=['GET'])
def stream_endpoint(call_sid):
    """WebSocket endpoint for real-time audio streaming"""
    # This endpoint would handle WebSocket upgrade
    # For now, return a simple response
    return jsonify({
        'status': 'WebSocket endpoint',
        'call_sid': call_sid,
        'message': 'This endpoint should handle WebSocket connections for real-time audio processing'
    })

@phone_bp.route('/status', methods=['POST'])
def call_status():
    """Handle call status updates from Twilio"""
    try:
        call_sid = request.form.get('CallSid')
        call_status = request.form.get('CallStatus')
        call_duration = request.form.get('CallDuration')
        
        logging.info(f"Call status update: {call_sid} - {call_status} (Duration: {call_duration}s)")
        
        # Update call session if needed
        session = CallSession.query.filter_by(call_sid=call_sid).first()
        if session:
            session.data = session.data or {}
            session.data['call_status'] = call_status
            session.data['call_duration'] = call_duration
            session.data['ended_at'] = request.form.to_dict()
            
            from flaskapp import db
            db.session.commit()
        
        return '', 200
        
    except Exception as e:
        logging.error(f"Error in call_status: {e}")
        return str(e), 500
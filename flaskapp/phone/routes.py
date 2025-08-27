from flask import Blueprint, request, Response, jsonify
from .twilio_handler import TwilioPhoneHandler
from .plivo_handler import PlivoPhoneHandler
from .telnyx_handler import TelnyxPhoneHandler
from . import phone_logger
from flask_login import current_user, login_required

# Use centralized phone logger
logger = phone_logger

# Create phone blueprint
phone = Blueprint('phone', __name__)

# Initialize phone handlers
logger.info("Phone routes initialized with both Twilio and Plivo handlers")

@phone.route('/incoming-call', methods=['POST'])
def incoming_call():
    """Handle incoming phone call from Twilio"""
    try:
        # Get call details from Twilio
        call_sid = request.form.get('CallSid')
        from_number = request.form.get('From')
        
        if not call_sid or not from_number:
            logger.error("Missing required call parameters")
            return Response("Error: Missing parameters", status=400)
        
        logger.info(f"Received incoming call from {from_number}")
        
        # Generate TwiML response
        phone_handler = TwilioPhoneHandler()
        twiml_response = phone_handler.handle_incoming_call(call_sid, from_number)
        
        # Return TwiML response
        return Response(twiml_response, mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error handling incoming call: {str(e)}", exc_info=True)
        return Response("Error processing call", status=500)

@phone.route('/process-voice/<call_sid>', methods=['POST'])
def process_voice(call_sid):
    """Process recorded voice input from caller"""
    try:
        # Get audio recording URL from Twilio
        recording_url = request.form.get('RecordingUrl')
        
        if not recording_url:
            logger.error(f"No recording URL provided for call {call_sid}")
            return Response("Error: No recording", status=400)
        
        logger.info(f"Processing voice input for call {call_sid}")
        
        # Process the voice input
        phone_handler = TwilioPhoneHandler()
        twiml_response = phone_handler.process_voice_input(call_sid, recording_url)
        
        # Return TwiML response
        return Response(twiml_response, mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error processing voice input: {str(e)}", exc_info=True)
        return Response("Error processing voice", status=500)

@phone.route('/call-status/<call_sid>', methods=['GET'])
def get_call_status(call_sid):
    """Get current status of a call"""
    try:
        phone_handler = TwilioPhoneHandler()
        status = phone_handler.get_call_status(call_sid)
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Call not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting call status: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal error'}), 500

@phone.route('/end-call/<call_sid>', methods=['POST'])
def end_call(call_sid):
    """End a call manually"""
    try:
        phone_handler = TwilioPhoneHandler()
        phone_handler.end_call(call_sid)
        return jsonify({'message': 'Call ended successfully'})
        
    except Exception as e:
        logger.error(f"Error ending call: {str(e)}", exc_info=True)
        return jsonify({'error': 'Error ending call'}), 500

@phone.route('/test-phone', methods=['GET'])
@login_required
def test_phone():
    """Test endpoint to verify phone integration is working"""
    logger.info("Phone integration test endpoint called")
    logger.debug("Testing phone handler configuration")
    phone_handler = TwilioPhoneHandler()
    
    test_result = {
        'status': 'Phone integration is working',
        'twilio_configured': bool(phone_handler.client),
        'phone_number': phone_handler.phone_number,
        'logging_configured': True
    }
    
    logger.info(f"Phone test result: {test_result}")
    return jsonify(test_result)


@phone.route('/telnyx/incoming-call', methods=['POST'])
def telnyx_incoming_call():
    """Handle incoming phone call from Telnyx (TeXML)."""
    try:
        session_id = request.form.get('CallSessionId') or request.form.get('session_id') or 'unknown'
        from_number = request.form.get('From') or request.form.get('from')
        if not from_number:
            logger.error("Missing Telnyx from number")
            return Response("Bad Request", status=400)
        handler = TelnyxPhoneHandler()
        xml = handler.handle_incoming_call(session_id, from_number)
        return Response(xml, mimetype='text/xml')
    except Exception as e:
        logger.error(f"Error handling Telnyx incoming call: {str(e)}", exc_info=True)
        return Response("Error", status=500)


@phone.route('/telnyx/process-voice/<session_id>', methods=['POST'])
def telnyx_process_voice(session_id: str):
    try:
        recording_url = request.form.get('RecordUrl') or request.form.get('recording_url') or request.form.get('record_url')
        if not recording_url:
            logger.error(f"No Telnyx recording URL for session {session_id}")
            return Response("Bad Request", status=400)
        handler = TelnyxPhoneHandler()
        xml = handler.process_voice_input(session_id, recording_url)
        return Response(xml, mimetype='text/xml')
    except Exception as e:
        logger.error(f"Error processing Telnyx voice: {str(e)}", exc_info=True)
        return Response("Error", status=500)


@phone.route('/plivo/incoming-call', methods=['POST'])
def plivo_incoming_call():
    """Handle incoming phone call from Plivo"""
    try:
        # Get call details from Plivo
        call_uuid = request.form.get('CallUUID')
        from_number = request.form.get('From')
        
        if not call_uuid or not from_number:
            logger.error("Missing required Plivo call parameters")
            return Response("Error: Missing parameters", status=400)
        
        logger.info(f"Received Plivo incoming call from {from_number}")
        
        # Generate Plivo XML response
        phone_handler = PlivoPhoneHandler()
        plivo_response = phone_handler.handle_incoming_call(call_uuid, from_number)
        
        # Return Plivo XML response
        return Response(plivo_response, mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error handling Plivo incoming call: {str(e)}", exc_info=True)
        return Response("Error processing Plivo call", status=500)


@phone.route('/plivo/process-voice/<call_uuid>', methods=['POST'])
def plivo_process_voice(call_uuid):
    """Process recorded voice input from Plivo caller"""
    try:
        # Get audio recording URL from Plivo
        recording_url = request.form.get('RecordFile')
        
        if not recording_url:
            logger.error(f"No recording URL provided for Plivo call {call_uuid}")
            return Response("Error: No recording", status=400)
        
        logger.info(f"Processing Plivo voice input for call {call_uuid}")
        
        # Process the voice input
        phone_handler = PlivoPhoneHandler()
        plivo_response = phone_handler.process_voice_input(call_uuid, recording_url)
        
        # Return Plivo XML response
        return Response(plivo_response, mimetype='text/xml')
        
    except Exception as e:
        logger.error(f"Error processing Plivo voice input: {str(e)}", exc_info=True)
        return Response("Error processing Plivo voice", status=500)


@phone.route('/plivo/call-status/<call_uuid>', methods=['GET'])
def get_plivo_call_status(call_uuid):
    """Get current status of a Plivo call"""
    try:
        phone_handler = PlivoPhoneHandler()
        status = phone_handler.get_call_status(call_uuid)
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Plivo call not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting Plivo call status: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@phone.route('/plivo/end-call/<call_uuid>', methods=['POST'])
def end_plivo_call(call_uuid):
    """End a Plivo call manually"""
    try:
        phone_handler = PlivoPhoneHandler()
        phone_handler.end_call(call_uuid)
        return jsonify({'message': 'Plivo call ended successfully'})
        
    except Exception as e:
        logger.error(f"Error ending Plivo call: {str(e)}", exc_info=True)
        return jsonify({'error': 'Error ending Plivo call'}), 500


@phone.route('/test-plivo', methods=['GET'])
@login_required
def test_plivo():
    """Test endpoint to verify Plivo integration is working"""
    logger.info("Plivo integration test endpoint called")
    logger.debug("Testing Plivo handler configuration")
    
    test_result = {
        'status': 'Plivo integration is working',
        'plivo_configured': bool(plivo_handler.auth_id and plivo_handler.auth_token),
        'phone_number': plivo_handler.phone_number,
        'logging_configured': True
    }
    
    logger.info(f"Plivo test result: {test_result}")
    return jsonify(test_result)


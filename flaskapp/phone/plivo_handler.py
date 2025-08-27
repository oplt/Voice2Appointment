import os
import logging
from typing import Dict, Any, Optional
from plivo import plivoxml
from plivo.utils import validate_signature
from datetime import datetime
import json
from .ai_integration import AIVoiceIntegration

# Setup logger
logger = logging.getLogger(__name__)

class PlivoPhoneHandler:
    """Handles incoming phone calls and voice interactions via Plivo"""
    
    def __init__(self):
        # Plivo credentials from environment variables
        self.auth_id = os.getenv('PLIVO_AUTH_ID')
        self.auth_token = os.getenv('PLIVO_AUTH_TOKEN')
        self.phone_number = os.getenv('PLIVO_PHONE_NUMBER')
        
        if not all([self.auth_id, self.auth_token, self.phone_number]):
            logger.warning("Plivo credentials not fully configured")
        
        # Initialize AI integration
        self.ai_integration = AIVoiceIntegration()
        
        # Call session storage (in production, use Redis or database)
        self.call_sessions = {}
        
        logger.info(f"PlivoPhoneHandler initialized - Auth ID: {self.auth_id[:8] if self.auth_id else 'None'}..., Phone: {self.phone_number}")
    
    def handle_incoming_call(self, call_uuid: str, from_number: str) -> str:
        """Handle incoming call and return Plivo XML response"""
        try:
            logger.info(f"Incoming call from {from_number}, UUID: {call_uuid}")
            
            # Initialize call session
            self.call_sessions[call_uuid] = {
                'from_number': from_number,
                'start_time': datetime.now(),
                'step': 'greeting',
                'appointment_date': None,
                'preferred_time': None
            }
            
            # Create Plivo XML response
            response = plivoxml.ResponseElement()
            
            # Welcome message
            response.add(plivoxml.SpeechElement("Welcome to the Voice Assistant Appointment Scheduler. I'll help you schedule an appointment."))
            response.add(plivoxml.SpeechElement("Please tell me when you'd like to schedule your appointment. You can say something like 'I need an appointment on March 15th at 2 PM'."))
            
            # Record user's response
            response.add(plivoxml.RecordElement(
                action=f'/phone/process-voice/{call_uuid}',
                method='POST',
                maxLength='30',
                playBeep=False,
                trim='trim-silence'
            ))
            
            # If no input, redirect to main menu
            response.add(plivoxml.RedirectElement(f'/phone/process-voice/{call_uuid}'))
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error handling incoming call: {str(e)}", exc_info=True)
            return self._create_error_response()
    
    def process_voice_input(self, call_uuid: str, audio_url: str) -> str:
        """Process recorded voice input and respond accordingly"""
        try:
            if call_uuid not in self.call_sessions:
                logger.error(f"Call session not found for UUID: {call_uuid}")
                return self._create_error_response()
            
            session = self.call_sessions[call_uuid]
            logger.info(f"Processing voice input for call {call_uuid}, step: {session['step']}")
            
            # Process voice with AI integration
            ai_result = self.ai_integration.process_voice_request(audio_url, call_uuid)
            
            # Generate appropriate voice response
            voice_response = self.ai_integration.generate_voice_response(ai_result, session)
            
            # Create Plivo XML response
            response = plivoxml.ResponseElement()
            
            if session['step'] == 'greeting':
                # Process appointment request
                response.add(plivoxml.SpeechElement(voice_response))
                
                # If appointment was scheduled successfully, end call
                if "scheduled" in voice_response.lower() and "thank you" in voice_response.lower():
                    response.add(plivoxml.SpeechElement("Goodbye!"))
                    response.add(plivoxml.HangupElement())
                elif "not available" in voice_response.lower():
                    # Ask for alternative time
                    response.add(plivoxml.SpeechElement("Please suggest another time slot."))
                    response.add(plivoxml.RecordElement(
                        action=f'/phone/process-voice/{call_uuid}',
                        method='POST',
                        maxLength='30',
                        playBeep=False,
                        trim='trim-silence'
                    ))
                    session['step'] = 'alternative_time'
                else:
                    # End call for other responses
                    response.add(plivoxml.SpeechElement("Goodbye!"))
                    response.add(plivoxml.HangupElement())
            
            elif session['step'] == 'alternative_time':
                # Process alternative time suggestion
                response.add(plivoxml.SpeechElement(voice_response))
                response.add(plivoxml.SpeechElement("Goodbye!"))
                response.add(plivoxml.HangupElement())
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error processing voice input: {str(e)}", exc_info=True)
            return self._create_error_response()
    
    def _create_error_response(self) -> str:
        """Create error response when something goes wrong"""
        response = plivoxml.ResponseElement()
        response.add(plivoxml.SpeechElement("I'm sorry, there was an error processing your request. Please try calling again later."))
        response.add(plivoxml.HangupElement())
        return str(response)
    
    def end_call(self, call_uuid: str):
        """End the call and clean up session"""
        try:
            if call_uuid in self.call_sessions:
                del self.call_sessions[call_uuid]
                logger.info(f"Call session ended for UUID: {call_uuid}")
            
            # Note: Plivo doesn't require explicit call termination like Twilio
            
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}", exc_info=True)
    
    def get_call_status(self, call_uuid: str) -> Optional[Dict[str, Any]]:
        """Get current call status and session info"""
        return self.call_sessions.get(call_uuid)
    
    def validate_webhook_signature(self, url: str, signature: str, timestamp: str, nonce: str) -> bool:
        """Validate Plivo webhook signature for security"""
        try:
            return validate_signature(url, signature, timestamp, nonce, self.auth_token)
        except Exception as e:
            logger.error(f"Error validating webhook signature: {str(e)}")
            return False


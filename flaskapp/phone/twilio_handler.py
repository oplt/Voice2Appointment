import os
from typing import Dict, Any, Optional
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from datetime import datetime
import json
from .ai_integration import AIVoiceIntegration
from . import phone_logger
from db.models import CallSession
from flask_login import current_user


# Use centralized phone logger
logger = phone_logger

class TwilioPhoneHandler:

    def __init__(self):
        self.account_sid =os.environ.get('TWILIO_ACCOUNT_SID' or None)
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN' or None)
        self.phone_number = os.environ.get('TWILIO_PHONE_NUMBER' or None)

        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Twilio credentials not fully configured")
        
        # Initialize Twilio client
        self.client = Client(self.account_sid, self.auth_token) if self.account_sid and self.auth_token else None
        
        # Initialize AI integration
        self.ai_integration = AIVoiceIntegration(
            twilio_account_sid=self.account_sid,
            twilio_auth_token=self.auth_token
        )
        
        # Call session storage (in production, use Redis or database)
        self.call_sessions = CallSession.query.all()
        
        logger.info(f"TwilioPhoneHandler initialized - Account SID: {self.account_sid[:8]}..., Phone: {self.phone_number}")
    
    def handle_incoming_call(self, call_sid: str, from_number: str) -> str:
        """Handle incoming call and return TwiML response"""
        try:
            logger.info(f"Incoming call from {from_number}, SID: {call_sid}")

            # Initialize call session
            current_callsession = [session for session in self.call_sessions if session.call_sid == call_sid]
            current_callsession = {
                'from_number': from_number,
                'start_time': datetime.now(),
                'step': 'greeting',
                'appointment_date': None,
                'preferred_time': None
            }

            # Create TwiML response
            response = VoiceResponse()

            # Welcome message
            response.say("Welcome to the Voice Assistant Appointment Scheduler. I'll help you schedule an appointment.")
            response.say("Please tell me when you'd like to schedule your appointment. You can say something like 'I need an appointment on March 15th at 2 PM'.")

            # Option 1: Record user's response (current approach)
            response.record(
                action=f'/phone/process-voice/{call_sid}',
                method='POST',
                maxLength='30',
                playBeep=False,
                trim='trim-silence'
            )

            # Option 2: Real-time audio processing (future enhancement)
            # This would use Twilio's Media Streams API for live processing
            # response.say("I'm listening. Please tell me when you'd like your appointment.")
            # response.start_stream(url=f'/phone/stream-audio/{call_sid}')

            # If no input, redirect to main menu
            response.redirect(f'/phone/process-voice/{call_sid}')

            return str(response)

        except Exception as e:
            logger.error(f"Error handling incoming call: {str(e)}", exc_info=True)
            return self._create_error_response()

    def handle_incoming_call_with_streaming(self, call_sid: str, from_number: str) -> str:
        """Handle incoming call with real-time audio streaming"""
        try:
            logger.info(f"Incoming call with streaming from {from_number}, SID: {call_sid}")

            # Initialize call session
            current_callsession = {
                'from_number': from_number,
                'start_time': datetime.now(),
                'step': 'greeting',
                'appointment_date': None,
                'preferred_time': None
            }

            # Create TwiML response with streaming
            response = VoiceResponse()

            # Welcome message
            response.say("Welcome to the Voice Assistant Appointment Scheduler. I'm listening to you in real-time.")
            response.say("Please tell me when you'd like to schedule your appointment.")

            # Start real-time audio streaming
            response.start()
            response.stream(
                url=f'{self.base_url}/phone/stream-audio/{call_sid}',
                track='inbound_track'
            )

            # Add a pause to let user speak
            response.pause(length=10)

            # Process the streamed audio and respond
            response.say("Let me process what you said and check availability.")
            
            # Redirect to processing endpoint
            response.redirect(f'/phone/process-streamed-audio/{call_sid}')

            return str(response)

        except Exception as e:
            logger.error(f"Error handling streaming call: {str(e)}", exc_info=True)
            return self._create_error_response()

    def process_voice_input(self, call_sid: str, audio_url: str) -> str:
        """Process recorded voice input and respond accordingly"""
        try:
            session = next((session for session in self.call_sessions if session.call_sid == call_sid), None)
            if not session:
                logger.error(f"Call session not found for SID: {call_sid}")
                return self._create_error_response()

            # session = self.call_sessions[call_sid]
            logger.info(f"Processing voice input for call {call_sid}, step: {session.step}")

            # Process voice with AI integration
            ai_result = self.ai_integration.process_voice_request(audio_url, call_sid)

            # Generate appropriate voice response
            voice_response = self.ai_integration.generate_voice_response(ai_result, session)

            # Create TwiML response
            response = VoiceResponse()

            if session.step == 'greeting':
                # Process appointment request
                response.say(voice_response)

                # If appointment was scheduled successfully, end call
                if "scheduled" in voice_response.lower() and "thank you" in voice_response.lower():
                    response.say("Goodbye!")
                    response.hangup()
                elif "not available" in voice_response.lower():
                    # Ask for alternative time
                    response.say("Please suggest another time slot.")
                    response.record(
                        action=f'/phone/process-voice/{call_sid}',
                        method='POST',
                        maxLength='30',
                        playBeep=False,
                        trim='trim-silence'
                    )
                    session.step = 'alternative_time'
                else:
                    # End call for other responses
                    response.say("Goodbye!")
                    response.hangup()

            elif session.step == 'alternative_time':
                # Process alternative time suggestion
                response.say(voice_response)
                response.say("Goodbye!")
                response.hangup()

            return str(response)

        except Exception as e:
            logger.error(f"Error processing voice input: {str(e)}", exc_info=True)
            return self._create_error_response()

    def process_streamed_audio(self, call_sid: str, audio_chunks: list) -> str:
        """Process audio chunks received from Media Streams"""
        try:
            logger.info(f"Processing streamed audio for call {call_sid}, chunks: {len(audio_chunks)}")
            
            # Combine audio chunks into single audio data
            combined_audio = b''.join(audio_chunks)
            
            # Process with AI integration
            ai_result = self.ai_integration.process_realtime_audio(combined_audio, call_sid)
            
            # Generate voice response
            voice_response = self.ai_integration.generate_voice_response(ai_result, {'call_sid': call_sid})
            
            # Create TwiML response
            response = VoiceResponse()
            response.say(voice_response)
            
            # End call or continue based on response
            if "scheduled" in voice_response.lower() and "thank you" in voice_response.lower():
                response.say("Goodbye!")
                response.hangup()
            else:
                response.say("Please call back if you need further assistance.")
                response.hangup()
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error processing streamed audio: {str(e)}", exc_info=True)
            return self._create_error_response()

    def _check_availability(self, session: Dict[str, Any]) -> bool:
        """Check if requested time slot is available"""
        # TODO: Integrate with your Google Calendar logic
        # For now, return random availability
        import random
        return random.choice([True, False])

    def _create_error_response(self) -> str:
        """Create error response when something goes wrong"""
        response = VoiceResponse()
        response.say("I'm sorry, there was an error processing your request. Please try calling again later.")
        response.hangup()
        return str(response)

    def end_call(self, call_sid: str):
        """End the call and clean up session"""
        try:
            if call_sid in self.call_sessions:
                del self.call_sessions[call_sid]
                logger.info(f"Call session ended for SID: {call_sid}")

            if self.client:
                # End the call via Twilio API
                call = self.client.calls(call_sid).fetch()
                if call.status != 'completed':
                    self.client.calls(call_sid).update(status='completed')

        except Exception as e:
            logger.error(f"Error ending call: {str(e)}", exc_info=True)

    def get_call_status(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """Get current call status and session info"""
        return self.call_sessions.get(call_sid)

    def get_base_url(self) -> str:
        """Get base URL for webhook endpoints"""
        return os.environ.get('FLASK_BASE_URL', 'http://localhost:5001')
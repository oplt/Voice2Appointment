import os
from typing import Dict, Any, Optional
from datetime import datetime
from .ai_integration import AIVoiceIntegration
from . import phone_logger

logger = phone_logger

class TelnyxPhoneHandler:
	"""Handles incoming phone calls and voice interactions via Telnyx (TeXML style)."""
	
	def __init__(self):
		self.api_key = os.getenv('TELNYX_API_KEY')
		self.connection_id = os.getenv('TELNYX_CONNECTION_ID')
		self.webhook_secret = os.getenv('TELNYX_WEBHOOK_SECRET')
		self.phone_number = os.getenv('TELNYX_PHONE_NUMBER')
		self.ai_integration = AIVoiceIntegration()
		self.call_sessions: Dict[str, Dict[str, Any]] = {}
		logger.info(f"TelnyxPhoneHandler initialized - Phone: {self.phone_number}")
	
	def handle_incoming_call(self, session_id: str, from_number: str) -> str:
		"""Return TeXML XML response for greeting + record."""
		try:
			logger.info(f"Telnyx incoming call from {from_number}, session: {session_id}")
			self.call_sessions[session_id] = {
				'from_number': from_number,
				'start_time': datetime.now(),
				'step': 'greeting',
				'appointment_date': None,
				'preferred_time': None
			}
			# TeXML-like response
			xml = f"""
			<?xml version="1.0" encoding="UTF-8"?>
			<Response>
				<Say>Welcome to the Voice Assistant Appointment Scheduler. I'll help you schedule an appointment.</Say>
				<Say>Please tell me when you'd like to schedule your appointment. You can say something like I need an appointment on March 15th at 2 PM.</Say>
				<Record action="/phone/telnyx/process-voice/{session_id}" method="POST" maxLength="30" playBeep="false"/>
				<Redirect>/phone/telnyx/process-voice/{session_id}</Redirect>
			</Response>
			""".strip()
			return xml
		except Exception as e:
			logger.error(f"Error handling Telnyx incoming call: {str(e)}", exc_info=True)
			return self._error_response()
	
	def process_voice_input(self, session_id: str, audio_url: str) -> str:
		try:
			if session_id not in self.call_sessions:
				logger.error(f"Telnyx session not found: {session_id}")
				return self._error_response()
			session = self.call_sessions[session_id]
			logger.info(f"Processing Telnyx audio for session {session_id}")
			ai_result = self.ai_integration.process_voice_request(audio_url, session_id)
			voice_text = self.ai_integration.generate_voice_response(ai_result, session)
			xml = f"""
			<?xml version="1.0" encoding="UTF-8"?>
			<Response>
				<Say>{voice_text}</Say>
				<Hangup/>
			</Response>
			""".strip()
			return xml
		except Exception as e:
			logger.error(f"Error processing Telnyx voice input: {str(e)}", exc_info=True)
			return self._error_response()
	
	def _error_response(self) -> str:
		return """
		<?xml version="1.0" encoding="UTF-8"?>
		<Response>
			<Say>I'm sorry, there was an error processing your request. Please try calling again later.</Say>
			<Hangup/>
		</Response>
		""".strip()

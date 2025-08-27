import os
import requests
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import pytz
from . import phone_logger
from flaskapp.main.routes import get_user_timezone

# Use centralized phone logger
logger = phone_logger

class AIVoiceIntegration:
    """Integrates phone system with AI processor and Google Calendar"""
    
    def __init__(self):
        self.base_url = os.getenv('FLASK_BASE_URL', 'http://localhost:5001')
        self.timezone = get_user_timezone or 'Europe/Brussels'  # Default timezone
        logger.info(f"AI Voice Integration initialized with base URL: {self.base_url}")
    
    def process_voice_request(self, audio_url: str, call_sid: str) -> Dict[str, Any]:
        """Process voice request using your existing AI processor"""
        try:
            logger.info(f"Processing voice request for call {call_sid}")
            
            # Download audio from Twilio URL
            audio_file = self._download_audio(audio_url)
            if not audio_file:
                return {'error': 'Failed to download audio'}
            
            # Process with your existing AI system
            result = self._process_with_ai(audio_file, call_sid)
            
            # Clean up temporary file
            if os.path.exists(audio_file):
                os.remove(audio_file)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing voice request: {str(e)}", exc_info=True)
            return {'error': f'Processing error: {str(e)}'}
    
    def _download_audio(self, audio_url: str) -> Optional[str]:
        """Download audio file from Twilio URL"""
        try:
            # Add .wav extension for proper processing
            temp_filename = f"temp_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            temp_filepath = os.path.join('/tmp', temp_filename)
            
            # Download the audio file
            response = requests.get(audio_url, stream=True)
            response.raise_for_status()
            
            with open(temp_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Audio downloaded to {temp_filepath}")
            return temp_filepath
            
        except Exception as e:
            logger.error(f"Error downloading audio: {str(e)}", exc_info=True)
            return None
    
    def _process_with_ai(self, audio_file: str, call_sid: str) -> Dict[str, Any]:
        """Process audio with your existing AI processor"""
        try:
            # Use your existing voice processing endpoint
            url = f"{self.base_url}/voice/record-simple"
            
            with open(audio_file, 'rb') as f:
                files = {'audio': f}
                response = requests.post(url, files=files)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"AI processing successful: {result}")
                return result
            else:
                logger.error(f"AI processing failed: {response.status_code} - {response.text}")
                return {'error': 'AI processing failed'}
                
        except Exception as e:
            logger.error(f"Error calling AI processor: {str(e)}", exc_info=True)
            return {'error': f'AI processing error: {str(e)}'}
    
    def check_calendar_availability(self, date: str, time: str, duration_minutes: int = 60) -> Dict[str, Any]:
        """Check if requested time slot is available in Google Calendar"""
        try:
            # Parse the date and time
            parsed_datetime = self._parse_datetime(date, time)
            if not parsed_datetime:
                return {'error': 'Invalid date/time format'}
            
            # Check availability using your existing calendar logic
            # This would integrate with your GoogleCalendarAuth and calendar functionality
            availability = self._check_google_calendar_availability(parsed_datetime, duration_minutes)
            
            return {
                'available': availability['available'],
                'suggested_alternatives': availability.get('alternatives', []),
                'requested_time': parsed_datetime.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error checking calendar availability: {str(e)}")
            return {'error': f'Calendar check error: {str(e)}'}
    
    def schedule_appointment(self, date: str, time: str, caller_info: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule appointment in Google Calendar"""
        try:
            parsed_datetime = self._parse_datetime(date, time)
            if not parsed_datetime:
                return {'error': 'Invalid date/time format'}
            
            # Create appointment using your existing calendar functionality
            appointment_result = self._create_google_calendar_event(parsed_datetime, caller_info)
            
            return {
                'success': appointment_result['success'],
                'appointment_id': appointment_result.get('id'),
                'message': appointment_result.get('message', 'Appointment scheduled successfully')
            }
            
        except Exception as e:
            logger.error(f"Error scheduling appointment: {str(e)}")
            return {'error': f'Appointment scheduling error: {str(e)}'}
    
    def _parse_datetime(self, date: str, time: str) -> Optional[datetime]:
        """Parse date and time strings into datetime object"""
        try:
            # This is a simplified parser - you might want to use dateutil.parser
            # or integrate with your existing LLM date parsing logic
            
            # For now, assume format like "March 15th" and "2 PM"
            # You should integrate this with your existing LLM date extraction
            
            # Placeholder implementation
            current_year = datetime.now().year
            # This would need to be enhanced based on your LLM output format
            
            return datetime.now() + timedelta(days=1)  # Placeholder
            
        except Exception as e:
            logger.error(f"Error parsing datetime: {str(e)}")
            return None
    
    def _check_google_calendar_availability(self, requested_time: datetime, duration_minutes: int) -> Dict[str, Any]:
        """Check Google Calendar for availability"""
        # TODO: Integrate with your existing Google Calendar functionality
        # This should use your GoogleCalendarAuth and calendar integration
        
        # Placeholder implementation
        return {
            'available': True,  # Placeholder
            'alternatives': []
        }
    
    def _create_google_calendar_event(self, appointment_time: datetime, caller_info: Dict[str, Any]) -> Dict[str, Any]:
        """Create Google Calendar event"""
        # TODO: Integrate with your existing Google Calendar functionality
        # This should use your existing calendar integration code
        
        # Placeholder implementation
        return {
            'success': True,
            'id': 'placeholder_id',
            'message': 'Appointment created successfully'
        }
    
    def generate_voice_response(self, ai_result: Dict[str, Any], call_context: Dict[str, Any]) -> str:
        """Generate appropriate voice response based on AI processing result"""
        try:
            if 'error' in ai_result:
                return f"I'm sorry, I encountered an error: {ai_result['error']}. Please try again."
            
            # Extract appointment details from AI result
            appointment_details = ai_result.get('appointment_details', {})
            
            if not appointment_details:
                return "I couldn't understand your appointment request. Please try again with a clear date and time."
            
            # Check availability
            date = appointment_details.get('date')
            time = appointment_details.get('time')
            
            if not date or not time:
                return "I need both a date and time for your appointment. Please specify when you'd like to schedule it."
            
            # Check calendar availability
            availability = self.check_calendar_availability(date, time)
            
            if availability.get('available'):
                # Schedule the appointment
                schedule_result = self.schedule_appointment(date, time, call_context)
                
                if schedule_result.get('success'):
                    return f"Perfect! I've scheduled your appointment for {date} at {time}. You'll receive a confirmation shortly. Thank you for calling!"
                else:
                    return f"I found an available slot, but there was an error scheduling it: {schedule_result.get('error')}. Please try again."
            else:
                # Suggest alternatives
                alternatives = availability.get('suggested_alternatives', [])
                if alternatives:
                    alt_text = ", ".join(alternatives[:3])  # Show first 3 alternatives
                    return f"That time slot is not available. Here are some alternatives: {alt_text}. Please let me know which works for you."
                else:
                    return "That time slot is not available. Please suggest another date and time, and I'll check availability for you."
                    
        except Exception as e:
            logger.error(f"Error generating voice response: {str(e)}")
            return "I'm sorry, I'm having trouble processing your request. Please try calling again later."

import os
import requests
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import pytz
from . import phone_logger
from flaskapp.main.routes import get_user_timezone
from db.models import User

# Use centralized phone logger
logger = phone_logger

class AIVoiceIntegration:
    """Integrates phone system with AI processor and Google Calendar"""
    
    def __init__(self, twilio_account_sid: str = None, twilio_auth_token: str = None):
        self.base_url = os.getenv('FLASK_BASE_URL', 'http://localhost:5001')
        self.timezone = get_user_timezone or 'Europe/Brussels'  # Default timezone
        self.twilio_account_sid = twilio_account_sid
        self.twilio_auth_token = twilio_auth_token
        logger.info(f"AI Voice Integration initialized with base URL: {self.base_url}")
        if twilio_account_sid:
            logger.info(f"Twilio credentials configured - Account SID: {twilio_account_sid[:8]}...")
        else:
            logger.warning("No Twilio credentials provided - audio downloads will fail")
    
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
    
    def process_realtime_audio(self, audio_data: bytes, call_sid: str) -> Dict[str, Any]:
        """Process real-time audio data during an ongoing call"""
        try:
            logger.info(f"Processing real-time audio for call {call_sid}, size: {len(audio_data)} bytes")
            
            # Detect audio format (Twilio typically sends WAV or MP3)
            audio_format = self._detect_audio_format(audio_data)
            logger.info(f"Detected audio format: {audio_format}")
            
            # Save audio data to temporary file for processing
            temp_filename = f"realtime_audio_{call_sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{audio_format}"
            temp_filepath = os.path.join('/tmp', temp_filename)
            
            with open(temp_filepath, 'wb') as f:
                f.write(audio_data)
            
            # Process with AI
            result = self._process_with_ai(temp_filepath, call_sid)
            
            # Clean up temporary file
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            
            logger.info(f"Real-time audio processing completed for call {call_sid}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing real-time audio: {str(e)}", exc_info=True)
            return {'error': f'Real-time processing error: {str(e)}'}
    
    def get_streaming_audio_url(self, call_sid: str) -> Optional[str]:
        """Get streaming audio URL for real-time processing during call"""
        try:
            if not (self.twilio_account_sid and self.twilio_auth_token):
                logger.error("Missing Twilio credentials for streaming audio")
                return None
            
            # This would integrate with Twilio's Media Streams API
            # For now, return None to indicate streaming not available
            logger.info(f"Streaming audio not yet implemented for call {call_sid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting streaming audio URL: {str(e)}")
            return None
    
    def _download_audio(self, audio_url: str) -> Optional[str]:
        """Download audio file from Twilio URL"""
        try:
            if not (self.twilio_account_sid and self.twilio_auth_token):
                logger.error("Missing Twilio credentials for recording download")
                return None
            
            # First, try to extract recording SID and use REST API
            recording_sid = self._extract_recording_sid(audio_url)
            if recording_sid:
                logger.info(f"Attempting to download via REST API using SID: {recording_sid}")
                result = self._download_audio_via_api(recording_sid)
                if result:
                    return result
                logger.warning("REST API download failed, trying direct URL access")
            
            # Fallback to direct URL access
            logger.info("Falling back to direct URL access")
            return self._download_audio_direct(audio_url)
            
        except Exception as e:
            logger.error(f"Error in main download method: {str(e)}", exc_info=True)
            return None
    
    def _download_audio_direct(self, audio_url: str) -> Optional[str]:
        """Download audio file directly from URL (fallback method)"""
        try:
            # Create temp file
            temp_filename = f"temp_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            temp_filepath = os.path.join('/tmp', temp_filename)
            
            # Fix Twilio recording URL format
            download_url = self._fix_twilio_recording_url(audio_url)
            logger.info(f"Downloading audio directly from: {download_url}")
            
            # Use proper Twilio authentication headers
            headers = {
                'Authorization': f'Basic {self._get_twilio_auth_header()}',
                'User-Agent': 'VoiceAssistant/1.0'
            }
            
            response = requests.get(download_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # Check if we got audio content
            content_type = response.headers.get('content-type', '')
            content_length = response.headers.get('content-length', '0')
            logger.info(f"Response: {response.status_code}, Content-Type: {content_type}, Size: {content_length}")
            
            if not content_type.startswith('audio/') and not content_type.startswith('application/octet-stream'):
                logger.warning(f"Unexpected content type: {content_type}")
            
            with open(temp_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Verify file was created and has content
            if os.path.exists(temp_filepath) and os.path.getsize(temp_filepath) > 0:
                logger.info(f"Audio downloaded successfully to {temp_filepath} ({os.path.getsize(temp_filepath)} bytes)")
                return temp_filepath
            else:
                logger.error("Downloaded file is empty or missing")
                return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error downloading audio directly: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response text: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error downloading audio directly: {str(e)}", exc_info=True)
            return None
    
    def _download_audio_via_api(self, recording_sid: str) -> Optional[str]:
        """Download audio using Twilio REST API instead of direct URL access"""
        try:
            if not (self.twilio_account_sid and self.twilio_auth_token):
                logger.error("Missing Twilio credentials for API download")
                return None
            
            # Create temp file
            temp_filename = f"temp_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            temp_filepath = os.path.join('/tmp', temp_filename)
            
            # Use Twilio REST API to get recording
            from twilio.rest import Client
            client = Client(self.twilio_account_sid, self.twilio_auth_token)
            
            # Get recording details
            recording = client.recordings(recording_sid).fetch()
            logger.info(f"Recording details: SID={recording.sid}, Duration={recording.duration}, Status={recording.status}")
            
            # Download the recording
            with open(temp_filepath, 'wb') as f:
                recording.download(file=f)
            
            # Verify file was created and has content
            if os.path.exists(temp_filepath) and os.path.getsize(temp_filepath) > 0:
                logger.info(f"Audio downloaded via API to {temp_filepath} ({os.path.getsize(temp_filepath)} bytes)")
                return temp_filepath
            else:
                logger.error("Downloaded file is empty or missing")
                return None
            
        except Exception as e:
            logger.error(f"Error downloading audio via API: {str(e)}", exc_info=True)
            return None

    def _extract_recording_sid(self, recording_url: str) -> Optional[str]:
        """Extract recording SID from Twilio recording URL"""
        try:
            # URL format: https://api.twilio.com/2010-04-01/Accounts/AC.../Recordings/RE...
            if '/Recordings/' in recording_url:
                recording_sid = recording_url.split('/Recordings/')[-1].split('.')[0]
                logger.info(f"Extracted recording SID: {recording_sid}")
                return recording_sid
            return None
        except Exception as e:
            logger.error(f"Error extracting recording SID: {str(e)}")
            return None
    
    def _fix_twilio_recording_url(self, audio_url: str) -> str:
        """Fix Twilio recording URL format for proper access"""
        try:
            # Twilio RecordingUrl format: https://api.twilio.com/2010-04-01/Accounts/AC.../Recordings/RE...
            if 'api.twilio.com' in audio_url and '/Recordings/' in audio_url:
                # Ensure proper format - remove any .wav extension if present
                base_url = audio_url.split('.wav')[0] if audio_url.endswith('.wav') else audio_url
                
                # Add .wav extension for audio download
                download_url = f"{base_url}.wav"
                logger.info(f"Fixed Twilio URL: {audio_url} -> {download_url}")
                return download_url
            else:
                # Not a Twilio URL, return as-is
                return audio_url
                
        except Exception as e:
            logger.error(f"Error fixing Twilio URL: {str(e)}")
            return audio_url
    
    def _get_twilio_auth_header(self) -> str:
        """Generate Twilio Basic Auth header"""
        import base64
        try:
            credentials = f"{self.twilio_account_sid}:{self.twilio_auth_token}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            return encoded_credentials
        except Exception as e:
            logger.error(f"Error generating auth header: {str(e)}")
            return ""
    
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
    
    def _detect_audio_format(self, audio_data: bytes) -> str:
        """Detect audio format from file header"""
        try:
            # Check for common audio format headers
            if audio_data.startswith(b'RIFF') and audio_data[8:12] == b'WAVE':
                return 'wav'
            elif audio_data.startswith(b'\xff\xfb') or audio_data.startswith(b'ID3'):
                return 'mp3'
            elif audio_data.startswith(b'OggS'):
                return 'ogg'
            elif audio_data.startswith(b'fLaC'):
                return 'flac'
            else:
                # Default to WAV if format can't be determined
                logger.warning("Could not determine audio format, defaulting to WAV")
                return 'wav'
        except Exception as e:
            logger.error(f"Error detecting audio format: {str(e)}")
            return 'wav'  # Default fallback
    
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

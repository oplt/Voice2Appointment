import os
import sounddevice as sd
from scipy.io.wavfile import write
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pytz
from db.models import GoogleCalendarAuth
import subprocess
from typing import Dict, List, Tuple, Optional, Any
from .config import AUDIO_CONFIG, CALENDAR_CONFIG, VOICE_CONFIG, WHISPER_CONFIG, TTS_CONFIG, LLM_CONFIG, STT_LANGUAGE
from .logging_config import ai_logger, calendar_logger, voice_logger, log_function_call, log_execution_time
import json
import re
import time
from datetime import datetime
from typing import Any, Dict
import requests
from zoneinfo import ZoneInfo


class AudioProcessor:
    """Handles audio recording and transcription operations"""
    
    def __init__(self, sample_rate: int = None, channels: int = None, record_seconds: int = None):
        self.sample_rate = sample_rate or AUDIO_CONFIG['SAMPLE_RATE']
        self.channels = channels or AUDIO_CONFIG['CHANNELS']
        self.record_seconds = record_seconds or AUDIO_CONFIG['RECORD_SECONDS']
    
    def record_audio(self, output_filename: str = "temp_recording.wav") -> str:
        """Record audio from microphone and save to file"""
        voice_logger.info("Starting audio recording...")
        recording = sd.rec(
            int(self.record_seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype='int16'
        )
        sd.wait()
        voice_logger.info("Audio recording completed")
        
        write(output_filename, self.sample_rate, recording)
        voice_logger.debug(f"Audio saved to {output_filename}")
        return output_filename
    
    def transcribe_with_whisper(self, file_path: str) -> str:
        """Transcribe audio file using Whisper"""
        try:
            # Convert input to 16kHz mono WAV to improve Whisper accuracy and compatibility
            safe_wav_path = self._ensure_wav_16k_mono(file_path)
            import whisper
            model = whisper.load_model(WHISPER_CONFIG['MODEL_SIZE'])
            
            transcribe_kwargs = {
                'fp16': WHISPER_CONFIG['FP16'],
                'verbose': WHISPER_CONFIG['VERBOSE']
            }
            if STT_LANGUAGE:
                transcribe_kwargs['language'] = STT_LANGUAGE

            result = model.transcribe(safe_wav_path, **transcribe_kwargs)
            
            return result["text"].strip()
        except ImportError:
            voice_logger.error("Whisper not installed")
            raise ImportError("Whisper not installed. Install with: pip install openai-whisper")
        except Exception as e:
            voice_logger.error(f"Transcription error: {str(e)}")
            raise Exception(f"Transcription error: {str(e)}")

    def _ensure_wav_16k_mono(self, input_path: str) -> str:
        """Ensure the audio is 16kHz mono WAV using ffmpeg; returns path to converted file."""
        try:
            import tempfile
            import subprocess as sp
            import os as _os

            # If already a WAV, we still normalize sample rate and channels to be safe
            temp_dir = tempfile.gettempdir()
            base = _os.path.splitext(_os.path.basename(input_path))[0]
            output_path = _os.path.join(temp_dir, f"{base}_16k_mono.wav")

            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-ac', '1',            # mono
                '-ar', '16000',        # 16 kHz
                '-vn',                 # no video
                '-f', 'wav',
                output_path
            ]

            try:
                sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE)
                voice_logger.debug(f"Audio converted for STT: {output_path}")
                return output_path
            except FileNotFoundError:
                # ffmpeg not installed; fall back to original file and warn
                voice_logger.warning("ffmpeg not found. Using original audio file; transcription quality may suffer.")
                return input_path
            except sp.CalledProcessError as conv_err:
                # Conversion failed; fall back to original file
                voice_logger.warning(f"ffmpeg conversion failed: {conv_err}. Using original file.")
                return input_path
        except Exception as e:
            voice_logger.warning(f"Audio normalization failed: {e}. Using original file.")
            return input_path


class LLMProcessor:

    MODEL_NAME = "gpt-oss:20b"
    OLLAMA_URL = "http://localhost:11434/api/generate"

    def __init__(self, timezone: str = None):
        self.timezone = timezone or LLM_CONFIG.get('Timezone', 'UTC')
        self._session = requests.Session()
        self._session.headers.update({'Content-Type': 'application/json'})

        # Response cache for repeated queries
        self._response_cache: Dict[tuple, str] = {}
        self._last_request_time = 0
        self._min_request_interval = 0.1  # Minimum time between requests

    def _rate_limit(self) -> None:
        """Implement basic rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._min_request_interval:
            time.sleep(self._min_request_interval - time_since_last)
        self._last_request_time = time.time()


    def _cached_gptoss_request(self, prompt: str, temperature: float = None, num_predict: int = 150) -> str:
        key = (prompt, round(temperature or 0.7, 2), num_predict)
        cached = self._response_cache.get(key)
        if cached is not None:
            return cached

        result = self._make_gptoss_request(prompt, temperature=temperature, num_predict=num_predict)
        # Only cache if it's a non-empty, non-"{}" response
        if result and result.strip() != "{}":
            self._response_cache[key] = result
        if result is None:
            time.sleep(0.2)
            result = self._make_gptoss_request(prompt, temperature=temperature, num_predict=num_predict)
        return result

    def _make_gptoss_request(self, prompt: str, temperature: float = None, num_predict: int = 150) -> str:
        """
        Calls local Ollama /api/generate with the gpt-oss:20b model.
        """
        self._rate_limit()

        payload = {
            "model": self.MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                # Ollama expects num_predict, NOT max_tokens
                "temperature": temperature or 0.7,
                "num_predict": num_predict
            }
        }

        try:
            resp = self._session.post(
                self.OLLAMA_URL,
                json=payload,
                timeout=60  # adjust if your 20B is slower on your machine
            )
            resp.raise_for_status()
            # Ollama returns {"response": "...", "done": true, ...}
            result = resp.json().get("response", "")
            result = result.strip() if isinstance(result, str) else ""
            return result or None

        except requests.exceptions.RequestException as e:
            try:
                ai_logger.info(f"❌ Ollama API error: {e}")
            except NameError:
                print(f"❌ Ollama API error: {e}")
        except json.JSONDecodeError as e:
            try:
                ai_logger.info(f"❌ JSON decode error: {e}")
            except NameError:
                print(f"❌ JSON decode error: {e}")
        except Exception as e:
            try:
                ai_logger.info(f"❌ Unexpected error in AI request: {e}")
            except NameError:
                print(f"❌ Unexpected error in AI request: {e}")
        return None


    def extract_appointment_details(self, text: str):
        today = datetime.now(ZoneInfo(self.timezone)).strftime('%Y-%m-%d')
        text = self._preprocess_text(text)
        prompt = f"""Extract the appointment details from the following text. 
        Return a JSON object with these fields:
        - "date": The date in YYYY-MM-DD format (use 'today' if no date specified)
        - "time": The time in HH:MM format (use '9:00' if no time specified)
        - "title": A brief title for the appointment
        
        If multiple dates/times are mentioned, use the first one.
        Today is {today} in timezone {self.timezone}.
        Text: {text}"""

        response = self._cached_gptoss_request(prompt, temperature=0.3, num_predict=200) or "{}"
        details_dict = self._parse_json_response(response)
        details_dict = self._validate_appointment_details(details_dict)
        return {
            'date': details_dict.get('date'),
            'time': details_dict.get('time'),
            'title': details_dict.get('title')
        }

    def generate_response(self, prompt: str, context: str = "") -> str:
        full_prompt = f"""You are a helpful scheduling assistant.   
Context: {context}    
User input: {prompt}    
Respond naturally and helpfully. Keep responses brief and conversational.
Focus on scheduling-related assistance."""

        try:
            response = self._make_gptoss_request(full_prompt, temperature=0.7, num_predict=250)
            response = (response or "").strip()
            if not response:
                return "I'm sorry, I didn't quite understand that. Could you please rephrase?"
            return response

        except Exception as e:
            print(f"❌ Error generating response: {e}")
            return "I'm having trouble processing that. Could you please try again?"

    def analyze_confirmation(self, text: str) -> bool:
        text_lower = text.lower().strip()

        # Positive indicators
        positive_words = ['yes', 'yeah', 'yep', 'correct', 'right', 'ok', 'okay',
                          'sure', 'good', 'perfect', 'exactly', 'confirm']

        # Negative indicators
        negative_words = ['no', 'nope', 'wrong', 'incorrect', 'change', 'different',
                          'not', 'cancel', 'abort']

        for word in positive_words:
            if word in text_lower:
                return True

        for word in negative_words:
            if word in text_lower:
                return False

        return None  # Unclear response

    # ------------------------
    # Utilities
    # ------------------------
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text to normalize common patterns."""
        text = re.sub(r'\btomorrow\b', 'tomorrow', text, flags=re.IGNORECASE)
        text = re.sub(r'\btoday\b', 'today', text, flags=re.IGNORECASE)
        text = re.sub(r'\bnext week\b', 'next week', text, flags=re.IGNORECASE)

        # Normalize time formats
        text = re.sub(r'(\d{1,2})\s*pm', r'\1:00 PM', text, flags=re.IGNORECASE)
        text = re.sub(r'(\d{1,2})\s*am', r'\1:00 AM', text, flags=re.IGNORECASE)

        return text.strip()

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from the AI model."""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                return {}

            json_str = response[json_start:json_end]
            return json.loads(json_str)

        except (json.JSONDecodeError, IndexError) as e:
            print(f"⚠️ Failed to parse JSON response: {e}")
            print(f"Raw response: {response}")
            return {}

    def _validate_appointment_details(self, details: Dict[str, Any]) -> Dict[str, str]:
        """Validate and normalize appointment details."""
        validated = {}

        # Validate date
        date_value = details.get('date', 'today')
        if not date_value or str(date_value).lower() in ['today', 'now']:
            validated['date'] = 'today'
        else:
            try:
                if re.match(r'^\d{4}-\d{2}-\d{2}$', str(date_value)):
                    validated['date'] = str(date_value)
                else:
                    validated['date'] = 'today'
            except:
                validated['date'] = 'today'

        # Validate time
        time_value = details.get('time', "9:00")
        if not time_value:
            validated['time'] = "9:00"
        else:
            try:
                if re.match(r'^\d{1,2}:\d{2}$', str(time_value)):
                    validated['time'] = str(time_value)
                else:
                    validated['time'] = "9:00"
            except:
                validated['time'] = "9:00"

        # Validate title
        title_value = details.get('title', 'Meeting')
        if not title_value or len(str(title_value).strip()) == 0:
            validated['title'] = 'Meeting'
        else:
            title = str(title_value).strip()[:100]
            validated['title'] = title if title else 'Meeting'

        return validated

    # ------------------------
    # Cache controls
    # ------------------------
    def clear_cache(self) -> None:
        """Clear the response cache."""
        self._response_cache.clear()

    def get_cache_info(self) -> Dict[str, Any]:
        """Get basic cache statistics for the dict-based cache."""
        return {
            'cache_size': len(self._response_cache)
        }


class CalendarManager:
    """Manages Google Calendar operations"""
    
    def __init__(self, timezone: str = None, working_hours: Tuple[int, int] = None):
        self.timezone = timezone or CALENDAR_CONFIG['TIMEZONE']
        self.working_hours = working_hours or CALENDAR_CONFIG['WORKING_HOURS']
        self.scopes = CALENDAR_CONFIG['SCOPES']
        self.calendar_id = CALENDAR_CONFIG['CALENDAR_ID']
        
        # Validate timezone
        try:
            pytz.timezone(self.timezone)
            calendar_logger.info(f"Calendar manager initialized with timezone: {self.timezone}")
        except pytz.exceptions.UnknownTimeZoneError:
            calendar_logger.error(f"Invalid timezone: {self.timezone}, falling back to UTC")
            self.timezone = 'UTC'
    
    def authenticate(self, user_id: Optional[int] = None) -> any:
        """Authenticate with Google Calendar"""
        try:
            if user_id:
                # Try to get credentials from database
                auth_record = GoogleCalendarAuth.query.filter_by(user_id=user_id).first()
                if auth_record and auth_record.credentials_json and auth_record.token_json:
                    try:
                        calendar_logger.info(f"Attempting database authentication for user {user_id}")
                        
                        # Parse the stored credentials and token
                        creds_data = json.loads(auth_record.credentials_json)
                        token_data = json.loads(auth_record.token_json)
                        
                        calendar_logger.debug(f"Credentials type: {creds_data.get('type', 'OAuth')}")
                        calendar_logger.debug(f"Token keys: {list(token_data.keys())}")
                        
                        # Check if it's a service account key
                        if 'type' in creds_data and creds_data['type'] == 'service_account':
                            # Service account authentication
                            calendar_logger.info("Using service account authentication")
                            from google.oauth2 import service_account
                            creds = service_account.Credentials.from_service_account_info(
                                creds_data, 
                                scopes=self.scopes
                            )
                        else:
                            # OAuth user credentials - handle the 'installed' format
                            calendar_logger.info("Using OAuth authentication")
                            
                            # Extract OAuth client info from credentials
                            if 'installed' in creds_data:
                                oauth_client_info = creds_data['installed']
                                calendar_logger.debug("Found 'installed' OAuth client info")
                            else:
                                oauth_client_info = creds_data
                                calendar_logger.debug("Using direct OAuth client info")
                            
                            # Create credentials from token data
                            # The token data has the format we need for from_authorized_user_info
                            creds = Credentials.from_authorized_user_info(token_data, self.scopes)
                        
                        if creds and creds.valid:
                            calendar_logger.info("Database authentication successful - credentials valid")
                            return build('calendar', 'v3', credentials=creds)
                        elif creds and creds.expired and creds.refresh_token:
                            calendar_logger.info("Refreshing expired credentials")
                            creds.refresh(Request())
                            return build('calendar', 'v3', credentials=creds)
                        else:
                            calendar_logger.warning("Credentials obtained but not valid")
                            
                    except Exception as db_auth_error:
                        calendar_logger.warning(f"Database authentication failed: {db_auth_error}")
                        # Continue to fallback authentication
            
            # Fallback to local files
            credentials_file = 'credentials.json'
            token_file = 'token.json'
            
            creds = None
            if os.path.exists(token_file):
                try:
                    creds = Credentials.from_authorized_user_file(token_file, self.scopes)
                except Exception as file_auth_error:
                    calendar_logger.warning(f"File authentication failed: {file_auth_error}")
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as refresh_error:
                        calendar_logger.warning(f"Token refresh failed: {refresh_error}")
                        creds = None
                
                if not creds:
                    if os.path.exists(credentials_file):
                        try:
                            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, self.scopes)
                            creds = flow.run_local_server(port=0)
                            
                            with open(token_file, 'w') as token:
                                token.write(creds.to_json())
                        except Exception as flow_error:
                            calendar_logger.error(f"OAuth flow failed: {flow_error}")
                    else:
                        raise Exception("No credentials file found and no valid database credentials")
            
            if creds:
                return build('calendar', 'v3', credentials=creds)
            else:
                raise Exception("Could not obtain valid credentials from any source")
                
        except Exception as e:
            raise Exception(f"Calendar authentication failed: {str(e)}")
    
    def get_timezone_info(self) -> Dict[str, any]:
        """Get timezone information for debugging"""
        try:
            tz = pytz.timezone(self.timezone)
            now = datetime.now(pytz.UTC)
            local_now = now.astimezone(tz)
            
            return {
                'timezone': self.timezone,
                'utc_offset': local_now.utcoffset().total_seconds() / 3600,  # hours
                'is_dst': local_now.dst() != timedelta(0),
                'current_utc': now.isoformat(),
                'current_local': local_now.isoformat(),
                'timezone_name': local_now.tzname()
            }
        except Exception as e:
            return {
                'timezone': self.timezone,
                'error': str(e)
            }
    
    def debug_authentication(self, user_id: Optional[int] = None) -> Dict[str, any]:
        """Debug authentication issues and return diagnostic information"""
        debug_info = {
            'user_id': user_id,
            'database_credentials': None,
            'local_files': {},
            'errors': []
        }
        
        try:
            # Check database credentials
            if user_id:
                auth_record = GoogleCalendarAuth.query.filter_by(user_id=user_id).first()
                if auth_record:
                    debug_info['database_credentials'] = {
                        'has_credentials': bool(auth_record.credentials_json),
                        'has_token': bool(auth_record.token_json),
                        'account_email': auth_record.account_email,
                        'status': auth_record.status,
                        'last_tested': auth_record.last_tested_at.isoformat() if auth_record.last_tested_at else None,
                        'last_error': auth_record.last_error
                    }
                    
                    if auth_record.credentials_json:
                        try:
                            creds_data = json.loads(auth_record.credentials_json)
                            debug_info['database_credentials']['credentials_type'] = creds_data.get('type', 'OAuth')
                            
                            # Check for OAuth client info (might be nested under 'installed')
                            if 'installed' in creds_data:
                                oauth_info = creds_data['installed']
                                debug_info['database_credentials']['has_client_id'] = 'client_id' in oauth_info
                                debug_info['database_credentials']['has_client_secret'] = 'client_secret' in oauth_info
                                debug_info['database_credentials']['oauth_format'] = 'installed'
                            else:
                                debug_info['database_credentials']['has_client_id'] = 'client_id' in creds_data
                                debug_info['database_credentials']['has_client_secret'] = 'client_secret' in creds_data
                                debug_info['database_credentials']['oauth_format'] = 'direct'
                            
                            # Check for service account fields
                            debug_info['database_credentials']['is_service_account'] = 'type' in creds_data and creds_data['type'] == 'service_account'
                            
                        except Exception as parse_error:
                            debug_info['database_credentials']['parse_error'] = str(parse_error)
                    
                    if auth_record.token_json:
                        try:
                            token_data = json.loads(auth_record.token_json)
                            debug_info['database_credentials']['has_refresh_token'] = 'refresh_token' in token_data
                            debug_info['database_credentials']['token_keys'] = list(token_data.keys())
                        except Exception as parse_error:
                            debug_info['database_credentials']['token_parse_error'] = str(parse_error)
                else:
                    debug_info['database_credentials'] = {'error': 'No auth record found for user'}
            
            # Check local files
            credentials_file = 'credentials.json'
            token_file = 'token.json'
            
            debug_info['local_files']['credentials_exists'] = os.path.exists(credentials_file)
            debug_info['local_files']['token_exists'] = os.path.exists(token_file)
            
            if os.path.exists(credentials_file):
                try:
                    with open(credentials_file, 'r') as f:
                        creds_data = json.load(f)
                        debug_info['local_files']['credentials_type'] = creds_data.get('type', 'unknown')
                except Exception as file_error:
                    debug_info['local_files']['credentials_error'] = str(file_error)
            
            if os.path.exists(token_file):
                try:
                    with open(token_file, 'r') as f:
                        token_data = json.load(f)
                        debug_info['local_files']['token_has_refresh'] = 'refresh_token' in token_data
                except Exception as file_error:
                    debug_info['local_files']['token_error'] = str(file_error)
            
        except Exception as e:
            calendar_logger.error(f"Debug authentication error: {str(e)}")
            debug_info['errors'].append(f"Debug error: {str(e)}")
        
        return debug_info
    
    def check_availability(self, service: any, start_time: datetime, end_time: datetime) -> bool:
        """Check if a time slot is available"""
        events_result = service.events().list(
            calendarId=self.calendar_id,
            timeMin=start_time.isoformat(),
            timeMax=end_time.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return len(events) == 0
    
    def find_available_slots(self, service: any, date: datetime, duration_minutes: int = 30) -> List[datetime]:
        """Find available time slots for a given date"""
        tz = pytz.timezone(self.timezone)
        date = date.astimezone(tz)
        
        start_of_day = date.replace(hour=self.working_hours[0], minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=self.working_hours[1], minute=0, second=0, microsecond=0)
        
        current_time = start_of_day
        available_slots = []
        
        while current_time + timedelta(minutes=duration_minutes) <= end_of_day:
            end_time = current_time + timedelta(minutes=duration_minutes)
            
            if self.check_availability(service, current_time, end_time):
                available_slots.append(current_time)
            
            current_time += timedelta(minutes=30)
        
        return available_slots
    
    def create_event(self, service: any, start_time: datetime, end_time: datetime, title: str) -> Tuple[bool, str]:
        """Create a calendar event"""
        # Log timezone information for debugging
        calendar_logger.info(f"Creating event with timezone: {self.timezone}")
        calendar_logger.info(f"Start time: {start_time} (timezone: {start_time.tzinfo})")
        calendar_logger.info(f"End time: {end_time} (timezone: {end_time.tzinfo})")
        
        # Send local times with timezone information to Google Calendar
        # This prevents the date shift issue - Google Calendar will handle the timezone conversion correctly
        calendar_logger.info(f"Start time (local): {start_time}")
        calendar_logger.info(f"End time (local): {end_time}")
        
        event = {
            'summary': title,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': self.timezone,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': self.timezone,
            },
            'reminders': {
                'useDefault': True,
            },
        }
        
        try:
            calendar_logger.info(f"Attempting to create event: {title} at {start_time.isoformat()}")
            calendar_logger.info(f"Event payload: {json.dumps(event, indent=2)}")
            
            event = service.events().insert(
                calendarId=self.calendar_id,
                body=event,
                sendNotifications=True
            ).execute()
            
            calendar_logger.info(f"Event created successfully: {event.get('htmlLink')}")
            # Log the created event details for verification
            if 'start' in event:
                calendar_logger.info(f"Created event start: {event['start']}")
            if 'end' in event:
                calendar_logger.info(f"Created event end: {event['end']}")
            
            return True, event.get('htmlLink')
        except Exception as e:
            calendar_logger.error(f"Error creating calendar event: {str(e)}")
            return False, str(e)


class AppointmentProcessor:
    """Processes and manages appointments"""
    
    def __init__(self, appointment_duration: int = None):
        self.appointment_duration = appointment_duration or CALENDAR_CONFIG['APPOINTMENT_DURATION']
    
    def create_datetime_object(self, date_str: str, time_str: str, timezone: str = None) -> datetime:
        """Create datetime object from date and time strings"""
        tz = pytz.timezone(timezone or CALENDAR_CONFIG['TIMEZONE'])
        
        # Handle relative dates first
        if date_str.lower() in ['today', 'tmr', 'tmrw']:
            # Use UTC now and convert to target timezone to avoid midnight boundary issues
            utc_now = datetime.now(pytz.UTC)
            date_obj = utc_now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_str.lower() == 'tomorrow':
            # Use UTC now and convert to target timezone, then add one day
            utc_now = datetime.now(pytz.UTC)
            today_local = utc_now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
            date_obj = today_local + timedelta(days=1)
        else:
            try:
                # Try to parse as YYYY-MM-DD format
                # Create naive datetime first, then localize to avoid timezone conversion issues
                naive_date = datetime.strptime(date_str, '%Y-%m-%d')
                date_obj = tz.localize(naive_date)
            except ValueError:
                # If parsing fails, default to today
                ai_logger.warning(f"Could not parse date '{date_str}', defaulting to today")
                utc_now = datetime.now(pytz.UTC)
                date_obj = utc_now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Parse time
        try:
            hour, minute = map(int, time_str.split(':'))
            # Use replace to avoid timezone conversion issues
            date_obj = date_obj.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, AttributeError):
            # If time parsing fails, default to 9 AM
            ai_logger.warning(f"Could not parse time '{time_str}', defaulting to 9:00 AM")
            date_obj = date_obj.replace(hour=CALENDAR_CONFIG['WORKING_HOURS'][0], minute=0, second=0, microsecond=0)
        
        ai_logger.debug(f"Created datetime object: {date_obj} (timezone: {date_obj.tzinfo})")
        
        # No date adjustment needed - the issue is in how we send the event to Google Calendar
        # The fix is in the create_event method where we convert to UTC
        return date_obj
    

    def process_appointment_request_enhanced(self, text: str, calendar_manager: CalendarManager, 
                                          llm_processor: LLMProcessor, service: any) -> str:
        """Enhanced appointment processing with better availability checking and user interaction"""
        try:
            # Extract details using LLM
            details = llm_processor.extract_appointment_details(text)
            ai_logger.info(f"Extracted meeting details: {details}")
            
            # Create datetime objects
            start_time = self.create_datetime_object(details['date'], details['time'])
            end_time = start_time + timedelta(minutes=self.appointment_duration)
            
            # Log timezone information for debugging
            ai_logger.info(f"Appointment timezone info: {calendar_manager.get_timezone_info()}")
            ai_logger.info(f"Start time: {start_time} (timezone: {start_time.tzinfo})")
            ai_logger.info(f"End time: {end_time} (timezone: {end_time.tzinfo})")
            
            # Check if the requested time is in the past
            now = datetime.now(start_time.tzinfo)
            if start_time < now:
                return f"I'm sorry, but {start_time.strftime('%A, %B %d at %I:%M %p')} is in the past. Please suggest a future time."
            
            # Check availability for the requested time
            if calendar_manager.check_availability(service, start_time, end_time):
                # Time slot is available - schedule the appointment
                success, event_link = calendar_manager.create_event(service, start_time, end_time, details['title'])
                if success:
                    return f"Perfect! I've successfully scheduled '{details['title']}' for {start_time.strftime('%A, %B %d at %I:%M %p')}. The meeting will last {self.appointment_duration} minutes."
                else:
                    return f"I'm sorry, but I couldn't schedule the meeting due to an error: {event_link}"
            else:
                # Time slot is not available - find alternatives
                return self._suggest_alternative_slots(calendar_manager, service, start_time, details['title'])
        
        except Exception as e:
            return f"Error processing appointment request: {str(e)}"
    
    def _suggest_alternative_slots(self, calendar_manager: CalendarManager, service: any, 
                                  requested_time: datetime, title: str) -> str:
        """Suggest alternative time slots when requested time is unavailable"""
        try:
            # First, check the same day for available slots
            available_slots = calendar_manager.find_available_slots(service, requested_time)
            
            if available_slots:
                # Format available slots for user
                formatted_slots = []
                for slot in available_slots[:5]:  # Show up to 5 alternatives
                    formatted_slots.append(slot.strftime('%I:%M %p'))
                
                slots_text = ', '.join(formatted_slots)
                return f"I'm sorry, but {requested_time.strftime('%I:%M %p')} on {requested_time.strftime('%A, %B %d')} is not available. However, I found these available time slots on the same day: {slots_text}. Please let me know which time works better for you, or suggest another time."
            
            # If no slots on the same day, check the next few days
            next_days = []
            for day_offset in range(1, 4):  # Check next 3 days
                next_day = requested_time + timedelta(days=day_offset)
                available_slots = calendar_manager.find_available_slots(service, next_day)
                if available_slots:
                    next_days.append({
                        'date': next_day,
                        'slots': available_slots[:3]  # Top 3 slots per day
                    })
            
            if next_days:
                # Build response with next available days
                response_parts = [f"I'm sorry, but {requested_time.strftime('%I:%M %p')} on {requested_time.strftime('%A, %B %d')} is not available."]
                response_parts.append("Here are some available times on upcoming days:")
                
                for day_info in next_days:
                    date_str = day_info['date'].strftime('%A, %B %d')
                    slots_str = ', '.join([slot.strftime('%I:%M %p') for slot in day_info['slots']])
                    response_parts.append(f"• {date_str}: {slots_str}")
                
                response_parts.append("Please let me know which date and time works better for you.")
                return ' '.join(response_parts)
            
            # If no availability found in the next few days
            return f"I'm sorry, but I couldn't find any available time slots on {requested_time.strftime('%A, %B %d')} or the next few days. Please suggest a different date or time, or contact me directly to discuss scheduling options."
            
        except Exception as e:
            return f"Error finding alternative slots: {str(e)}"


class VoiceAssistant:
    """Main voice assistant orchestrator"""
    
    def __init__(self, voice_response: bool = None):
        self.voice_response = voice_response if voice_response is not None else VOICE_CONFIG['VOICE_RESPONSE']
        self.audio_processor = AudioProcessor()
        self.llm_processor = LLMProcessor()
        self.calendar_manager = CalendarManager()
        self.appointment_processor = AppointmentProcessor()
    
    def speak_response(self, text: str) -> None:
        """Convert text to speech"""
        try:
            if TTS_CONFIG['ENGINE'] == 'espeak':
                voice_logger.debug(f"Speaking text: {text[:50]}...")
                subprocess.run(['espeak', '-s', str(TTS_CONFIG['SPEED']), text])
                voice_logger.debug("Text-to-speech completed")
            else:
                voice_logger.warning(f"TTS engine {TTS_CONFIG['ENGINE']} not implemented yet")
        except FileNotFoundError:
            voice_logger.error("espeak not installed. Please install with: sudo apt-get install espeak")
        except Exception as e:
            voice_logger.error(f"Text-to-speech error: {e}")
    
    def process_voice_input(self, audio_file_path: str, user_id: Optional[int] = None) -> str:
        """Process voice input and return response"""
        try:
            voice_logger.info(f"Processing voice input from: {audio_file_path}")
            
            # Transcribe audio
            transcript = self.audio_processor.transcribe_with_whisper(audio_file_path)
            if not transcript:
                voice_logger.warning("Could not transcribe audio")
                return "Could not transcribe your audio. Please try again."
            
            voice_logger.info(f"Transcribed text: {transcript}")
            
            # Authenticate with calendar
            voice_logger.debug("Authenticating with Google Calendar")
            service = self.calendar_manager.authenticate(user_id)
            voice_logger.info("Calendar authentication successful")
            
            # Process appointment request with enhanced availability checking
            voice_logger.debug("Processing appointment request")
            response = self.appointment_processor.process_appointment_request_enhanced(
                transcript, self.calendar_manager, self.llm_processor, service
            )
            
            # Speak response if enabled
            if self.voice_response:
                voice_logger.debug("Speaking response")
                self.speak_response(response)
            
            voice_logger.info("Voice input processing completed successfully")
            return response
            
        except Exception as e:
            error_msg = f"Error processing voice input: {str(e)}"
            voice_logger.error(error_msg, exc_info=True)
            if self.voice_response:
                self.speak_response(error_msg)
            return error_msg
    
    def cleanup_temp_file(self, file_path: str) -> None:
        """Clean up temporary audio file"""
        try:
            os.remove(file_path)
        except:
            pass



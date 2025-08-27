"""
Configuration settings for the AI Voice Assistant
"""

# Audio Processing Configuration
AUDIO_CONFIG = {
    'SAMPLE_RATE': 44100,
    'CHANNELS': 1,
    'RECORD_SECONDS': 5,
    'SUPPORTED_FORMATS': ['wav', 'mp3', 'ogg', 'm4a']
}


# Google Calendar Configuration
CALENDAR_CONFIG = {
    'SCOPES': ['https://www.googleapis.com/auth/calendar'],
    'CALENDAR_ID': 'primary',
    'TIMEZONE': 'Europe/Brussels',
    'WORKING_HOURS': (9, 17),  # 9 AM to 5 PM
    'APPOINTMENT_DURATION': 30  # minutes
}
LLM_CONFIG = {'Timezone': 'Europe/Brussels'}

# Voice Assistant Configuration
VOICE_CONFIG = {
    'VOICE_RESPONSE': True,  # Enable/disable text-to-speech
    'TEMP_DIR': None,  # Will use system temp directory if None
    'CLEANUP_TEMP_FILES': True
}

# Whisper Configuration
WHISPER_CONFIG = {
    'MODEL_SIZE': 'base',  # 'tiny', 'base', 'small', 'medium', 'large'
    'FP16': False,
    'VERBOSE': True
}

# Text-to-Speech Configuration
TTS_CONFIG = {
    'ENGINE': 'espeak',  # 'espeak', 'gtts', 'pyttsx3'
    'SPEED': 150,
    'VOLUME': 1.0
}

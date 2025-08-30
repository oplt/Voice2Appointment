import os
from dataclasses import dataclass
from dotenv import load_dotenv
import os
import logging

load_dotenv()

def setup_logging():
    """Centralized logging configuration with environment variable support"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Clear any existing handlers to prevent conflicts
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler("VoiceAsst.log")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Configure root logger
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Prevent Flask from overriding our logging
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('werkzeug').handlers = []



@dataclass
class Settings:

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', '')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.getenv('FLASK_TESTING', 'False').lower() == 'true'

    # Mail Configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('EMAIL_USER')
    MAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

    # Twilio Configuration
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

    DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

    CALENDAR = {
        'SCOPES': ['https://www.googleapis.com/auth/calendar'],
        'CALENDAR_ID': 'primary',
        'TIMEZONE': 'Europe/Brussels',
        'WORKING_HOURS': (9, 17),  # 9 AM to 5 PM
        'APPOINTMENT_DURATION': 30  # minutes
    }
    # Other Configurations


settings = Settings()
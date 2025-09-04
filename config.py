from dataclasses import dataclass, field
from dotenv import load_dotenv
import os, time
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any
from datetime import timedelta


load_dotenv()


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # UTC timestamps (optional)
    logging.Formatter.converter = time.gmtime

    # Reset root handlers
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        "logs/VoiceAsst.log", maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, log_level, logging.INFO))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    logging.getLogger("werkzeug").setLevel(logging.INFO)



@dataclass
class Settings:
    SECRET_KEY: str = os.getenv('SECRET_KEY', '')
    DEBUG: bool = False
    TESTING: bool = False

    SQLALCHEMY_DATABASE_URI: str = os.getenv('DATABASE_URL', '')
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: Dict[str, Any] = field(default_factory=dict)

    MAIL_SERVER: str = 'smtp.gmail.com'
    MAIL_PORT: int = 587
    MAIL_USE_TLS: bool = True
    MAIL_USERNAME: Optional[str] = os.getenv('EMAIL_USER')
    MAIL_PASSWORD: Optional[str] = os.getenv('EMAIL_PASSWORD')

    TWILIO_ACCOUNT_SID: Optional[str] = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN: Optional[str] = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER: Optional[str] = os.getenv('TWILIO_PHONE_NUMBER')
    CALL_EXPIRES_IN: int = 5

    DEEPGRAM_API_KEY: Optional[str] = os.getenv('DEEPGRAM_API_KEY')

    FERNET_KEY: Optional[str] = os.getenv('FERNET_KEY')

    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    CELERYBEAT_SCHEDULE = {
        'fetch-twilio-calls-every-hour': {
            'task': 'app.tasks.twilio_tasks.fetch_twilio_calls',
            'schedule': timedelta(seconds=3600),  # Every hour
        },
    }


settings = Settings()
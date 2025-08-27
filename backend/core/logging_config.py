"""
Logging configuration for the Voice Assistant project
"""

import logging
import logging.handlers
import os
from datetime import datetime

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Log file paths
app_log_file = os.path.join(logs_dir, 'voice_assistant.log')
ai_log_file = os.path.join(logs_dir, 'ai_processor.log')
auth_log_file = os.path.join(logs_dir, 'auth.log')
error_log_file = os.path.join(logs_dir, 'errors.log')

def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """Setup a logger with file and console handlers"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Console handler (INFO level and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # File handler (DEBUG level and above)
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
    
    logger.addHandler(console_handler)
    
    return logger

def setup_error_logger() -> logging.Logger:
    """Setup a dedicated error logger"""
    error_logger = logging.getLogger('errors')
    error_logger.setLevel(logging.ERROR)
    
    if error_logger.handlers:
        return error_logger
    
    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    ))
    
    error_logger.addHandler(error_handler)
    
    return error_logger

# Setup main loggers
app_logger = setup_logger('voice_assistant', app_log_file)
ai_logger = setup_logger('ai_processor', ai_log_file)
auth_logger = setup_logger('auth', auth_log_file)
error_logger = setup_error_logger()

# Flask app logger
flask_logger = setup_logger('flask_app')

# Database logger
db_logger = setup_logger('database')

# Calendar logger
calendar_logger = setup_logger('calendar')

# Voice processing logger
voice_logger = setup_logger('voice_processing')

# Phone integration logger
phone_logger = setup_logger('phone', os.path.join(logs_dir, 'phone.log'))

def log_function_call(func):
    """Decorator to log function calls with parameters"""
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        logger.debug(f"Calling {func.__name__} with args: {args}, kwargs: {kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed with error: {str(e)}", exc_info=True)
            raise
    return wrapper

def log_execution_time(func):
    """Decorator to log function execution time"""
    import time
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"{func.__name__} executed in {execution_time:.2f} seconds")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.2f} seconds with error: {str(e)}", exc_info=True)
            raise
    return wrapper

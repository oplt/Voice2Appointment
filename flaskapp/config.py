import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))


class Config:
	SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
	SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
		'sqlite:///' + os.path.join(basedir, '..', 'app.db')
	SQLALCHEMY_TRACK_MODIFICATIONS = False
	
	# Mail settings
	MAIL_SERVER = os.environ.get('MAIL_SERVER')
	MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
	MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
	MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
	MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
	
	# Twilio settings
	TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
	TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
	TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
	
	# Google Calendar settings
	GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE') or 'credentials.json'
	GOOGLE_TOKEN_FILE = os.environ.get('GOOGLE_TOKEN_FILE') or 'token.json'

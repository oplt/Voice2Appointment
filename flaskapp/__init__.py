from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flaskapp.config import Config
import logging


db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'users.login'
login_manager.login_message_category = 'info'
mail = Mail()


def create_app(config_class=Config):
	app = Flask(__name__)
	app.config.from_object(Config)

	# Setup logging
	from backend.core.logging_config import setup_logger
	flask_logger = setup_logger('flask_app')
	
	# Configure Flask's built-in logger
	app.logger.handlers = flask_logger.handlers
	app.logger.setLevel(flask_logger.level)

	db.init_app(app)
	bcrypt.init_app(app)
	login_manager.init_app(app)
	mail.init_app(app)

	from flaskapp.users.routes import users
	from flaskapp.main.routes import main
	from flaskapp.errors.handlers import errors
	from flaskapp.calendar.calendar import google_bp
	from flaskapp.phone.routes import phone
	app.register_blueprint(users)
	app.register_blueprint(main)
	app.register_blueprint(errors)
	app.register_blueprint(google_bp)
	app.register_blueprint(phone, url_prefix='/phone')

	flask_logger.info("Flask application created successfully")
	return app
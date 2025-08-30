# __init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
import logging
from config import settings as Config

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'users.login'
login_manager.login_message_category = 'info'
mail = Mail()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions with app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Import models here to avoid circular imports
    with app.app_context():
        from flaskapp.database.models import User

        @login_manager.user_loader
        def load_user(user_id):
            try:
                user_id_int = int(user_id)
                return User.query.get(user_id_int)
            except (ValueError, TypeError):
                return None
            except Exception as e:
                logging.error(f"Error loading user: {e}")
                return None

    # Import and register blueprints
    from flaskapp.users.routes import users
    from flaskapp.main.routes import main
    from flaskapp.errors.handlers import errors
    from flaskapp.phone.routes import phone_bp

    app.register_blueprint(users)
    app.register_blueprint(main)
    app.register_blueprint(errors)
    app.register_blueprint(phone_bp, url_prefix='/phone')

    logging.info("Flask application created successfully")
    return app
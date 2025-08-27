from flaskapp import create_app
from flaskapp import db
import logging

# Setup logging for the main application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = create_app()

if __name__ == '__main__':
    logger.info("Starting Voice Assistant application")
    with app.app_context():
        logger.info("Creating database tables")
        db.create_all()
        logger.info("Database tables created successfully")
    
    logger.info("Starting Flask development server on localhost:5001")
    app.run(debug=True, host='localhost', port=5001)
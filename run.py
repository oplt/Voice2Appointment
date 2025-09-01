# run.py
import asyncio
import threading
import websockets
from flaskapp import create_app, db
from flaskapp.utils.websocket_handler import twilio_handler
import logging
from config import settings, setup_logging


app = create_app()


def run_websocket_server():
    """Run WebSocket server in a separate thread"""
    async def main():
        with app.app_context():
            server = await websockets.serve(twilio_handler, "0.0.0.0", 5001)
            logging.info("WebSocket server started on localhost:5001")
            await asyncio.Future()

    asyncio.run(main())


if __name__ == '__main__':
    setup_logging()
    logging.info("Starting Voice Assistant application")

    with app.app_context():
        logging.info("Creating database tables")
        db.create_all()
        logging.info("Database tables created successfully")

    # Start WebSocket server in background thread
    websocket_thread = threading.Thread(target=run_websocket_server, daemon=True)
    websocket_thread.start()
    logging.info("WebSocket server thread started")

    # Run Flask app on different port
    logging.info("Starting Flask server on localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
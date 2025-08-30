# run.py
import asyncio
import threading
import websockets
from flaskapp import create_app, db
from flaskapp.utils.websocket_handler import twilio_handler
import logging
from config import settings, setup_logging
import re

app = create_app()

async def websocket_handler(websocket, path):
    """Handle WebSocket connections with user authentication"""
    try:
        # Extract user_id from path (e.g., /ws/123)
        user_id_match = re.match(r'/ws/(\d+)', path)
        if user_id_match:
            user_id = int(user_id_match.group(1))
            logging.info(f"WebSocket connection established for user {user_id}")
            
            # Handle the WebSocket connection with user_id
            await twilio_handler(websocket, user_id)
        else:
            logging.warning(f"Invalid WebSocket path: {path}")
            await websocket.close(1008, "Invalid path")
            
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        await websocket.close(1011, "Internal error")

def run_websocket_server():
    """Run WebSocket server in a separate thread"""
    async def main():
        server = await websockets.serve(websocket_handler, "localhost", 5001)
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
import asyncio, websockets, threading,logging, os
from flaskapp.utils.websocket_handler import twilio_handler
from config import setup_logging
from flaskapp import create_app, db




'''
    TO-DO:
    - Add error handling and logging
    - reminder emails with celery and redis
    - retrieve config.json and user.id on websocket connection from database
    - on dashboard, mirror google calendar view
    - improve config.json content
    - delete and add the components on the dashboard
    - modify app for logistics (add shipment tracking, etc)
    - modify app for restaurants (add menu, orders, etc)
    - modify app for hotels (add room service, bookings, etc)
    - modify app for retail (add product catalog, orders, etc)
    - modify app for healthcare (add patient records, appointments, etc)
    - check for other languages
    - populate unused fields in other tables
    - add visulization for appointments and call sessions
    - test twilio webhook for recording
    - make a Settings table in database for user settings
    '''


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
    app = create_app()

    with app.app_context():
        logging.info("Creating database tables")
        db.create_all()
        logging.info("Database tables created successfully")


    websocket_thread = threading.Thread(target=run_websocket_server, daemon=True)
    websocket_thread.start()
    logging.info("WebSocket server thread started")

    logging.info("Starting Flask server on localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
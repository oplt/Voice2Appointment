"""Production web ASGI entry (HTTP API only — no voice WebSocket).

Run with Gunicorn + UvicornWorker::

    gunicorn asgi:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
"""

from __future__ import annotations

from app.factory import create_app

app = create_app(include_api=True, include_voice=False, title="Voice2Appointment Web API")

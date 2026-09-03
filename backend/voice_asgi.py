"""Production voice gateway ASGI entry (WebSocket only + health).

Run with Uvicorn (async WebSockets)::

    uvicorn voice_asgi:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

from app.factory import create_app

app = create_app(
    include_api=False,
    include_voice=True,
    title="Voice2Appointment Voice Gateway",
)

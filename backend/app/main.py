"""FastAPI application entrypoint (modular monolith).

Default ``app`` includes HTTP API + voice WebSocket (local/dev).
Production splits processes via ``asgi:app`` (web) and ``voice_asgi:app``.
"""

from __future__ import annotations

from app.factory import create_app

app = create_app(include_api=True, include_voice=True)

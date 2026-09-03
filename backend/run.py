"""Run the FastAPI app with uvicorn (local/dev — includes WebSocket routes)."""

from __future__ import annotations

import uvicorn

from app.core.config import settings
from app.core.logging import setup_logging

if __name__ == "__main__":
    setup_logging()
    # Never enable reload in production regardless of DEBUG.
    use_reload = settings.debug and not settings.is_production
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=use_reload,
    )

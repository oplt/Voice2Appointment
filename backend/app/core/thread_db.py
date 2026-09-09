"""Helpers to run sync DB/provider work off the asyncio event loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import anyio

from app.db.session import SessionLocal

T = TypeVar("T")


def run_db_sync(fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Open a Session in this thread, run ``fn(db, ...)``, then close it."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    try:
        return fn(db, *args, **kwargs)  # type: ignore[arg-type]
    finally:
        db.close()


async def to_thread_db(fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Run ``fn`` with a thread-local Session via anyio worker threads."""
    return await anyio.to_thread.run_sync(lambda: run_db_sync(fn, *args, **kwargs))

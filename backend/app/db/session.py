"""Database engine and session factory."""

from __future__ import annotations

import time
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.core.metrics import metrics


class InstrumentedQueuePool(QueuePool):
    """Preserve QueuePool defaults while observing time spent acquiring a connection."""

    def _do_get(self):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        result = "success"
        try:
            return super()._do_get()
        except Exception:  # noqa: BLE001
            result = "failure"
            raise
        finally:
            metrics.observe(
                "db_pool_wait_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"result": result},
            )


_engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("postgresql"):
    _engine_options.update(
        poolclass=InstrumentedQueuePool,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )

engine = create_engine(settings.database_url, **_engine_options) if settings.database_url else None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None


def _pool_checked_out() -> float:
    if engine is None:
        return 0.0
    checked_out = getattr(engine.pool, "checkedout", None)
    if not callable(checked_out):
        return 0.0
    try:
        return float(checked_out())
    except Exception:  # noqa: BLE001
        return 0.0


def _observe_pool() -> None:
    if engine is None:
        return
    metrics.set_gauge("db_pool_checked_out", _pool_checked_out())
    size = getattr(engine.pool, "size", None)
    if callable(size):
        try:
            metrics.set_gauge("db_pool_capacity", float(size()))
        except Exception:  # noqa: BLE001
            pass


if engine is not None:

    @event.listens_for(engine.pool, "checkout")
    def _on_checkout(*_args: object) -> None:
        _observe_pool()

    @event.listens_for(engine.pool, "checkin")
    def _on_checkin(*_args: object) -> None:
        _observe_pool()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: object) -> None:
        info = getattr(connection, "info", None)
        if isinstance(info, dict):
            info["metrics_transaction_started"] = time.perf_counter()

    def _observe_transaction(connection: object, result: str) -> None:
        info = getattr(connection, "info", None)
        if not isinstance(info, dict):
            return
        started = info.pop("metrics_transaction_started", None)
        if isinstance(started, float):
            metrics.observe(
                "db_transaction_duration_ms",
                (time.perf_counter() - started) * 1000.0,
                labels={"result": result},
            )

    @event.listens_for(engine, "commit")
    def _on_commit(connection: object) -> None:
        _observe_transaction(connection, "commit")

    @event.listens_for(engine, "rollback")
    def _on_rollback(connection: object) -> None:
        _observe_transaction(connection, "rollback")


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

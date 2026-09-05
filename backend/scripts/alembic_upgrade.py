#!/usr/bin/env python3
"""Run Alembic upgrade head.

If tables exist but ``alembic_version`` is missing (SQLAlchemy ``create_all``
or a partial apply), add any missing model columns/indexes, stamp head, then
upgrade. Never drop or rewrite user data.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateColumn, CreateIndex

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.db.models  # noqa: E402, F401

logger = logging.getLogger("alembic_upgrade")


def _config() -> Config:
    cfg = Config(str(_BACKEND.parent / "alembic.ini"))
    if settings.database_url:
        cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return cfg


def _version_rows(conn) -> list:
    insp = inspect(conn)
    if "alembic_version" not in set(insp.get_table_names()):
        return []
    return list(conn.execute(text("SELECT version_num FROM alembic_version")))


def _needs_repair(url: str) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            insp = inspect(conn)
            tables = set(insp.get_table_names())
            if "res_user" not in tables:
                return False
            return not _version_rows(conn)
    finally:
        engine.dispose()


def _repair_to_models(url: str) -> None:
    """Create missing tables; ADD missing columns/indexes. No drops."""
    engine = create_engine(url)
    try:
        Base.metadata.create_all(bind=engine)
        dialect = engine.dialect
        preparer = dialect.identifier_preparer
        with engine.begin() as conn:
            insp = inspect(conn)
            for table in Base.metadata.sorted_tables:
                if not insp.has_table(table.name):
                    continue
                existing_cols = {c["name"] for c in insp.get_columns(table.name)}
                quoted_table = preparer.quote(table.name)
                for col in table.columns:
                    if col.name in existing_cols:
                        continue
                    col_ddl = str(CreateColumn(col).compile(dialect=dialect))
                    logger.info("Adding column %s.%s", table.name, col.name)
                    conn.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {col_ddl}"))
                existing_ix = {
                    ix["name"] for ix in insp.get_indexes(table.name) if ix.get("name")
                }
                for ix in table.indexes:
                    if not ix.name or ix.name in existing_ix:
                        continue
                    logger.info("Creating index %s", ix.name)
                    conn.execute(CreateIndex(ix))
    finally:
        engine.dispose()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    url = (settings.database_url or "").strip()
    if not url:
        logger.error("DATABASE_URL is not configured")
        return 1
    cfg = _config()
    if _needs_repair(url):
        logger.info(
            "Schema exists without alembic_version; repairing to current models then stamping head"
        )
        _repair_to_models(url)
        command.stamp(cfg, "head")
    command.upgrade(cfg, "head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

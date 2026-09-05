"""Destructive PostgreSQL migration-path verification for an isolated CI database."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DEPLOYED_REVISION = "c3d4e5f6a7b8"
PREVIOUS_HEAD = "c9d0e1f2a3b4"
CURRENT_HEAD = "d0e1f2a3b4c5"


def _config(database_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _require_isolated_ci_database(database_url: str) -> None:
    database = make_url(database_url).database or ""
    if os.getenv("ALLOW_DESTRUCTIVE_MIGRATION_TEST") != "1" or not database.endswith(
        "_ci"
    ):
        raise RuntimeError(
            "Refusing destructive migration test: use an *_ci database and set "
            "ALLOW_DESTRUCTIVE_MIGRATION_TEST=1"
        )


def _seed_deployed_revision(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO res_user (
                    id, username, email, image_file, password,
                    twilio_account_sid, twilio_auth_token, deepgram_api_key,
                    config_json, twilio_last_synced_at
                ) VALUES (
                    701, 'migration-user', 'migration@example.invalid',
                    'default.jpg', 'password-hash',
                    'ACaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'enc:twilio',
                    'enc:deepgram', '{}', now()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO callsession (
                    id, user_id, call_sid, status, data, started_at
                ) VALUES (
                    702, 701, 'CAbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                    'completed', CAST('{"source":"migration"}' AS jsonb), now()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO appointment (
                    id, user_id, callsession_id, summary, start_datetime,
                    end_datetime, timezone, status, google_calendar_event_id,
                    idempotency_key, created_at, updated_at
                ) VALUES (
                    703, 701, 702, 'Migration appointment',
                    '2026-09-07T10:00:00+00:00', '2026-09-07T10:30:00+00:00',
                    'UTC', 'confirmed', 'provider-event-703',
                    'migration-idempotency-703', now(), now()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO google_calendar_auth (
                    id, user_id, provider, credentials_json, token_json,
                    revoked, status, created_at, updated_at
                ) VALUES (
                    704, 701, 'google', 'enc:credentials', 'enc:token',
                    false, 'connected', now(), now()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO twilio_call_analytics (
                    id, user_id, date, call_data, processed_metrics,
                    created_at, updated_at
                ) VALUES (
                    705, 701, '2026-09-04', CAST('{"calls":1}' AS jsonb),
                    CAST('{"count":1}' AS jsonb), now(), now()
                )
                """
            )
        )
    engine.dispose()


def _reset_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _assert_preserved(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT u.twilio_auth_token, u.deepgram_api_key, c.user_id,
                       a.user_id, a.callsession_id, a.google_calendar_event_id,
                       g.user_id, g.token_json, t.user_id,
                       a.provider_attempt_count, a.provider_calendar_id
                FROM res_user u
                JOIN callsession c ON c.user_id = u.id
                JOIN appointment a ON a.callsession_id = c.id
                JOIN google_calendar_auth g ON g.user_id = u.id
                JOIN twilio_call_analytics t ON t.user_id = u.id
                WHERE u.id = 701
                """
            )
        ).one()
        assert row == (
            "enc:twilio",
            "enc:deepgram",
            701,
            701,
            702,
            "provider-event-703",
            701,
            "enc:token",
            701,
            0,
            "primary",
        )
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == CURRENT_HEAD
    engine.dispose()


def main() -> None:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    _require_isolated_ci_database(database_url)
    config = _config(database_url)

    _reset_schema(database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    _reset_schema(database_url)
    command.upgrade(config, DEPLOYED_REVISION)
    _seed_deployed_revision(database_url)
    command.upgrade(config, "head")
    _assert_preserved(database_url)
    command.downgrade(config, PREVIOUS_HEAD)
    command.upgrade(config, "head")
    _assert_preserved(database_url)
    command.check(config)


if __name__ == "__main__":
    main()

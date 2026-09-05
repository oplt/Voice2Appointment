"""Validated transient Twilio recording processing."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CallSession, User
from app.telephony.security import (
    assert_valid_twilio_sid,
    is_allowed_twilio_media_host,
    twilio_recording_api_url,
)

RECORDING_DIR = Path(os.environ.get("RECORDING_DIR", "/tmp/voice_recordings"))
_AUDIO_MIME_PREFIXES = ("audio/",)


def _validated_content_length(headers: Any, maximum: int) -> int | None:
    raw = (headers.get("Content-Length") or "").strip()
    if not raw:
        return None
    try:
        length = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid recording content length") from exc
    if length < 0 or length > maximum:
        raise ValueError("recording exceeds size limit")
    return length


def _record_processing_result(
    db: Session,
    call: CallSession,
    *,
    byte_count: int,
    checksum: str,
) -> None:
    data = dict(call.data or {})
    data["recording_processing"] = {
        "status": "processed_transiently",
        "bytes": byte_count,
        "sha256": checksum,
    }
    call.data = data
    call.recording_path = None
    call.recording_downloaded_at = datetime.now(timezone.utc)
    db.add(call)
    db.commit()


def process_recording_download(
    *,
    recording_sid: str,
    recording_url: str,
    call_sid: str,
    account_sid: str | None,
    user_id: int | None,
    session_factory: Callable[[], Session] | None,
) -> dict[str, Any]:
    """Download, validate, process, and always remove transient recording bytes."""
    if session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    if not recording_sid or not call_sid:
        return {"ok": False, "error": "missing arguments"}

    recording_sid = assert_valid_twilio_sid(recording_sid, prefix="RE")
    call_sid = assert_valid_twilio_sid(call_sid, prefix="CA")
    db = session_factory()
    temp_path: str | None = None
    try:
        call = db.scalar(select(CallSession).where(CallSession.call_sid == call_sid))
        if call is None:
            return {"ok": False, "error": "call session not found"}
        if user_id is not None and call.user_id != user_id:
            return {"ok": False, "error": "ownership mismatch"}

        user = db.get(User, call.user_id)
        if user is None:
            return {"ok": False, "error": "user not found"}
        if not user.twilio_account_sid or not user.twilio_auth_token:
            return {"ok": False, "error": "twilio credentials missing"}

        effective_account = assert_valid_twilio_sid(
            account_sid or user.twilio_account_sid,
            prefix="AC",
        )
        if effective_account != user.twilio_account_sid:
            return {"ok": False, "error": "account mismatch"}

        audio_url = twilio_recording_api_url(
            account_sid=effective_account,
            recording_sid=recording_sid,
        )
        if recording_url and recording_url.rstrip("/") != audio_url.rstrip("/"):
            supplied = urlparse(recording_url)
            if supplied.scheme != "https" or not is_allowed_twilio_media_host(
                supplied.hostname or ""
            ):
                return {"ok": False, "error": "disallowed recording host"}

        RECORDING_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(RECORDING_DIR, 0o700)
        with requests.get(
            audio_url,
            auth=(user.twilio_account_sid, user.twilio_auth_token),
            timeout=settings.recording_download_timeout_seconds,
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                return {"ok": False, "error": "redirect refused"}
            response.raise_for_status()
            content_type = (
                (response.headers.get("Content-Type") or "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if not content_type or not any(
                content_type.startswith(prefix) for prefix in _AUDIO_MIME_PREFIXES
            ):
                return {"ok": False, "error": "unexpected content type"}
            _validated_content_length(response.headers, settings.recording_max_bytes)

            digest = hashlib.sha256()
            written = 0
            with tempfile.NamedTemporaryFile(
                dir=RECORDING_DIR,
                prefix="recording-",
                suffix=".partial",
                delete=False,
            ) as temporary:
                temp_path = temporary.name
                os.chmod(temp_path, 0o600)
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > settings.recording_max_bytes:
                        raise ValueError("recording exceeds size limit")
                    digest.update(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())

        # Deletion is part of successful processing: do not persist success while
        # a transient copy remains on disk.
        Path(temp_path).unlink()
        temp_path = None
        _record_processing_result(
            db,
            call,
            byte_count=written,
            checksum=digest.hexdigest(),
        )
        return {"ok": True, "processed_bytes": written}
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                # Do not report success while transient content remains.
                db.rollback()
                raise
        db.close()

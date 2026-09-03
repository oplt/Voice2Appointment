"""Call history HTTP routes (P4-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.calls import service as calls_service
from app.calls.schemas import CallSessionDetailOut, CallSessionListOut, CallSessionOut
from app.core.errors import NotFoundError, map_exception, raise_http
from app.db.models import User

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("", response_model=CallSessionListOut)
def list_calls(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> CallSessionListOut:
    try:
        rows, next_cursor = calls_service.list_call_sessions(
            db, current_user.id, limit=limit, cursor=cursor
        )
    except ValueError as exc:
        raise_http(map_exception(exc))
    items = [
        CallSessionOut.model_validate(calls_service.to_list_item(r)) for r in rows
    ]
    return CallSessionListOut(items=items, next_cursor=next_cursor, limit=limit)


@router.delete("/{call_id}/content")
def delete_call_content(
    call_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    from app.core.errors import AppError, NotFoundError, raise_http
    from app.privacy import service as privacy_service

    try:
        return privacy_service.delete_call_content_for_user(db, current_user.id, call_id)
    except LookupError:
        raise_http(NotFoundError("Call not found"))
    except PermissionError:
        raise_http(AppError("Legal hold is active", code="legal_hold", http_status=403))


@router.get("/{call_id}", response_model=CallSessionDetailOut)
def get_call(
    call_id: int,
    include_transcript: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> CallSessionDetailOut:
    row = calls_service.get_call_session(db, current_user.id, call_id)
    if row is None:
        raise_http(NotFoundError("Call not found"))
    payload = calls_service.to_list_item(row)
    if include_transcript and row.content_purged_at is None:
        payload["transcript"] = row.transcript
    else:
        payload["transcript"] = None
    return CallSessionDetailOut.model_validate(payload)

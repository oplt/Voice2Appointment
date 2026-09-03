"""CallSession persistence using FastAPI SQLAlchemy models."""

from __future__ import annotations

from app.db.models import CallSession, User


def test_callsession_create_persists(db_session) -> None:
    user = User(
        username="alice",
        email="alice@example.com",
        password="x",
        twilio_phone_number="+15550001111",
    )
    db_session.add(user)
    db_session.commit()

    call_sid = "CA1234567890"
    from_number = "+15550002222"
    to_number = "+15550001111"

    CallSession.create(
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        user_id=user.id,
        session=db_session,
    )

    saved = db_session.query(CallSession).filter_by(call_sid=call_sid).first()
    assert saved is not None
    assert saved.user_id == user.id
    assert saved.from_number == from_number
    assert saved.to_number == to_number
    assert saved.status == "active"
    assert saved.started_at is not None

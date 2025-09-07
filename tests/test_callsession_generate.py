import pytest
from datetime import timezone, datetime

from flaskapp import create_app
from flaskapp.database.models import db, User, CallSession

@pytest.fixture
def app():
    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_callsession_create_persists(app):
    # Arrange: make a user whose twilio number matches the "to" number
    with app.app_context():
        u = User(
            username="alice",
            email="alice@example.com",
            password="x",
            twilio_phone_number="+15550001111"
        )
        db.session.add(u)
        db.session.commit()

        call_sid = "CA1234567890"
        from_number = "+15550002222"
        to_number = "+15550001111"

        # Act: create the CallSession as your code does
        cs = CallSession.create(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            user_id=u.id,
        )

        # Assert: it exists and fields are correct
        saved = CallSession.query.filter_by(call_sid=call_sid).first()
        assert saved is not None
        assert saved.user_id == u.id
        assert saved.from_number == from_number
        assert saved.to_number == to_number
        assert saved.status == "active"
        assert saved.started_at is not None

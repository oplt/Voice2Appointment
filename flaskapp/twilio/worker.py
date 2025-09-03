import os, requests, datetime as dt
from celery import Celery
from flaskapp import create_app, db
from flaskapp.database.models import CallSession, User

celery = Celery(
    "worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

@celery.task
def download_and_archive_recording(recording_sid, recording_url, call_sid):
    audio_url = f"{recording_url}.mp3?Download=true"
    cs = CallSession.query.filter_by(call_sid=call_sid).first()
    user_id = cs.user_id
    user = User.query.filter_by(id=user_id).first()

    resp = requests.get(
        audio_url,
        auth=(user.twilio_account_sid, user.twilio_auth_token),
        timeout=30,
    )
    resp.raise_for_status()
    path = f"/tmp/{recording_sid}.mp3"
    with open(path, "wb") as f:
        f.write(resp.content)

    app = create_app()
    with app.app_context():
        if cs:
            cs.update({
                        'recording_path': path,
                        'recording_downloaded_at': dt.datetime.utcnow()
            })

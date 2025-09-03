import logging
from flask import Blueprint, request, jsonify, abort
from twilio.request_validator import RequestValidator
from flaskapp.database.models import CallSession
from flaskapp import db
from .worker import download_and_archive_recording  # Celery task
from flaskapp.database.models import User

logger = logging.getLogger(__name__)
twilio_bp = Blueprint("twilio", __name__)

# this is a webhook endpoint that Twilio will call when a recording is available
@twilio_bp.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    account_sid = request.form.get("AccountSid")
    user = User.query.filter_by(account_sid=account_sid).first()
    auth_token = user.auth_token

    validator = RequestValidator(auth_token)
    url = request.url
    form = request.form.to_dict(flat=True)
    signature = request.headers.get("X-Twilio-Signature", "")

    if not validator.validate(url, form, signature):
        logger.warning("Invalid Twilio signature")
        abort(403)

    payload = form
    call_sid = payload.get("CallSid")
    recording_sid = payload.get("RecordingSid")
    recording_url = payload.get("RecordingUrl")
    duration = payload.get("RecordingDuration")

    if not call_sid or not recording_sid or not recording_url:
        logger.warning("Missing required fields: %s", payload)
        return jsonify({"status": "missing fields"}), 200  # or 400

    cs = CallSession.query.filter_by(call_sid=call_sid).first()
    if not cs:
        logger.warning("No CallSession for %s", call_sid)
        return jsonify({"status": "no matching call session"}), 200

    cs.update({
        'recording_sid': recording_sid,
        'recording_url': recording_url,
        'duration_seconds': duration
    })
    download_and_archive_recording.delay(
                                        recording_sid=recording_sid,
                                        recording_url=recording_url,
                                        call_sid=call_sid,
                                    )

    return jsonify({"status": "ok"}), 200

import asyncio
import base64
import json
import websockets
import os
from dotenv import load_dotenv
from pathlib import Path
from flaskapp.calendar.functions_map import FUNCTION_MAP
from flaskapp import create_app
from datetime import datetime, timedelta, timezone
import pytz
from flaskapp.database.models import CallSession, User
from config import settings


load_dotenv()

_app = None
def get_app():
    global _app
    if _app is None:
        _app = create_app()
    return _app


def sts_connect():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise Exception("DEEPGRAM_API_KEY not found")

    sts_ws = websockets.connect(
        "wss://agent.deepgram.com/v1/agent/converse",
        subprotocols=["token", api_key]
    )
    return sts_ws


def load_config():
    current_dir = Path(__file__).parent
    config_path = current_dir / "config.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    current_date_context = get_current_date_context()

    # Inject current date context into the prompt
    if "agent" in config and "think" in config["agent"] and "prompt" in config["agent"]["think"]:
        config["agent"]["think"]["prompt"] = config["agent"]["think"]["prompt"].format(
            current_date_context=current_date_context
        )

    return config


def get_current_date_context():
    """Generate comprehensive date context for the AI assistant"""
    try:
        # Get current time in UTC
        now_utc = datetime.now(pytz.UTC)
        
        # Get timezone from config (default to Europe/Brussels)
        config = get_app().config
        timezone_name = config.get('CALENDAR', {}).get('TIMEZONE', 'Europe/Brussels')
        
        try:
            user_tz = pytz.timezone(timezone_name)
            now_local = now_utc.astimezone(user_tz)
        except pytz.exceptions.UnknownTimeZoneError:
            user_tz = pytz.UTC
            now_local = now_utc
        
        # Generate comprehensive date context
        date_context = f"""
Current Date and Time Context:
- Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC
- Current local time ({timezone_name}): {now_local.strftime('%Y-%m-%d %H:%M:%S')} {timezone_name}
- Today: {now_local.strftime('%A, %B %d, %Y')}
- Tomorrow: {(now_local + timedelta(days=1)).strftime('%A, %B %d, %Y')}
- Next week: {(now_local + timedelta(days=7)).strftime('%A, %B %d, %Y')}
- Current working hours: 9:00 AM - 5:00 PM {timezone_name}
- Current day of week: {now_local.strftime('%A')}
- Current month: {now_local.strftime('%B')}
- Current year: {now_local.year}

Date Reference Guide:
- "today" = {now_local.strftime('%Y-%m-%d')}
- "tomorrow" = {(now_local + timedelta(days=1)).strftime('%Y-%m-%d')}
- "next week" = {(now_local + timedelta(days=7)).strftime('%Y-%m-%d')}
- "this afternoon" = {now_local.strftime('%Y-%m-%d')} (after 12:00 PM)
- "this evening" = {now_local.strftime('%Y-%m-%d')} (after 5:00 PM)
- "next Monday" = {(now_local + timedelta(days=(7 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
- "next Tuesday" = {(now_local + timedelta(days=(8 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
- "next Wednesday" = {(now_local + timedelta(days=(9 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
- "next Thursday" = {(now_local + timedelta(days=(10 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
- "next Friday" = {(now_local + timedelta(days=(11 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
- "next Saturday" = {(now_local + timedelta(days=(12 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
- "next Sunday" = {(now_local + timedelta(days=(13 - now_local.weekday()) % 7)).strftime('%Y-%m-%d')}
"""
        return date_context.strip()
        
    except Exception as e:
        # Fallback to basic date context if there's an error
        now = datetime.now()
        return f"""
Current Date Context (Fallback):
- Current date: {now.strftime('%Y-%m-%d')}
- Current time: {now.strftime('%H:%M:%S')}
- Today: {now.strftime('%A, %B %d, %Y')}
- Tomorrow: {(now + timedelta(days=1)).strftime('%Y-%m-%d')}
"""


async def handle_barge_in(decoded, twilio_ws, streamsid):
    if decoded["type"] == "UserStartedSpeaking":
        clear_message = {
            "event": "clear",
            "streamSid": streamsid
        }
        await twilio_ws.send(json.dumps(clear_message))


def execute_function_call(func_name, arguments):
    if func_name in FUNCTION_MAP:
        flask_app = get_app()
        # ensure we’re inside an app context
        with flask_app.app_context():
            result = FUNCTION_MAP[func_name](**arguments)
        print(f"Function call result: {result}")
        return result
    else:
        result = {"error": f"Unknown function: {func_name}"}
        print(result)
        return result


def create_function_call_response(func_id, func_name, result):
    return {
        "type": "FunctionCallResponse",
        "id": func_id,
        "name": func_name,
        "content": json.dumps(result)
    }


async def handle_function_call_request(decoded, sts_ws):
    try:
        for function_call in decoded["functions"]:
            func_name = function_call["name"]
            func_id = function_call["id"]
            arguments = json.loads(function_call["arguments"])

            print(f"Function call: {func_name} (ID: {func_id}), arguments: {arguments}")

            result = execute_function_call(func_name, arguments)

            function_result = create_function_call_response(func_id, func_name, result)
            await sts_ws.send(json.dumps(function_result))
            print(f"Sent function result: {function_result}")

    except Exception as e:
        print(f"Error calling function: {e}")
        error_result = create_function_call_response(
            func_id if "func_id" in locals() else "unknown",
            func_name if "func_name" in locals() else "unknown",
            {"error": f"Function call failed with: {str(e)}"}
        )
        await sts_ws.send(json.dumps(error_result))


async def handle_text_message(decoded, twilio_ws, sts_ws, streamsid):
    await handle_barge_in(decoded, twilio_ws, streamsid)

    if decoded["type"] == "FunctionCallRequest":
        await handle_function_call_request(decoded, sts_ws)


async def sts_sender(sts_ws, audio_queue):
    print("sts_sender started")
    while True:
        chunk = await audio_queue.get()
        await sts_ws.send(chunk)


async def sts_receiver(sts_ws, twilio_ws, streamsid_queue):
    print("sts_receiver started")
    streamsid = await streamsid_queue.get()

    async for message in sts_ws:
        if type(message) is str:
            print(message)
            decoded = json.loads(message)
            await handle_text_message(decoded, twilio_ws, sts_ws, streamsid)
            continue

        raw_mulaw = message

        media_message = {
            "event": "media",
            "streamSid": streamsid,
            "media": {"payload": base64.b64encode(raw_mulaw).decode("ascii")}
        }

        await twilio_ws.send(json.dumps(media_message))


async def twilio_receiver(twilio_ws, audio_queue, streamsid_queue):
    BUFFER_SIZE = 20 * 160
    inbuffer = bytearray(b"")
    cs = None

    async for message in twilio_ws:
        try:
            data = json.loads(message)
            event = data["event"]

            if event == "start":
                print("get our streamsid")
                start = data["start"]
                streamsid = start.get("streamSid")
                call_sid   = start.get("callSid")
                from_number   = start.get("from")
                to_number     = start.get("to")
                user_id = User.query.filter_by(phone_number=to_number).first().id
                cs = CallSession.create(call_sid=call_sid,
                                        from_number=from_number,
                                        to_number=to_number,
                                        started_at=datetime.now(timezone.utc),
                                        user_id=user_id
                                    )
                streamsid_queue.put_nowait(streamsid)
            elif event == "connected":
                continue
            elif event == "media":
                media = data["media"]
                chunk = base64.b64decode(media["payload"])
                if media["track"] == "inbound":
                    inbuffer.extend(chunk)
            elif event == "stop":
                if cs is not None:
                    with get_app().app_context():
                        cs.update({
                            'status': 'ended',
                            'ended_at': datetime.now(timezone.utc)
                        })

                break

            while len(inbuffer) >= BUFFER_SIZE:
                chunk = inbuffer[:BUFFER_SIZE]
                audio_queue.put_nowait(chunk)
                inbuffer = inbuffer[BUFFER_SIZE:]
        except:
            try:
                call_sid = (data.get("start") or {}).get("callSid") \
                           or (data.get("stop") or {}).get("callSid")
                if call_sid:
                    session = CallSession.query.filter_by(call_sid=call_sid).first()
                    if session:
                        with get_app().app_context():
                            cs.update({'status': 'error'})
            except Exception:
                pass
            break


async def twilio_handler(twilio_ws):
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    async with sts_connect() as sts_ws:
        config_message = load_config()
        await sts_ws.send(json.dumps(config_message))

        await asyncio.wait(
            [
                asyncio.ensure_future(sts_sender(sts_ws, audio_queue)),
                asyncio.ensure_future(sts_receiver(sts_ws, twilio_ws, streamsid_queue)),
                asyncio.ensure_future(twilio_receiver(twilio_ws, audio_queue, streamsid_queue)),
            ]
        )

        await twilio_ws.close()

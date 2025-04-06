import os
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import requests
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pytz
import re

# Configuration
VOICE_RESPONSE = True  # Set to False if you want text-only responses
SAMPLE_RATE = 44100
CHANNELS = 1
RECORD_SECONDS = 5  # Maximum recording duration

OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "deepseek-r1:8b"

# Google Calendar API Configuration
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = 'primary'
TIMEZONE = 'America/New_York'  #

# Appointment Configuration
WORKING_HOURS = (9, 17)
APPOINTMENT_DURATION = 30


def authenticate_google_calendar():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


def record_audio():
    print("Recording... Speak now!")
    recording = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE),
                       samplerate=SAMPLE_RATE,
                       channels=CHANNELS,
                       dtype='int16')
    sd.wait()
    print("Recording complete")

    write("temp_recording.wav", SAMPLE_RATE, recording)
    return "temp_recording.wav"


def transcribe_with_whisper(file_path):
    import whisper

    model = whisper.load_model("base")

    result = model.transcribe(
        file_path,
        fp16=False,
        verbose=True
    )

    return result["text"].strip()


def get_deepseek_response(prompt):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "max_tokens": 150,
        }
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"API Error: {e}")
        return "Sorry, I couldn't generate a response."


def extract_appointment_details(text):
    prompt = f"""Extract the appointment details from the following text. 
    Return a JSON object with these fields:
    - "date": The date in YYYY-MM-DD format (use 'today' if no date specified)
    - "time": The time in HH:MM format (use '9:00' if no time specified)
    - "title": A brief title for the appointment

    If multiple dates/times are mentioned, use the first one.
    Text: {text}"""

    response = get_deepseek_response(prompt)

    try:
        # Clean the response to extract valid JSON
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        json_str = response[json_start:json_end]
        details = json.loads(json_str)

        if 'date' not in details or not details['date']:
            details['date'] = 'today'
        if 'time' not in details or not details['time']:
            details['time'] = f"{WORKING_HOURS[0]}:00"
        if 'title' not in details or not details['title']:
            details['title'] = 'Meeting'

        return details
    except Exception as e:
        print(f"Error parsing appointment details: {e}")
        return {
            'date': 'today',
            'time': f"{WORKING_HOURS[0]}:00",
            'title': 'Meeting'
        }


def create_datetime_object(date_str, time_str):
    tz = pytz.timezone(TIMEZONE)

    if date_str.lower() == 'today':
        date_obj = datetime.now(tz)
    else:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=tz)
        except:
            date_obj = datetime.now(tz)

    try:
        hour, minute = map(int, time_str.split(':'))
        date_obj = date_obj.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except:
        date_obj = date_obj.replace(hour=WORKING_HOURS[0], minute=0, second=0, microsecond=0)

    return date_obj


def check_calendar_availability(service, start_time, end_time):
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    return len(events) == 0


def find_available_slots(service, date, duration_minutes=APPOINTMENT_DURATION):
    tz = pytz.timezone(TIMEZONE)
    date = date.astimezone(tz)

    start_of_day = date.replace(hour=WORKING_HOURS[0], minute=0, second=0, microsecond=0)
    end_of_day = date.replace(hour=WORKING_HOURS[1], minute=0, second=0, microsecond=0)

    current_time = start_of_day
    available_slots = []

    while current_time + timedelta(minutes=duration_minutes) <= end_of_day:
        end_time = current_time + timedelta(minutes=duration_minutes)

        if check_calendar_availability(service, current_time, end_time):
            available_slots.append(current_time)

        current_time += timedelta(minutes=30)  # Check every 30 minutes

    return available_slots


def create_calendar_event(service, start_time, end_time, title):
    event = {
        'summary': title,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': TIMEZONE,
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': TIMEZONE,
        },
        'reminders': {
            'useDefault': True,
        },
    }

    try:
        print(f"Attempting to create event: {title} at {start_time.isoformat()}")
        event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
            sendNotifications=True
        ).execute()

        print(f"Event created successfully: {event.get('htmlLink')}")
        return True, event.get('htmlLink')
    except Exception as e:
        print(f"Error creating calendar event: {str(e)}")
        return False, str(e)


def speak_response(text):
    import subprocess
    try:
        subprocess.run(['espeak', '-s', '150', text])
    except FileNotFoundError:
        print("espeak not installed. Please install with:")
        print("sudo apt-get install espeak")
    except Exception as e:
        print(f"Text-to-speech error: {e}")


def confirm_appointment(service, start_time, end_time, title):
    success, event_link = create_calendar_event(service, start_time, end_time, title)
    if success:
        return f"Meeting '{title}' has been successfully scheduled for {start_time.strftime('%A, %B %d at %I:%M %p')}."
    else:
        return f"Failed to schedule the meeting. Error: {event_link}"


def main():
    print("Meeting Scheduling System with DeepSeek and Google Calendar")
    print("Press Enter to start recording your meeting request...")

    try:
        service = authenticate_google_calendar()
        print("Successfully authenticated with Google Calendar")
    except Exception as e:
        print(f"Failed to authenticate with Google Calendar: {e}")
        return

    while True:
        user_input = input("Press Enter to record or 'q' to quit...")
        if user_input.lower() == 'q':
            break

        try:
            audio_file = record_audio()
        except Exception as e:
            print(f"Error recording audio: {e}")
            continue

        try:
            prompt = transcribe_with_whisper(audio_file)
            if not prompt:
                print("Could not transcribe your audio. Please try again.")
                continue

            print(f"\nYour request: {prompt}")

            details = extract_appointment_details(prompt)
            print(f"Extracted meeting details: {details}")

            start_time = create_datetime_object(details['date'], details['time'])
            end_time = start_time + timedelta(minutes=APPOINTMENT_DURATION)

            if check_calendar_availability(service, start_time, end_time):
                response = confirm_appointment(service, start_time, end_time, details['title'])
            else:
                available_slots = find_available_slots(service, start_time)

                if available_slots:
                    formatted_slots = [slot.strftime('%I:%M %p') for slot in
                                       available_slots[:3]]  # Show first 3 options
                    response = f"The requested time is not available. Here are some available slots on " \
                               f"{start_time.strftime('%A, %B %d')}: {', '.join(formatted_slots)}"
                else:
                    next_day = start_time + timedelta(days=1)
                    while True:
                        available_slots = find_available_slots(service, next_day)
                        if available_slots:
                            break
                        next_day += timedelta(days=1)

                    formatted_slots = [slot.strftime('%I:%M %p') for slot in available_slots[:3]]
                    response = f"No availability on {start_time.strftime('%A, %B %d')}. " \
                               f"The next available day is {next_day.strftime('%A, %B %d')} " \
                               f"with slots at: {', '.join(formatted_slots)}"

            print(f"\nResponse: {response}")

            if VOICE_RESPONSE:
                speak_response(response)

        except Exception as e:
            print(f"Error: {e}")
            response = f"An error occurred: {str(e)}"
            print(f"\nResponse: {response}")
            if VOICE_RESPONSE:
                speak_response(response)

        try:
            os.remove(audio_file)
        except:
            pass


if __name__ == "__main__":
    main()
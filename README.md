# 🎤 Voice Assistant - AI-Powered Appointment Scheduler

A sophisticated voice-enabled appointment scheduling system that integrates Twilio for phone calls, Deepgram for speech recognition and synthesis, and Google Calendar for appointment management. Built with Flask and WebSocket technology for real-time communication.

## 🌟 Features

- **Voice-First Interface**: Natural language appointment scheduling via phone calls
- **AI-Powered Assistant**: GPT-4 powered conversation handling with function calling
- **Real-Time Communication**: WebSocket-based audio streaming between Twilio and Deepgram
- **Google Calendar Integration**: Seamless appointment management
- **Multi-User Support**: User authentication and profile management
- **Responsive Web Dashboard**: Modern web interface for managing appointments
- **Barge-in Support**: Interrupt the AI assistant mid-sentence
- **Timezone Handling**: Intelligent timezone management for global users

## 🏗️ Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│   Twilio    │◄──►│  WebSocket   │◄──►│  Deepgram   │◄──►│   OpenAI    │
│   Phone     │    │   Server     │    │     STT     │    │     LLM     │
└─────────────┘    └──────────────┘    └─────────────┘    └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │     Flask     │
                    │   Backend    │
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Google     │
                    │   Calendar   │
                    └──────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- PostgreSQL or SQLite database
- Twilio account with phone number
- Deepgram API key
- OpenAI API key
- Google Calendar API credentials

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd VoiceAssistant
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

4. **Initialize the database**
   ```bash
   python run.py
   ```

5. **Start the application**
   ```bash
   python run.py
   ```

The application will start on:
- **Flask Web Server**: http://localhost:5000
- **WebSocket Server**: ws://localhost:5001

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True
FLASK_TESTING=False

# Database Configuration
DATABASE_URL=sqlite:///voice_assistant.db

# Twilio Configuration
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# Deepgram Configuration
DEEPGRAM_API_KEY=your-deepgram-api-key

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# Email Configuration (for password reset)
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# Logging
LOG_LEVEL=INFO
```

### Google Calendar Setup

1. **Enable Google Calendar API**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable Google Calendar API
   - Create OAuth 2.0 credentials

2. **Download credentials**
   - Download the OAuth 2.0 client credentials JSON file
   - Store it securely (the system will save it to the database)

## 📞 Twilio Integration

### Phone Call Flow

1. **Incoming Call**: User calls your Twilio phone number
2. **Webhook**: Twilio sends webhook to `/phone/webhook`
3. **Stream Connection**: Establishes WebSocket connection for audio streaming
4. **Voice Processing**: Audio streams to Deepgram for speech-to-text
5. **AI Processing**: OpenAI processes the conversation and calls functions
6. **Calendar Operations**: Google Calendar API manages appointments
7. **Response**: AI response converted to speech via Deepgram TTS
8. **Audio Output**: Speech sent back to user via Twilio

### Twilio Configuration

```python
# In your Twilio console, set these webhook URLs:
# Voice Configuration:
# - Webhook URL: https://your-domain.com/phone/webhook
# - HTTP Method: POST

# Stream Configuration:
# - WebSocket URL: wss://your-domain.com:5001
# - Track: Both inbound and outbound
```

### WebSocket Endpoints

- **Main WebSocket**: `ws://localhost:5001` (for Twilio Stream)
- **Test Endpoint**: `GET /phone/test_websocket`
- **Status Endpoint**: `GET /phone/twilio`

## 🎯 Deepgram Integration

### Speech-to-Text (STT)

- **Model**: `nova-3` (latest and most accurate)
- **Sample Rate**: 8000 Hz (optimized for phone calls)
- **Encoding**: μ-law (standard for telephony)
- **Language**: English (configurable)

### Text-to-Speech (TTS)

- **Model**: `aura-2-thalia-en` (natural-sounding voice)
- **Real-time**: Low-latency streaming
- **Quality**: High-fidelity audio output

### Configuration

```json
{
  "audio": {
    "input": {
      "encoding": "mulaw",
      "sample_rate": 8000
    },
    "output": {
      "encoding": "mulaw",
      "sample_rate": 8000,
      "container": "none"
    }
  },
  "agent": {
    "listen": {
      "provider": {
        "type": "deepgram",
        "model": "nova-3"
      }
    },
    "speak": {
      "provider": {
        "type": "deepgram",
        "model": "aura-2-thalia-en"
      }
    }
  }
}
```

## 🤖 AI Assistant Features

### Function Calling

The AI assistant can perform these calendar operations:

1. **Check Availability**
   ```python
   check_calendar_availability(
       datetime_start="2024-01-15T10:00:00Z",
       datetime_end="2024-01-15T11:00:00Z"
   )
   ```

2. **Create Appointment**
   ```python
   create_calendar_event(
       summary="Dr. Smith Appointment",
       datetime_start="2024-01-15T10:00:00Z",
       datetime_end="2024-01-15T11:00:00Z",
       description="Annual checkup",
       attendees=["john@example.com"]
   )
   ```

3. **Reschedule Appointment**
   ```python
   reschedule_appointment(
       original_datetime="2024-01-15T10:00:00Z",
       new_datetime_start="2024-01-16T14:00:00Z",
       new_datetime_end="2024-01-16T15:00:00Z",
       reason="Conflict with another meeting"
   )
   ```

4. **Cancel Appointment**
   ```python
   cancel_appointment(
       datetime_start="2024-01-15T10:00:00Z",
       reason="Emergency came up"
   )
   ```

### Conversation Examples

**User**: "I need to schedule a doctor's appointment for tomorrow at 2 PM"

**Assistant**: "I'd be happy to help you schedule a doctor's appointment. Let me check the availability for tomorrow at 2 PM. What type of appointment is this, and what's your name?"

**User**: "It's for a checkup, and my name is John Smith"

**Assistant**: "Perfect, John Smith. I'm checking availability for a checkup tomorrow at 2 PM. Let me verify that slot is available and then book it for you."

## 📱 Web Dashboard

### Features

- **User Authentication**: Secure login and registration
- **Profile Management**: Update personal information and profile pictures
- **Appointment Overview**: View all scheduled appointments
- **Settings**: Configure Twilio and Deepgram API keys
- **Google Calendar Sync**: Manage calendar integration

### Routes

- `/` - Home page
- `/login` - User authentication
- `/register` - User registration
- `/dashboard` - Main dashboard (requires login)
- `/settings` - User settings and API configuration
- `/phone/*` - Phone integration endpoints

## 🔌 API Endpoints

### Phone Integration

- `POST /phone/webhook` - Handle incoming Twilio calls
- `POST /phone/gather` - Process speech input
- `POST /phone/check_availability` - Check calendar availability
- `POST /phone/confirm_appointment` - Confirm appointment scheduling
- `GET /phone/twilio` - Twilio integration information

### Calendar Management

- `GET /dashboard/stats` - Get dashboard statistics
- `POST /calendar/check` - Check calendar availability
- `POST /calendar/create` - Create new appointment
- `PUT /calendar/update` - Update existing appointment
- `DELETE /calendar/delete` - Cancel appointment

## 🗄️ Database Models

### Core Models

- **User**: User authentication and profile information
- **GoogleCalendarAuth**: Google OAuth credentials storage
- **CallSession**: Phone call session tracking
- **Appointment**: Calendar appointment data

### Database Schema

```sql
-- Users table
CREATE TABLE user (
    id INTEGER PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(128),
    profile_picture VARCHAR(120),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Google Calendar Authentication
CREATE TABLE google_calendar_auth (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES user(id),
    credentials_json TEXT,
    token_json TEXT,
    time_zone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Call Sessions
CREATE TABLE call_session (
    id INTEGER PRIMARY KEY,
    call_sid VARCHAR(100) UNIQUE,
    user_id INTEGER REFERENCES user(id),
    status VARCHAR(50),
    duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🚀 Deployment

### Production Setup

1. **Web Server**: Use Gunicorn or uWSGI
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 run:app
   ```

2. **Reverse Proxy**: Configure Nginx
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
       
       location /ws {
           proxy_pass http://127.0.0.1:5001;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```

3. **SSL Certificate**: Use Let's Encrypt
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```

4. **Environment**: Set production environment variables
   ```bash
   export FLASK_ENV=production
   export FLASK_DEBUG=False
   ```

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000 5001

CMD ["python", "run.py"]
```

## 🧪 Testing

### Manual Testing

1. **Phone Call Test**
   - Call your Twilio number
   - Speak naturally about scheduling
   - Verify appointment creation

2. **Web Dashboard Test**
   - Login to web interface
   - Check appointment creation
   - Verify Google Calendar sync

3. **WebSocket Test**
   - Use WebSocket client to connect to port 5001
   - Send test audio data
   - Verify response

### Automated Testing

```bash
# Install test dependencies
pip install pytest pytest-flask

# Run tests
pytest tests/
```

## 🔒 Security Considerations

- **API Key Protection**: Store sensitive keys in environment variables
- **HTTPS**: Use SSL/TLS in production
- **Authentication**: Implement proper user authentication
- **Input Validation**: Validate all user inputs
- **Rate Limiting**: Implement API rate limiting
- **Logging**: Monitor and log all activities

## 🐛 Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check if WebSocket server is running on port 5001
   - Verify firewall settings
   - Check Twilio Stream configuration

2. **Audio Quality Issues**
   - Verify sample rate settings (8000 Hz)
   - Check encoding format (μ-law)
   - Ensure stable internet connection

3. **Calendar Sync Problems**
   - Verify Google Calendar API credentials
   - Check OAuth token expiration
   - Verify calendar permissions

4. **Speech Recognition Issues**
   - Check Deepgram API key validity
   - Verify audio format compatibility
   - Check network connectivity

### Debug Mode

Enable debug logging in your `.env` file:

```env
LOG_LEVEL=DEBUG
FLASK_DEBUG=True
```

## 📚 API Documentation

### Deepgram API

- [Speech-to-Text Documentation](https://developers.deepgram.com/docs/speech-to-text)
- [Text-to-Speech Documentation](https://developers.deepgram.com/docs/text-to-speech)
- [Real-Time API](https://developers.deepgram.com/docs/real-time-api)

### Twilio API

- [Voice API Documentation](https://www.twilio.com/docs/voice/api)
- [Stream API Documentation](https://www.twilio.com/docs/voice/stream)
- [Webhook Configuration](https://www.twilio.com/docs/voice/configure-webhooks)

### Google Calendar API

- [Calendar API Reference](https://developers.google.com/calendar/api/v3/reference)
- [OAuth 2.0 Setup](https://developers.google.com/calendar/api/guides/auth)
- [Event Management](https://developers.google.com/calendar/api/v3/reference/events)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Twilio** for phone integration capabilities
- **Deepgram** for speech recognition and synthesis
- **OpenAI** for AI conversation handling
- **Google** for calendar API integration
- **Flask** community for the excellent web framework

## 📞 Support

For support and questions:

- **Issues**: Create an issue on GitHub
- **Documentation**: Check the project wiki
- **Community**: Join our Discord server

---

**Made with ❤️ for seamless voice-powered appointment scheduling**

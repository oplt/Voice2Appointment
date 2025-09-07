# VoiceAssistant

A Flask-based voice assistant application that integrates with Twilio for voice calls, Google Calendar for appointment management, and Deepgram for speech-to-text processing. The system allows users to schedule, reschedule, and manage appointments through voice interactions.

## 🚀 Features

### Core Functionality
- **Voice Call Processing**: Real-time voice interaction using Twilio WebRTC and Deepgram STT
- **Calendar Integration**: Google Calendar API integration for appointment management
- **Appointment Management**: Create, reschedule, cancel, and check appointment availability
- **Analytics Dashboard**: Comprehensive call analytics with geographic mapping and cost tracking
- **Menu Builder**: Restaurant menu management system with categories and products

### Voice Assistant Capabilities
- Check calendar availability for specific time slots
- Create new appointments with client details
- Reschedule existing appointments
- Cancel appointments with reason tracking
- Get appointment details and upcoming events
- Natural language processing for date/time recognition

### Analytics & Reporting
- Call duration and cost analysis
- Geographic call distribution maps
- Peak hours and days heatmap
- Export functionality (CSV, Excel)
- Real-time dashboard with interactive charts

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Twilio WebRTC │────│  Flask Backend   │────│ Google Calendar │
│   (Voice Calls) │    │  (WebSocket)     │    │      API        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                       ┌──────────────────┐
                       │   Deepgram STT   │
                       │  (Speech-to-Text)│
                       └──────────────────┘
```

## 📋 Prerequisites

- Python 3.8+
- PostgreSQL (or SQLite for development)
- Twilio Account with WebRTC capabilities
- Google Cloud Platform account with Calendar API enabled
- Deepgram API key

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd VoiceAssistant
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file in the root directory:
   ```env
   # Database
   DATABASE_URL=postgresql://username:password@localhost/voiceassistant
   
   # Twilio Configuration
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_PHONE_NUMBER=your_twilio_phone_number
   
   # Deepgram Configuration
   DEEPGRAM_API_KEY=your_deepgram_api_key
   
   # Google Calendar Configuration
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   GOOGLE_REDIRECT_URI=http://localhost:5000/google/callback
   
   # Flask Configuration
   SECRET_KEY=your_secret_key
   FLASK_ENV=development
   ```

5. **Database Setup**
   ```bash
   # Initialize database
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

6. **Run the application**
   ```bash
   python run.py
   ```

## 🔧 Configuration

### Twilio Setup
1. Create a Twilio account and get your Account SID and Auth Token
2. Purchase a phone number with WebRTC capabilities
3. Configure webhooks in Twilio Console:
   - Voice URL: `https://yourdomain.com/twilio/voice`
   - Recording Status Callback: `https://yourdomain.com/twilio/recording`

### Google Calendar Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs

### Deepgram Setup
1. Sign up at [Deepgram](https://deepgram.com/)
2. Create a new project
3. Generate an API key
4. Add the key to your `.env` file

## 📁 Project Structure

```
VoiceAssistant/
├── flaskapp/
│   ├── __init__.py
│   ├── analysis/           # Analytics and dashboard functions
│   ├── calendar/           # Google Calendar integration
│   ├── database/           # Database models and configuration
│   ├── errors/             # Error handling
│   ├── routes/             # Flask routes and blueprints
│   ├── static/             # CSS, JS, and static assets
│   ├── templates/          # HTML templates
│   ├── twilio/             # Twilio integration
│   └── utils/              # Utility functions
├── migrations/             # Database migrations
├── tests/                  # Test files
├── logs/                   # Application logs
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
└── run.py                 # Application entry point
```

## 🚀 Usage

### Starting the Application
```bash
python run.py
```

The application will be available at `http://localhost:5000`

### Voice Assistant Usage
1. **Login** to the dashboard
2. **Connect Google Calendar** for appointment management
3. **Make a call** to your Twilio phone number
4. **Speak naturally** to schedule appointments:
   - "Schedule a meeting tomorrow at 2 PM"
   - "Check my availability next Tuesday"
   - "Reschedule my 3 PM appointment to 4 PM"
   - "Cancel my appointment on Friday"

### Dashboard Features
- **Calendar View**: View and manage appointments
- **Analytics**: Analyze call patterns and costs
- **Menu Builder**: Create and manage restaurant menus

## 🔌 API Endpoints

### Calendar Management
- `POST /calendar/check-availability` - Check time slot availability
- `POST /calendar/create-event` - Create new appointment
- `POST /calendar/reschedule` - Reschedule existing appointment
- `POST /calendar/cancel` - Cancel appointment
- `GET /calendar/events` - Get upcoming events

### Analytics
- `GET /analytics/dashboard` - Get analytics data
- `GET /analytics/export/csv` - Export data as CSV
- `GET /analytics/export/excel` - Export data as Excel

### Twilio Webhooks
- `POST /twilio/voice` - Handle incoming calls
- `POST /twilio/recording` - Handle recording callbacks

## 🧪 Testing

Run the test suite:
```bash
pytest tests/
```

Run specific test files:
```bash
pytest tests/test_callsession_generate.py
```

## 📊 Monitoring & Logging

### Logs
- Application logs: `logs/VoiceAsst.log`
- Error tracking and debugging information
- Call session tracking and analytics

### Health Checks
- Database connectivity
- Google Calendar API status
- Twilio service status
- Deepgram API availability

## 🔒 Security Considerations

- **Authentication**: Flask-Login for user sessions
- **API Security**: Twilio request validation
- **Data Encryption**: Sensitive data encrypted at rest
- **HTTPS**: Required for production deployment
- **Environment Variables**: Sensitive configuration in `.env`

## 🚨 Known Issues & Limitations

### Current Issues
1. **Database Persistence**: Appointment creation currently only syncs with Google Calendar
2. **Error Handling**: Limited retry mechanisms for API failures
3. **Call History**: No persistent call session storage

### Limitations
- Requires stable internet connection for real-time processing
- Google Calendar API rate limits apply
- Twilio WebRTC requires modern browsers
- Voice recognition accuracy depends on audio quality

## 🔄 Deployment

### Production Deployment
1. **Environment Setup**
   ```bash
   export FLASK_ENV=production
   export DATABASE_URL=postgresql://user:pass@host:port/db
   ```

2. **Database Migration**
   ```bash
   flask db upgrade
   ```

3. **Static Files**
   ```bash
   python -m flask assets build
   ```

4. **Web Server** (using Gunicorn)
   ```bash
   gunicorn -w 4 -b 0.0.0.0:8000 run:app
   ```

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "run:app"]
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the GitHub repository
- Check the documentation in the `/docs` folder
- Review the logs in `/logs` for debugging

## 🔮 Roadmap

### Upcoming Features
- [ ] Multi-language support
- [ ] Advanced appointment templates
- [ ] SMS notifications
- [ ] Integration with CRM systems
- [ ] Mobile app companion
- [ ] Advanced analytics and reporting
- [ ] Voice command customization
- [ ] Offline mode capabilities

### Technical Improvements
- [ ] Implement proper error handling and retry logic
- [ ] Add comprehensive test coverage
- [ ] Database persistence for audit trails
- [ ] Performance optimization
- [ ] Security enhancements

---

**Note**: This application is currently in active development. Some features may be experimental or subject to change.

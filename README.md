# **Meeting Scheduling Assistant**  
*A voice-controlled AI assistant that schedules meetings using Google Calendar, DeepSeek, and Whisper transcription.*  

![Demo](https://img.shields.io/badge/Demo-Coming_Soon-blue) ![Python](https://img.shields.io/badge/Python-3.8%2B-green) ![License](https://img.shields.io/badge/License-MIT-orange)  

## **Features**  
- 🎤 **Voice Recording**: Speak your meeting request (e.g., *"Schedule a meeting tomorrow at 2 PM"*).  
- 🤖 **AI-Powered Parsing**: Uses **DeepSeek-R1** (via Ollama) to extract date, time, and title from your request.  
- 📅 **Google Calendar Integration**: Automatically checks availability and books appointments.  
- 🔊 **Voice Feedback** (Optional): Get spoken responses using `espeak`.  
- ⏳ **Smart Slot Suggestions**: Recommends alternative times if the requested slot is busy.  

---

## **Prerequisites**  
Before running, ensure you have:  
- **Python 3.8+**  
- **Ollama** running locally (`ollama pull deepseek-r1:8b`)  
- **Google Calendar API Credentials** (`credentials.json` in the project root)  
- **Whisper** (for speech-to-text): `pip install openai-whisper`  
- **Required Packages**:  
  ```bash
  pip install sounddevice numpy scipy requests google-auth google-auth-oauthlib google-api-python-client pytz
  ```

---

## **Setup & Usage**  
### **1. Configure Google Calendar API**  
1. Enable the **Google Calendar API** [here](https://developers.google.com/workspace/calendar/api/quickstart/python).  
2. Download `credentials.json` and place it in the project folder.  

### **2. Run the Program**  
```bash
python main.py
```  
- Press **Enter** to start recording your voice request.  
- The AI will parse your request and book the meeting (or suggest alternatives).  

### **3. (Optional) Enable Voice Responses**  
Install `espeak` for text-to-speech:  
```bash
sudo apt-get install espeak  # Linux
# Or use other TTS engines (e.g., pyttsx3 for Windows/macOS)
```

---

## **Configuration**  
Edit these variables in the script:  
| Variable | Description | Default |  
|----------|-------------|---------|  
| `VOICE_RESPONSE` | Enable/disable voice feedback | `True` |  
| `MODEL_NAME` | Ollama model to use | `deepseek-r1:8b` |  
| `TIMEZONE` | Your timezone | `America/New_York` |  
| `WORKING_HOURS` | Business hours for slot suggestions | `(9, 17)` |  

---

## **How It Works**  
1. **Record Audio** → Transcribe with **Whisper**.  
2. **Extract Details** → DeepSeek parses date/time/title.  
3. **Check Calendar** → Finds availability or suggests slots.  
4. **Book Event** → Creates a Google Calendar event.  

---

## **Troubleshooting**  
- **Ollama Not Running?**  
  ```bash
  ollama serve  # Start the Ollama server first
  ```  
- **Whisper Model Missing?**  
  ```bash
  pip install --upgrade whisper
  ```  
- **Google Auth Errors?** Delete `token.json` and re-authenticate.  

---



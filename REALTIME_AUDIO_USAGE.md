# Real-Time Audio Processing Usage Guide

## How to Use the New Functions

### 1. **Setup Twilio Webhook for Streaming**

Configure your Twilio phone number to use the streaming endpoint:

```
Webhook URL: https://your-domain.com/phone/incoming-call-streaming
HTTP Method: POST
```

### 2. **Call Flow with Real-Time Processing**

#### Option A: Streaming Call (Real-Time)
```
1. Caller dials your number
2. Twilio sends POST to /phone/incoming-call-streaming
3. Your app responds with TwiML including <Stream>
4. Twilio streams audio to /phone/stream-audio/{call_sid}
5. Audio chunks are accumulated in memory
6. After streaming ends, process accumulated audio
7. Generate response and end call
```

#### Option B: Traditional Recording (Current)
```
1. Caller dials your number
2. Twilio sends POST to /phone/incoming-call
3. Your app responds with TwiML including <Record>
4. Caller speaks, recording is saved
5. Twilio sends POST to /phone/process-voice/{call_sid}
6. Download recording and process with AI
7. Generate response and end call
```

### 3. **Function Usage Examples**

#### Using `process_realtime_audio`
```python
# In your webhook handler
from flaskapp.phone.ai_integration import AIVoiceIntegration

# Initialize with Twilio credentials
ai_integration = AIVoiceIntegration(
    twilio_account_sid="your_account_sid",
    twilio_auth_token="your_auth_token"
)

# Process real-time audio data
audio_data = b'...'  # Raw audio bytes from Media Streams
call_sid = "CA1234567890abcdef"

result = ai_integration.process_realtime_audio(audio_data, call_sid)
print(f"AI Processing Result: {result}")
```

#### Using `get_streaming_audio_url`
```python
# Get streaming URL for a call
streaming_url = ai_integration.get_streaming_audio_url(call_sid)
if streaming_url:
    print(f"Streaming URL: {streaming_url}")
else:
    print("Streaming not available, using recording instead")
```

### 4. **Testing the Implementation**

#### Test Streaming Endpoint
```bash
# Test the streaming call handler
curl -X POST http://localhost:5001/phone/incoming-call-streaming \
  -d "CallSid=test123" \
  -d "From=+1234567890" \
  -d "To=+0987654321"
```

#### Test Audio Processing
```python
# Test real-time audio processing
import requests

# Simulate audio chunk
audio_chunk = b'fake_audio_data'
call_sid = 'test123'

response = requests.post(
    f'http://localhost:5001/phone/stream-audio/{call_sid}',
    files={'audio': ('chunk.wav', audio_chunk, 'audio/wav')}
)

print(f"Response: {response.status_code}")
```

### 5. **Production Considerations**

#### Memory Management
- **Current**: Audio chunks stored in memory (function attribute)
- **Production**: Use Redis or database for persistent storage
- **Cleanup**: Ensure chunks are deleted after processing

#### Error Handling
- **Network Issues**: Handle streaming interruptions
- **Audio Quality**: Validate audio format and size
- **Fallback**: Switch to recording if streaming fails

#### Scaling
- **Multiple Calls**: Handle concurrent streaming calls
- **Load Balancing**: Distribute audio processing across workers
- **Monitoring**: Track streaming performance and errors

### 6. **Configuration Options**

#### Environment Variables
```bash
# Required for Twilio integration
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_phone_number

# Optional for streaming
FLASK_BASE_URL=https://your-domain.com
```

#### Twilio Configuration
```python
# In your Twilio console
# Phone Number > Voice Configuration
# Webhook: /phone/incoming-call-streaming
# HTTP Method: POST
# Primary Handler: Yes
```

### 7. **Monitoring and Debugging**

#### Logs to Watch
```python
# Key log messages to monitor
logger.info(f"Received streaming call from {from_number}")
logger.info(f"Stored audio chunk for call {call_sid}")
logger.info(f"Processing streamed audio for call {call_sid}")
logger.info(f"Real-time audio processing completed for call {call_sid}")
```

#### Common Issues
1. **Missing Credentials**: Check Twilio account SID and auth token
2. **Audio Format**: Verify audio format detection is working
3. **Memory Usage**: Monitor audio chunk storage
4. **Network Timeouts**: Check streaming endpoint availability

### 8. **Performance Comparison**

| Method | Latency | Memory | Complexity | User Experience |
|--------|---------|--------|------------|-----------------|
| **Streaming** | ~100-200ms | Low | High | Excellent |
| **Recording** | 1-3 seconds | Medium | Low | Good |
| **Hybrid** | Variable | Medium | Medium | Very Good |

### 9. **Next Steps**

1. **Test Basic Streaming**: Verify endpoints work with test data
2. **Integrate with Twilio**: Configure webhook for streaming calls
3. **Optimize Processing**: Fine-tune audio chunk handling
4. **Add Monitoring**: Implement performance tracking
5. **Production Deployment**: Scale and monitor in production

## Summary

The new functions provide a foundation for real-time audio processing:

- **`process_realtime_audio`**: Processes streaming audio chunks
- **`get_streaming_audio_url`**: Gets streaming URLs (placeholder for Media Streams)
- **New Routes**: Handle streaming calls and audio chunks
- **Enhanced Handler**: Supports both recording and streaming modes

Choose the approach that best fits your use case:
- **Real-time**: Use streaming for immediate responses
- **Reliability**: Use recording for guaranteed audio capture
- **Hybrid**: Combine both for best user experience

# Voice pipeline

## Supported mode

Only `VOICE_PIPELINE=deepgram_agent` is supported. Deepgram Agent owns speech
recognition, turn detection, LLM/tool orchestration, TTS, barge-in, and
conversation state for Twilio Media Streams.

```text
Twilio μ-law 8 kHz
  → FastAPI VoiceSession bridge
  → Deepgram Agent (global DEEPGRAM_API_KEY)
  → appointment/calendar tools
  → Deepgram Agent TTS
  → Twilio
```

Any other `VOICE_PIPELINE` value fails application startup.

## Credentials

Speech uses the platform-managed `DEEPGRAM_API_KEY` (and optional
`DEEPGRAM_REGION` / `DEEPGRAM_AGENT_URL`). Tenant Settings no longer collect
per-user Deepgram keys.

## Reconnect

Transient Deepgram disconnects reconnect within
`DEEPGRAM_RECONNECT_MAX_ATTEMPTS` and `DEEPGRAM_RECONNECT_DEADLINE_SECONDS`.
Authentication failures terminate the call immediately.

## Hybrid mode (removed)

The former `VOICE_PIPELINE=hybrid` path (NVIDIA STT + local LLM + Deepgram TTS)
is not supported and has been removed from the codebase.

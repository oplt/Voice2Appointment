# Hybrid Deepgram + NVIDIA speech

## Runtime modes

`VOICE_PIPELINE=deepgram_agent` is the production default. Deepgram continues to own
speech recognition, turn detection, LLM/tool orchestration, TTS, barge-in, and
conversation state.

`VOICE_PIPELINE=hybrid` separates those responsibilities:

```text
Twilio μ-law 8 kHz
  → configured STT (Deepgram Listen or NVIDIA Speech NIM)
  → OpenAI-compatible LLM
  → existing appointment/calendar tools
  → Deepgram TTS μ-law 8 kHz
  → Twilio
```

Provider selection happens once when a call starts. `STT_FALLBACK_PROVIDER` may
select the other provider only if the configured provider is unavailable at that
point; the gateway never switches in the middle of an utterance.

## NVIDIA deployment contract

The application does not import NeMo or load CUDA in FastAPI/Uvicorn workers. Run
the current NVIDIA Speech NIM container separately and expose its HTTP/WebSocket
port to the voice gateway. NIM loads and optimizes the model once. The gateway's
startup warmup checks `/v1/health/ready` and opens one realtime session; a failed
warmup is non-fatal because call-start fallback remains available.

The verified target is `nvidia/nemotron-3.5-asr-streaming-0.6b` via the
`nemotron-asr-streaming` NIM with `NIM_TAGS_SELECTOR=type=multi`. It is a
streaming-only 0.6B model. The multilingual profile includes English, Dutch,
French, German, and Turkish as transcription-ready locales, and supports automatic
language detection. The realtime API accepts mono PCM16 at 16 kHz, so only the
NVIDIA adapter decodes and upsamples Twilio's mono μ-law 8 kHz stream.

Follow NVIDIA's current deployment guide rather than pinning a GPU image in this
repository:

- Model and license: https://build.nvidia.com/nvidia/nemotron-asr-streaming/modelcard
- Deployment: https://docs.nvidia.com/nim/speech/latest/get-started/tutorials/asr.html
- Realtime API: https://docs.nvidia.com/nim/speech/latest/reference/api-references/asr/realtime-asr.html
- Hardware/software matrix: https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html

As of the verified 26.05 documentation, the container is governed by the NVIDIA
Software License Agreement and the model by the NVIDIA Open Model License. The
support matrix requires Linux, NVIDIA Docker 23.0.1+, driver 535+, a compute
capability 8.0+ GPU, and at least 16 GB VRAM at the host level. The selected
batch-32 profile reports 8 GB CPU and 6 GB GPU memory. There is no NVIDIA Python
runtime compatibility constraint in the application process: it uses NVIDIA's
official realtime WebSocket API with the project's Python 3.12-compatible
`websockets` and `httpx` dependencies.

Minimum hybrid configuration:

```dotenv
VOICE_PIPELINE=hybrid
STT_PROVIDER=nvidia
STT_FALLBACK_PROVIDER=deepgram
NVIDIA_STT_URL=http://nvidia-stt:9000
NVIDIA_STT_MODEL=nemotron-3.5-asr-streaming-0.6b
NVIDIA_STT_LANGUAGE=auto
LLM_API_KEY=...
DEEPGRAM_API_KEY=...
```

## Benchmarking and selection

Capture consented representative Twilio μ-law 8 kHz calls for `en-US`, `nl-NL`,
`fr-FR`, `de-DE`, and `tr-TR`. Include names, emails, phone numbers, street names,
dates, times, and company names. Submit the same audio to Deepgram Nova-3,
Deepgram Flux, and Nemotron 3.5. Store one JSON object per result:

```json
{"provider":"nvidia_nemotron_3_5","language":"nl-NL","audio_path":"audio/nl-01.wav","reference":"...","transcript":"...","entities":["..."],"date_times":["..."],"first_partial_ms":120,"final_transcript_ms":540,"gpu_utilization_percent":42,"ram_mb":8100,"cost_per_minute":0.004}
```

Then run:

```bash
python backend/scripts/benchmark_stt.py benchmark-results.jsonl --output report.json
```

The report groups WER, entity accuracy, date/time accuracy, first-partial latency,
final latency, GPU utilization, RAM, and cost/minute by provider and language.
Do not make a production selection until this dataset is populated.

Provisional modes, pending local benchmark evidence:

- Default SaaS or low-infrastructure deployments: Deepgram Agent.
- Deployments that must self-host audio transcription and have a supported GPU:
  NVIDIA hybrid. Note that the current LLM and TTS configuration can still send
  transcript text to their configured providers; validate that data path against
  the deployment's privacy requirements.
- High-volume GPU-equipped deployments: choose NVIDIA only when measured
  concurrency and cost/minute beat the hosted path at the required accuracy.
- Development: Deepgram by default; NVIDIA when a local NIM is already available.

NVIDIA replaces STT only. It is not evidence that NVIDIA is globally better than
Deepgram or a replacement for Deepgram Voice Agent.

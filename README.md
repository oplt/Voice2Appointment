# Voice2Appointment

Modular monolith: **React + Vite + TypeScript + MUI** frontend and **FastAPI** backend.

Voice appointment scheduling with Twilio, Deepgram, and Google Calendar.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React, Vite, TypeScript, MUI, MUI X Charts |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Data | PostgreSQL, Redis, Celery |
| Integrations | Twilio, Deepgram, Google Calendar |

## Repository layout

```text
frontend/          React SPA
backend/app/       FastAPI modular monolith
backend/migrations Alembic
docker/            Dockerfiles + nginx
compose.yaml       postgres, redis, web, voice, worker, frontend
DESIGN.md          UI authority
```

## Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL (or Docker)
- Redis (for Celery recordings)

## Quick start (local)

```bash
cp .env.example .env   # once; edit secrets
make local             # backend :8000 + frontend :5173; opens the homepage in a new tab
```

Required in `.env`: `SECRET_KEY`, `FERNET_KEY`, `DATABASE_URL`. Generate a Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Uses `Procfile` + [honcho](https://github.com/nickstenning/honcho). `make local` opens http://localhost:5173 when Vite is ready. Vite proxies `/api` and `/ws` to the API.

### Manual (without Make)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

PYTHONPATH=backend alembic upgrade head
cd backend
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# or: python run.py
# or: make migrate && make backend
```

Production process split (web HTTP vs voice WebSocket):

```bash
# Web API (Gunicorn + UvicornWorker) — asgi:app has no /ws
cd backend && PYTHONPATH=. gunicorn asgi:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
# Voice gateway — voice_asgi:app is WebSocket + health only
cd backend && PYTHONPATH=. uvicorn voice_asgi:app --host 0.0.0.0 --port 8001
# Or: honcho -f Procfile.production start
```

Health probes: `GET /health/live` (liveness), `GET /health/ready` (database + Redis only).

Frontend:

```bash
cd frontend
npm install
npm run dev
```

### 4. Celery worker (optional, recordings)

```bash
cd backend
PYTHONPATH=. celery -A app.workers.celery_app.celery_app worker --loglevel=INFO
```

## Docker

```bash
docker compose up --build
```

- Frontend: http://localhost:3000 (nginx proxies `/api` → `web`, `/ws` → `voice`)
- Web API: http://localhost:8000
- Voice gateway: internal `:8001` (reached via nginx `/ws/`)
- Health: `/health/live`, `/health/ready`
- OpenAPI docs are disabled when `APP_ENV=production`

## API surface (selected)

```text
GET  /health/live
GET  /health/ready
GET  /health
GET  /api/v1/health
POST /api/v1/auth/login|register|logout
GET  /api/v1/auth/csrf
GET  /api/v1/auth/me
GET  /api/v1/dashboard/summary
CRUD /api/v1/appointments
GET  /api/v1/calendars/status|events|availability
GET  /api/v1/analytics/summary
POST /api/v1/analytics/fetch-twilio
GET/PATCH /api/v1/users/me
POST /api/v1/telephony/twilio/voice
POST /api/v1/telephony/twilio/recording
WS   /ws/voice
```

### Password-reset delivery

Each reset request replaces any previous unconsumed reset nonce for that account.
The new nonce is committed before its retryable mail job is published; broker or
SMTP retries reuse that same one-time link and never fall back to inline SMTP.

### Production schema release

The Compose `migrate` service is the only production migration actor. It must
complete successfully before web, voice, worker, or beat starts. Deploy
backward-compatible schema changes before application code; on rollback, deploy
the prior application only while its required schema remains compatible. Run
local migrations explicitly with `make migrate`.

### Production request boundary

Production requires explicit `ALLOWED_HOSTS`, HTTPS public/frontend/Google
callback URLs, and HTTPS non-wildcard CORS origins. nginx is the TLS terminator
in the supported deployment and is responsible for HSTS only after TLS is
verified; direct application deployments must provide an equivalent TLS edge.

`GET /api/v1/analytics/summary` returns compact chart JSON (series + country counts). The SPA renders charts with MUI X Charts — no server-side Matplotlib/Folium/PNG or world GeoJSON.

Observability: JSON structured logs (`LOG_FORMAT=json`) include `request_id`, `call_sid`, `user_id`, and `operation`. Optional Sentry via `SENTRY_DSN`.

Provider secrets stay on the backend. React never receives Google/Twilio/Deepgram tokens.

### Settings contract

`config_json` is internal persistence, not a public settings field. Profile
updates reject it; booking policy and product preferences are changed only via
their typed `/api/v1/users/me/booking-policy` and
`/api/v1/users/me/product-prefs` endpoints. Booking windows are saved in sorted
canonical `HH:MM` form and same-day overlaps are rejected. Existing legacy JSON
is preserved on read; operators should validate it before editing rather than
overwriting it with raw profile data.

### Error envelope

Public provider failures use `{"detail":{"code","message","retryable"}}`.
The stable code and retryability are the versioned contract; provider text,
URLs, tokens, and exception messages are never returned or logged as fields.

When Google Calendar is disconnected, appointment creation uses the same
local-only policy in HTTP and voice: creates are immediately `confirmed`, and
no external availability or mutation is attempted. Connected calendar mutations
first persist a pending provider operation, then reconcile by operation
key/event ID after an ambiguous provider or process failure.

Voice media queues are bounded by `VOICE_AUDIO_QUEUE_MAXSIZE` (1–500 frames).
During a normal Deepgram bridge, overflow drops the oldest queued frame to keep
memory and latency bounded; `VOICE_AUDIO_QUEUE_MAX_DROPS` (1–500, default 50)
then terminates the call with `voice:audio_backpressure` rather than silently
continuing sustained audio loss. Reconnect buffering uses its separate
`VOICE_RECONNECT_BUFFER_FRAMES` limit and is discarded before a replacement
agent starts. `/health/metrics` exposes only aggregate Twilio queue/anomaly and
bridge-latency series, labeled by provider/result and never by call or payload.

### Deepgram credential operation

`DEEPGRAM_API_KEY` is the only Deepgram credential source. It is set in the
server runtime environment or secret manager; tenant/user settings never accept
or return a Deepgram key. Rotate it by updating the runtime secret and
restarting the HTTP and voice gateway processes. New voice connections then use
the replacement key; existing provider connections should be allowed to end or
be drained before revoking the old key. Do not place either value in browser
configuration, logs, metrics, error messages, or support tickets.

Startup does not contact Deepgram. `/health/ready` checks only database and
Redis, so it remains an infrastructure readiness signal rather than a provider
credential check. A missing or invalid `DEEPGRAM_API_KEY` is detected when a
voice connection is opened: the call follows the existing safe fallback path
and records only the non-secret `deepgram:auth` reason.

Legacy encrypted values may still exist in `res_user.deepgram_api_key` on
databases upgraded from earlier versions. The application no longer reads that
column. Before the column can be removed, an authorized operator must run and
record this inventory using a privileged database session:

```sql
SELECT count(*) AS legacy_deepgram_key_rows
FROM res_user
WHERE deepgram_api_key IS NOT NULL;
```

Do not export or decrypt those values. Obtain written approval that specifies
secure deletion or an approved migration/retention policy, record the result,
then deploy the dedicated column-drop migration. Its rollback must restore an
empty nullable column only; dropped secrets cannot be recovered.

## Tests & lint

```bash
# Backend
PYTHONPATH=backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest backend/tests -q
cd backend && ruff check app run.py asgi.py voice_asgi.py && mypy
cd backend && pip-audit -r requirements.txt

# Migrations (needs DATABASE_URL; run from repository root)
PYTHONPATH=backend alembic upgrade head

# Frontend
cd frontend && npm ci && npm test && npm run build
```

GitHub Actions (`.github/workflows/ci.yml`) runs, in order: install → ruff → mypy → pytest → migration test → `pip-audit` → Docker image builds (plus a parallel frontend job).

## Design

UI follows `DESIGN.md` (Tesla-inspired: white canvas, Electric Blue `#3E6AE1`, minimal chrome, no shadows).

## Architecture notes

- Single deployable backend (modular monolith — not microservices)
- Sync SQLAlchemy sessions
- Domain logic lives under `app/*/service.py` without Flask
- Voice WebSocket is transport-thin; tools live in `app/calendars/tools.py`

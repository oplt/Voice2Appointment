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
make local             # backend :8000 + frontend :5173
```

Required in `.env`: `SECRET_KEY`, `FERNET_KEY`, `DATABASE_URL`. Generate a Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Uses `Procfile` + [honcho](https://github.com/nickstenning/honcho). Open http://localhost:5173 — Vite proxies `/api` and `/ws` to the API.

### Manual (without Make)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

cd backend
PYTHONPATH=. alembic upgrade head
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

`GET /api/v1/analytics/summary` returns compact chart JSON (series + country counts). The SPA renders charts with MUI X Charts — no server-side Matplotlib/Folium/PNG or world GeoJSON.

Observability: JSON structured logs (`LOG_FORMAT=json`) include `request_id`, `call_sid`, `user_id`, and `operation`. Optional Sentry via `SENTRY_DSN`.

Provider secrets stay on the backend. React never receives Google/Twilio/Deepgram tokens.

## Tests & lint

```bash
# Backend
PYTHONPATH=backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest backend/tests -q
cd backend && ruff check app run.py asgi.py voice_asgi.py && mypy
cd backend && pip-audit -r requirements.txt

# Migrations (needs DATABASE_URL)
cd backend && PYTHONPATH=. alembic upgrade head

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

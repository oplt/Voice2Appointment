# AGENTS.md

## Architecture

Voice2Appointment is a modular monolith:

* Backend: Python 3.12, FastAPI, Pydantic, sync SQLAlchemy 2, Alembic
* Frontend: React, TypeScript, Vite, MUI
* Data/jobs: PostgreSQL, Redis, Celery
* Integrations: Twilio, Deepgram, Google Calendar

Do not convert the backend to microservices or async SQLAlchemy unless explicitly requested.

## Repository map

```text
backend/app/        FastAPI feature modules
backend/app/db/     SQLAlchemy models/session
backend/migrations/ Alembic migrations
backend/tests/      Backend tests
backend/asgi.py     Production HTTP API
backend/voice_asgi.py Production voice WebSocket gateway

frontend/src/api/        Backend API access
frontend/src/features/   Feature-specific UI
frontend/src/pages/      Route-level UI
frontend/src/components/ Shared components
frontend/src/theme/      MUI theme

DESIGN.md            UI design authority
Makefile             Development commands
compose.yaml         Local/container services
```

## Backend conventions

Features normally live under `backend/app/<feature>/`.

Use existing responsibilities when present:

* `router.py` — HTTP transport
* `schemas.py` — Pydantic contracts
* `service.py` — application/domain logic
* `providers/` — external integrations

Keep routers thin and business logic in services/domain code.

Database changes require both SQLAlchemy model changes and an Alembic migration.

Use existing provider boundaries for Twilio, Deepgram, and Google Calendar. Provider credentials remain backend-only.

## HTTP / voice boundary

`backend/app/factory.py` creates the shared application.

Production intentionally separates:

* `backend/asgi.py` — HTTP API
* `backend/voice_asgi.py` — voice WebSocket gateway

Preserve this split unless explicitly changing deployment architecture.

Keep the voice gateway transport-focused and reuse existing services/tools.

Preserve `/api/v1/...`, `/ws/voice`, and health contracts unless explicitly changing them.

## Frontend

Use existing `api/`, `features/`, `pages/`, `components/`, and `theme/` boundaries.

Backend remains authoritative for business rules.

For visual/UX work, consult the relevant section of `DESIGN.md`.
Do not read `DESIGN.md` for backend-only tasks.

## Validation

Focused backend test:

```bash
PYTHONPATH=backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
pytest -p timeout backend/tests/<test>.py -q
```

Python checks when relevant:

```bash
cd backend && ruff check <changed-paths>
cd backend && mypy
```

Focused frontend test:

```bash
cd frontend && npm test -- <test-or-pattern>
```

Frontend checks when relevant:

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

Use `.github/workflows/ci.yml` as the authority for full CI; do not reproduce full CI locally unless needed.

## Reference files

* `README.md` — setup, runtime, API, deployment
* `DESIGN.md` — frontend visual rules
* `.env.example` — configuration contract
* `backend/pyproject.toml` — Python test/lint/type-check configuration
* `frontend/package.json` — frontend scripts

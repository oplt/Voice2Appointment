.PHONY: local help backend frontend install migrate

PYTHON ?= $(CURDIR)/.venv/bin/python
PIP ?= $(CURDIR)/.venv/bin/pip
HONCHO ?= $(CURDIR)/.venv/bin/honcho
UVICORN ?= $(CURDIR)/.venv/bin/uvicorn

help:
	@echo "Targets:"
	@echo "  make local     Start backend (:8000) + frontend (:5173) via Procfile"
	@echo "  make backend   Start FastAPI only"
	@echo "  make frontend  Start Vite only"
	@echo "  make migrate   Run Alembic migrations (alembic upgrade head)"
	@echo "  make install   Install Python + Node deps (incl. honcho)"

install:
	@test -x $(PYTHON) || python3.12 -m venv .venv
	$(PIP) install -r backend/requirements.txt -r backend/requirements-dev.txt honcho
	cd frontend && npm install

migrate:
	@test -x $(PYTHON) || $(MAKE) install
	cd backend && PYTHONPATH=. ../.venv/bin/alembic upgrade head

local:
	@test -x $(HONCHO) && test -x $(UVICORN) || $(MAKE) install
	@test -d frontend/node_modules || (cd frontend && npm install)
	@$(MAKE) migrate
	@echo "Backend  http://127.0.0.1:8000"
	@echo "Frontend http://127.0.0.1:5173"
	$(HONCHO) start -f Procfile

backend:
	@test -x $(UVICORN) || $(MAKE) install
	@$(MAKE) migrate
	cd backend && PYTHONPATH=. ../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	@test -d frontend/node_modules || (cd frontend && npm install)
	cd frontend && npm run dev

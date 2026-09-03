.PHONY: local help backend frontend install migrate free-ports open-home

PYTHON ?= $(CURDIR)/.venv/bin/python
PIP ?= $(CURDIR)/.venv/bin/pip
HONCHO ?= $(CURDIR)/.venv/bin/honcho
UVICORN ?= $(CURDIR)/.venv/bin/uvicorn
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173

help:
	@echo "Targets:"
	@echo "  make local      Start backend (:$(BACKEND_PORT)) + frontend (:$(FRONTEND_PORT)) and open the homepage"
	@echo "  make backend    Start FastAPI only"
	@echo "  make frontend   Start Vite only"
	@echo "  make migrate    Run Alembic migrations (alembic upgrade head)"
	@echo "  make install    Install Python + Node deps (incl. honcho)"
	@echo "  make free-ports Kill processes listening on :$(BACKEND_PORT) and :$(FRONTEND_PORT)"

# SIGTERM listeners on PORTS. No-op if a port is already free.
free-ports: PORTS ?= $(BACKEND_PORT) $(FRONTEND_PORT)
free-ports:
	@for port in $(PORTS); do \
		if command -v fuser >/dev/null 2>&1; then \
			fuser -k -TERM $$port/tcp >/dev/null 2>&1 || true; \
		elif command -v lsof >/dev/null 2>&1; then \
			pids=$$(lsof -tiTCP:$$port -sTCP:LISTEN 2>/dev/null || true); \
			if [ -n "$$pids" ]; then kill $$pids 2>/dev/null || true; fi; \
		else \
			echo "Neither fuser nor lsof found; cannot free port $$port"; \
		fi; \
	done; \
	sleep 0.3

install:
	@test -x $(PYTHON) || python3.12 -m venv .venv
	$(PIP) install -r backend/requirements.txt -r backend/requirements-dev.txt honcho
	cd frontend && npm install

migrate:
	@test -x $(PYTHON) || $(MAKE) install
	cd backend && PYTHONPATH=. ../.venv/bin/python scripts/alembic_upgrade.py

local:
	@test -x $(HONCHO) && test -x $(UVICORN) || $(MAKE) install
	@test -d frontend/node_modules || (cd frontend && npm install)
	@$(MAKE) migrate
	@$(MAKE) free-ports
	@echo "Backend  http://127.0.0.1:$(BACKEND_PORT)"
	@echo "Frontend http://127.0.0.1:$(FRONTEND_PORT)"
	@$(MAKE) open-home &
	$(HONCHO) start -f Procfile

# Wait until Vite answers, then open the homepage in a new tab of the default browser.
open-home:
	@url="http://127.0.0.1:$(FRONTEND_PORT)/"; \
	ready=0; \
	for _ in $$(seq 1 80); do \
		if $(PYTHON) -c "import urllib.request; urllib.request.urlopen('$$url', timeout=0.5)" >/dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		sleep 0.25; \
	done; \
	if [ "$$ready" != 1 ]; then \
		echo "Frontend did not become ready; open $$url manually"; \
		exit 0; \
	fi; \
	desktop=$$(xdg-settings get default-web-browser 2>/dev/null || true); \
	case "$$desktop" in \
		*firefox*) firefox --new-tab "$$url" >/dev/null 2>&1 || true ;; \
		*chrome*|*chromium*|*brave*) \
			cmd=$$(command -v google-chrome || command -v google-chrome-stable || command -v chromium-browser || command -v chromium || command -v brave-browser || true); \
			if [ -n "$$cmd" ]; then "$$cmd" --new-tab "$$url" >/dev/null 2>&1 || true; \
			elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$$url" >/dev/null 2>&1 || true; fi ;; \
		*) \
			if command -v xdg-open >/dev/null 2>&1; then xdg-open "$$url" >/dev/null 2>&1 || true; \
			else echo "Open $$url in your browser"; fi ;; \
	esac

backend:
	@test -x $(UVICORN) || $(MAKE) install
	@$(MAKE) migrate
	@$(MAKE) free-ports PORTS=$(BACKEND_PORT)
	cd backend && PYTHONPATH=. ../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port $(BACKEND_PORT)

frontend:
	@test -d frontend/node_modules || (cd frontend && npm install)
	@$(MAKE) free-ports PORTS=$(FRONTEND_PORT)
	cd frontend && npm run dev

# Testing

Canonical commands for deterministic backend and frontend validation (P7-01 / P7-08).

## Backend

From the repository root, with the project virtualenv activated:

```bash
cd backend
pip install -r requirements-dev.txt
ruff check app run.py asgi.py voice_asgi.py
mypy
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. pytest -p timeout tests -q
```

Or from the repo root (matches CI):

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend pytest -p timeout backend/tests -q
```

Notes:

- Pytest is configured with `--timeout=60` in `backend/pyproject.toml`. A hung
  `TestClient` fails with a timeout instead of hanging forever. When using
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, load the plugin explicitly: `-p timeout`.
  For hang diagnostics, also pass `--faulthandler-timeout=65` with `-p faulthandler`.
- Default unit tests use in-memory SQLite. Redis rate limiting is disabled in
  the autouse fixture so shared Redis state cannot flake auth/password-reset
  tests.
- Integration tests (`@pytest.mark.integration`) require PostgreSQL:

```bash
DATABASE_URL=postgresql://voice_asst:voice_asst@localhost:5432/voice_asst_ci \
  PYTHONPATH=backend pytest backend/tests -q -m integration
```

## Frontend

```bash
cd frontend
npm ci
npm run lint
npm test -- --run
npm run build
```

## Dependency audits

```bash
cd backend && pip-audit -r requirements.txt
cd frontend && npm audit --omit=dev
```

Network failure during an audit is a **failed / inconclusive** result, never a
clean pass. See `docs/security-audits.md`.

## Capacity harness (P8-01)

```bash
PYTHONPATH=backend python backend/scripts/voice_capacity_harness.py --stages 10,25,100 --cap 25
```

See `docs/capacity.md` and `docs/phase8-decisions.md`.

## Alembic

From the repository root:

```bash
alembic current
alembic upgrade head
# only when models changed, against an existing head:
# alembic revision --autogenerate -m "describe the change"
```

The chain already starts at `c9a6910c93ea` (initial schema). Do not generate another initial or “create users” migration.

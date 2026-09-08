#!/usr/bin/env bash
# Phase 13 production acceptance gate (local/CI helper).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "== backend acceptance =="
PYTHONPATH=backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  "${PYTHON:-python}" -m pytest -p timeout \
  backend/tests/test_phase13_production_acceptance.py \
  backend/tests/test_phase1_reliability.py \
  backend/tests/test_phase2_provider_io.py \
  backend/tests/test_phase7_tool_registry.py \
  backend/tests/test_phase12_observability.py \
  -q --timeout=60

echo "== frontend unit =="
(cd frontend && npm test)

echo "== frontend build =="
(cd frontend && npm run build)

echo "PASS: Phase 13 acceptance commands completed."
echo "Reminder: live voice load + ENABLE_* for production still require ops sign-off."

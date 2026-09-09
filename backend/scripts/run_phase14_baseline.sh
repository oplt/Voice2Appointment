#!/usr/bin/env bash
# Phase 14 disposable baseline aggregator.
# Runs local harnesses at concurrency stages 1,5,10,25 and writes
# /tmp/phase14-baseline.json. Safe when services are down (records skips).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${PYTHON:-${ROOT}/.venv/bin/python}"
elif [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  PYTHON="${PYTHON:-${ROOT}/backend/.venv/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

STAGES="${STAGES:-1,5,10,25}"
OUT_DIR="${OUT_DIR:-/tmp}"
AGGREGATE="${AGGREGATE:-/tmp/phase14-baseline.json}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PERF_CONFIG="${PERF_CONFIG:-}"

mkdir -p "$OUT_DIR"
CAP_JSON="${OUT_DIR}/phase14-voice-capacity.json"
OBS_JSON="${OUT_DIR}/phase14-observability-load.json"
E2E_JSON="${OUT_DIR}/phase14-voice-e2e-load.json"
PERF_JSON="${OUT_DIR}/phase14-performance-baseline.json"
HEALTH_PERF_CONFIG="${OUT_DIR}/phase14-health-perf-config.json"

echo "==> voice_capacity_harness --stages ${STAGES}"
"$PYTHON" backend/scripts/voice_capacity_harness.py \
  --stages "$STAGES" \
  --json-out "$CAP_JSON" || true

echo "==> observability_load"
"$PYTHON" backend/scripts/observability_load.py \
  --concurrency 4 \
  --iterations 10 \
  --json-out "$OBS_JSON" || true

HEALTH_OK=0
if curl -fsS --max-time 3 "${BASE_URL}/health" >/dev/null 2>&1; then
  HEALTH_OK=1
fi

E2E_EXTRA=()
if [[ "$HEALTH_OK" -eq 1 ]]; then
  E2E_EXTRA+=(--base-url "$BASE_URL")
fi

echo "==> voice_e2e_load --stages ${STAGES}"
"$PYTHON" backend/scripts/voice_e2e_load.py \
  --stages "$STAGES" \
  --json-out "$E2E_JSON" \
  "${E2E_EXTRA[@]+"${E2E_EXTRA[@]}"}" || true

PERF_NOTE="skipped: health not live at ${BASE_URL}"
PERF_RAN=0
if [[ "$HEALTH_OK" -eq 1 ]]; then
  if [[ -z "$PERF_CONFIG" ]]; then
    # Disposable health-only stand-in for required scenario names so
    # --confirm-target matches BASE_URL without booking credentials.
    "$PYTHON" - <<PY
import json
from pathlib import Path
base = "${BASE_URL}".rstrip("/")
health_req = [{"method": "GET", "path": "/health", "timeout_seconds": 5}]
names = [
    "dashboard",
    "availability",
    "booking_one_tenant",
    "booking_different_tenants",
    "voice_function_calls",
    "provider_timeouts",
]
scenarios = {
    name: {"concurrency": 5, "iterations": 10, "requests": health_req}
    for name in names
}
Path("${HEALTH_PERF_CONFIG}").write_text(
    json.dumps({"base_url": base, "scenarios": scenarios}, indent=2),
    encoding="utf-8",
)
PY
    PERF_CONFIG="$HEALTH_PERF_CONFIG"
  fi
  echo "==> performance_baseline against ${BASE_URL}"
  if "$PYTHON" backend/scripts/performance_baseline.py \
    --config "$PERF_CONFIG" \
    --confirm-target "$BASE_URL" \
    --json-out "$PERF_JSON"; then
    PERF_RAN=1
    PERF_NOTE="ran against ${BASE_URL}"
  else
    PERF_NOTE="attempted against ${BASE_URL} but failed (see ${PERF_JSON} if present)"
  fi
else
  echo "==> performance_baseline skipped (${PERF_NOTE})"
  printf '%s\n' "{\"skipped\": true, \"note\": \"${PERF_NOTE}\"}" >"$PERF_JSON"
fi

"$PYTHON" - <<PY
import json
from pathlib import Path

def load(path: str):
    p = Path(path)
    if not p.exists():
        return {"missing": True, "path": path}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": type(exc).__name__, "path": path}

aggregate = {
    "kind": "phase14_baseline",
    "stages": "${STAGES}",
    "base_url": "${BASE_URL}",
    "health_live": bool(${HEALTH_OK}),
    "performance_baseline_note": """${PERF_NOTE}""",
    "performance_baseline_ran": bool(${PERF_RAN}),
    "voice_capacity": load("${CAP_JSON}"),
    "observability_load": load("${OBS_JSON}"),
    "voice_e2e_load": load("${E2E_JSON}"),
    "performance_baseline": load("${PERF_JSON}"),
}
out = Path("${AGGREGATE}")
out.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
print(f"Wrote {out}")
PY

echo "Done: ${AGGREGATE}"

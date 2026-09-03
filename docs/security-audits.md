# Security and dependency audits (P7-08)

Release gates must run reproducibly. Audit outcomes:

| Outcome | Meaning | Release |
| --- | --- | --- |
| Clean (exit 0, no findings) | Advisory DB reachable; no known issues in scope | Allowed |
| Findings (non-zero, vulnerabilities listed) | Known CVEs or policy violations | Blocked until fixed or time-bounded exception |
| Inconclusive | Network / advisory DB unreachable or tooling crash before scan | Blocked — never treat as clean |

## Backend

```bash
cd backend
pip-audit -r requirements.txt
```

Time-bounded exceptions (if any) belong in the PR description with owner,
CVE id, and expiry date — not as silent `continue-on-error` in CI.

## Frontend

```bash
cd frontend
npm audit --omit=dev
```

## Lint / types

Backend: `ruff check app run.py asgi.py voice_asgi.py` and `mypy` must pass.
Frontend: `npm run lint` and `npm run build` (includes `tsc -b`) must pass.

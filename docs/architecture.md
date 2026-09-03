# Minimal architecture notes for the migrated modular monolith.
# Authoritative specs: ../architecture.txt and ../DESIGN.md

## Boundaries

- Browser → REST/WebSocket → FastAPI modules → SQLAlchemy / providers
- Secrets (Google/Twilio/Deepgram) never leave the backend
- Domain services must not import Flask or React

## Dashboard / analytics

KPI and funnel contracts: [dashboard-analytics.md](./dashboard-analytics.md)

## Product features (Phase 6)

Notifications, retention, handoff, setup: [product-features.md](./product-features.md)
Multilingual gate: [multilingual-gate.md](./multilingual-gate.md)

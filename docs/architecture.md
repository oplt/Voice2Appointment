# Minimal architecture notes for the migrated modular monolith.
# Authoritative specs: ../architecture.txt and ../DESIGN.md

## Boundaries

- Browser → REST/WebSocket → FastAPI modules → SQLAlchemy / providers
- Secrets (Google/Twilio/Deepgram) never leave the backend
- Domain services must not import Flask or React

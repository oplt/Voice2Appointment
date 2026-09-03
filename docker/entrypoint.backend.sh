#!/bin/sh
set -e
# Production path: migrate, then start. Never mutate schema from app code.
cd /app
alembic upgrade head
exec "$@"

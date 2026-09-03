#!/bin/sh
set -e
# Runtime services do not migrate. Set RUN_DB_MIGRATE=1 on the one-shot migrate job.
cd /app
if [ "${RUN_DB_MIGRATE:-0}" = "1" ]; then
  alembic upgrade head
fi
if [ "${MIGRATE_ONLY:-0}" = "1" ]; then
  exit 0
fi
exec "$@"

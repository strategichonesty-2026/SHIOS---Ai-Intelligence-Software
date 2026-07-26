#!/usr/bin/env sh
# Production entrypoint: migrate, then serve. Migrations are idempotent.
set -e
echo "Running migrations..."
alembic upgrade head
if [ "${BOOTSTRAP_ON_START}" = "true" ]; then
  echo "Bootstrapping first intelligence loop..."
  python -m app.cli run --mode full || echo "Bootstrap loop failed; API will still start."
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

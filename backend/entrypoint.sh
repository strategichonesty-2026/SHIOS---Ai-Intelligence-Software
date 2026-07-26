#!/usr/bin/env sh
set -e
echo "Starting SHIOS..."
echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo yes || echo NO)"
echo "ENVIRONMENT: ${ENVIRONMENT:-development}"
echo "Running migrations..."
alembic upgrade head
if [ "${BOOTSTRAP_ON_START}" = "true" ]; then
  echo "Bootstrapping..."
  python -m app.cli run --mode full || echo "Bootstrap failed; API will still start."
fi
echo "Starting uvicorn on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

#!/bin/sh
set -e
WORKERS="${PROCESSOR_WORKERS:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-300}"
PORT="${PORT:-8080}"
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "$WORKERS" \
  --bind "0.0.0.0:${PORT}" \
  --timeout "$TIMEOUT" \
  --graceful-timeout 60 \
  --access-logfile - \
  --error-logfile -

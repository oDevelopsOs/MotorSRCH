#!/bin/sh
set -e
WORKERS="${UVICORN_WORKERS:-2}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"
PORT="${PORT:-8000}"
exec gunicorn main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "$WORKERS" \
  --bind "0.0.0.0:${PORT}" \
  --timeout "$TIMEOUT" \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile -

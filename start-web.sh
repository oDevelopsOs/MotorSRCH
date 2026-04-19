#!/bin/sh
# Used when Render runs as native Python (not Docker): set Start Command to `sh start-web.sh`
# Docker deploys should use api/Dockerfile or root Dockerfile (ENTRYPOINT), not this script.
set -e
if [ -f ./api/main.py ]; then
  cd api
elif [ -f ./main.py ]; then
  :
else
  echo "start-web.sh: expected api/main.py (repo root) or main.py (api as root dir)" >&2
  exit 1
fi
WORKERS="${WEB_CONCURRENCY:-${UVICORN_WORKERS:-2}}"
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

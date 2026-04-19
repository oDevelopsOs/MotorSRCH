#!/usr/bin/env bash
# Prueba de carga rápida con Vegeta (Linux/macOS/WSL). Instalar: go install github.com/tsenart/vegeta/v12@latest
# Uso:
#   BASE_URL=http://127.0.0.1:8888 RATE=50 DURATION=30s ./scripts/loadtest-vegeta.sh
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8888}"
RATE="${RATE:-30}"
DURATION="${DURATION:-30s}"
QUERY="${QUERY:-loadtest}"

if ! command -v vegeta >/dev/null 2>&1; then
  echo "Instala vegeta: https://github.com/tsenart/vegeta#install"
  exit 1
fi

echo "Target: ${BASE_URL}/search?q=${QUERY}&limit=3  rate=${RATE}/s duration=${DURATION}"
echo "GET ${BASE_URL}/search?q=${QUERY}&limit=3" | vegeta attack -rate="${RATE}" -duration="${DURATION}" | vegeta report

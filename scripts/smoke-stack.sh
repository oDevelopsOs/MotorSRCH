#!/usr/bin/env bash
# Pruebas de humo del stack (Linux / VPS). Misma lógica que smoke-stack.ps1.
# Uso: chmod +x scripts/smoke-stack.sh && ./scripts/smoke-stack.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
NGINX_BASE="${NGINX_BASE:-http://127.0.0.1:8888}"
PROC_BASE="${PROC_BASE:-http://127.0.0.1:8081}"
SEARX_BASE="${SEARX_BASE:-http://127.0.0.1:8088}"
# Compose producción (processor no publicado): SKIP_PROCESSOR=1 API_BASE=http://127.0.0.1:8888
SKIP_PROCESSOR="${SKIP_PROCESSOR:-0}"

FAILED=0
step() {
  local name="$1" url="$2"
  local code
  code=$(curl -sS -o /tmp/smoke_last.txt -w "%{http_code}" --max-time 60 "$url") || true
  if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
    echo "[ OK ] $name -> HTTP $code"
  else
    echo "[FAIL] $name -> HTTP $code ($url)"
    FAILED=$((FAILED + 1))
  fi
}

echo "=== MotorDeBusqueda smoke (bash) ==="
echo ""

step "API health" "$API_BASE/health"
step "NGINX health" "$NGINX_BASE/health"
if [[ "$SKIP_PROCESSOR" == "1" ]]; then
  echo "[SKIP] Processor health (puerto no publicado; p. ej. docker-compose.prod)"
else
  step "Processor health" "$PROC_BASE/health"
fi

if [[ -f .env ]] && grep -qE '^[[:space:]]*ENABLE_SEARXNG[[:space:]]*=[[:space:]]*1[[:space:]]*$' .env; then
  step "SearXNG (host)" "$SEARX_BASE/"
else
  echo "[SKIP] SearXNG (ENABLE_SEARXNG no es 1 en .env)"
fi

step "GET /search" "$API_BASE/search?q=smoke+test&limit=3"
if grep -q '"results"' /tmp/smoke_last.txt 2>/dev/null; then
  echo "[ OK ] /search JSON contiene 'results'"
else
  echo "[FAIL] /search JSON sin clave 'results'"
  FAILED=$((FAILED + 1))
fi

step "GET /resolve" "$API_BASE/resolve?q=smoke+test&limit=3"
if grep -q '"results"' /tmp/smoke_last.txt 2>/dev/null; then
  echo "[ OK ] /resolve JSON contiene 'results'"
else
  echo "[FAIL] /resolve JSON sin clave 'results'"
  FAILED=$((FAILED + 1))
fi

echo ""
if [[ "$FAILED" -gt 0 ]]; then
  echo "=== SMOKE FALLIDO ($FAILED error(es)) ==="
  exit 1
fi
echo "=== SMOKE OK ==="
exit 0

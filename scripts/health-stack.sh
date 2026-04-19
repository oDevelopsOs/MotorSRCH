#!/usr/bin/env bash
# Comprueba /health de los servicios expuestos (después de compose up).
set -euo pipefail
BASE_API="${BASE_API:-http://127.0.0.1:8000}"
BASE_NGINX="${BASE_NGINX:-http://127.0.0.1:8888}"
BASE_PROC="${BASE_PROC:-http://127.0.0.1:8081}"

check() {
  name=$1
  url=$2
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" || echo "000")
  if [ "$code" = "200" ]; then
    echo "OK  $name ($url)"
  else
    echo "FAIL $name HTTP $code ($url)"
    return 1
  fi
}

check "API direct" "${BASE_API}/health"
check "NGINX" "${BASE_NGINX}/health"
check "Processor" "${BASE_PROC}/health"
echo "Done."

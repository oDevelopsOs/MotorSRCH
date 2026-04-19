#!/bin/sh
set -e
export NGINX_WORKER_CONNECTIONS="${NGINX_WORKER_CONNECTIONS:-4096}"
export NGINX_LIMIT_REQ_RATE="${NGINX_LIMIT_REQ_RATE:-200r/s}"
export NGINX_LIMIT_REQ_BURST="${NGINX_LIMIT_REQ_BURST:-100}"
export NGINX_SEARCH_CACHE_INACTIVE="${NGINX_SEARCH_CACHE_INACTIVE:-10m}"
export NGINX_SEARCH_CACHE_MAX="${NGINX_SEARCH_CACHE_MAX:-2g}"
export API_UPSTREAM_SERVERS="${API_UPSTREAM_SERVERS:-api:8000}"

API_UPSTREAM_BLOCK=""
for s in $(echo "$API_UPSTREAM_SERVERS" | tr ',' ' '); do
  s=$(echo "$s" | tr -d ' ')
  if [ -n "$s" ]; then
    API_UPSTREAM_BLOCK="${API_UPSTREAM_BLOCK}        server ${s};
"
  fi
done
export API_UPSTREAM_BLOCK

envsubst '${NGINX_WORKER_CONNECTIONS} ${NGINX_LIMIT_REQ_RATE} ${NGINX_LIMIT_REQ_BURST} ${NGINX_SEARCH_CACHE_INACTIVE} ${NGINX_SEARCH_CACHE_MAX} ${API_UPSTREAM_BLOCK}' \
  < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

exec nginx -g "daemon off;"

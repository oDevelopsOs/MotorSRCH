FROM nginx:1.27-alpine

RUN apk add --no-cache gettext \
  && mkdir -p /var/cache/nginx && chown nginx:nginx /var/cache/nginx

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]

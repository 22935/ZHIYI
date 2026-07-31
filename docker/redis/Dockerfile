ARG REDIS_IMAGE=public.ecr.aws/docker/library/redis:7.4.9-alpine@sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99
FROM ${REDIS_IMAGE}

COPY entrypoint.sh /usr/local/bin/kinlin-redis-entrypoint
COPY healthcheck.sh /usr/local/bin/kinlin-redis-healthcheck
RUN apk add --no-cache su-exec \
    && chmod 0755 /usr/local/bin/kinlin-redis-entrypoint /usr/local/bin/kinlin-redis-healthcheck

ENTRYPOINT ["/usr/local/bin/kinlin-redis-entrypoint"]

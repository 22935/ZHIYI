#!/bin/sh
set -eu

: "${KINLIN_DEPLOYMENT_ID:?KINLIN_DEPLOYMENT_ID is required}"
marker=/data/.kinlin-deployment-id
if [ -f "$marker" ] && [ "$(cat "$marker")" != "$KINLIN_DEPLOYMENT_ID" ]; then
  echo "Redis data deployment marker mismatch" >&2
  exit 1
fi
if [ ! -f "$marker" ]; then
  printf '%s\n' "$KINLIN_DEPLOYMENT_ID" > "$marker"
fi
chown -R redis:redis /data
source_secret=/run/secrets/redis_password
test -r "$source_secret" || { echo "Redis secret is unreadable" >&2; exit 78; }
install -d -m 0700 -o redis -g redis /run/kinlin-secrets
{
  echo "bind 0.0.0.0"
  echo "protected-mode yes"
  # RDB is the canonical persisted/backup format for P0/P1.  Enabling an empty
  # AOF before first start would take precedence over a restored dump.rdb.
  echo "appendonly no"
  echo "save 900 1"
  echo "save 300 10"
  echo "save 60 10000"
  echo "dir /data"
  echo "dbfilename dump.rdb"
  printf 'requirepass %s\n' "$(tr -d '\r\n' < "$source_secret")"
} > /run/kinlin-secrets/redis.conf
chown redis:redis /run/kinlin-secrets/redis.conf
chmod 0400 /run/kinlin-secrets/redis.conf
chmod 0700 /run/secrets
if su-exec redis test -r "$source_secret" 2>/dev/null; then
  echo "Redis runtime user can still read the bind-mounted secret source" >&2
  exit 78
fi
exec su-exec redis redis-server /run/kinlin-secrets/redis.conf

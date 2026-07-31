#!/bin/sh
set -eu
test -r /run/secrets/db_password || { echo "Flyway database secret is unreadable" >&2; exit 78; }
install -d -m 0700 -o 10004 -g 10004 /run/kinlin-secrets
{
  printf 'flyway.url=%s\n' "${FLYWAY_URL:?}"
  printf 'flyway.user=%s\n' "${FLYWAY_USER:?}"
  printf 'flyway.password=%s\n' "$(tr -d '\r\n' < /run/secrets/db_password)"
  echo 'flyway.baselineOnMigrate=false'
  echo 'flyway.validateOnMigrate=true'
  echo 'flyway.locations=filesystem:/flyway/sql'
} > /run/kinlin-secrets/flyway.conf
chown 10004:10004 /run/kinlin-secrets/flyway.conf
chmod 0400 /run/kinlin-secrets/flyway.conf
chmod 0700 /run/secrets
su-exec 10004:10004 test -r /run/kinlin-secrets/flyway.conf
if su-exec 10004:10004 test -r /run/secrets/db_password 2>/dev/null; then
  echo "Flyway runtime user can still read the bind-mounted secret source" >&2
  exit 78
fi
if su-exec 10001:10001 test -r /run/kinlin-secrets/flyway.conf 2>/dev/null; then
  echo "Flyway secret config is readable by an unauthorized UID" >&2
  exit 78
fi
exec su-exec 10004:10004 flyway -configFiles=/run/kinlin-secrets/flyway.conf "$@"

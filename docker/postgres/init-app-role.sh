#!/bin/sh
set -eu

if [ "${KINLIN_SKIP_APP_INIT:-false}" = true ]; then
  echo "Skipping application role initialization for isolated restore bootstrap"
  exit 0
fi

case "${KINLIN_DB_USER:?KINLIN_DB_USER is required}" in
  *[!A-Za-z0-9_]*|'') echo "unsafe KINLIN_DB_USER" >&2; exit 78 ;;
esac
case "${KINLIN_DB_NAME:?KINLIN_DB_NAME is required}" in
  *[!A-Za-z0-9_]*|'') echo "unsafe KINLIN_DB_NAME" >&2; exit 78 ;;
esac
app_secret=${KINLIN_DB_PASSWORD_FILE:-/run/kinlin-secrets/db_password}
test -r "$app_secret" || { echo "application database secret is unreadable" >&2; exit 78; }

app_password=$(tr -d '\r\n' < "$app_secret")
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v app_user="$KINLIN_DB_USER" -v app_password="$app_password" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
SQL
createdb --username "$POSTGRES_USER" --owner "$KINLIN_DB_USER" "$KINLIN_DB_NAME"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$KINLIN_DB_NAME" \
  -v app_user="$KINLIN_DB_USER" <<'SQL'
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SQL

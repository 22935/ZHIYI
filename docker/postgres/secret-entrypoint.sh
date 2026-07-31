#!/bin/sh
set -eu

target=/run/kinlin-secrets
postgres_uid=$(id -u postgres)
postgres_gid=$(id -g postgres)
install -d -m 0700 -o "$postgres_uid" -g "$postgres_gid" "$target"

copy_secret() {
  source_path=$1
  target_path=$2
  test -r "$source_path" || { echo "PostgreSQL secret is unreadable: $source_path" >&2; exit 78; }
  install -m 0400 -o "$postgres_uid" -g "$postgres_gid" "$source_path" "$target_path"
}

copy_secret /run/secrets/db_admin_password "$target/db_admin_password"
copy_secret /run/secrets/db_password "$target/db_password"
chmod 0700 /run/secrets
export POSTGRES_PASSWORD_FILE="$target/db_admin_password"
export KINLIN_DB_PASSWORD_FILE="$target/db_password"

su-exec postgres test -r "$target/db_admin_password"
if su-exec postgres test -r /run/secrets/db_admin_password 2>/dev/null; then
  echo "PostgreSQL runtime user can still read the bind-mounted secret source" >&2
  exit 78
fi
exec docker-entrypoint.sh "$@"

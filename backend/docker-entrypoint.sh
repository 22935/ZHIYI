#!/bin/sh
set -eu

target=/run/kinlin-secrets
install -d -m 0700 -o 10001 -g 10001 "$target"

copy_secret() {
  source_path=$1
  target_name=$2
  test -r "$source_path" || { echo "required secret is unreadable: $source_path" >&2; exit 78; }
  secret_value=$(tr -d '\r\n' < "$source_path")
  test -n "$secret_value" || { echo "required secret is empty: $source_path" >&2; exit 78; }
  umask 077
  printf '%s' "$secret_value" > "$target/$target_name"
  chown 10001:10001 "$target/$target_name"
  chmod 0400 "$target/$target_name"
}

copy_secret /run/secrets/db_password spring.datasource.password
copy_secret /run/secrets/redis_password spring.data.redis.password
copy_secret /run/secrets/jwt_secret app.jwt.secret
copy_secret /run/secrets/ai_internal_token ai.internal.token
chmod 0700 /run/secrets

su-exec 10001:10001 test -r "$target/spring.datasource.password"
if su-exec 10001:10001 test -r /run/secrets/db_password 2>/dev/null; then
  echo "backend runtime user can still read the bind-mounted secret source" >&2
  exit 78
fi
if su-exec 10002:10002 test -r "$target/spring.datasource.password" 2>/dev/null; then
  echo "backend secret is readable by an unauthorized UID" >&2
  exit 78
fi

marker=/app/data/uploads/.kinlin-deployment-id
mkdir -p "$(dirname "$marker")"
if test -f "$marker" && test "$(cat "$marker")" != "${KINLIN_DEPLOYMENT_ID:?}"; then
  echo "upload volume belongs to a different deployment" >&2
  exit 78
fi
echo "$KINLIN_DEPLOYMENT_ID" > "$marker"
chown -R 10001:10001 /app/data/uploads

if test "${KINLIN_SECRET_VERIFY_ONLY:-false}" = true; then
  echo "backend secrets verified uid=10001"
  exit 0
fi

data_peer=$(getent hosts postgres | awk 'NR==1 {print $1}')
data_ip=$(ip route get "$data_peer" | awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}')
agent_ip=$(ip route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}')
web_ip=
for candidate in $(hostname -i); do
  if test "$candidate" != "$data_ip" && test "$candidate" != "$agent_ip"; then
    web_ip=$candidate
    break
  fi
done
test -n "$web_ip" || { echo "unable to identify Backend web-network address" >&2; exit 78; }
printf '%s\n' "$web_ip" > /tmp/backend-listen-address
chown 10001:10001 /tmp/backend-listen-address
chmod 0444 /tmp/backend-listen-address
export SERVER_ADDRESS=$web_ip
exec su-exec 10001:10001 "$@"

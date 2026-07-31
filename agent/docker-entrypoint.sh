#!/bin/sh
set -eu

target=/run/kinlin-secrets
install -d -m 0700 -o 10002 -g 10002 "$target"
copy_secret() {
  source_path=$1
  target_name=$2
  required=${3:-true}
  if test ! -r "$source_path"; then
    test "$required" = false && return 0
    echo "required secret is unreadable: $source_path" >&2
    exit 78
  fi
  install -m 0400 -o 10002 -g 10002 "$source_path" "$target/$target_name"
}
copy_secret /run/secrets/ai_internal_token ai_internal_token
copy_secret /run/secrets/deepseek_api_key deepseek_api_key false
copy_secret /run/secrets/dashscope_api_key dashscope_api_key false
copy_secret /run/secrets/tavily_api_key tavily_api_key false
copy_secret /run/secrets/redis_password redis_password false
chmod 0700 /run/secrets

su-exec 10002:10002 test -r "$target/ai_internal_token"
if su-exec 10002:10002 test -r /run/secrets/ai_internal_token 2>/dev/null; then
  echo "AI runtime user can still read the bind-mounted secret source" >&2
  exit 78
fi
if su-exec 10001:10001 test -r "$target/ai_internal_token" 2>/dev/null; then
  echo "AI secret is readable by an unauthorized UID" >&2
  exit 78
fi

marker=/app/data/.kinlin-deployment-id
if test -f "$marker" && test "$(cat "$marker")" != "${KINLIN_DEPLOYMENT_ID:?}"; then
  echo "AgentOS volume belongs to a different deployment" >&2
  exit 78
fi
echo "$KINLIN_DEPLOYMENT_ID" > "$marker"
cache_marker=/app/.cache/.kinlin-deployment-id
if test -f "$cache_marker" && test "$(cat "$cache_marker")" != "$KINLIN_DEPLOYMENT_ID"; then
  echo "AI cache volume belongs to a different deployment" >&2
  exit 78
fi
echo "$KINLIN_DEPLOYMENT_ID" > "$cache_marker"
chown -R 10002:10002 /app/data /app/.cache

if test "${KINLIN_SECRET_VERIFY_ONLY:-false}" = true; then
  echo "AI secrets verified uid=10002"
  exit 0
fi
exec su-exec 10002:10002 "$@"

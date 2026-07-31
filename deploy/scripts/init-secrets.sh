#!/bin/sh
set -eu
target=${1:?usage: init-secrets.sh EXTERNAL_DIRECTORY}
[ ! -e "$target" ] || { echo "refusing to overwrite existing Secret directory: $target" >&2; exit 1; }
umask 077
mkdir -p "$target"
random_value() { if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$1"; else od -An -N "$1" -tx1 /dev/urandom | tr -d ' \n'; fi; }
random_value 24 > "$target/db_admin_password"
random_value 24 > "$target/db_password"
random_value 24 > "$target/redis_password"
random_value 48 > "$target/jwt_secret"
random_value 48 > "$target/ai_internal_token"
: > "$target/deepseek_api_key"
: > "$target/dashscope_api_key"
chmod 0600 "$target"/*
echo "Secret files initialized in $target"

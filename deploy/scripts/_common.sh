#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PACKAGE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
INSTALL_ROOT=${KINLIN_INSTALL_ROOT:-/opt/kinlin-ai}
ENV_FILE=${KINLIN_ENV_FILE:-/etc/kinlin-ai/deployment.env}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

normalize_arch() {
  case "$1" in
    x86_64|amd64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    *) fail "unsupported architecture: $1" ;;
  esac
}

version_ge() {
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)" = "$2" ]
}

load_manifest() {
  manifest=${1:-$PACKAGE_ROOT/manifest.env}
  [ -f "$manifest" ] || fail "missing manifest.env: $manifest"
  while IFS='=' read -r key value; do
    [ -n "$key" ] || continue
    case "$key" in
      RELEASE_VERSION|RELEASE_ARCH|MIN_UPGRADE_VERSION|ROLLBACK_COMPATIBLE|IMAGE_FRONTEND|IMAGE_BACKEND|IMAGE_AI_SERVICE|IMAGE_POSTGRES|IMAGE_REDIS|IMAGE_FLYWAY|IMAGE_ID_FRONTEND|IMAGE_ID_BACKEND|IMAGE_ID_AI_SERVICE|IMAGE_ID_POSTGRES|IMAGE_ID_REDIS|IMAGE_ID_FLYWAY)
        case "$value" in *[!A-Za-z0-9_./:@+-]*) fail "unsafe manifest value for $key" ;; esac
        export "$key=$value"
        ;;
      *) fail "unexpected manifest key: $key" ;;
    esac
  done < "$manifest"
}

load_deployment() {
  [ -f "$ENV_FILE" ] || fail "missing external deployment env: $ENV_FILE"
  deployment_id=$(sed -n 's/^KINLIN_DEPLOYMENT_ID=//p' "$ENV_FILE" | tail -n 1)
  secrets_dir=$(sed -n 's/^KINLIN_SECRETS_DIR=//p' "$ENV_FILE" | tail -n 1)
  case "$deployment_id" in ''|*[!a-z0-9-]*) fail "invalid KINLIN_DEPLOYMENT_ID" ;; esac
  [ ${#deployment_id} -ge 3 ] && [ ${#deployment_id} -le 32 ] || fail "invalid KINLIN_DEPLOYMENT_ID length"
  [ -d "$secrets_dir" ] || fail "Secret directory does not exist: $secrets_dir"
  for name in db_admin_password db_password redis_password jwt_secret ai_internal_token; do
    [ -f "$secrets_dir/$name" ] || fail "missing Secret file: $name"
  done
  export KINLIN_DEPLOYMENT_ID=$deployment_id KINLIN_SECRETS_DIR=$secrets_dir
}

release_home() {
  echo "$INSTALL_ROOT/releases/$1"
}

compose() {
  home=${KINLIN_RELEASE_HOME:-$PACKAGE_ROOT}
  docker compose \
    --env-file "$ENV_FILE" \
    --env-file "$home/config/images.release" \
    -f "$home/compose/compose.yaml" \
    -f "$home/compose/compose.prod.yaml" \
    -f "$home/compose/compose.release.yaml" \
    "$@"
}

verify_image_arches() {
  verify_image "$IMAGE_FRONTEND" "$IMAGE_ID_FRONTEND"
  verify_image "$IMAGE_BACKEND" "$IMAGE_ID_BACKEND"
  verify_image "$IMAGE_AI_SERVICE" "$IMAGE_ID_AI_SERVICE"
  verify_image "$IMAGE_POSTGRES" "$IMAGE_ID_POSTGRES"
  verify_image "$IMAGE_REDIS" "$IMAGE_ID_REDIS"
  verify_image "$IMAGE_FLYWAY" "$IMAGE_ID_FLYWAY"
}

verify_image() {
    ref=$1
    expected_id=$2
    actual=$(docker image inspect "$ref" --format '{{.Architecture}}' 2>/dev/null || true)
    [ -n "$actual" ] || fail "required image is not loaded: $ref"
    [ "$(normalize_arch "$actual")" = "$RELEASE_ARCH" ] || fail "image architecture mismatch: $ref actual=$actual package=$RELEASE_ARCH"
    actual_id=$(docker image inspect "$ref" --format '{{.Id}}')
    [ "$actual_id" = "$expected_id" ] || fail "image ID mismatch: $ref expected=$expected_id actual=$actual_id"
}

#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
[ "${1:-}" = "--to" ] && [ -n "${2:-}" ] || fail "usage: rollback.sh --to VERSION"
target=$2
home=$(release_home "$target")
[ -d "$home" ] || fail "target release is not retained: $target"
load_manifest "$home/manifest.env"
[ "$ROLLBACK_COMPATIBLE" = true ] || fail "release manifest does not permit image-only rollback after migration"
load_deployment
export KINLIN_RELEASE_HOME=$home
verify_image_arches
compose stop frontend backend ai-service
compose up -d --pull never --no-build --wait
compose exec -T frontend wget -qO- http://127.0.0.1:8080/health >/dev/null
ln -sfn "$home" "$INSTALL_ROOT/current"
echo "rolled application images back to $target; no volume or database migration was removed"

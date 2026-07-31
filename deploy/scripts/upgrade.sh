#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
"$SCRIPT_DIR/preflight.sh"
[ -L "$INSTALL_ROOT/current" ] || fail "existing managed installation is required"
load_manifest
load_deployment
current=$(cat "$INSTALL_ROOT/current/VERSION")
[ "$current" != "$RELEASE_VERSION" ] || fail "version is already installed"

"$INSTALL_ROOT/current/scripts/backup.sh" --output-root "$INSTALL_ROOT/backups"
for archive in "$PACKAGE_ROOT"/images/*.tar.gz; do gzip -dc "$archive" | docker load >/dev/null; done
verify_image_arches
home=$(release_home "$RELEASE_VERSION")
[ ! -e "$home" ] || fail "release directory already exists: $home"
cp -a "$PACKAGE_ROOT" "$home"
export KINLIN_RELEASE_HOME=$home
compose config --quiet
compose stop frontend backend ai-service
compose --profile migration run --rm --no-deps schema-tool migrate
compose up -d --pull never --no-build --wait
compose exec -T frontend wget -qO- http://127.0.0.1:8080/health >/dev/null
ln -sfn "$home" "$INSTALL_ROOT/current"
echo "upgraded Kinlin AI $current -> $RELEASE_VERSION"

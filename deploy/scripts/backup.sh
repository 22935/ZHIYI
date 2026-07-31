#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
load_manifest
load_deployment
case $# in
  0) output_root=$INSTALL_ROOT/backups ;;
  2) [ "$1" = "--output-root" ] || fail "usage: backup.sh [--output-root DIRECTORY]"; output_root=$2 ;;
  *) fail "usage: backup.sh [--output-root DIRECTORY]" ;;
esac
home=${KINLIN_RELEASE_HOME:-$PACKAGE_ROOT}
export KINLIN_RELEASE_COMPOSE=$home/compose/compose.release.yaml
export PYTHONPATH=$home
mkdir -p "$output_root"
compose stop frontend backend ai-service
trap 'compose up -d --pull never --no-build frontend backend ai-service >/dev/null 2>&1 || true' EXIT
(cd "$home/compose" && python3 -m scripts.infra.schema_audit --deployment-id "$KINLIN_DEPLOYMENT_ID" --output "$output_root/schema-audit.json")
(cd "$home/compose" && python3 -m scripts.infra.backup --deployment-id "$KINLIN_DEPLOYMENT_ID" --output-root "$output_root" --schema-report "$output_root/schema-audit.json" --maintenance-confirmed)
compose up -d --pull never --no-build --wait frontend backend ai-service
trap - EXIT

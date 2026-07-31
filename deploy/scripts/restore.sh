#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
[ $# -eq 3 ] || fail "usage: restore.sh BACKUP NEW_DEPLOYMENT_ID NEW_SECRET_DIRECTORY"
load_manifest
load_deployment
home=${KINLIN_RELEASE_HOME:-$PACKAGE_ROOT}
export KINLIN_RELEASE_COMPOSE=$home/compose/compose.release.yaml PYTHONPATH=$home
(cd "$home/compose" && python3 -m scripts.infra.restore "$1" --target-deployment-id "$2" --secrets-dir "$3" --execute)

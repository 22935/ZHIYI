#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"

for command in docker sha256sum awk sed grep df uname gzip sort; do
  command -v "$command" >/dev/null 2>&1 || fail "missing required command: $command"
done
docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable"
docker_version=$(docker version --format '{{.Server.Version}}')
compose_version=$(docker compose version --short)
version_ge "$docker_version" 24.0.0 || fail "Docker 24.0.0 or newer is required"
version_ge "$compose_version" 2.24.4 || fail "Docker Compose 2.24.4 or newer is required"

load_manifest
load_deployment
package_arch=$RELEASE_ARCH
kernel_arch=$(normalize_arch "$(uname -m)")
docker_arch=$(normalize_arch "$(docker info --format '{{.Architecture}}')")
[ "$kernel_arch" = "$package_arch" ] || fail "kernel/package architecture mismatch: $kernel_arch/$package_arch"
[ "$docker_arch" = "$package_arch" ] || fail "Docker/package architecture mismatch: $docker_arch/$package_arch"

(cd "$PACKAGE_ROOT" && sha256sum -c SHA256SUMS) || fail "package checksum verification failed"
available_kb=$(df -Pk "$INSTALL_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -z "$available_kb" ]; then
  available_kb=$(df -Pk / | awk 'NR==2 {print $4}')
fi
[ "$available_kb" -ge 10485760 ] || fail "at least 10 GiB free disk space is required"

if [ -f "$INSTALL_ROOT/deployment-id" ]; then
  [ "$(cat "$INSTALL_ROOT/deployment-id")" = "$KINLIN_DEPLOYMENT_ID" ] || fail "KINLIN_DEPLOYMENT_ID does not match installed deployment"
fi
if [ -f "$INSTALL_ROOT/current/VERSION" ]; then
  current=$(cat "$INSTALL_ROOT/current/VERSION")
  version_ge "$RELEASE_VERSION" "$current" || fail "downgrade installation is forbidden: $current -> $RELEASE_VERSION"
  version_ge "$current" "$MIN_UPGRADE_VERSION" || fail "upgrade crosses an unsupported version boundary"
fi

echo "preflight passed version=$RELEASE_VERSION arch=$RELEASE_ARCH deployment=$KINLIN_DEPLOYMENT_ID"

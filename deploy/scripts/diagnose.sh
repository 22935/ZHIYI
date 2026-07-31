#!/bin/sh
set -eu
. "$(dirname "$0")/_common.sh"
load_manifest
load_deployment
compose version
compose ps
docker info --format 'server={{.ServerVersion}} arch={{.Architecture}} root={{.DockerRootDir}}'
docker volume ls --filter "label=com.kinlin.deployment-id=$KINLIN_DEPLOYMENT_ID"
compose logs --no-color --tail 100 | sed -E 's/(password|secret|token|api[_-]?key)[^ ]*/\1=[REDACTED]/Ig'

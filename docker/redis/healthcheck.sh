#!/bin/sh
set -eu
export REDISCLI_AUTH="$(tr -d '\r\n' < /run/secrets/redis_password)"
exec redis-cli ping

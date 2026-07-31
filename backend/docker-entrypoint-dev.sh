#!/bin/sh
set -eu

install -d -m 0750 -o 10001 -g 10001 /home/kinlin /home/kinlin/.m2 /app/target /app/target/.jansi
if [ ! -f /home/kinlin/.m2/.kinlin-cache-seeded ]; then
    cp -a /opt/kinlin-m2/. /home/kinlin/.m2/
    touch /home/kinlin/.m2/.kinlin-cache-seeded
fi
chown 10001:10001 /home/kinlin /home/kinlin/.m2 /app/target /app/target/.jansi
if [ "${KINLIN_BACKEND_SOURCE_SYNC_ENABLED:-false}" = true ]; then
    /usr/local/bin/kinlin-sync-backend-source
fi
exec /usr/local/bin/kinlin-entrypoint "$@"

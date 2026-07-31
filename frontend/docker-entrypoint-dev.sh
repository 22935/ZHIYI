#!/bin/sh
set -eu

expected=$(sha256sum /app/package-lock.json | cut -d ' ' -f 1)
actual=$(cat /app/node_modules/.kinlin-package-lock.sha256 2>/dev/null || true)
if [ "$expected" != "$actual" ]; then
  echo "Frontend dependency manifest changed; synchronizing the node_modules volume"
  npm ci
  printf '%s\n' "$expected" > /app/node_modules/.kinlin-package-lock.sha256
else
  echo "Frontend dependency volume is current; skipping npm ci"
fi

exec "$@"

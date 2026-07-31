#!/bin/sh
set -eu

base_manifest=/app/requirements.lock
tools_manifest=/app/requirements.tools.lock
venv=/opt/kinlin-venv
expected=$(cat "$base_manifest" "$tools_manifest" | sha256sum | cut -d ' ' -f 1)
actual=$(cat "$venv/.kinlin-requirements.sha256" 2>/dev/null || true)
if [ "$expected" != "$actual" ]; then
  echo "Python dependency manifest changed; synchronizing the named virtualenv volume"
  "$venv/bin/pip" install --cache-dir /pip-cache --require-hashes --only-binary=:all: \
    -r "$base_manifest" \
    -r "$tools_manifest"
  printf '%s\n' "$expected" > "$venv/.kinlin-requirements.sha256"
else
  echo "Python dependency volume is current; skipping pip install"
fi

exec /usr/local/bin/kinlin-entrypoint "$@"

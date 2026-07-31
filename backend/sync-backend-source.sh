#!/bin/sh
set -eu

source_dir=${KINLIN_BACKEND_SOURCE_DIR:-/kinlin-host/backend-src}
target_dir=${KINLIN_BACKEND_SOURCE_CACHE_DIR:-/app/src}
build_dir=${KINLIN_BACKEND_BUILD_DIR:-/app/target}
lock_file=${KINLIN_BACKEND_SYNC_LOCK_FILE:-$build_dir/.kinlin-source-sync.lock}
lock_timeout=${KINLIN_BACKEND_SYNC_LOCK_TIMEOUT_SECONDS:-120}
runtime_uid=${KINLIN_BACKEND_RUNTIME_UID:-10001}
runtime_gid=${KINLIN_BACKEND_RUNTIME_GID:-10001}

fail() {
  echo "backend source sync failed: $*" >&2
  exit 78
}

monotonic_ms() {
  awk '{ printf "%.0f\n", $1 * 1000 }' /proc/uptime
}

test -d "$source_dir" || fail "source mount is unavailable: $source_dir"
test "$source_dir" != "$target_dir" || fail "source mount and cache directory must differ"
case "$target_dir" in
  ""|/) fail "unsafe cache directory: $target_dir" ;;
esac
case "$build_dir" in
  ""|/) fail "unsafe build directory: $build_dir" ;;
esac
case "$lock_timeout" in
  *[!0-9]*|"") fail "lock timeout must be a positive integer" ;;
esac
test "$lock_timeout" -gt 0 || fail "lock timeout must be a positive integer"

install -d -m 0755 -o "$runtime_uid" -g "$runtime_gid" "$target_dir"
install -d -m 0750 -o "$runtime_uid" -g "$runtime_gid" "$build_dir"
touch "$lock_file"
chown "$runtime_uid:$runtime_gid" "$lock_file"
chmod 0600 "$lock_file"

exec 9>"$lock_file"
lock_wait_started_ms=$(monotonic_ms)
if ! flock -x -w "$lock_timeout" 9; then
  echo "backend source sync lock timed out after ${lock_timeout}s: $lock_file" >&2
  exit 75
fi
lock_wait_finished_ms=$(monotonic_ms)
lock_wait_ms=$((lock_wait_finished_ms - lock_wait_started_ms))

changes_file=$(mktemp "${TMPDIR:-/tmp}/kinlin-backend-source-sync.XXXXXX")
trap 'rm -f "$changes_file"' EXIT HUP INT TERM
started_ms=$(monotonic_ms)

rsync -rltc \
  --delete \
  --itemize-changes \
  --out-format='KINLIN_RSYNC|%i|%n' \
  --chown="$runtime_uid:$runtime_gid" \
  --chmod='Du=rwx,Dgo=rx,Fu=rw,Fgo=r' \
  "$source_dir/" "$target_dir/" > "$changes_file"

deleted_count=0
changed_count=0
while IFS='|' read -r prefix item relative_path; do
  test "$prefix" = "KINLIN_RSYNC" || continue
  case "$item" in
    \*deleting*)
      deleted_count=$((deleted_count + 1))
      ;;
    *)
      update_type=$(printf '%s' "$item" | cut -c1)
      file_type=$(printf '%s' "$item" | cut -c2)
      case "$update_type:$file_type" in
        \>:d|c:d|h:d|.:d) ;;
        \>:*|c:*|h:*)
          changed_count=$((changed_count + 1))
          if test -e "$target_dir/$relative_path" || test -L "$target_dir/$relative_path"; then
            touch -h "$target_dir/$relative_path"
          fi
          ;;
      esac
      ;;
  esac
done < "$changes_file"

if test "$deleted_count" -gt 0; then
  rm -rf "$build_dir/classes" "$build_dir/generated-sources"
  sync_result=deleted
elif test "$changed_count" -gt 0; then
  sync_result=changed
else
  sync_result=unchanged
fi

awk -F'|' '$1 == "KINLIN_RSYNC" && ($2 ~ /^\*deleting/ || substr($2, 1, 1) ~ /^[>ch]$/) { print }' "$changes_file"
finished_ms=$(monotonic_ms)
elapsed_ms=$((finished_ms - started_ms))
echo "KINLIN_SOURCE_SYNC_RESULT=$sync_result"
echo "KINLIN_SOURCE_SYNC_CHANGED_COUNT=$changed_count"
echo "KINLIN_SOURCE_SYNC_DELETED_COUNT=$deleted_count"
echo "KINLIN_SOURCE_SYNC_LOCK_WAIT_MS=$lock_wait_ms"
echo "KINLIN_SOURCE_SYNC_ELAPSED_MS=$elapsed_ms"

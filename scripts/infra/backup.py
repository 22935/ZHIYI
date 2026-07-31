#!/usr/bin/env python3
"""Maintenance-window full backup for a canonical Kinlin deployment."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import shutil
from pathlib import Path

from scripts.infra.common import compose_command, run, validate_deployment_id, verify_volume_labels, volume_names, write_checksums, write_json


def compose(deployment_id: str, *args: str, capture: bool = True):
    secret_root = os.environ.get("KINLIN_SECRETS_DIR", str((Path(".secrets") / deployment_id).resolve()))
    return run(
        compose_command(*args),
        env={"KINLIN_DEPLOYMENT_ID": deployment_id, "KINLIN_SECRETS_DIR": secret_root},
        capture=capture,
    )


def dump_binary(deployment_id: str, output: Path, command: list[str]) -> None:
    secret_root = os.environ.get("KINLIN_SECRETS_DIR", str((Path(".secrets") / deployment_id).resolve()))
    with output.open("wb") as handle:
        subprocess.run(
            compose_command("exec", "-T", "postgres", *command),
            check=True,
            stdout=handle,
            env={**os.environ, "KINLIN_DEPLOYMENT_ID": deployment_id, "KINLIN_SECRETS_DIR": secret_root},
        )


def archive_volume(volume: str, output_dir: Path, filename: str) -> None:
    helper = os.environ.get("IMAGE_POSTGRES", os.environ.get("KINLIN_POSTGRES_IMAGE", "kinlin-ai-postgres:dev"))
    run(["docker", "run", "--rm", "--entrypoint", "tar", "-v", f"{volume}:/source:ro", "-v", f"{output_dir.resolve()}:/backup", helper, "-C", "/source", "-czf", f"/backup/{filename}", "."], capture=False)


def image_inventory(deployment_id: str) -> list[dict]:
    try:
        image_output = compose(deployment_id, "images", "--format", "json").stdout.strip()
        try:
            parsed = json.loads(image_output) if image_output else []
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            return [json.loads(line) for line in image_output.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        # Docker Desktop may prune an old manifest-list digest after a local
        # image tag is rebuilt while a container still references its config
        # image.  Container inspect remains the authoritative runtime record.
        container_ids = compose(deployment_id, "ps", "-aq").stdout.split()
        if not container_ids:
            raise
        inspected = json.loads(run(["docker", "inspect", *container_ids]).stdout)
        return [
            {
                "container": item["Name"].lstrip("/"),
                "service": item.get("Config", {}).get("Labels", {}).get("com.docker.compose.service"),
                "configuredImage": item.get("Config", {}).get("Image"),
                "runtimeImageId": item.get("Image"),
                "source": "container-inspect-fallback",
            }
            for item in inspected
        ]


def source_commit() -> str:
    configured = os.environ.get("KINLIN_SOURCE_COMMIT")
    if configured:
        return configured
    try:
        return run(["git", "rev-parse", "HEAD"]).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "packaged-windows-amd64"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--database", default="kinlin_ai")
    parser.add_argument("--app-db-user", default="kinlin_ai")
    parser.add_argument("--db-admin-user", default="postgres")
    parser.add_argument("--output-root", default="backups")
    parser.add_argument("--schema-report", required=True)
    parser.add_argument("--maintenance-confirmed", action="store_true")
    args = parser.parse_args()
    deployment_id = validate_deployment_id(args.deployment_id)
    schema_report_path = Path(args.schema_report).resolve()
    schema_report = json.loads(schema_report_path.read_text(encoding="utf-8"))
    if schema_report.get("state") not in {"managed", "legacy"}:
        raise SystemExit("backup requires a non-drift schema audit report")
    if schema_report.get("deploymentId") != deployment_id:
        raise SystemExit("schema audit report deployment ID does not match backup target")
    if not args.maintenance_confirmed:
        raise SystemExit("--maintenance-confirmed is required")
    running = set(compose(deployment_id, "ps", "--status", "running", "--services").stdout.split())
    writers = running & {"frontend", "backend", "ai-service"}
    if writers:
        raise SystemExit(f"write-capable services must be stopped: {sorted(writers)}")
    if not {"postgres", "redis"}.issubset(running):
        raise SystemExit("postgres and redis must be running for a consistent backup")

    volumes = volume_names(deployment_id)
    verify_volume_labels(deployment_id, volumes)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output_root) / f"{deployment_id}-{timestamp}"
    output.mkdir(parents=True, exist_ok=False)
    dump_binary(deployment_id, output / "postgres-globals.sql", ["pg_dumpall", "-U", args.db_admin_user, "--globals-only", "--no-role-passwords"])
    dump_binary(deployment_id, output / "postgres-database.dump", ["pg_dump", "-U", args.db_admin_user, "-d", args.database, "-Fc"])

    redis_script = r'''export REDISCLI_AUTH="$(tr -d '\r\n' < /run/secrets/redis_password)"
before=$(redis-cli LASTSAVE)
redis-cli BGSAVE >/dev/null
i=0
while [ "$i" -lt 60 ]; do
  now=$(redis-cli LASTSAVE)
  status=$(redis-cli INFO persistence | tr -d "\r" | sed -n "s/^rdb_last_bgsave_status://p")
  [ "$now" -gt "$before" ] && [ "$status" = ok ] && break
  i=$((i+1)); sleep 1
done
[ "$i" -lt 60 ] || exit 1
echo "dbsize=$(redis-cli DBSIZE)"
redis-cli INFO persistence | tr -d "\r" | grep "^rdb_last_bgsave_status:ok$"
redis-cli --scan | head -n 5 | while IFS= read -r key; do
  type=$(redis-cli --raw TYPE "$key")
  case "$type" in
    string) redis-cli --raw GET "$key" >/dev/null ;;
    hash) redis-cli --raw HSCAN "$key" 0 COUNT 1 >/dev/null ;;
    list) redis-cli --raw LRANGE "$key" 0 0 >/dev/null ;;
    set) redis-cli --raw SSCAN "$key" 0 COUNT 1 >/dev/null ;;
    zset) redis-cli --raw ZSCAN "$key" 0 COUNT 1 >/dev/null ;;
    stream) redis-cli --raw XRANGE "$key" - + COUNT 1 >/dev/null ;;
    *) redis-cli --raw EXISTS "$key" >/dev/null ;;
  esac
  digest=$(printf %s "$key" | sha256sum | cut -d " " -f1)
  echo "sample_read_ok type=$type key_sha256=$digest"
done'''
    redis_result = compose(deployment_id, "exec", "-T", "redis", "sh", "-ec", redis_script).stdout
    (output / "redis-verification.txt").write_text(redis_result, encoding="utf-8")
    compose(deployment_id, "cp", "redis:/data/dump.rdb", str(output / "redis-dump.rdb"), capture=False)

    archive_volume(volumes["backend_uploads_v11"], output, "backend-uploads.tar.gz")
    archive_volume(volumes["agentos_data_v11"], output, "agentos-data.tar.gz")
    archive_volume(volumes["ai_cache_v11"], output, "ai-cache.tar.gz")
    # The application is stopped before this point.  The backup helper needs a
    # writable source mount so SQLite can create/refresh WAL shared-memory state
    # while its online backup API takes the consistent snapshot.
    python_helper = os.environ.get("IMAGE_AI_SERVICE", os.environ.get("KINLIN_AI_IMAGE", "kinlin-ai-service:dev"))
    run(["docker", "run", "--rm", "--entrypoint", "python", "-v", f'{volumes["agentos_data_v11"]}:/data', "-v", f"{output.resolve()}:/backup", python_helper, "-c", "import sqlite3,json,pathlib; s=sqlite3.connect('file:/data/agentos/workflows.sqlite3?mode=rw',uri=True); d=sqlite3.connect('/backup/agentos-workflows.sqlite3'); s.backup(d); ok=d.execute('pragma integrity_check').fetchone()[0]; counts={'integrity':ok,'tasks':d.execute('select count(*) from tasks').fetchone()[0],'runs':d.execute('select count(*) from runs').fetchone()[0]}; pathlib.Path('/backup/agentos-sqlite-verification.json').write_text(json.dumps(counts)); d.close(); s.close()"], capture=False)

    shutil.copy2(schema_report_path, output / "schema-audit.json")
    images = image_inventory(deployment_id)
    redis_lines = redis_result.splitlines()
    redis_size = int(next(line.split("=", 1)[1] for line in redis_lines if line.startswith("dbsize=")))
    redis_samples = sum(line.startswith("sample_read_ok ") for line in redis_lines)
    manifest = {
        "formatVersion": "1.1",
        "deploymentId": deployment_id,
        "createdAt": timestamp,
        "database": args.database,
        "databaseUser": args.app_db_user,
        "databaseAdminUser": args.db_admin_user,
        "schemaFingerprint": schema_report["fingerprint"],
        "schemaState": schema_report["state"],
        "volumes": volumes,
        "gitCommit": source_commit(),
        "dockerCompose": run(["docker", "compose", "version", "--short"]).stdout.strip(),
        "images": images,
        "redisClassification": "rebuildable-cache",
        "redisDatabaseSize": redis_size,
        "redisSampleReadCount": redis_samples,
    }
    write_json(output / "manifest.json", manifest)
    write_checksums(output)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

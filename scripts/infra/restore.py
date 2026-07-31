#!/usr/bin/env python3
"""Restore a full backup into a new, isolated deployment ID and verify it."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from scripts.infra.common import compose_command, run, validate_deployment_id, verify_checksums, verify_volume_labels, volume_names


IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def compose(target: str, secrets_dir: Path, *args: str, db_user: str, db_name: str, admin_user: str = "postgres", skip_app_init: bool = False):
    return run(
        compose_command(*args),
        env={
            "KINLIN_DEPLOYMENT_ID": target,
            "KINLIN_SECRETS_DIR": str(secrets_dir),
            "KINLIN_DB_USER": db_user,
            "KINLIN_DB_NAME": db_name,
            "KINLIN_DB_ADMIN_USER": admin_user,
            "KINLIN_SKIP_APP_INIT": "true" if skip_app_init else "false",
        },
    )


def restore_archive(volume: str, backup: Path, filename: str) -> None:
    helper = os.environ.get("IMAGE_POSTGRES", os.environ.get("KINLIN_POSTGRES_IMAGE", "kinlin-ai-postgres:dev"))
    run([
        "docker", "run", "--rm", "--entrypoint", "tar", "-v", f"{volume}:/target", "-v", f"{backup}:/backup:ro",
        helper, "-C", "/target", "-xzf", f"/backup/{filename}",
    ], capture=False)


def write_deployment_marker(volume: str, deployment_id: str) -> None:
    helper = os.environ.get("IMAGE_POSTGRES", os.environ.get("KINLIN_POSTGRES_IMAGE", "kinlin-ai-postgres:dev"))
    run([
        "docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{volume}:/target", helper,
        "-ec", "printf '%s\\n' \"$1\" > /target/.kinlin-deployment-id", "sh", deployment_id,
    ])


def pipe_to_compose(path: Path, command: list[str], environment: dict[str, str]) -> None:
    with path.open("rb") as source:
        subprocess.run(command, check=True, stdin=source, env={**os.environ, **environment})


def restore_globals(path: Path, command: list[str], environment: dict[str, str], existing_admin: str) -> None:
    """Restore globals while retaining initdb's permanent bootstrap administrator."""
    role = re.escape(existing_admin)
    duplicate_admin = re.compile(rf'^(?:CREATE|ALTER) ROLE (?:"{role}"|{role})(?:\s|;)', re.MULTILINE)
    lines = [line for line in path.read_text(encoding="utf-8").splitlines(keepends=True) if not duplicate_admin.match(line)]
    subprocess.run(
        command,
        check=True,
        input="".join(lines).encode("utf-8"),
        env={**os.environ, **environment},
    )


def redis_verify(target: str, secrets: Path, db_user: str, db_name: str, *, admin_user: str = "postgres", skip_app_init: bool = False) -> str:
    script = r'''export REDISCLI_AUTH="$(tr -d '\r\n' < /run/secrets/redis_password)"
echo "dbsize=$(redis-cli DBSIZE)"
redis-cli INFO persistence | tr -d "\r" | grep -E "^(loading:0|rdb_last_bgsave_status:ok)$"
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
  echo "sample_read_ok type=$type"
done'''
    return compose(target, secrets, "exec", "-T", "redis", "sh", "-ec", script, db_user=db_user, db_name=db_name, admin_user=admin_user, skip_app_init=skip_app_init).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup")
    parser.add_argument("--target-deployment-id", required=True)
    parser.add_argument("--secrets-dir", required=True)
    parser.add_argument("--execute", action="store_true", help="required acknowledgement that new target volumes will be created")
    args = parser.parse_args()

    backup = Path(args.backup).resolve()
    secrets = Path(args.secrets_dir).resolve()
    verify_checksums(backup)
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    target = validate_deployment_id(args.target_deployment_id)
    source = validate_deployment_id(manifest["deploymentId"])
    if target == source:
        raise SystemExit("restore target must use a different KINLIN_DEPLOYMENT_ID")
    if not args.execute:
        raise SystemExit("--execute is required; restore never overwrites an existing deployment")

    db_user = manifest["databaseUser"]
    db_name = manifest["database"]
    db_admin = manifest.get("databaseAdminUser", "postgres")
    if not IDENTIFIER.fullmatch(db_user) or not IDENTIFIER.fullmatch(db_name) or not IDENTIFIER.fullmatch(db_admin):
        raise SystemExit("manifest contains an unsafe database identifier")
    targets = volume_names(target)
    existing = set(run(["docker", "volume", "ls", "--format", "{{.Name}}"] ).stdout.splitlines())
    collisions = sorted(set(targets.values()) & existing)
    if collisions:
        raise SystemExit(f"target volumes already exist; refusing overwrite: {collisions}")

    for name in targets.values():
        run(["docker", "volume", "create", "--label", f"com.kinlin.deployment-id={target}", name])
    verify_volume_labels(target, targets)

    restore_archive(targets["backend_uploads_v11"], backup, "backend-uploads.tar.gz")
    restore_archive(targets["agentos_data_v11"], backup, "agentos-data.tar.gz")
    restore_archive(targets["ai_cache_v11"], backup, "ai-cache.tar.gz")
    write_deployment_marker(targets["backend_uploads_v11"], target)
    write_deployment_marker(targets["agentos_data_v11"], target)
    write_deployment_marker(targets["ai_cache_v11"], target)
    # Replace the archived live database files with the standalone SQLite
    # backup produced by sqlite3_backup(), and discard stale WAL sidecars.
    python_helper = os.environ.get("IMAGE_AI_SERVICE", os.environ.get("KINLIN_AI_IMAGE", "kinlin-ai-service:dev"))
    run([
        "docker", "run", "--rm", "--entrypoint", "python", "-v", f'{targets["agentos_data_v11"]}:/data',
        "-v", f"{backup}:/backup:ro", python_helper, "-c",
        "import pathlib,shutil; d=pathlib.Path('/data/agentos'); d.mkdir(parents=True,exist_ok=True); shutil.copyfile('/backup/agentos-workflows.sqlite3',d/'workflows.sqlite3'); (d/'workflows.sqlite3').chmod(0o640); [(p.unlink()) for p in (d/'workflows.sqlite3-wal',d/'workflows.sqlite3-shm') if p.exists()]",
    ])
    redis_helper = os.environ.get("IMAGE_REDIS", os.environ.get("KINLIN_REDIS_IMAGE", "kinlin-ai-redis:dev"))
    run([
        "docker", "run", "--rm", "--entrypoint", "cp", "-v", f'{targets["redis_data_v11"]}:/data',
        "-v", f"{backup}:/backup:ro", redis_helper, "/backup/redis-dump.rdb", "/data/dump.rdb",
    ])

    bootstrap_env = {
        "KINLIN_DEPLOYMENT_ID": target,
        "KINLIN_SECRETS_DIR": str(secrets),
        "KINLIN_DB_USER": db_user,
        "KINLIN_DB_NAME": db_name,
        "KINLIN_DB_ADMIN_USER": db_admin,
        "KINLIN_SKIP_APP_INIT": "true",
    }
    compose(target, secrets, "up", "-d", "--wait", "postgres", "redis", db_user=db_user, db_name=db_name, admin_user=db_admin, skip_app_init=True)
    base = compose_command("exec", "-T", "postgres")
    restore_globals(
        backup / "postgres-globals.sql",
        [*base, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", db_admin, "-d", "postgres"],
        bootstrap_env,
        db_admin,
    )

    password_reset = '''admin_password=$(tr -d '\r\n' < /run/secrets/db_admin_password)
app_password=$(tr -d '\r\n' < /run/secrets/db_password)
psql -X -v ON_ERROR_STOP=1 -v admin_role="$1" -v admin_password="$admin_password" -v app_role="$2" -v app_password="$app_password" -U "$3" -d postgres <<'SQL'
ALTER ROLE :"admin_role" PASSWORD :'admin_password';
ALTER ROLE :"app_role" PASSWORD :'app_password';
SQL'''
    compose(target, secrets, "exec", "-T", "postgres", "sh", "-ec", password_reset, "sh", db_admin, db_user, db_admin, db_user=db_user, db_name=db_name, admin_user=db_admin, skip_app_init=True)
    compose(target, secrets, "exec", "-T", "postgres", "createdb", "-U", db_admin, "--owner", db_user, db_name, db_user=db_user, db_name=db_name, admin_user=db_admin, skip_app_init=True)
    pipe_to_compose(
        backup / "postgres-database.dump",
        [
            *base,
            "pg_restore",
            "-U",
            db_admin,
            "-d",
            db_name,
            "--exit-on-error",
            "--no-owner",
            "--role",
            db_user,
        ],
        bootstrap_env,
    )
    redis_output = redis_verify(target, secrets, db_user, db_name, admin_user=db_admin, skip_app_init=True)
    restored_size = int(next(line.split("=", 1)[1] for line in redis_output.splitlines() if line.startswith("dbsize=")))
    restored_samples = sum(line.startswith("sample_read_ok ") for line in redis_output.splitlines())
    if restored_size != manifest["redisDatabaseSize"]:
        raise SystemExit(f"Redis key count mismatch: expected={manifest['redisDatabaseSize']} actual={restored_size}")
    if restored_samples != manifest["redisSampleReadCount"]:
        raise SystemExit(f"Redis sample count mismatch: expected={manifest['redisSampleReadCount']} actual={restored_samples}")

    sqlite_check = run([
        "docker", "run", "--rm", "--entrypoint", "python", "-v", f'{targets["agentos_data_v11"]}:/data:ro', python_helper,
        "-c", "import sqlite3,json; c=sqlite3.connect('file:/data/agentos/workflows.sqlite3?mode=ro&immutable=1',uri=True); print(json.dumps({'integrity':c.execute('pragma integrity_check').fetchone()[0],'tasks':c.execute('select count(*) from tasks').fetchone()[0],'runs':c.execute('select count(*) from runs').fetchone()[0]}))",
    ]).stdout.strip()

    compose(target, secrets, "stop", "postgres", "redis", db_user=db_user, db_name=db_name, admin_user=db_admin, skip_app_init=True)
    compose(target, secrets, "up", "-d", "--wait", "postgres", "redis", db_user=db_user, db_name=db_name, admin_user=db_admin)
    db_count = compose(target, secrets, "exec", "-T", "postgres", "psql", "-X", "-U", db_user, "-d", db_name, "-At", "-c", "SELECT count(*) FROM flyway_schema_history WHERE success", db_user=db_user, db_name=db_name).stdout.strip()
    result = {
        "backup": str(backup), "source": source, "target": target, "checksums": "verified",
        "targetVolumes": targets, "postgresSuccessfulMigrations": int(db_count),
        "redis": {"classification": manifest["redisClassification"], "keyCount": restored_size, "sampleReads": restored_samples, "persistence": "ok"},
        "sqlite": json.loads(sqlite_check),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

from scripts.release.common import (
    ROOT,
    SERVICES,
    git_sha,
    image_reference,
    inspect_local_image,
    repository_version,
    require_clean_worktree,
    scan_release_tree,
    write_checksums,
    write_json,
)


IMAGE_ENV_NAMES = {
    "frontend": "KINLIN_FRONTEND_IMAGE",
    "backend": "KINLIN_BACKEND_IMAGE",
    "ai-service": "KINLIN_AI_IMAGE",
    "postgres": "KINLIN_POSTGRES_IMAGE",
    "redis": "KINLIN_REDIS_IMAGE",
    "flyway": "KINLIN_FLYWAY_IMAGE",
}
MANIFEST_ENV_NAMES = {
    "frontend": "IMAGE_FRONTEND",
    "backend": "IMAGE_BACKEND",
    "ai-service": "IMAGE_AI_SERVICE",
    "postgres": "IMAGE_POSTGRES",
    "redis": "IMAGE_REDIS",
    "flyway": "IMAGE_FLYWAY",
}


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def save_image(reference: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(["docker", "save", reference], stdout=subprocess.PIPE)
    assert process.stdout is not None
    with target.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        shutil.copyfileobj(process.stdout, compressed, length=1024 * 1024)
    if process.wait() != 0:
        raise RuntimeError(f"docker save failed: {reference}; incomplete staging directory retained for audit")


def deterministic_archive(source: Path, target: Path) -> None:
    with target.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in sorted(source.rglob("*")):
                info = archive.gettarinfo(str(path), arcname=f"{source.name}/{path.relative_to(source).as_posix()}")
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = 0
                if path.is_file():
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)
                else:
                    archive.addfile(info)


def validated_security(security_dir: Path, arch: str) -> dict:
    gate_path = security_dir / "gate.json"
    if not gate_path.is_file():
        raise RuntimeError("security gate.json is required")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "passed":
        raise RuntimeError("security gate did not pass")
    pairs = {(item.get("service"), item.get("platform")) for item in gate.get("images", [])}
    expected = {(service, f"linux/{arch}") for service in SERVICES}
    if not expected.issubset(pairs):
        raise RuntimeError(f"security gate lacks service/platform coverage: {sorted(expected - pairs)}")
    return gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", choices=("amd64", "arm64"), required=True)
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--security-dir", required=True)
    parser.add_argument("--output-root", default="artifacts/releases")
    args = parser.parse_args()

    require_clean_worktree()
    version = repository_version()
    commit = git_sha()
    security_dir = Path(args.security_dir).resolve()
    validated_security(security_dir, args.arch)
    output_root = Path(args.output_root).resolve()
    package = output_root / f"kinlin-ai-{version}-linux-{args.arch}"
    archive = output_root / f"kinlin-ai-{version}-linux-{args.arch}.tar.gz"
    if package.exists() or archive.exists():
        raise RuntimeError("release output already exists; refusing to overwrite or delete it")
    package.mkdir(parents=True)

    copy_file(ROOT / "VERSION", package / "VERSION")
    for name in ("compose.yaml", "compose.prod.yaml", "compose.release.yaml"):
        copy_file(ROOT / name, package / "compose" / name)
    migrations = ROOT / "backend" / "src" / "main" / "resources" / "db" / "migration"
    shutil.copytree(migrations, package / "compose" / "migrations")
    copy_file(ROOT / "deploy" / ".env.prod.example", package / "config" / ".env.prod.example")
    copy_file(ROOT / "deploy" / "secrets" / "README.md", package / "config" / "secrets" / "README.md")
    shutil.copytree(ROOT / "deploy" / "scripts", package / "scripts")
    copy_file(ROOT / "deploy" / "DEPLOYMENT.md", package / "docs" / "DEPLOYMENT.md")
    infra_target = package / "scripts" / "infra"
    infra_target.mkdir(parents=True)
    for name in ("__init__.py", "common.py", "preflight.py", "init_secrets.py", "schema_audit.py", "backup.py", "restore.py"):
        copy_file(ROOT / "scripts" / "infra" / name, infra_target / name)
    scripts_package = package / "scripts" / "__init__.py"
    if not scripts_package.exists():
        scripts_package.write_text("\"\"\"Offline deployment scripts.\"\"\"\n", encoding="utf-8")

    image_records = []
    image_env = []
    manifest_env = [
        f"RELEASE_VERSION={version}",
        f"RELEASE_ARCH={args.arch}",
        "MIN_UPGRADE_VERSION=1.0.0",
        "ROLLBACK_COMPATIBLE=true",
    ]
    for service in SERVICES:
        reference = image_reference(args.image_prefix, service, version)
        record = inspect_local_image(reference, args.arch)
        record["service"] = service
        record["archive"] = f"images/{service}.tar.gz"
        save_image(reference, package / record["archive"])
        image_records.append(record)
        image_env.append(f"{IMAGE_ENV_NAMES[service]}={reference}")
        manifest_env.append(f"{MANIFEST_ENV_NAMES[service]}={reference}")
        manifest_env.append(f"IMAGE_ID_{MANIFEST_ENV_NAMES[service].removeprefix('IMAGE_')}={record['id']}")
    (package / "config" / "images.release").write_text("\n".join(image_env) + "\n", encoding="utf-8")
    (package / "manifest.env").write_text("\n".join(manifest_env) + "\n", encoding="utf-8")

    for source in security_dir.iterdir():
        if source.name.endswith(".spdx.json"):
            copy_file(source, package / "sbom" / source.name)
        else:
            copy_file(source, package / "security" / source.name)
    manifest = {
        "formatVersion": 1,
        "status": "complete",
        "product": "kinlin-ai",
        "version": version,
        "gitCommit": commit,
        "platform": f"linux/{args.arch}",
        "images": image_records,
        "schema": {"current": 6, "minimumUpgradeVersion": "1.0.0", "rollbackCompatible": True},
        "installPolicy": {"pull": "never", "build": "forbidden", "architectureMismatch": "reject"},
        "securityGate": "security/gate.json",
    }
    write_json(package / "manifest.json", manifest)
    findings = scan_release_tree(package)
    if findings:
        raise RuntimeError(f"release package policy scan failed: {findings}")
    write_checksums(package)
    deterministic_archive(package, archive)
    print(package)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


DEPLOYMENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
VOLUME_SUFFIXES = ("postgres_data_v11", "redis_data_v11", "agentos_data_v11", "backend_uploads_v11", "ai_cache_v11")


def compose_command(*args: str) -> list[str]:
    configured_files = os.environ.get("KINLIN_COMPOSE_FILES")
    compose_files = configured_files.split(os.pathsep) if configured_files else ["compose.yaml", "compose.prod.yaml"]
    command = ["docker", "compose"]
    for compose_file in compose_files:
        if not compose_file:
            raise ValueError("KINLIN_COMPOSE_FILES contains an empty path")
        command.extend(["-f", compose_file])
    release_overlay = os.environ.get("KINLIN_RELEASE_COMPOSE")
    if release_overlay:
        command.extend(["-f", release_overlay])
    return [*command, *args]


def validate_deployment_id(value: str) -> str:
    if not DEPLOYMENT_ID_PATTERN.fullmatch(value or ""):
        raise ValueError("KINLIN_DEPLOYMENT_ID must match ^[a-z0-9][a-z0-9-]{2,31}$")
    return value


def volume_names(deployment_id: str) -> dict[str, str]:
    validate_deployment_id(deployment_id)
    return {suffix: f"{deployment_id}_{suffix}" for suffix in VOLUME_SUFFIXES}


def verify_volume_labels(deployment_id: str, names: dict[str, str], *, require_all: bool = True) -> None:
    for name in names.values():
        completed = subprocess.run(
            ["docker", "volume", "inspect", name, "--format", "{{ index .Labels \"com.kinlin.deployment-id\" }}"],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        if completed.returncode != 0:
            if require_all:
                raise RuntimeError(f"required volume does not exist: {name}")
            continue
        actual = completed.stdout.strip()
        if actual != deployment_id:
            raise RuntimeError(f"volume deployment label mismatch: {name} expected={deployment_id} actual={actual!r}")


def run(command: list[str], *, env: dict[str, str] | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=capture,
        env={**os.environ, **(env or {})},
    )


def docker_is_supported_rootful() -> tuple[bool, str]:
    result = run(["docker", "info", "--format", "{{json .SecurityOptions}}|{{.DockerRootDir}}"])
    security, _, root_dir = result.stdout.strip().partition("|")
    lowered = security.lower()
    if "rootless" in lowered:
        return False, "rootless Docker is not supported"
    if "userns" in lowered:
        return False, "userns-remap is not supported"
    if not root_dir.strip():
        return False, "DockerRootDir is unavailable"
    return True, f"rootful DockerRootDir={root_dir.strip()} security={security}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(directory: Path) -> Path:
    checksum_file = directory / "SHA256SUMS"
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path != checksum_file:
            entries.append(f"{sha256_file(path)}  {path.relative_to(directory).as_posix()}")
    checksum_file.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return checksum_file


def verify_checksums(directory: Path) -> None:
    checksum_file = directory / "SHA256SUMS"
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        actual = sha256_file(directory / relative)
        if actual != expected:
            raise RuntimeError(f"checksum mismatch: {relative}")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

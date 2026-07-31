from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("frontend", "backend", "ai-service", "postgres", "redis", "flyway")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ARCH_ALIASES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def run(command: list[str], *, env: dict[str, str] | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=capture,
        env={**os.environ, **(env or {})},
    )


def repository_version() -> str:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid VERSION: {version!r}")
    return version


def git_sha() -> str:
    value = run(["git", "rev-parse", "HEAD"]).stdout.strip().lower()
    if not SHA_PATTERN.fullmatch(value):
        raise ValueError(f"invalid Git commit: {value!r}")
    return value


def require_clean_worktree() -> None:
    status = run(["git", "status", "--porcelain=v1"]).stdout.strip()
    if status:
        raise RuntimeError("release requires an empty worktree and index")


def normalize_arch(value: str) -> str:
    try:
        return ARCH_ALIASES[value.lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported architecture: {value}") from exc


def image_reference(prefix: str, service: str, tag: str) -> str:
    if service not in SERVICES:
        raise ValueError(f"unknown service: {service}")
    prefix = prefix.strip().rstrip("/")
    if not prefix or "://" in prefix or "latest" in tag.lower():
        raise ValueError("image prefix is required and latest is forbidden")
    return f"{prefix}/{service}:{tag}"


def inspect_local_image(reference: str, expected_arch: str | None = None) -> dict:
    payload = json.loads(run(["docker", "image", "inspect", reference]).stdout)[0]
    architecture = normalize_arch(payload["Architecture"])
    if expected_arch and architecture != normalize_arch(expected_arch):
        raise RuntimeError(f"image architecture mismatch: {reference} expected={expected_arch} actual={architecture}")
    return {
        "reference": reference,
        "id": payload["Id"],
        "architecture": architecture,
        "os": payload["Os"],
        "repoDigests": sorted(payload.get("RepoDigests") or []),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_checksums(root: Path) -> Path:
    target = root / "SHA256SUMS"
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != target
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env(?:\..*)?|\.secrets|secrets?|node_modules|target|__pycache__|\.cache)(/|$)|"
    r"\.(?:db|sqlite|sqlite3|pem|key|p12|pfx|dump)$",
    re.IGNORECASE,
)
SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "alibaba-signed-url": re.compile(r"\bOSSAccessKeyId="),
}
TEXT_SUFFIXES = {"", ".conf", ".env", ".example", ".hcl", ".json", ".md", ".py", ".sh", ".txt", ".yaml", ".yml"}


def scan_release_tree(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {"config/.env.prod.example", "config/secrets/README.md"}:
            pass
        elif FORBIDDEN_NAMES.search(relative):
            findings.append(f"forbidden-file:{relative}")
        if relative.startswith(("images/", "sbom/", "security/")):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 5 * 1024 * 1024:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{name}:{relative}")
    return findings


def scan_tracked_secrets() -> list[str]:
    findings: list[str] = []
    tracked = run(["git", "ls-files", "-z"]).stdout.split("\0")
    excluded = {"scripts/release/common.py"}
    excluded_prefixes = ("agent/app/data/", "agent/app/static/digital-human/data/")
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not relative or relative in excluded or normalized.startswith(excluded_prefixes) or "/tests/" in normalized:
            continue
        path = ROOT / relative
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 5 * 1024 * 1024:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{name}:{relative}")
    return findings

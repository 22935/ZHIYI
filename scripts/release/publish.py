#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from scripts.release.common import (
    ROOT,
    SERVICES,
    git_sha,
    image_reference,
    repository_version,
    require_clean_worktree,
    run,
    write_json,
)
from scripts.release.security_gate import run_gate


DIGEST_PATTERN = re.compile(r"^Digest:\s+(sha256:[0-9a-f]{64})$", re.MULTILINE)


def remote_digest(reference: str) -> str:
    output = run(["docker", "buildx", "imagetools", "inspect", reference]).stdout
    match = DIGEST_PATTERN.search(output)
    if not match:
        raise RuntimeError(f"manifest digest unavailable: {reference}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--namespace", default="kinlin-ai")
    parser.add_argument("--output", required=True)
    parser.add_argument("--exceptions", default=str(ROOT / "security" / "vulnerability-exceptions.json"))
    args = parser.parse_args()

    require_clean_worktree()
    version = repository_version()
    commit = git_sha()
    expected_tag = f"v{version}"
    tags = run(["git", "tag", "--points-at", "HEAD"]).stdout.split()
    if expected_tag not in tags:
        raise RuntimeError(f"formal publication requires Git tag {expected_tag} at HEAD")
    registry = args.registry.strip().rstrip("/")
    namespace = args.namespace.strip().strip("/")
    if not registry or not namespace or "://" in registry:
        raise ValueError("registry and namespace must be explicit OCI names without a URL scheme")
    prefix = f"{registry}/{namespace}"
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)

    run(["python", "-m", "scripts.release.check_builder", "--require", "linux/amd64", "--require", "linux/arm64"], capture=False)
    sha_tag = f"sha-{commit[:12]}"
    bake = ["docker", "buildx", "bake", "-f", "docker-bake.hcl", "release-multiarch", "--push"]
    for service in SERVICES:
        bake.extend(["--set", f"{service}-multiarch.tags={image_reference(prefix, service, sha_tag)}"])
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run(
        bake,
        env={"IMAGE_PREFIX": prefix, "VERSION": version, "GIT_SHA": commit, "CREATED": created},
        capture=False,
    )

    sha_images = {service: image_reference(prefix, service, sha_tag) for service in SERVICES}
    sha_digests = {service: remote_digest(reference) for service, reference in sha_images.items()}
    security_dir = output / "security"
    run_gate(
        prefix,
        sha_tag,
        security_dir,
        Path(args.exceptions),
        source="registry",
        platforms=("linux/amd64", "linux/arm64"),
    )

    releases = []
    for service in SERVICES:
        version_ref = image_reference(prefix, service, version)
        run(["docker", "buildx", "imagetools", "create", "--tag", version_ref, sha_images[service]], capture=False)
        digest = remote_digest(version_ref)
        if digest != sha_digests[service]:
            raise RuntimeError(f"digest changed while promoting {service}: {sha_digests[service]} != {digest}")
        releases.append(
            {
                "service": service,
                "versionReference": version_ref,
                "commitReference": sha_images[service],
                "manifestDigest": digest,
                "platforms": ["linux/amd64", "linux/arm64"],
            }
        )

    manifest = {
        "formatVersion": 1,
        "status": "complete",
        "product": "kinlin-ai",
        "version": version,
        "gitCommit": commit,
        "gitTag": expected_tag,
        "createdAt": created,
        "images": releases,
        "schema": {"current": 6, "minimumUpgradeVersion": "1.0.0", "rollbackCompatible": True},
        "availabilityRule": "Only this complete release manifest marks the version available; image tags alone do not.",
        "latestTag": "forbidden",
        "securityGate": "security/gate.json",
    }
    write_json(output / "manifest.json", manifest)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

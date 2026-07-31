#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess


def normalize_arch(value: str) -> str:
    mapping = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64", "amd64": "amd64"}
    try:
        return mapping[value.lower()]
    except KeyError as exc:
        raise ValueError(f"unsupported architecture: {value}") from exc


def current_builder(lines: str) -> dict:
    builders = [json.loads(line) for line in lines.splitlines() if line.strip()]
    selected = next((builder for builder in builders if builder.get("Current")), None)
    if not selected:
        raise RuntimeError("no current Buildx builder")
    return selected


def builder_platforms(builder: dict) -> set[str]:
    return {
        platform.split("/v", 1)[0]
        for node in builder.get("Nodes", [])
        if node.get("Status") == "running"
        for platform in node.get("Platforms", [])
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require", action="append", default=["linux/amd64"])
    args = parser.parse_args()

    listing = subprocess.run(
        ["docker", "buildx", "ls", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    host_arch = normalize_arch(
        subprocess.run(
            ["docker", "info", "--format", "{{.Architecture}}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    )
    builder = current_builder(listing)
    available = builder_platforms(builder)
    required = set(args.require)
    missing = sorted(required - available)
    report = {
        "builder": builder["Name"],
        "driver": builder["Driver"],
        "hostPlatform": f"linux/{host_arch}",
        "availablePlatforms": sorted(available),
        "requiredPlatforms": sorted(required),
        "missingPlatforms": missing,
        "arm64Mode": "native" if host_arch == "arm64" else ("cross-capable" if "linux/arm64" in available else "unavailable"),
    }
    print(json.dumps(report, indent=2))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

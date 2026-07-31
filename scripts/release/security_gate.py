#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from scripts.release.common import ROOT, SERVICES, image_reference, scan_tracked_secrets, write_json


def sarif_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        result["ruleId"]
        for run in payload.get("runs", [])
        for result in run.get("results", [])
        if result.get("ruleId")
    }


def active_exceptions(path: Path, service: str, cve_ids: set[str], today: dt.date) -> tuple[set[str], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed: set[str] = set()
    errors: list[str] = []
    for item in payload.get("exceptions", []):
        if item.get("service") not in {service, "*"} or item.get("cve") not in cve_ids:
            continue
        if not item.get("reason") or not item.get("owner") or not item.get("expires"):
            errors.append(f"incomplete exception: {item.get('cve')}")
            continue
        expires = dt.date.fromisoformat(item["expires"])
        if expires < today:
            errors.append(f"expired exception: {item['cve']}")
            continue
        allowed.add(item["cve"])
    return allowed, errors


def scout_report(artifact: str, severity: str, output: Path, platform: str) -> int:
    completed = subprocess.run(
        [
            "docker",
            "scout",
            "cves",
            "--only-severity",
            severity,
            "--format",
            "sarif",
            "--output",
            str(output),
            "--platform",
            platform,
            artifact,
        ],
        text=True,
        encoding="utf-8",
    )
    return completed.returncode


def run_gate(
    prefix: str,
    version: str,
    output: Path,
    exceptions: Path,
    *,
    source: str = "local",
    platforms: tuple[str, ...] = ("linux/amd64",),
) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    source_findings = scan_tracked_secrets()
    if source_findings:
        raise RuntimeError(f"repository secret scan failed: {source_findings[:10]}")

    results = []
    failures = []
    if source not in {"local", "registry"}:
        raise ValueError(f"invalid scanner source: {source}")
    for service in SERVICES:
        reference = image_reference(prefix, service, version)
        for platform in platforms:
            arch = platform.rsplit("/", 1)[-1]
            artifact = f"{source}://{reference}"
            sbom = output / f"{service}-{arch}.spdx.json"
            sbom_run = subprocess.run(
                ["docker", "scout", "sbom", "--format", "spdx", "--output", str(sbom), "--platform", platform, artifact],
                text=True,
                encoding="utf-8",
            )
            if sbom_run.returncode != 0 or not sbom.is_file():
                raise RuntimeError(f"SBOM generation unavailable for {reference} {platform}")

            critical_path = output / f"{service}-{arch}.critical.sarif.json"
            high_path = output / f"{service}-{arch}.high.sarif.json"
            if scout_report(artifact, "critical", critical_path, platform) != 0:
                raise RuntimeError(f"vulnerability scanner unavailable for {reference} {platform}")
            if scout_report(artifact, "high", high_path, platform) != 0:
                raise RuntimeError(f"vulnerability scanner unavailable for {reference} {platform}")
            critical = sarif_ids(critical_path)
            high = sarif_ids(high_path)
            allowed, exception_errors = active_exceptions(exceptions, service, high, dt.datetime.now(dt.timezone.utc).date())
            unresolved = sorted(high - allowed)
            if critical or unresolved or exception_errors:
                failures.append(
                    {
                        "service": service,
                        "platform": platform,
                        "critical": sorted(critical),
                        "unresolvedHigh": unresolved,
                        "exceptionErrors": exception_errors,
                    }
                )
            results.append(
                {
                    "service": service,
                    "platform": platform,
                    "reference": reference,
                    "critical": sorted(critical),
                    "high": sorted(high),
                    "exemptedHigh": sorted(allowed),
                    "sbom": sbom.name,
                }
            )
    report = {
        "formatVersion": 1,
        "status": "passed" if not failures else "failed",
        "policy": {"critical": "zero", "high": "documented-unexpired-exception-required", "sbom": "required", "secretFindings": 0},
        "images": results,
        "failures": failures,
    }
    write_json(output / "gate.json", report)
    if failures:
        raise RuntimeError(f"security gate failed: {failures}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--exceptions", default=str(ROOT / "security" / "vulnerability-exceptions.json"))
    parser.add_argument("--source", choices=("local", "registry"), default="local")
    parser.add_argument("--platform", action="append", default=[])
    args = parser.parse_args()
    run_gate(
        args.image_prefix,
        args.version,
        Path(args.output),
        Path(args.exceptions),
        source=args.source,
        platforms=tuple(args.platform or ["linux/amd64"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

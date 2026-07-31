#!/usr/bin/env python3
"""Explicitly baseline a schema only after matching an immutable audit report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from scripts.infra.common import validate_deployment_id
from scripts.infra.schema_audit import classify, snapshot_container


def authorize(report: dict, *, deployment_id: str, report_id: str, fingerprint: str, baseline_version: int, current: dict) -> None:
    if baseline_version <= 0:
        raise ValueError("baseline version 0 or lower is forbidden")
    if report.get("deploymentId") != deployment_id:
        raise ValueError("audit report deployment ID does not match target")
    expected = (report.get("reportId"), report.get("fingerprint"), report.get("baselineVersion"), report.get("state"))
    supplied = (report_id, fingerprint, baseline_version, "legacy")
    if expected != supplied:
        raise ValueError(f"audit authorization mismatch: expected={expected}, supplied={supplied}")
    live = (current.get("fingerprint"), current.get("baselineVersion"), current.get("state"))
    audited = (report.get("fingerprint"), report.get("baselineVersion"), report.get("state"))
    if live != audited:
        raise ValueError(f"live schema changed after audit: audited={audited}, live={live}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--baseline-version", required=True, type=int)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--container")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--secrets-dir")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    deployment_id = validate_deployment_id(args.deployment_id)
    container = args.container or f"{deployment_id}-postgres-1"
    current = classify(snapshot_container(container, args.user, report.get("database", "kinlin_ai")))
    try:
        authorize(
            report,
            deployment_id=deployment_id,
            report_id=args.report_id,
            fingerprint=args.fingerprint,
            baseline_version=args.baseline_version,
            current=current,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    command = [
        "docker", "compose", "-f", "compose.yaml", "-f", "compose.prod.yaml",
        "--profile", "migration", "run", "--rm", "schema-tool",
        "baseline", f"-baselineVersion={args.baseline_version}",
        f"-placeholders.auditReportId={args.report_id}",
    ]
    secrets_dir = args.secrets_dir or os.environ.get("KINLIN_SECRETS_DIR") or str((Path(".secrets") / deployment_id).resolve())
    environment = {"KINLIN_DEPLOYMENT_ID": deployment_id, "KINLIN_SECRETS_DIR": secrets_dir}
    completed = subprocess.run(command, env={**os.environ, **environment})
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

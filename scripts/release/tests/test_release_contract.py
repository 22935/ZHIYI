import datetime as dt
import json
import os
from pathlib import Path

import pytest

from scripts.infra.common import compose_command
from scripts.release.common import image_reference, scan_release_tree
from scripts.release.package_offline import validated_security
from scripts.release.security_gate import active_exceptions, sarif_ids


ROOT = Path(__file__).resolve().parents[3]
SERVICES = ("frontend", "backend", "ai-service", "postgres", "redis", "flyway")


def test_image_reference_requires_prefix_and_forbids_latest():
    assert image_reference("registry.example/kinlin-ai", "backend", "1.2.3") == "registry.example/kinlin-ai/backend:1.2.3"
    with pytest.raises(ValueError):
        image_reference("", "backend", "1.2.3")
    with pytest.raises(ValueError):
        image_reference("registry.example/kinlin-ai", "backend", "latest")


def test_release_tree_rejects_data_and_private_keys_but_allows_templates(tmp_path: Path):
    (tmp_path / "config" / "secrets").mkdir(parents=True)
    (tmp_path / "config" / ".env.prod.example").write_text("KINLIN_SECRETS_DIR=/external\n", encoding="utf-8")
    (tmp_path / "config" / "secrets" / "README.md").write_text("No values here.\n", encoding="utf-8")
    assert scan_release_tree(tmp_path) == []

    (tmp_path / "data.sqlite3").write_bytes(b"SQLite")
    (tmp_path / "leak.txt").write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    findings = scan_release_tree(tmp_path)
    assert "forbidden-file:data.sqlite3" in findings
    assert "private-key:leak.txt" in findings


def test_security_gate_requires_every_service_for_the_package_arch(tmp_path: Path):
    gate = {
        "status": "passed",
        "images": [{"service": service, "platform": "linux/amd64"} for service in SERVICES],
    }
    (tmp_path / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
    assert validated_security(tmp_path, "amd64")["status"] == "passed"
    with pytest.raises(RuntimeError):
        validated_security(tmp_path, "arm64")


def test_high_exception_must_be_complete_and_unexpired(tmp_path: Path):
    exceptions = {
        "exceptions": [
            {"service": "backend", "cve": "CVE-1", "owner": "security", "reason": "no fix", "expires": "2026-07-20"},
            {"service": "backend", "cve": "CVE-2", "owner": "security", "reason": "expired", "expires": "2026-07-18"},
        ]
    }
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps(exceptions), encoding="utf-8")
    allowed, errors = active_exceptions(path, "backend", {"CVE-1", "CVE-2"}, dt.date(2026, 7, 19))
    assert allowed == {"CVE-1"}
    assert errors == ["expired exception: CVE-2"]


def test_sarif_ids_are_extracted(tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"runs": [{"results": [{"ruleId": "CVE-1"}, {"ruleId": "CVE-2"}]}]}), encoding="utf-8")
    assert sarif_ids(path) == {"CVE-1", "CVE-2"}


def test_release_overlay_is_injected_only_when_requested(monkeypatch):
    monkeypatch.delenv("KINLIN_COMPOSE_FILES", raising=False)
    monkeypatch.delenv("KINLIN_RELEASE_COMPOSE", raising=False)
    assert compose_command("ps") == ["docker", "compose", "-f", "compose.yaml", "-f", "compose.prod.yaml", "ps"]
    monkeypatch.setenv("KINLIN_RELEASE_COMPOSE", "/release/compose.release.yaml")
    assert compose_command("ps")[-3:] == ["-f", "/release/compose.release.yaml", "ps"]


def test_compose_command_accepts_windows_package_files(monkeypatch):
    monkeypatch.setenv("KINLIN_COMPOSE_FILES", os.pathsep.join(["C:/package/compose.yaml", "C:/package/compose.windows.prod.yaml"]))
    monkeypatch.delenv("KINLIN_RELEASE_COMPOSE", raising=False)

    assert compose_command("ps") == [
        "docker", "compose", "-f", "C:/package/compose.yaml",
        "-f", "C:/package/compose.windows.prod.yaml", "ps",
    ]


def test_offline_scripts_never_pull_build_or_delete_volumes():
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "deploy" / "scripts").glob("*.sh"))
    assert "--pull never" in scripts
    assert "--no-build" in scripts
    assert "down -v" not in scripts
    assert "volume rm" not in scripts
    assert "docker pull" not in scripts
    assert "curl " not in scripts
    assert ":latest" not in scripts


def test_release_compose_removes_builds_and_repoints_migrations():
    overlay = (ROOT / "compose.release.yaml").read_text(encoding="utf-8")
    assert overlay.count("build: !reset null") == 6
    assert "./migrations:/flyway/sql:ro" in overlay
    assert "KINLIN_FRONTEND_IMAGE is required" in overlay


def test_ai_runtime_data_and_generated_static_files_are_excluded_from_build_context():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "agent/app/data/" in dockerignore
    assert "agent/app/static/digital-human/data/" in dockerignore

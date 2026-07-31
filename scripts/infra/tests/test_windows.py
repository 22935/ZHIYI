import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from scripts.infra import backup


ROOT = Path(__file__).resolve().parents[3]


def test_windows_overlay_keeps_ingress_and_debug_ports_scoped():
    overlay = (ROOT / "compose.windows.yaml").read_text(encoding="utf-8")
    production = (ROOT / "compose.prod.yaml").read_text(encoding="utf-8")

    assert "windows-ingress-network" in overlay
    assert '"127.0.0.1:${KINLIN_HTTP_PORT:-8080}:8080"' in overlay
    assert "profiles: [debug-ports]" in overlay
    assert '"127.0.0.1:${KINLIN_BACKEND_DEBUG_PORT:-18080}:18080"' in overlay
    assert '"127.0.0.1:${KINLIN_AI_DEBUG_PORT:-18000}:18000"' in overlay
    assert "windows-ingress-network" not in production
    assert "depends_on: !override" in overlay
    assert "condition: service_started" in overlay
    assert overlay.count("start_interval: 1s") == 5
    assert "start_interval" not in production


def test_windows_environment_example_contains_no_sensitive_assignment():
    example = (ROOT / ".env.windows.example").read_text(encoding="utf-8")
    forbidden = re.compile(r"^(?!KINLIN_SECRETS_DIR=).*(PASSWORD|TOKEN|SECRET|API_?KEY|JWT).*=" , re.MULTILINE)
    assert not forbidden.search(example)


def test_safe_down_never_deletes_volumes_and_required_scripts_exist():
    scripts = ROOT / "scripts" / "infra" / "windows"
    expected = {
        "preflight.ps1", "up.ps1", "down.ps1", "restart-service.ps1",
        "logs.ps1", "status.ps1", "clean-build-cache.ps1", "diagnose.ps1",
        "clear-backend-source-cache.ps1",
    }
    assert expected.issubset({path.name for path in scripts.glob("*.ps1")})
    down = (scripts / "down.ps1").read_text(encoding="utf-8").lower()
    assert "down -v" not in down
    assert "--volumes" not in down


def test_windows_up_reuses_images_unless_build_is_requested():
    script = (ROOT / "scripts" / "infra" / "windows" / "up.ps1").read_text(encoding="utf-8")

    assert '[switch]$Build' in script
    assert '[string]$BuildService' in script
    assert 'Invoke-KinlinCompose $context @profileArguments build' in script
    assert 'Invoke-KinlinCompose $context build $BuildService' in script
    assert '@("up", "-d", "--wait")' in script
    assert "image build excluded" in script


def test_windows_preflight_accepts_empty_optional_secret_files_on_powershell_51():
    script = (ROOT / "scripts" / "infra" / "windows" / "preflight.ps1").read_text(encoding="utf-8")

    assert "if ($null -eq $rawSecretValue)" in script
    assert '"deepseek_api_key", "dashscope_api_key"' in script


def test_backend_restart_syncs_then_uses_safe_maven_compile():
    script = (ROOT / "scripts" / "infra" / "windows" / "restart-service.ps1").read_text(encoding="utf-8")

    assert "-DskipTests compile" in script
    assert "--user 10001:10001" in script
    assert "/usr/local/bin/kinlin-sync-backend-source" in script
    assert "KINLIN_SOURCE_SYNC_RESULT" in script
    assert "skipping Maven compile" in script
    assert "Started KinlinAiApplication" in script
    assert '[switch]$FullRestart' in script
    assert "useIncrementalCompilation" not in script


def test_backend_source_cache_and_sync_contract():
    overlay = (ROOT / "compose.windows.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "backend" / "Dockerfile.dev").read_text(encoding="utf-8")
    entrypoint = (ROOT / "backend" / "docker-entrypoint-dev.sh").read_text(encoding="utf-8")
    sync = (ROOT / "backend" / "sync-backend-source.sh").read_text(encoding="utf-8")

    assert "source: backend-source-cache" in overlay
    assert "target: /app/src" in overlay
    assert "nocopy: true" in overlay
    assert "source: ./backend/src" in overlay
    assert "target: /kinlin-host/backend-src" in overlay
    assert "read_only: true" in overlay
    assert "p1-windows-development-cache" in overlay
    assert "rsync util-linux" in dockerfile
    assert "kinlin-sync-backend-source" in dockerfile
    assert "/usr/local/bin/kinlin-sync-backend-source" in entrypoint
    assert "build_dir=${KINLIN_BACKEND_BUILD_DIR:-/app/target}" in sync
    assert "lock_file=${KINLIN_BACKEND_SYNC_LOCK_FILE:-$build_dir/.kinlin-source-sync.lock}" in sync
    assert "flock -x -w" in sync
    assert "rsync -rltc" in sync
    assert "--delete" in sync
    assert 'sync_result=unchanged' in sync
    assert 'sync_result=changed' in sync
    assert 'sync_result=deleted' in sync
    assert "KINLIN_SOURCE_SYNC_LOCK_WAIT_MS" in sync
    assert "/proc/uptime" in sync
    assert 'rm -rf "$build_dir/classes" "$build_dir/generated-sources"' in sync
    assert "useIncrementalCompilation" not in sync


def test_backend_source_cache_has_narrow_deletion_and_backup_boundaries():
    clear_script = (ROOT / "scripts" / "infra" / "windows" / "clear-backend-source-cache.ps1").read_text(encoding="utf-8")
    remove_data = (ROOT / "scripts" / "infra" / "windows" / "remove-data-volumes.ps1").read_text(encoding="utf-8")
    down = (ROOT / "scripts" / "infra" / "windows" / "down.ps1").read_text(encoding="utf-8").lower()
    backup = (ROOT / "scripts" / "infra" / "backup.py").read_text(encoding="utf-8")
    common = (ROOT / "scripts" / "infra" / "common.py").read_text(encoding="utf-8")

    assert "IUnderstandDevelopmentCacheWillBeDeleted" in clear_script
    assert '_backend_source_cache"' in clear_script
    assert "p1-windows-development-cache" in clear_script
    assert "Deployment containers are still running" in clear_script
    assert "Preserving explicit development cache volume" in remove_data
    assert "p1-windows-development-cache" in remove_data
    assert "volume rm" not in down
    assert "backend_source_cache" not in backup
    assert "backend_source_cache" not in common


def test_windows_development_uses_locked_dependencies_and_complete_frontend_mounts():
    compose = (ROOT / "compose.dev.yaml").read_text(encoding="utf-8")
    ai_dockerfile = (ROOT / "agent" / "Dockerfile.dev").read_text(encoding="utf-8")
    ai_entrypoint = (ROOT / "agent" / "docker-entrypoint-dev.sh").read_text(encoding="utf-8")

    assert "requirements.lock:/app/requirements.lock:ro" in compose
    assert "--require-hashes --only-binary=:all:" in ai_dockerfile
    assert "--require-hashes --only-binary=:all:" in ai_entrypoint
    for filename in ("index.html", "vite.config.ts", "tsconfig.json", "tsconfig.node.json"):
        assert f"./frontend/{filename}:/app/{filename}:ro" in compose


def test_root_windows_entrypoint_delegates_to_canonical_scripts():
    script = (ROOT / "dev.ps1").read_text(encoding="utf-8")

    assert r"scripts\infra\windows" in script
    assert 'Join-Path $windowsScripts "up.ps1"' in script
    assert "compose.yaml" not in script


def test_windows_deployment_package_has_required_entrypoints_and_no_secret_values():
    package = ROOT / "deploy" / "windows" / "package"
    expected = {
        ".env.example", "start.ps1", "stop.ps1", "status.ps1",
        "logs.ps1", "backup.ps1", "restore.ps1", "README.md",
    }

    assert expected.issubset({path.name for path in package.iterdir()})
    assert "down -v" not in "\n".join(path.read_text(encoding="utf-8").lower() for path in package.glob("*.ps1"))
    example = (package / ".env.example").read_text(encoding="utf-8")
    forbidden = re.compile(r"^(?!KINLIN_SECRETS_DIR=).*(PASSWORD|TOKEN|SECRET|API_?KEY|JWT).*=" , re.MULTILINE)
    assert not forbidden.search(example)
    restore = (package / "restore.ps1").read_text(encoding="utf-8")
    assert "TargetSecretsDir" in restore


def test_windows_package_uses_the_canonical_compose_baseline():
    package = ROOT / "deploy" / "windows" / "package"
    package_script = (ROOT / "scripts" / "infra" / "windows" / "package.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    windows_production = (ROOT / "compose.windows.prod.yaml").read_text(encoding="utf-8")

    assert not (package / "compose.yaml").exists()
    assert 'Join-Path $projectRoot "compose.yaml"' in package_script
    assert 'Join-Path $output "compose.yaml"' in package_script
    assert 'Join-Path $projectRoot "compose.prod.yaml"' in package_script
    assert 'Join-Path $output "compose.prod.yaml"' in package_script
    assert "build: !reset null" in windows_production
    assert "./migrations:/flyway/sql:ro" in windows_production
    assert "backend-uploads:/app/data/uploads" in compose
    assert "agentos-data:/app/data" in compose
    assert "postgres-data:/var/lib/postgresql/data" in compose
    assert "./backend/src/main/resources/db/migration:/flyway/sql:ro" in compose

    model = yaml.safe_load(compose)
    for service in model["services"].values():
        for mount in service.get("tmpfs", []):
            assert mount.startswith("/"), mount
    for network in model["networks"].values():
        for config in network.get("ipam", {}).get("config", []):
            subnet = config["subnet"]
            assert subnet.endswith("/28") or "/28}" in subnet


def test_backup_image_inventory_falls_back_to_runtime_container_inspect():
    compose_failure = subprocess.CalledProcessError(1, ["docker", "compose", "images"])
    inspected = '[{"Name":"/demo-backend-1","Image":"sha256:abc","Config":{"Image":"demo:dev","Labels":{"com.docker.compose.service":"backend"}}}]'

    with patch.object(backup, "compose", side_effect=[compose_failure, SimpleNamespace(stdout="container-id\n")]), patch.object(
        backup, "run", return_value=SimpleNamespace(stdout=inspected)
    ):
        inventory = backup.image_inventory("demo")

    assert inventory == [{
        "container": "demo-backend-1",
        "service": "backend",
        "configuredImage": "demo:dev",
        "runtimeImageId": "sha256:abc",
        "source": "container-inspect-fallback",
    }]

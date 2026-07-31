from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT_SERVICES = {"backend", "ai-service", "postgres", "redis", "schema-tool"}
EXPECTED_ENTRYPOINT_CAPS = {"CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"}


def test_production_services_use_read_only_roots_and_capability_allowlists():
    production = yaml.safe_load((ROOT / "compose.prod.yaml").read_text(encoding="utf-8"))

    for name, service in production["services"].items():
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert service["security_opt"] == ["no-new-privileges:true"], name
        if name in ENTRYPOINT_SERVICES:
            assert set(service["cap_add"]) == EXPECTED_ENTRYPOINT_CAPS, name
            assert any(item.startswith("/run/secrets:") for item in service["tmpfs"]), name
        else:
            assert "cap_add" not in service, name


def test_windows_production_overlay_is_amd64_image_only_and_loopback_scoped():
    overlay = (ROOT / "compose.windows.prod.yaml").read_text(encoding="utf-8")

    assert "127.0.0.1:${KINLIN_HTTP_PORT:-8080}:8080" in overlay
    assert "windows-ingress-network" in overlay
    assert "command:" not in overlay
    assert overlay.count("volumes:") == 1
    assert "./migrations:/flyway/sql:ro" in overlay
    assert overlay.count("platform: linux/amd64") == 6
    assert overlay.count("build: !reset null") == 6
    assert "windows-amd64" in overlay

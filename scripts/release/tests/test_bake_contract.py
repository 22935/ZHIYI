from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_bake_contract_has_all_release_groups_and_no_latest_tag():
    bake = (ROOT / "docker-bake.hcl").read_text(encoding="utf-8")

    for name in (
        "frontend",
        "backend",
        "ai-service",
        "runtime-dependencies",
        "all",
        "release-amd64",
        "release-arm64",
        "release-multiarch",
    ):
        assert f'"{name}"' in bake
    assert ":latest" not in bake
    assert '"type=sbom"' in bake
    assert '"type=provenance,mode=max"' in bake


def test_every_release_architecture_uses_the_same_service_target():
    bake = (ROOT / "docker-bake.hcl").read_text(encoding="utf-8")

    for service in ("frontend", "backend", "ai-service", "postgres", "redis", "flyway"):
        assert f'inherits = ["{service}", "_release"]' in bake

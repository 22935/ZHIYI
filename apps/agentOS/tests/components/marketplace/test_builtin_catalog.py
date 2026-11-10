"""真实包安装、签名执行、租户隔离和卸载集成验证。"""
import hashlib
import json
import time
import httpx
from components.marketplace.builtins.catalog import build_builtin_catalog
from components.marketplace.infrastructure import LocalPackageLauncher, InMemoryCatalog, InMemoryInstallationJobs, LoopbackHttpEndpointProbe, validate_package
from components.marketplace.application.service import MarketplaceService
from components.resource.application.resource_plane import ResourcePlane
from contracts.resource.resource_signing import build_resource_signature


def test_catalog_packages_are_hashed_and_deterministic(tmp_path):
    items = build_builtin_catalog(tmp_path / "catalog", tmp_path / "packages")
    again = build_builtin_catalog(tmp_path / "catalog", tmp_path / "packages")
    assert {i.catalog_id for i in items} == {"tool.pdf-parser", "tool.file-converter"}
    assert [i.sha256 for i in items] == [i.sha256 for i in again]
    for item in items:
        assert validate_package(tmp_path / "packages", item).is_file()
        assert item.runtime["adapter"] == "agentos_http"


def test_actual_install_signed_execute_stop_and_uninstall(tmp_path):
    items = build_builtin_catalog(tmp_path / "catalog", tmp_path / "packages")
    plane = ResourcePlane()
    launcher = LocalPackageLauncher(package_root=tmp_path / "packages", install_root=tmp_path / "installed")
    service = MarketplaceService(catalog=InMemoryCatalog(items), jobs=InMemoryInstallationJobs(), package_root=tmp_path / "packages", launcher=launcher, endpoint_probe=LoopbackHttpEndpointProbe(), plane=plane)
    try:
        job = service.install(catalog_id="tool.file-converter", owner_scope="tenant-a")
        assert job.status.value == "running", job.error_summary
        runtime = plane.runtime(job.runtime_id)
        workspace = launcher.workspace(job.runtime_id)
        (workspace / "input.md").write_text("# Hello", encoding="utf-8")
        body = json.dumps({"capability": "file.convert", "input": {"sourcePath": "input.md", "targetFormat": "html"}}).encode()
        timestamp, nonce = int(time.time()), "integration-test-nonce"
        credential_id, secret = plane.current_signing_credential(job.runtime_id)
        headers = {"X-Resource-Credential": credential_id, "X-Resource-Timestamp": str(timestamp), "X-Resource-Nonce": nonce,
                   "X-Resource-Signature": build_resource_signature(secret, method="POST", path="/execute", timestamp=timestamp, nonce=nonce, body=body)}
        address = runtime.endpoint.address + "/execute"
        assert httpx.post(address, content=body).status_code == 401
        result = httpx.post(address, content=body, headers=headers, timeout=40)
        assert result.status_code == 200, result.text
        output = result.json()["output"]
        assert "<h1>Hello</h1>" in (workspace / output["outputPath"]).read_text(encoding="utf-8")
        assert httpx.post(address, content=body, headers=headers).status_code == 401
        assert service.stop(job.job_id, owner_scope="tenant-a").status.value == "stopped"
        assert service.uninstall(job.job_id, owner_scope="tenant-a").status.value == "removed"
        assert not workspace.exists()
    finally:
        launcher.close()

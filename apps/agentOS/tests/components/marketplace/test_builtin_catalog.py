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
        assert not {"startup", "runtime", "packagePath", "sha256"} & service.public_catalog()[0].keys()
        import pytest
        with pytest.raises(KeyError):
            service.upload_tool_file(job.job_id, owner_scope="other-tenant", filename="input.md", content=b"# Hello")
        uploaded = service.upload_tool_file(job.job_id, owner_scope="tenant-a", filename="input.md", content=b"# Uploaded")
        converted = service.execute_tool(job.job_id, owner_scope="tenant-a", data={"sourcePath": uploaded["sourcePath"], "targetFormat": "html"})
        downloaded, name = service.download_tool_file(job.job_id, owner_scope="tenant-a", relative_path=converted["outputPath"])
        assert b"<h1>Uploaded</h1>" in downloaded
        assert name == "result.html"
        with pytest.raises(ValueError):
            service.download_tool_file(job.job_id, owner_scope="tenant-a", relative_path="../ready.json")
        workspace = launcher.workspace(job.runtime_id)
        (workspace / "input.md").write_text("# Hello", encoding="utf-8")
        body = json.dumps({"capability": "file.convert", "input": {"sourcePath": "input.md", "targetFormat": "html"}}).encode()
        timestamp, nonce = int(time.time()), "integration-test-nonce"
        credential_id, secret = plane.current_signing_credential(job.runtime_id)
        with pytest.raises(ValueError, match="process-bound"):
            plane.rotate_runtime_credential(job.runtime_id)
        assert plane.current_signing_credential(job.runtime_id) == (credential_id, secret)
        headers = {"X-Resource-Credential": credential_id, "X-Resource-Timestamp": str(timestamp), "X-Resource-Nonce": nonce,
                   "X-Resource-Signature": build_resource_signature(secret, method="POST", path="/execute", timestamp=timestamp, nonce=nonce, body=body)}
        address = runtime.endpoint.address + "/execute"
        assert httpx.post(address, content=body).status_code == 401
        result = httpx.post(address, content=body, headers=headers, timeout=40)
        assert result.status_code == 200, result.text
        output = result.json()["output"]
        assert "<h1>Hello</h1>" in (workspace / output["outputPath"]).read_text(encoding="utf-8")
        assert httpx.post(address, content=body, headers=headers).status_code == 401
        # 验证真实 ACG HTTP 执行适配器也能消费工具的 AgentOutput 合同。
        from adapters.resource_execution import build_resource_execution_adapter
        from types import SimpleNamespace
        import asyncio
        adapter = build_resource_execution_adapter(runtime, credential_provider=plane)
        context = SimpleNamespace(run=SimpleNamespace(run_id="run-test"), task=SimpleNamespace(mission_id="mission-test"),
            step=SimpleNamespace(step_id="step-test", agent_name="document-tool", capability="file.convert", goal="convert"),
            context_pack=SimpleNamespace(data={"sourcePath": "input.md", "targetFormat": "html"}, attempt_id="attempt-test", evidence_refs=[]), commit_id="commit-test")
        async def invoke():
            try:
                return await adapter.run(context)
            finally:
                await adapter.aclose()
        assert asyncio.run(invoke()).output["format"] == "html"
        from adapters.resource_execution import ResourceExecutionError
        adapter = build_resource_execution_adapter(runtime, credential_provider=plane)
        context.context_pack.data = {"sourcePath": "input.md", "targetFormat": "exe"}
        with pytest.raises(ResourceExecutionError) as failure:
            asyncio.run(invoke())
        assert not failure.value.outcome_unknown
        assert service.stop(job.job_id, owner_scope="tenant-a").status.value == "stopped"
        assert service.uninstall(job.job_id, owner_scope="tenant-a").status.value == "removed"
        assert not workspace.exists()
    finally:
        launcher.close()


def test_service_detects_dead_process_and_allows_cleanup_after_restart(tmp_path):
    items = build_builtin_catalog(tmp_path / "catalog", tmp_path / "packages")
    plane, jobs = ResourcePlane(), InMemoryInstallationJobs()
    launcher = LocalPackageLauncher(package_root=tmp_path / "packages", install_root=tmp_path / "installed")
    service = MarketplaceService(catalog=InMemoryCatalog(items), jobs=jobs, package_root=tmp_path / "packages", launcher=launcher, endpoint_probe=LoopbackHttpEndpointProbe(), plane=plane)
    try:
        job = service.install(catalog_id="tool.pdf-parser", owner_scope="tenant-a")
        assert job.status.value == "running"
        workspace = launcher.workspace(job.runtime_id)
        service.refresh_managed_health()
        assert plane.health_monitor.health(job.runtime_id).healthy
        from test_builtin_tools import text_pdf
        text_pdf(workspace / "input.pdf")
        parsed = service.execute_tool(job.job_id, owner_scope="tenant-a", data={"sourcePath": "input.pdf"})
        assert parsed["text"] == "agentos"
        launcher.close()
        replacement = LocalPackageLauncher(package_root=tmp_path / "packages", install_root=tmp_path / "installed")
        service.launcher = replacement
        service.refresh_managed_health()
        assert not plane.runtime(job.runtime_id).enabled
        assert service.get_installation(job.job_id, owner_scope="tenant-a").status.value == "stopped"
        assert service.uninstall(job.job_id, owner_scope="tenant-a").status.value == "removed"
        assert not workspace.exists()
    finally:
        launcher.close()


def test_removal_retries_transient_directory_lock(tmp_path, monkeypatch):
    import shutil
    launcher = LocalPackageLauncher(package_root=tmp_path / "packages", install_root=tmp_path / "installed")
    path = launcher.install_root / "test-install"
    path.mkdir()
    original = shutil.rmtree
    calls = []
    def locked_once(target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError("sharing violation")
        return original(target)
    monkeypatch.setattr(shutil, "rmtree", locked_once)
    launcher._remove_installation_path(path)
    assert len(calls) == 2
    assert not path.exists()


def test_health_refresh_cannot_resurrect_uninstalled_job(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    items = build_builtin_catalog(tmp_path / "catalog", tmp_path / "packages")
    launcher = LocalPackageLauncher(package_root=tmp_path / "packages", install_root=tmp_path / "installed")
    service = MarketplaceService(catalog=InMemoryCatalog(items), jobs=InMemoryInstallationJobs(), package_root=tmp_path / "packages", launcher=launcher, endpoint_probe=LoopbackHttpEndpointProbe(), plane=ResourcePlane())
    entered, release = Event(), Event()
    try:
        job = service.install(catalog_id="tool.pdf-parser", owner_scope="tenant-a")
        assert job.status.value == "running"
        def unhealthy(runtime_id):
            entered.set()
            assert release.wait(5)
            return False
        monkeypatch.setattr(launcher, "healthy", unhealthy)
        with ThreadPoolExecutor(2) as pool:
            refreshed = pool.submit(service.refresh_managed_health)
            assert entered.wait(5)
            removed = pool.submit(service.uninstall, job.job_id, owner_scope="tenant-a")
            try:
                assert not removed.done()
            finally:
                release.set()
            refreshed.result(timeout=5)
            assert removed.result(timeout=5).status.value == "removed"
        assert service.get_installation(job.job_id, owner_scope="tenant-a").status.value == "removed"
    finally:
        release.set()
        launcher.close()

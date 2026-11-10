"""安装服务对资源平面产生的可观察行为。"""

from __future__ import annotations

import hashlib

from components.marketplace.application.service import MarketplaceService
from components.marketplace.contracts import CatalogItem, CustomResourceRequest, InstallationJob, InstallationStatus
from components.marketplace.infrastructure import InMemoryCatalog, InMemoryInstallationJobs
from components.marketplace.infrastructure import SQLiteInstallationJobStore
from components.resource.application.resource_plane import ResourcePlane
from contracts.resource import Placement, RuntimeKind, TrustLevel
from contracts.resource import RuntimeProfile


class _Launcher:
    def __init__(self, healthy: bool = True) -> None:
        self.is_healthy = healthy
        self.started: list[str] = []
        self.stopped: list[str] = []

    def start(self, item: CatalogItem, *, owner_scope: str):
        self.started.append(item.catalog_id)
        return RuntimeProfile.model_validate(item.runtime)

    def stop(self, runtime_id: str) -> None:
        self.stopped.append(runtime_id)

    def healthy(self, runtime_id: str) -> bool:
        return self.is_healthy


class _Probe:
    def __init__(self, healthy: bool = True) -> None:
        self.is_healthy = healthy

    def healthy(self, endpoint: str) -> bool:
        return self.is_healthy


def _service(tmp_path, *, healthy: bool = True, expected_hash: str | None = None):
    package = b"bundle"
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "demo.bundle").write_bytes(package)
    item = CatalogItem(
        catalogId="model.demo",
        kind="model_server",
        version="1.0.0",
        displayName="Demo Model",
        packagePath="models/demo.bundle",
        sha256=expected_hash or hashlib.sha256(package).hexdigest(),
        runtime={
            "runtimeId": "runtime:market:demo",
            "kind": "model_server",
            "nodeId": "node:device:marketplace",
            "placement": "device",
            "trust": "host_trusted",
            "provider": "Demo",
            "adapter": "agentos_model_http",
            "endpoint": {"protocol": "https", "address": "https://127.0.0.1:1234"},
            "capabilities": ["model.generate"],
            "modelIds": ["demo-chat"],
            "capacity": 1,
        },
    )
    launcher = _Launcher(healthy)
    plane = ResourcePlane()
    service = MarketplaceService(
        catalog=InMemoryCatalog([item]),
        jobs=InMemoryInstallationJobs(),
        package_root=tmp_path,
        launcher=launcher,
        endpoint_probe=_Probe(healthy),
        plane=plane,
    )
    return service, plane, launcher


def test_install_registers_healthy_local_runtime_after_package_validation(tmp_path):
    service, plane, launcher = _service(tmp_path)

    job = service.install(catalog_id="model.demo", owner_scope="tenant-a")

    assert job.status is InstallationStatus.RUNNING
    assert plane.runtime(job.runtime_id).kind is RuntimeKind.MODEL_SERVER
    assert plane.runtime(job.runtime_id).placement is Placement.DEVICE
    assert plane.health_monitor.health(job.runtime_id).healthy is True
    assert launcher.started == ["model.demo"]


def test_invalid_checksum_fails_without_registering_a_runtime(tmp_path):
    service, plane, launcher = _service(tmp_path, expected_hash="0" * 64)

    job = service.install(catalog_id="model.demo", owner_scope="tenant-a")

    assert job.status is InstallationStatus.FAILED
    assert "checksum" in job.error_summary.lower()
    assert launcher.started == []
    assert not any(profile.runtime_id == "runtime:market:demo" for profile in plane.runtimes())


def test_installation_job_survives_store_reopen_and_is_tenant_scoped(tmp_path):
    store_path = tmp_path / "marketplace.sqlite3"
    first = SQLiteInstallationJobStore(store_path)
    job = first.create(InstallationJob.new("job-persisted", "model.demo", "tenant-a"))
    first.close()

    reopened = SQLiteInstallationJobStore(store_path)
    try:
        assert reopened.get(job.job_id).owner_scope == "tenant-a"
        assert [item.job_id for item in reopened.list("tenant-a")] == [job.job_id]
        assert reopened.list("tenant-b") == []
    finally:
        reopened.close()


def test_custom_local_service_rejects_shell_command():
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        CustomResourceRequest(
            displayName="Local model",
            kind="model_server",
            endpoint={"protocol": "http", "address": "http://127.0.0.1:11434"},
            capabilities=["model.generate"],
            command="run arbitrary command",
        )


def test_custom_local_service_registers_only_after_loopback_health_check(tmp_path):
    service, plane, _ = _service(tmp_path)

    job = service.register_custom(
        CustomResourceRequest(
            displayName="Ollama local",
            kind="model_server",
            endpoint={"protocol": "http", "address": "http://127.0.0.1:11434"},
            capabilities=["model.generate"],
            modelIds=["qwen-local"],
            provider="Ollama",
            adapter="agentos_model_http",
        ),
        owner_scope="tenant-a",
    )

    assert job.status is InstallationStatus.RUNNING
    assert plane.runtime(job.runtime_id).source_type == "custom-local"
    assert plane.model_endpoint(f"model:{job.runtime_id}:qwen-local").model == "qwen-local"


def test_unhealthy_custom_endpoint_is_not_registered(tmp_path):
    service, plane, _ = _service(tmp_path, healthy=False)

    job = service.register_custom(
        CustomResourceRequest(
            displayName="Unavailable local model",
            kind="model_server",
            endpoint={"protocol": "http", "address": "http://localhost:11434"},
            capabilities=["model.generate"], modelIds=["model"], provider="Local",
        ),
        owner_scope="tenant-a",
    )

    assert job.status is InstallationStatus.FAILED
    assert not any(profile.source_type == "custom-local" for profile in plane.runtimes())


def test_uninstall_stops_launcher_and_removes_marketplace_runtime(tmp_path):
    service, plane, launcher = _service(tmp_path)
    job = service.install(catalog_id="model.demo", owner_scope="tenant-a")

    removed = service.uninstall(job.job_id, owner_scope="tenant-a")

    assert removed.status is InstallationStatus.REMOVED
    assert launcher.stopped == [job.runtime_id]
    assert not any(profile.runtime_id == job.runtime_id for profile in plane.runtimes())

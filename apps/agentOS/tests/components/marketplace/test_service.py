"""安装服务对资源平面产生的可观察行为。"""

from __future__ import annotations

import hashlib

from components.marketplace.application.service import MarketplaceService
from components.marketplace.contracts import CatalogItem, InstallationJob, InstallationStatus
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

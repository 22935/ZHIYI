"""本地目录安装任务与资源平面之间的应用编排。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from components.resource.application.resource_plane import ResourcePlane
from contracts.resource import HealthStatus, Placement, ResourceEndpoint, RuntimeKind, RuntimeProfile, RuntimeSnapshot, TrustLevel

from ..contracts import CatalogItem, InstallationJob, InstallationStatus
from ..infrastructure import validate_package
from ..ports import Catalog, InstallationJobStore, LocalEndpointProbe, LocalLauncher


class MarketplaceService:
    """校验平台本地包，委托受控启动器并将健康服务接入资源平面。"""

    def __init__(
        self,
        *,
        catalog: Catalog,
        jobs: InstallationJobStore,
        package_root: str | Path,
        launcher: LocalLauncher,
        endpoint_probe: LocalEndpointProbe,
        plane: ResourcePlane,
    ) -> None:
        self.catalog = catalog
        self.jobs = jobs
        self.package_root = Path(package_root)
        self.launcher = launcher
        self.endpoint_probe = endpoint_probe
        self.plane = plane

    def list_catalog(self) -> list[CatalogItem]:
        return self.catalog.list_items()

    def list_installations(self, owner_scope: str) -> list[InstallationJob]:
        return self.jobs.list(owner_scope)

    def get_installation(self, job_id: str, *, owner_scope: str) -> InstallationJob:
        job = self.jobs.get(job_id)
        if job.owner_scope != owner_scope:
            raise KeyError(f"unknown installation job: {job_id}")
        return job

    def install(self, *, catalog_id: str, owner_scope: str) -> InstallationJob:
        item = self.catalog.get(catalog_id)
        job = self.jobs.create(InstallationJob.new(
            f"install:{uuid.uuid4().hex}", catalog_id, owner_scope, display_name=item.display_name
        ))
        started_runtime: str | None = None
        registered_runtime: str | None = None
        stage = "package validation"
        try:
            validate_package(self.package_root, item)
            job = self._advance(job, InstallationStatus.INSTALLING)
            stage = "local service startup"
            profile = self.launcher.start(item, owner_scope=owner_scope)
            started_runtime = profile.runtime_id
            profile = self._validate_profile(profile, item, owner_scope)
            job = self._advance(job, InstallationStatus.REGISTERING, runtime_id=profile.runtime_id)
            stage = "resource registration"
            self._register_host(profile)
            snapshot = RuntimeSnapshot(
                runtimeId=profile.runtime_id,
                availableSlots=profile.capacity,
                utilization=0.0,
                healthStatus=HealthStatus.UNKNOWN,
            )
            if item.startup.get("pythonModule") == "agentos_local_tools.server":
                credential_id, secret = self.launcher.signing_credential(profile.runtime_id)
                self.plane.register_remote_runtime(profile, snapshot, credential_id=credential_id, secret=secret)
            else:
                self.plane.register_runtime(profile, snapshot)
            registered_runtime = profile.runtime_id
            stage = "local service health check"
            if not self.launcher.healthy(profile.runtime_id):
                raise RuntimeError("health check failed")
            self.plane.observe_execution(profile.runtime_id, success=True, latency_ms=0.0)
            return self._advance(job, InstallationStatus.RUNNING, runtime_id=profile.runtime_id)
        except Exception as exc:
            if started_runtime is not None:
                try:
                    self.launcher.stop(started_runtime)
                except Exception:
                    pass
            if registered_runtime is not None:
                try:
                    self.plane.unregister_marketplace_runtime(registered_runtime)
                except Exception:
                    pass
            if started_runtime is not None:
                remove = getattr(self.launcher, "remove", None)
                if callable(remove):
                    try:
                        remove(started_runtime)
                    except Exception:
                        pass
            summary = "package checksum mismatch" if "checksum mismatch" in str(exc).lower() else f"{stage} failed"
            return self._advance(job, InstallationStatus.FAILED, error_summary=summary)

    def register_custom(self, request, *, owner_scope: str) -> InstallationJob:
        job = self.jobs.create(InstallationJob.new(
            f"custom:{uuid.uuid4().hex}", None, owner_scope, display_name=request.display_name
        ))
        try:
            job = self._advance(job, InstallationStatus.INSTALLING)
            if not self.endpoint_probe.healthy(request.endpoint.address):
                raise RuntimeError("local endpoint health check failed")
            job = self._advance(job, InstallationStatus.REGISTERING)
            runtime_id = f"runtime:custom:{uuid.uuid4().hex}"
            adapter = request.adapter or (
                "agentos_model_http" if request.kind is RuntimeKind.MODEL_SERVER else "agentos_http"
            )
            profile = RuntimeProfile(
                runtimeId=runtime_id,
                kind=request.kind,
                displayName=request.display_name,
                nodeId=f"node:device:{owner_scope}",
                placement=Placement.DEVICE,
                capabilities=request.capabilities,
                trust=TrustLevel.HOST_TRUSTED,
                endpoint=request.endpoint,
                capacity=1,
                ownerScope=owner_scope,
                provider=request.provider,
                adapter=adapter,
                sourceType="custom-local",
                modelIds=request.model_ids,
                metadata={"managedBy": "marketplace", "customResource": True},
            )
            self._register_host(profile)
            self.plane.register_runtime(profile, RuntimeSnapshot(
                runtimeId=runtime_id, availableSlots=1, utilization=0.0,
                healthStatus=HealthStatus.UNKNOWN,
            ))
            self.plane.observe_execution(runtime_id, success=True, latency_ms=0.0)
            return self._advance(job, InstallationStatus.RUNNING, runtime_id=runtime_id)
        except Exception:
            return self._advance(job, InstallationStatus.FAILED, error_summary="custom local service registration failed")

    def stop(self, job_id: str, *, owner_scope: str) -> InstallationJob:
        job = self.get_installation(job_id, owner_scope=owner_scope)
        if job.status is not InstallationStatus.RUNNING or not job.runtime_id:
            raise ValueError("only running installations can be stopped")
        profile = self.plane.runtime(job.runtime_id)
        if profile.source_type != "custom-local":
            self.launcher.stop(job.runtime_id)
        self.plane.set_runtime_enabled(job.runtime_id, enabled=False)
        return self._advance(job, InstallationStatus.STOPPED)

    def uninstall(self, job_id: str, *, owner_scope: str) -> InstallationJob:
        job = self.get_installation(job_id, owner_scope=owner_scope)
        if job.status is InstallationStatus.RUNNING:
            job = self.stop(job_id, owner_scope=owner_scope)
        if job.status is not InstallationStatus.STOPPED or not job.runtime_id:
            raise ValueError("only stopped installations can be uninstalled")
        job = self._advance(job, InstallationStatus.UNINSTALLING)
        try:
            remove = getattr(self.launcher, "remove", None)
            if callable(remove):
                remove(job.runtime_id)
            self.plane.unregister_marketplace_runtime(job.runtime_id)
            return self._advance(job, InstallationStatus.REMOVED)
        except Exception:
            return self._advance(job, InstallationStatus.FAILED, error_summary="uninstall failed")

    def _advance(
        self,
        job: InstallationJob,
        status: InstallationStatus,
        *,
        runtime_id: str | None = None,
        error_summary: str | None = None,
    ) -> InstallationJob:
        return self.jobs.update(job.advance(status, runtime_id=runtime_id, error_summary=error_summary))

    @staticmethod
    def _validate_profile(profile: RuntimeProfile, item: CatalogItem, owner_scope: str) -> RuntimeProfile:
        declared = RuntimeProfile.model_validate(item.runtime)
        builtin = item.startup.get("pythonModule") == "agentos_local_tools.server"
        identity_matches = (profile.runtime_id.startswith(declared.runtime_id + ":installation:")
                            if builtin else profile.runtime_id == declared.runtime_id)
        if not identity_matches or profile.kind is not item.kind:
            raise ValueError("launcher runtime does not match catalog declaration")
        if profile.kind is RuntimeKind.MODEL_SERVER and not profile.model_ids:
            raise ValueError("model runtime must declare model ids")
        metadata = {**profile.metadata, "managedBy": "marketplace", "catalogId": item.catalog_id}
        return profile.model_copy(update={"owner_scope": owner_scope, "metadata": metadata})

    def _register_host(self, profile: RuntimeProfile) -> None:
        try:
            self.plane.node(profile.node_id)
        except KeyError:
            self.plane.ensure_node(
                profile.node_id,
                placement=profile.placement,
                display_name="本机设备",
                trust=TrustLevel.HOST_TRUSTED,
                owner_scope=profile.owner_scope,
                metadata={"managedBy": "marketplace"},
            )


__all__ = ["MarketplaceService"]

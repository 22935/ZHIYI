from __future__ import annotations

from datetime import datetime, timedelta, timezone

from components.resource.service import ResourceService
from components.scheduler.leases import InMemoryLeaseCoordinator
from components.scheduler.service import SchedulerService
from contracts.resource import (
    BindingRequirement,
    ComputeCapacity,
    DeploymentTier,
    ResourceHealthStatus,
    ResourceEndpoint,
    ResourceProfile,
    ResourceSnapshot,
    ResourceType,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


class _RacingResourceService(ResourceService):
    def __init__(self) -> None:
        super().__init__(heartbeat_timeout=timedelta(minutes=5))
        self._snapshot_calls = 0

    def snapshot(self, resource_id: str):
        current = super().snapshot(resource_id)
        self._snapshot_calls += 1
        if self._snapshot_calls == 2:
            self.update_snapshot(
                current.snapshot.model_copy(update={"available_slots": 0, "utilization": 1.0}),
                expected_version=current.version,
            )
        return current


def _resource(
    resources: ResourceService,
    resource_id: str,
    *,
    tier: DeploymentTier,
    privacy: str = "internal",
    model_ids: list[str] | None = None,
    gpu_memory_mb: int = 0,
    latency_ms: float = 20,
) -> None:
    resources.register(
        ResourceProfile(
            resourceId=resource_id,
            resourceType=ResourceType.WORKER,
            deploymentTier=tier,
            capabilities=["vision.infer"],
            privacyLevel=privacy,
            modelIds=model_ids or [],
            computeCapacity=ComputeCapacity(gpuMemoryMb=gpu_memory_mb),
            executionEndpoint=(
                ResourceEndpoint(protocol="http", address=f"http://{resource_id}:9000")
                if tier is not DeploymentTier.LOCAL
                else None
            ),
        ),
        ResourceSnapshot(
            resourceId=resource_id,
            availableSlots=1,
            utilization=0.0,
            healthStatus=ResourceHealthStatus.ONLINE,
            latencyMs=latency_ms,
        ),
    )
    resources.heartbeat(
        resource_id,
        received_at=NOW,
        source="external" if tier is not DeploymentTier.LOCAL else "local",
    )


def test_scheduler_filters_edge_cloud_resources_by_placement_constraints() -> None:
    resources = ResourceService(heartbeat_timeout=timedelta(minutes=5))
    _resource(resources, "terminal-01", tier=DeploymentTier.TERMINAL, model_ids=["vision-small"])
    _resource(resources, "edge-01", tier=DeploymentTier.EDGE, model_ids=["vision-small"], gpu_memory_mb=4096)
    _resource(resources, "cloud-01", tier=DeploymentTier.CLOUD, model_ids=["vision-large"], gpu_memory_mb=16384)
    scheduler = SchedulerService(resource_service=resources, coordinator=InMemoryLeaseCoordinator())

    result = scheduler.schedule_ready(
        run_id="run-placement",
        step_id="infer",
        attempt_id="attempt-1",
        requirement=BindingRequirement(
            requiredCapabilities=["vision.infer"],
            allowedDeploymentTiers=["cloud"],
            maxLatencyMs=100,
            privacyLevel="internal",
            requiredModelIds=["vision-large"],
            minGpuMemoryMb=8192,
        ),
        now=NOW,
    )

    assert result.status == "allocated"
    assert result.binding is not None
    assert result.binding.resource_id == "cloud-01"
    assert result.binding.metadata["deploymentTier"] == "cloud"
    assert result.binding.metadata["placementReasons"]
    rejected = {item.resource_id: {reason.value for reason in item.reasons} for item in result.candidates if item.reasons}
    assert "DEPLOYMENT_TIER_MISMATCH" in rejected["edge-01"]
    assert "MODEL_MISMATCH" in rejected["edge-01"]
    assert "GPU_MEMORY_INSUFFICIENT" in rejected["edge-01"]


def test_local_only_requirement_rejects_remote_resources() -> None:
    resources = ResourceService(heartbeat_timeout=timedelta(minutes=5))
    _resource(resources, "edge-01", tier=DeploymentTier.EDGE)
    scheduler = SchedulerService(resource_service=resources)

    result = scheduler.schedule_ready(
        run_id="run-local",
        step_id="infer",
        attempt_id="attempt-1",
        requirement=BindingRequirement(
            requiredCapabilities=["vision.infer"],
            allowRemoteExecution=False,
        ),
        now=NOW,
    )

    assert result.status == "queued"
    assert result.reason == "NO_ELIGIBLE_RESOURCE"
    assert result.candidates[0].reasons[0].value == "REMOTE_EXECUTION_DISABLED"


def test_scheduler_does_not_return_binding_for_a_stale_snapshot() -> None:
    resources = _RacingResourceService()
    _resource(resources, "edge-race", tier=DeploymentTier.EDGE)
    coordinator = InMemoryLeaseCoordinator()
    scheduler = SchedulerService(resource_service=resources, coordinator=coordinator)

    result = scheduler.schedule_ready(
        run_id="run-race",
        step_id="infer",
        attempt_id="attempt-1",
        requirement=BindingRequirement(requiredCapabilities=["vision.infer"]),
        now=NOW,
    )

    assert result.status == "queued"
    assert result.binding is None
    assert coordinator.active_slots("edge-race", now=NOW) == 0

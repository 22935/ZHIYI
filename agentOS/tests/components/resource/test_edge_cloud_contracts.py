from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.resource import (
    BindingRequirement,
    DeploymentTier,
    ResourceEndpoint,
    ResourceProfile,
    ResourceType,
)


def test_resource_profile_declares_deployment_tier_endpoint_and_compute_capacity() -> None:
    profile = ResourceProfile(
        resourceId="edge-01",
        resourceType=ResourceType.WORKER,
        deploymentTier=DeploymentTier.EDGE,
        capabilities=["vision.infer"],
        executionEndpoint=ResourceEndpoint(
            protocol="http",
            address="http://edge-01:9000",
            authReference="secret://edge-01",
        ),
        computeCapacity={
            "cpuCores": 8,
            "memoryMb": 16384,
            "gpuType": "T4",
            "gpuMemoryMb": 16384,
            "bandwidthMbps": 500,
        },
        modelIds=["vision-small"],
    )

    assert profile.deployment_tier is DeploymentTier.EDGE
    assert profile.execution_endpoint is not None
    assert profile.execution_endpoint.address == "http://edge-01:9000"
    assert profile.compute_capacity.gpu_memory_mb == 16384
    assert profile.model_ids == ["vision-small"]


def test_binding_requirement_expresses_edge_cloud_placement_constraints() -> None:
    requirement = BindingRequirement(
        requiredCapabilities=["vision.infer"],
        allowedDeploymentTiers=["edge", "cloud"],
        maxLatencyMs=80,
        privacyLevel="internal",
        requiredModelIds=["vision-small"],
        minGpuMemoryMb=8192,
        allowRemoteExecution=True,
    )

    assert requirement.allowed_deployment_tiers == [
        DeploymentTier.EDGE,
        DeploymentTier.CLOUD,
    ]
    assert requirement.max_latency_ms == 80
    assert requirement.required_model_ids == ["vision-small"]
    assert requirement.min_gpu_memory_mb == 8192
    assert requirement.allow_remote_execution is True


def test_endpoint_rejects_credentials_in_address() -> None:
    with pytest.raises(ValidationError):
        ResourceEndpoint(
            protocol="https",
            address="https://user:password@example.com/infer",
        )

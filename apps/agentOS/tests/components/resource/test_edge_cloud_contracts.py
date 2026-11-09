"""端/边/云放置维度与逻辑类型的契约不变量。

Placement（DEVICE/EDGE/CLOUD）描述"资源在哪、信任边界在哪"，与 RuntimeKind
（执行后端/模型服务/工具服务）正交：任何组合都应可表达，由 Plane 在注册时
校验宿主关系，而不是靠类型枚举硬编码组合。
"""

import pytest
from pydantic import ValidationError

from contracts.resource import (
    ComputeCapacity,
    ExecutionRequirement,
    ModelEndpointProfile,
    NodeProfile,
    NodeSnapshot,
    Placement,
    ResourceEndpoint,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)
from components.resource.application.resource_plane import ResourcePlane


def _runtime(**overrides) -> RuntimeProfile:
    values = dict(
        runtimeId="runtime:edge-exec-1",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-1",
        placement=Placement.EDGE,
        capabilities=["repo.read", "test.run"],
        trust=TrustLevel.TRUSTED,
        endpoint=ResourceEndpoint(
            protocol="https",
            address="https://edge-1.internal:8443/exec",
            authReference="vault:edge-exec-1",
        ),
        capacity=4,
        costMetadata={"costPerHour": 2.5},
    )
    values.update(overrides)
    return RuntimeProfile(**values)


def test_runtime_profile_declares_placement_endpoint_and_compute_capacity() -> None:
    profile = _runtime()
    assert profile.placement is Placement.EDGE
    assert profile.kind is RuntimeKind.EXECUTION_BACKEND
    assert profile.endpoint is not None and profile.endpoint.auth_reference == "vault:edge-exec-1"
    assert profile.capacity == 4
    assert profile.cost_metadata == {"costPerHour": 2.5}


def test_placement_is_orthogonal_to_runtime_kind() -> None:
    combinations = [
        (Placement.DEVICE, RuntimeKind.EXECUTION_BACKEND),
        (Placement.EDGE, RuntimeKind.EXECUTION_BACKEND),
        (Placement.CLOUD, RuntimeKind.EXECUTION_BACKEND),
        (Placement.DEVICE, RuntimeKind.MODEL_SERVER),
        (Placement.EDGE, RuntimeKind.MODEL_SERVER),
        (Placement.CLOUD, RuntimeKind.MODEL_SERVER),
        (Placement.EDGE, RuntimeKind.TOOL_SERVICE),
        (Placement.CLOUD, RuntimeKind.TOOL_SERVICE),
    ]
    for placement, kind in combinations:
        profile = _runtime(placement=placement, kind=kind)
        assert profile.placement is placement
        assert profile.kind is kind


def test_binding_requirement_expresses_edge_cloud_placement_constraints() -> None:
    requirement = ExecutionRequirement(
        requiredCapabilities=["repo.read"],
        runtimeKinds=[RuntimeKind.EXECUTION_BACKEND],
        allowedPlacements=[Placement.EDGE, Placement.CLOUD],
        minTrust=TrustLevel.TRUSTED,
    )
    assert Placement.DEVICE not in requirement.allowed_placements
    assert requirement.min_trust is TrustLevel.TRUSTED
    assert requirement.min_trust.rank > TrustLevel.SANDBOXED.rank


def test_trust_levels_rank_monotonically() -> None:
    ranks = [level.rank for level in TrustLevel]
    assert ranks == sorted(ranks, reverse=True)
    assert TrustLevel.HOST_TRUSTED.rank > TrustLevel.TRUSTED.rank
    assert TrustLevel.UNTRUSTED.rank == 0


def test_endpoint_rejects_credentials_in_address() -> None:
    with pytest.raises(ValidationError):
        ResourceEndpoint(protocol="https", address="https://user:pass@edge-1.internal/exec")


def test_runtime_profile_requires_at_least_one_capability() -> None:
    with pytest.raises(ValidationError):
        _runtime(capabilities=[])


def test_model_endpoint_defaults_to_cloud_and_declares_bindable_route() -> None:
    endpoint = ModelEndpointProfile(
        endpointId="endpoint:glm-coding",
        provider="zhipu",
        model="glm-4.6",
        modelVersion="2026-09",
        contextWindowTokens=200_000,
    )
    assert endpoint.placement is Placement.CLOUD
    assert endpoint.runtime_id is None
    assert endpoint.enabled is True


def test_node_profile_declares_trust_ceiling_and_compute_capacity() -> None:
    node = NodeProfile(
        nodeId="node:edge-1",
        placement=Placement.EDGE,
        trust=TrustLevel.TRUSTED,
        computeCapacity=ComputeCapacity(cpuCores=8.0, memoryMb=16_384),
    )
    assert node.trust is TrustLevel.TRUSTED
    assert node.compute.cpu_cores == 8.0


def test_runtime_snapshot_reports_slots_and_health_only() -> None:
    snapshot = RuntimeSnapshot(
        runtimeId="runtime:edge-exec-1",
        availableSlots=3,
        utilization=0.25,
        healthStatus="online",
        reliability=0.98,
        latencyMs=120.0,
    )
    assert snapshot.available_slots == 3
    assert snapshot.utilization == 0.25


def test_resource_contracts_accept_vendor_source_and_adapter_without_changing_placement():
    node = NodeProfile(nodeId="node:edge:vendor", placement=Placement.EDGE,
        sourceType="kubernetes", provider="acme", adapter="k8s-agentos", ownerScope="tenant-a")
    runtime = _runtime(nodeId=node.node_id, provider="acme", sourceType="vendor-runtime",
        adapter="agentos-http", metadata={"vendorRegion": "zone-a", "accelerator": {"name": "NPU-X"}})
    model = ModelEndpointProfile(endpointId="model:acme/chat", provider="acme", model="chat",
        sourceType="cloud-api", adapter="openai-compatible")

    assert node.placement is Placement.EDGE and node.provider == "acme"
    assert runtime.placement is Placement.EDGE and runtime.source_type == "vendor-runtime"
    assert runtime.metadata["accelerator"]["name"] == "NPU-X"
    assert model.source_type == "cloud-api" and model.adapter == "openai-compatible"


def test_model_registry_projection_preserves_declared_placement_and_vendor_metadata():
    plane = ResourcePlane()
    plane.sync_model_endpoints([{
        "provider": "vLLM",
        "model": "qwen-local",
        "runtimeId": "runtime:edge:vllm",
        "placement": "edge",
        "sourceType": "kubernetes",
        "adapter": "openai-compatible",
        "tier": "local-inference",
        "contextWindowTokens": 65536,
        "maxOutputTokens": 8192,
        "costMetadata": {"unit": 0.2},
        "labels": {"region": "cn-east"},
        "metadata": {"cluster": "edge-a"},
    }])

    endpoint = plane.model_endpoint("model:vLLM/qwen-local")
    assert endpoint.placement is Placement.EDGE
    assert endpoint.runtime_id == "runtime:edge:vllm"
    assert endpoint.source_type == "kubernetes"
    assert endpoint.adapter == "openai-compatible"
    assert endpoint.tier == "local-inference"
    assert endpoint.context_window_tokens == 65536
    assert endpoint.max_output_tokens == 8192
    assert endpoint.cost_metadata == {"unit": 0.2}
    assert endpoint.labels == {"region": "cn-east"}
    assert endpoint.metadata == {"cluster": "edge-a", "_resourcePlaneSync": "model-registry"}


def test_model_registry_projection_does_not_infer_placement_from_provider_name():
    plane = ResourcePlane()
    plane.sync_model_endpoints([{"provider": "ollama", "model": "remote-model", "placement": "cloud"}])

    assert plane.model_endpoint("model:ollama/remote-model").placement is Placement.CLOUD


@pytest.mark.parametrize(
    ("protocol", "address", "adapter"),
    [("grpc", "grpc://runtime.example.test", "grpc-vendor"),
     ("https", "https://runtime.example.test", "mcp")],
)
def test_remote_runtime_registration_rejects_unimplemented_execution_adapters(protocol, address, adapter):
    plane = ResourcePlane()
    profile = _runtime(endpoint=ResourceEndpoint(protocol=protocol, address=address), adapter=adapter)

    with pytest.raises(ValueError, match=r"supported AgentOS HTTP\(S\) adapter"):
        plane.register_remote_runtime(profile, RuntimeSnapshot(
            runtimeId=profile.runtime_id, availableSlots=profile.capacity, utilization=0.0
        ))


def test_remote_runtime_registration_requires_the_host_node_owner_scope():
    plane = ResourcePlane()
    plane.register_remote_node(
        NodeProfile(nodeId="node:edge:tenant-a", placement=Placement.EDGE,
                    trust=TrustLevel.TRUSTED, ownerScope="tenant-a"),
        NodeSnapshot(nodeId="node:edge:tenant-a", healthStatus="offline"),
    )
    profile = _runtime(nodeId="node:edge:tenant-a", ownerScope="tenant-b")

    with pytest.raises(ValueError, match="ownerScope must match"):
        plane.register_remote_runtime(profile, RuntimeSnapshot(
            runtimeId=profile.runtime_id, availableSlots=profile.capacity, utilization=0.0
        ))

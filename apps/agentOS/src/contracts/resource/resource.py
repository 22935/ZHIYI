"""资源平面合同：Node 承载 Runtime，Runtime 暴露能力与模型端点。

本文件回答资源平面的四个独立问题：

1. 部署实体是什么 —— ``NodeProfile``（设备/边缘节点/云提供方）。
2. 承载实体是什么 —— ``RuntimeProfile``（执行后端、模型服务、工具服务）。
3. 可调度能力是什么 —— Runtime 的 ``capabilities`` 与 ``ModelEndpointProfile``。
4. 任务要什么、拿到了什么 —— ``ExecutionRequirement`` 与 ``ExecutionBinding``。

逻辑类型（RuntimeKind）与部署位置（Placement）正交：一个执行后端可以部署在
DEVICE、EDGE 或 CLOUD；Placement 只是调度维度之一，不是资源类型。

Agent Role、Mission Planner、Coordinator 等逻辑角色不是资源，不出现在本合同中。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from ..authority import RuntimeResourceId
from ..capability import ModelFeatureSet


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Placement(str, Enum):
    """资源所在的位置与信任边界；与逻辑类型正交。"""

    DEVICE = "device"
    EDGE = "edge"
    CLOUD = "cloud"


class TrustLevel(str, Enum):
    """执行环境的信任等级；rank 越高越可信，约束按"至少达到"比较。"""

    HOST_TRUSTED = "host_trusted"
    TRUSTED = "trusted"
    SANDBOXED = "sandboxed"
    UNTRUSTED = "untrusted"

    @property
    def rank(self) -> int:
        return _TRUST_RANK[self]


_TRUST_RANK = {
    TrustLevel.HOST_TRUSTED: 3,
    TrustLevel.TRUSTED: 2,
    TrustLevel.SANDBOXED: 1,
    TrustLevel.UNTRUSTED: 0,
}


class RuntimeKind(str, Enum):
    """Runtime 的逻辑类型；与 Placement 无关。

    EXECUTION_BACKEND：Local Runtime、ZCode、DSH、Codex、Claude Code、
    进程内逻辑 Agent 运行时等"会执行任务"的后端。
    MODEL_SERVER：vLLM、Ollama、云 API 模型提供方等"提供模型推理"的服务。
    TOOL_SERVICE：Browser、MCP、Search 等工具服务。
    """

    EXECUTION_BACKEND = "execution_backend"
    MODEL_SERVER = "model_server"
    TOOL_SERVICE = "tool_service"


class HealthStatus(str, Enum):
    """可持久化的健康投影；UNKNOWN 是安全重启态。"""

    UNKNOWN = "unknown"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class NodeHealthStatus(str, Enum):
    """节点健康分级：在线、忙碌、过载、陈旧、离线。"""

    UNKNOWN = "unknown"
    ONLINE = "online"
    BUSY = "busy"
    OVERLOADED = "overloaded"
    STALE = "stale"
    OFFLINE = "offline"
    SUSPICIOUS = "suspicious"


class RemoteExecutionPolicy(str, Enum):
    """Node 对远程任务的准入策略。"""

    ALLOW = "allow"
    DENY = "deny"
    ALLOWLIST_ONLY = "allowlist_only"


class ResourceEndpoint(BaseModel):
    """远程 Runtime 的可调用地址；只保存凭据引用，不保存凭据内容。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    protocol: Literal["local", "http", "https", "grpc"] = "local"
    address: StrictStr = Field(min_length=1)
    auth_reference: StrictStr | None = Field(default=None, alias="authReference")

    @field_validator("address")
    @classmethod
    def reject_inline_credentials(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("resource endpoint must not contain inline credentials")
        return value


class ComputeCapacity(BaseModel):
    """节点算力摘要，供放置决策使用，不代表完整监控指标。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    cpu_cores: float = Field(default=0.0, ge=0.0, alias="cpuCores")
    memory_mb: int = Field(default=0, ge=0, alias="memoryMb")
    gpu_type: StrictStr | None = Field(default=None, alias="gpuType")
    gpu_memory_mb: int = Field(default=0, ge=0, alias="gpuMemoryMb")
    bandwidth_mbps: float = Field(default=0.0, ge=0.0, alias="bandwidthMbps")


class NodeProfile(BaseModel):
    """部署实体：设备、边缘算力节点或云提供方的静态画像。

    Node 不直接参与能力匹配；它承载 Runtime，并提供放置、算力与信任边界。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    node_id: StrictStr = Field(alias="nodeId", min_length=1, description="节点唯一标识。")
    display_name: StrictStr = Field(default="", alias="displayName")
    placement: Placement = Field(default=Placement.DEVICE)
    trust: TrustLevel = Field(default=TrustLevel.HOST_TRUSTED, description="该节点可提供的最高信任等级。")
    compute: ComputeCapacity = Field(default_factory=ComputeCapacity, alias="computeCapacity")
    location: StrictStr | None = None
    data_zone: StrictStr | None = Field(default=None, alias="dataZone")
    data_region: StrictStr | None = Field(default=None, alias="dataRegion")
    owner_scope: StrictStr | None = Field(default=None, alias="ownerScope")
    labels: dict[str, str] = Field(default_factory=dict)
    remote_execution_policy: RemoteExecutionPolicy = Field(
        default=RemoteExecutionPolicy.ALLOW, alias="remoteExecutionPolicy"
    )
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)


class NodeSnapshot(BaseModel):
    """节点动态状态：由心跳实时刷新。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    node_id: StrictStr = Field(alias="nodeId", min_length=1)
    observation_sequence: int = Field(default=0, ge=0, alias="observationSequence")
    observed_at: datetime = Field(default_factory=_utc_now, alias="observedAt")
    cpu_utilization: float = Field(default=0.0, ge=0.0, le=1.0, alias="cpuUtilization")
    gpu_utilization: float = Field(default=0.0, ge=0.0, le=1.0, alias="gpuUtilization")
    available_memory_mb: int = Field(default=0, ge=0, alias="availableMemoryMb")
    queued_tasks: int = Field(default=0, ge=0, alias="queuedTasks")
    latency_ms: float | None = Field(default=None, ge=0.0, alias="latencyMs")
    health_status: NodeHealthStatus = Field(default=NodeHealthStatus.ONLINE, alias="healthStatus")
    last_heartbeat: datetime | None = Field(default=None, alias="lastHeartbeat")
    consecutive_failures: int = Field(default=0, ge=0, alias="consecutiveFailures")
    time_anomaly_count: int = Field(default=0, ge=0, alias="timeAnomalyCount")
    metrics: dict[str, float] = Field(default_factory=dict)


class RuntimeProfile(BaseModel):
    """承载实体：运行在某个 Node 上、可被调度的后端或服务。

    这是候选过滤与绑定的主对象。``capabilities`` 是自由字符串能力标签
    （如 ``fs.write``、``shell.exec``、``exec.coding``、``search``），
    语义由能力目录与注册方约定；模型能力统一走 ModelEndpoint。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    runtime_id: StrictStr = Field(alias="runtimeId", min_length=1, description="Runtime 唯一标识。")
    kind: RuntimeKind = Field(default=RuntimeKind.EXECUTION_BACKEND)
    display_name: StrictStr = Field(default="", alias="displayName")
    node_id: StrictStr = Field(alias="nodeId", min_length=1, description="承载该 Runtime 的 Node。")
    placement: Placement = Field(default=Placement.DEVICE, description="从宿主 Node 继承的放置位置（冗余存储，注册时校验一致）。")
    capabilities: list[StrictStr] = Field(min_length=1, description="该 Runtime 暴露的执行/工具能力。")
    trust: TrustLevel = Field(default=TrustLevel.HOST_TRUSTED, description="执行信任等级，不得高于宿主 Node 的信任。")
    endpoint: ResourceEndpoint | None = None
    capacity: int = Field(default=1, ge=1, description="可并发承接的最大工作数。")
    domains: list[StrictStr] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    location: StrictStr | None = None
    data_zone: StrictStr | None = Field(default=None, alias="dataZone")
    owner_scope: StrictStr | None = Field(default=None, alias="ownerScope")
    cost_metadata: dict[str, float] = Field(default_factory=dict, alias="costMetadata")
    model_ids: list[StrictStr] = Field(default_factory=list, alias="modelIds", description="MODEL_SERVER 直接服务的模型标识。")
    enabled: bool = Field(default=True, description="是否可接受新调度。")
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)


class RuntimeSnapshot(BaseModel):
    """Runtime 某一时刻的可用性和负载观测值。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    runtime_id: StrictStr = Field(alias="runtimeId", min_length=1)
    observation_sequence: int = Field(default=0, ge=0, alias="observationSequence")
    observed_at: datetime = Field(default_factory=_utc_now, alias="observedAt")
    available_slots: int = Field(ge=0, alias="availableSlots")
    utilization: float = Field(ge=0.0, le=1.0)
    health_status: HealthStatus = Field(default=HealthStatus.UNKNOWN, alias="healthStatus")
    reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    latency_ms: float | None = Field(default=None, ge=0.0, alias="latencyMs")
    metrics: dict[str, float] = Field(default_factory=dict)


class ModelEndpointProfile(BaseModel):
    """模型端点：一条可绑定的模型推理路由。

    端点与执行后端相互独立注册；一个执行后端可以使用不同模型端点，
    模型端点也可以被多个执行后端复用。宿主 ``runtime_id`` 可为空，
    表示由应用层模型注册表提供的抽象端点（如云 API 直连）。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    endpoint_id: StrictStr = Field(alias="endpointId", min_length=1)
    runtime_id: StrictStr | None = Field(default=None, alias="runtimeId", description="承载该端点的 MODEL_SERVER。")
    provider: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)
    model_version: StrictStr | None = Field(default=None, alias="modelVersion", description="供应商模型版本号。")
    placement: Placement = Field(default=Placement.CLOUD)
    tier: StrictStr | None = Field(default=None, description="语义档位标签（如 frontier / lightweight），只作先验不作约束。")
    context_window_tokens: int | None = Field(default=None, alias="contextWindowTokens", ge=1)
    max_output_tokens: int | None = Field(default=None, alias="maxOutputTokens", ge=1)
    features: ModelFeatureSet = Field(default_factory=ModelFeatureSet)
    cost_metadata: dict[str, float] = Field(default_factory=dict, alias="costMetadata")
    labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)


class ModelDemand(BaseModel):
    """任务对模型能力的声明性需求；与执行能力需求相互独立。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    required_features: list[StrictStr] = Field(default_factory=list, alias="requiredFeatures", description="必需特性，如 json_schema、tools、thinking。")
    min_context_tokens: int = Field(default=0, alias="minContextTokens", ge=0)
    preferred_model_ids: list[StrictStr] = Field(default_factory=list, alias="preferredModelIds", description="软偏好；绝不构成硬白名单。")
    allowed_endpoint_ids: list[StrictStr] = Field(default_factory=list, alias="allowedEndpointIds")
    excluded_endpoint_ids: list[StrictStr] = Field(default_factory=list, alias="excludedEndpointIds")


class ExecutionRequirement(BaseModel):
    """冻结的 Run/Step 执行需求：只描述"需要什么"，不指定"用谁"。

    Planner/Coordinator 不得在此固化具体资源；策略性白名单
    （allowed/excluded）只能来自资源策略、失败隔离或运维 pin。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    required_capabilities: list[StrictStr] = Field(alias="requiredCapabilities", min_length=1)
    runtime_kinds: list[RuntimeKind] = Field(default_factory=list, alias="runtimeKinds")
    allowed_placements: list[Placement] = Field(default_factory=list, alias="allowedPlacements")
    min_trust: TrustLevel | None = Field(default=None, alias="minTrust")
    allowed_runtime_ids: list[RuntimeResourceId] = Field(default_factory=list, alias="allowedRuntimeIds")
    excluded_runtime_ids: list[RuntimeResourceId] = Field(default_factory=list, alias="excludedRuntimeIds")
    model: ModelDemand | None = None
    domain: StrictStr | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    data_zone: StrictStr | None = Field(default=None, alias="dataZone")
    owner_scope: StrictStr | None = Field(default=None, alias="ownerScope")
    max_cost: float | None = Field(default=None, alias="maxCost", ge=0.0)
    max_latency_ms: float | None = Field(default=None, alias="maxLatencyMs", ge=0.0)
    allow_remote_execution: bool = Field(default=True, alias="allowRemoteExecution")
    min_cpu_cores: float | None = Field(default=None, alias="minCpuCores", ge=0.0)
    min_memory_bytes: int | None = Field(default=None, alias="minMemoryBytes", ge=0)
    required_gpu_type: StrictStr | None = Field(default=None, alias="requiredGpuType")
    min_gpu_memory_bytes: int | None = Field(default=None, alias="minGpuMemoryBytes", ge=0)
    required_node_labels: dict[str, str] = Field(default_factory=dict, alias="requiredNodeLabels")
    required_data_region: StrictStr | None = Field(default=None, alias="requiredDataRegion")
    allowed_owner_scopes: list[StrictStr] = Field(default_factory=list, alias="allowedOwnerScopes")
    preferences: dict[str, Any] = Field(default_factory=dict, description="非权威评分偏好（preferredRuntimeId 等）。")
    routing_hints: dict[str, Any] = Field(default_factory=dict, alias="routingHints", description="上游语义路由先验（如 Laya）；只影响评分，绝无资格裁决权。")
    policy_metadata: dict[str, Any] = Field(default_factory=dict, alias="policyMetadata")


class ModelEndpointBinding(BaseModel):
    """一次执行尝试冻结的模型端点路由。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    endpoint_id: StrictStr | None = Field(default=None, alias="endpointId")
    provider: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)
    version: StrictStr | None = None


class ExecutionBinding(BaseModel):
    """一次不可变执行尝试的绑定结果：绑到哪个 Runtime、哪个模型端点。

    ``resource_id`` 是被绑定 Runtime 的标识（历史键名，持久化投影兼容）。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    binding_id: StrictStr = Field(alias="bindingId", min_length=1)
    run_id: StrictStr = Field(alias="runId", min_length=1)
    step_id: StrictStr = Field(alias="stepId", min_length=1)
    attempt_id: StrictStr = Field(alias="attemptId", min_length=1)
    resource_id: RuntimeResourceId = Field(alias="resourceId", min_length=1, description="被绑定的 Runtime 标识。")
    runtime_kind: RuntimeKind = Field(alias="runtimeKind")
    node_id: StrictStr | None = Field(default=None, alias="nodeId")
    placement: Placement = Field(default=Placement.DEVICE)
    trust: TrustLevel = Field(default=TrustLevel.HOST_TRUSTED)
    model_binding: ModelEndpointBinding | None = Field(default=None, alias="modelBinding")
    snapshot_version: int = Field(alias="snapshotVersion", ge=1)
    lease_id: StrictStr | None = Field(default=None, alias="leaseId")
    lease_version: int | None = Field(default=None, alias="leaseVersion", ge=1)
    bound_at: datetime = Field(default_factory=_utc_now, alias="boundAt")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceLease(BaseModel):
    """调度器授予某 Runtime 的一段有界使用权。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    lease_id: StrictStr = Field(alias="leaseId", min_length=1)
    resource_id: StrictStr = Field(alias="resourceId", min_length=1, description="被租用的 Runtime 标识。")
    owner_id: StrictStr | None = Field(default=None, alias="ownerId")
    run_id: StrictStr | None = Field(default=None, alias="runId")
    step_id: StrictStr | None = Field(default=None, alias="stepId")
    attempt_id: StrictStr | None = Field(default=None, alias="attemptId")
    slot_count: int = Field(default=1, alias="slotCount", ge=1)
    version: int = Field(default=1, ge=1)
    status: Literal["active", "expiring", "released", "expired"] = "active"
    created_at: datetime = Field(default_factory=_utc_now, alias="createdAt")
    expires_at: datetime = Field(alias="expiresAt")

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("lease timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def expiry_follows_creation(self) -> "ResourceLease":
        if self.expires_at <= self.created_at:
            raise ValueError("expiresAt must be later than createdAt")
        return self


__all__ = [
    "ComputeCapacity",
    "ExecutionBinding",
    "ExecutionRequirement",
    "HealthStatus",
    "ModelDemand",
    "ModelEndpointBinding",
    "ModelEndpointProfile",
    "NodeHealthStatus",
    "RemoteExecutionPolicy",
    "NodeProfile",
    "NodeSnapshot",
    "Placement",
    "ResourceEndpoint",
    "ResourceLease",
    "RuntimeKind",
    "RuntimeProfile",
    "RuntimeSnapshot",
    "TrustLevel",
]

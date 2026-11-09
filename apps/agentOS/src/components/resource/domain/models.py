"""资源部件内部使用的只读投影模型。

这些不可变数据类把合同对象、持久化版本和健康/候选计算结果拆开表示，防止
存储实现细节泄漏到跨部件契约，也让调度查询能携带完整的判定依据。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from contracts.resource import (
    HealthStatus,
    ModelEndpointProfile,
    NodeHealthStatus,
    NodeSnapshot,
    RuntimeProfile,
    RuntimeSnapshot,
)


@dataclass(frozen=True)
class VersionedRuntimeSnapshot:
    """附带单调递增版本号的 Runtime 快照。

    合同层的 ``RuntimeSnapshot`` 描述一次观测值，而版本属于本地存储语义。
    将两者分开可避免把持久化实现细节泄漏到跨部件合同中。
    """

    snapshot: RuntimeSnapshot
    version: int


@dataclass(frozen=True)
class RuntimeHealth:
    """由心跳和执行观测推导出的 Runtime 健康投影。"""

    resource_id: str
    healthy: bool
    reliability: float
    latency_ms: float | None
    last_heartbeat: datetime | None


@dataclass(frozen=True)
class ResourceHealthState:
    """健康存储中的单资源状态，version 表示本地写入顺序。"""

    resource_id: str
    reliability: float
    latency_ms: float | None
    last_heartbeat: datetime | None
    forced_health: bool | None
    updated_at: datetime
    version: int


@dataclass(frozen=True)
class RuntimeCandidate:
    """一个通过资格检查的 Runtime 候选及其观测依据。"""

    profile: RuntimeProfile
    snapshot: VersionedRuntimeSnapshot
    health: RuntimeHealth
    score: float


@dataclass(frozen=True)
class ModelEndpointCandidate:
    """一个通过资格检查的模型端点候选。"""

    endpoint: ModelEndpointProfile
    score: float


@dataclass(frozen=True)
class VersionedNodeSnapshot:
    """附带单调递增版本号的节点快照。"""

    snapshot: NodeSnapshot
    version: int


@dataclass(frozen=True)
class NodeHealth:
    """节点健康投影：分级状态 + 最后心跳 + 连续失败次数。"""

    node_id: str
    status: NodeHealthStatus
    last_heartbeat: datetime | None
    consecutive_failures: int


# 保留导入占位：合同枚举供下游模块再导出，避免兼容路径提前失效。
_ = (HealthStatus,)

# TODO(model-cleanup): 下游完成迁移后移除 HealthStatus 的兼容导出占位。

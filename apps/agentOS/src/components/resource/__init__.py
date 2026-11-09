"""资源部件的公开入口：分层资源平面（Node / Runtime / ModelEndpoint）。

本模块只负责聚合稳定的公共 API，调用方无需依赖具体的内存或 SQLite
存储实现。按层级导出 Node、Runtime 和模型端点相关能力，避免上层把
内部持久化、健康监控和鉴权细节耦合在一起。
"""

from .health import ResourceHealthMonitor
from .health_store import (
    InMemoryResourceHealthStore,
    ResourceHealthState,
    ResourceHealthStore,
    SQLiteResourceHealthStore,
)
from .auth import (
    NodeRequestAuthenticator,
    ResourceRequestAuthenticator,
    ResourceRequestExpired,
    ResourceRequestInvalid,
    ResourceRequestNotFound,
    ResourceRequestReplay,
    build_resource_signature,
)
from .crypto import ResourceSecretBox
from .embedded_runtime import (
    EMBEDDED_AGENTS_BASE_CAPABILITY,
    EMBEDDED_AGENTS_RUNTIME_ID,
    register_embedded_agents_runtime,
)
from .local_runtime import (
    DEFAULT_LOCAL_RUNTIME_NODE_ID,
    LOCAL_RUNTIME_RESOURCE_CAPABILITIES,
    LOCAL_RUNTIME_SHELL_CAPABILITY,
    LocalRuntimeHealthProjector,
    LocalRuntimeResourceConfig,
    RegisteredLocalRuntimeResource,
    ensure_local_runtime_resource,
    local_runtime_node_id,
    local_runtime_profile,
)
from .models import (
    ModelEndpointCandidate,
    NodeHealth,
    RuntimeCandidate,
    RuntimeHealth,
    VersionedNodeSnapshot,
    VersionedRuntimeSnapshot,
)
from .node_health import NodeHealthMonitor, infer_load_status
from .node_store import InMemoryNodeStore, NodeStore, SQLiteNodeStore
from .service import (
    compute_registration_id,
    IssuedNodeCredential,
    IssuedResourceCredential,
    ResourcePlane,
)
from .errors import (
    ResourceConfigMismatchError,
    ResourceDatabaseLockedError,
    ResourceObservationPersistenceError,
    ResourceObservationTimeInvalidError,
    ResourceVersionConflictError,
)
from .store import (
    InMemoryResourceStore,
    ResourceCredentialRecord,
    RuntimeStore,
    SQLiteResourceStore,
    StaleResourceObservation,
    VersionConflict,
)

__all__ = [
    # TODO(api-evolution): 新增公共符号时同步评估版本兼容性与弃用策略。
    "DEFAULT_LOCAL_RUNTIME_NODE_ID",
    "EMBEDDED_AGENTS_BASE_CAPABILITY",
    "EMBEDDED_AGENTS_RUNTIME_ID",
    "InMemoryNodeStore",
    "InMemoryResourceStore",
    "InMemoryResourceHealthStore",
    "IssuedNodeCredential",
    "IssuedResourceCredential",
    "LOCAL_RUNTIME_RESOURCE_CAPABILITIES",
    "LOCAL_RUNTIME_SHELL_CAPABILITY",
    "LocalRuntimeHealthProjector",
    "LocalRuntimeResourceConfig",
    "ModelEndpointCandidate",
    "NodeHealth",
    "NodeHealthMonitor",
    "NodeRequestAuthenticator",
    "NodeStore",
    "RegisteredLocalRuntimeResource",
    "ResourceCredentialRecord",
    "ResourceConfigMismatchError",
    "ResourceDatabaseLockedError",
    "ResourceObservationPersistenceError",
    "ResourceObservationTimeInvalidError",
    "ResourceVersionConflictError",
    "RuntimeCandidate",
    "RuntimeHealth",
    "RuntimeStore",
    "ResourceHealthMonitor",
    "ResourceHealthState",
    "ResourceHealthStore",
    "ResourcePlane",
    "ResourceRequestAuthenticator",
    "ResourceRequestExpired",
    "ResourceRequestInvalid",
    "ResourceRequestNotFound",
    "ResourceRequestReplay",
    "ResourceSecretBox",
    "SQLiteNodeStore",
    "SQLiteResourceHealthStore",
    "SQLiteResourceStore",
    "StaleResourceObservation",
    "VersionConflict",
    "VersionedNodeSnapshot",
    "VersionedRuntimeSnapshot",
    "build_resource_signature",
    "compute_registration_id",
    "ensure_local_runtime_resource",
    "infer_load_status",
    "local_runtime_node_id",
    "local_runtime_profile",
    "register_embedded_agents_runtime",
]

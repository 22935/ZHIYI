"""资源平面：Node / Runtime / ModelEndpoint 的登记、观测与候选查询。

本服务是资源状态的唯一权威入口。它回答"系统现在拥有哪些真实可调用的
运行能力"，但不做调度决策——候选过滤、评分与租约授予由 ResourceBinder
完成。逻辑 Agent 角色不是资源，不在这里登记。

ResourcePlane 负责跨 Node、Runtime、模型端点、健康投影与凭据存储的业务
不变量；它不承担 HTTP、任务执行或数据库连接生命周期等基础设施职责。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import sqlite3
import time
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit
from functools import wraps
from ..domain.audit import ResourceAuditEvent
from ..ports.audit_store import ResourceAuditStore
from ..infrastructure.audit_store import InMemoryResourceAuditStore

from contracts.capability import ModelFeatureSet
from contracts.resource import (
    HealthStatus,
    ModelDemand,
    ModelEndpointProfile,
    NodeHealthStatus,
    NodeProfile,
    NodeSnapshot,
    Placement,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)

from ..domain.algorithms import health_score, is_runtime_available
from ..infrastructure.crypto.fernet_secret_box import ResourceSecretBox
from ..infrastructure.health_store import InMemoryResourceHealthStore
from ..domain.runtime_health import ResourceHealthMonitor
from ..domain.models import (
    ModelEndpointCandidate,
    NodeHealth,
    RuntimeCandidate,
    RuntimeHealth,
    VersionedNodeSnapshot,
    VersionedRuntimeSnapshot,
)
from ..domain.credentials import ResourceCredentialRecord
from ..domain.node_health import NodeHealthMonitor, infer_load_status
from ..infrastructure.node_store import InMemoryNodeStore
from ..ports.node_store import NodeStore
from ..infrastructure.runtime_store import (
    InMemoryResourceStore,
    SQLiteResourceStore,
    StaleResourceObservation,
    VersionConflict,
)
from ..ports.runtime_store import RuntimeStore
from ..errors import (
    ResourceConfigMismatchError,
    ResourceDatabaseLockedError,
    ResourceObservationPersistenceError,
    ResourceObservationTimeInvalidError,
    ResourceVersionConflictError,
)


logger = logging.getLogger(__name__)
_MAX_OBSERVATION_WRITE_RETRIES = 3
_MAX_OBSERVATION_DELAY = timedelta(seconds=60)
_MAX_OBSERVATION_CLOCK_SKEW = timedelta(seconds=30)
_SUSPICIOUS_TIME_ANOMALY_LIMIT = 3


@dataclass(frozen=True)
class IssuedResourceCredential:
    """注册响应中一次性返回的 Runtime 密钥。"""

    resource_id: str
    credential_id: str
    owner_scope: str
    secret: str
    created: bool = True


@dataclass(frozen=True)
class IssuedNodeCredential:
    """远程节点登记响应中一次性返回的密钥。"""

    node_id: str
    credential_id: str
    owner_scope: str
    secret: str
    created: bool = True


def compute_registration_id(resource_id: str, owner_scope: str, profile: NodeProfile | RuntimeProfile) -> str:
    """为静态远程登记生成稳定的幂等键。

    忽略会随写入变化的 ``version`` 与登记键本身，使同一配置重试时保持
    标识不变，而配置实质变化时获得新的指纹。
    """
    import json

    payload = profile.model_dump(by_alias=True, mode="json")
    payload.pop("version", None)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("registrationId", None)
    # 规范 JSON 序列化确保字典插入顺序不会改变登记指纹。
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"{owner_scope}:{resource_id}:{fingerprint}"


def _audit_observation(method):
    """在应用边界统一记录被拒观测和 CAS 冲突，不记录输入正文。"""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        resource_id = args[0] if args else kwargs.get("runtime_id", kwargs.get("node_id"))
        try:
            return method(self, *args, **kwargs)
        except (StaleResourceObservation, ResourceObservationTimeInvalidError) as error:
            self.record_audit_event("observation_rejected", resource_id, reason=type(error).__name__)
            raise
        except (VersionConflict, ResourceVersionConflictError) as error:
            self.record_audit_event("snapshot_conflict", resource_id, reason=type(error).__name__)
            raise
    return wrapped


class ResourcePlane:
    """以分层模型暴露可调度资源，并向 Binder 提供候选查询。"""

    def __init__(
        self,
        store: RuntimeStore | None = None,
        node_store: NodeStore | None = None,
        health_monitor: ResourceHealthMonitor | None = None,
        node_health_monitor: NodeHealthMonitor | None = None,
        *,
        heartbeat_timeout: timedelta = timedelta(seconds=60),
        credential_key: str | bytes | None = None,
        audit_store: ResourceAuditStore | None = None,
    ) -> None:
        self.audit_store = audit_store if audit_store is not None else InMemoryResourceAuditStore()
        self.store = store or InMemoryResourceStore()
        self.node_store = node_store or InMemoryNodeStore()
        self.health_monitor = health_monitor or ResourceHealthMonitor(
            heartbeat_timeout=heartbeat_timeout,
            store=InMemoryResourceHealthStore(),
        )
        self.node_health_monitor = node_health_monitor or NodeHealthMonitor()
        self.secret_box = ResourceSecretBox(credential_key)
        # SQLite 快照是跨进程事实源；hydrate 仅加速本地读取，调度器仍会调用 get_node_health。
        for profile in self.node_store.list_profiles():
            snapshot = self.node_store.get_snapshot(profile.node_id).snapshot
            self.node_health_monitor.hydrate(
                profile.node_id,
                last_heartbeat=snapshot.last_heartbeat,
                status=snapshot.health_status,
                consecutive_failures=snapshot.consecutive_failures,
            )

    # ------------------------------------------------------------------
    # Node 层：部署实体
    # ------------------------------------------------------------------

    def register_node(self, profile: NodeProfile, snapshot: NodeSnapshot) -> VersionedNodeSnapshot:
        """登记节点；重复的完全一致登记幂等返回。"""
        if profile.node_id != snapshot.node_id:
            raise ValueError("node profile and snapshot nodeId must match")
        try:
            existing = self.node_store.get_profile(profile.node_id)
        except KeyError:
            result = self.node_store.register(profile, snapshot)
            self.record_audit_event("node_registered", profile.node_id)
            return result
        # 幂等重试只能复用完全相同的静态画像，防止调用方无意覆盖节点身份。
        if existing != profile:
            raise ValueError(f"node conflicts with existing profile: {profile.node_id}")
        return self.node_store.get_snapshot(profile.node_id)

    def ensure_node(
        self,
        node_id: str,
        *,
        placement: Placement = Placement.DEVICE,
        display_name: str = "",
        trust: TrustLevel = TrustLevel.HOST_TRUSTED,
        **profile_fields,
    ) -> NodeProfile:
        """幂等登记（或读取）节点；进程内引导路径专用。

        只允许更新引导自有的节点；远程登记（带凭据、无引导标记）的节点
        与引导声明冲突时必须显式失败，防止进程内代码静默改写外部身份。
        """
        metadata = dict(profile_fields.pop("metadata", None) or {})
        metadata.setdefault("managedBy", "bootstrap")
        profile = NodeProfile(
            nodeId=node_id,
            placement=placement,
            displayName=display_name,
            trust=trust,
            metadata=metadata,
            **profile_fields,
        )
        try:
            existing = self.node_store.get_profile(node_id)
        except KeyError:
            snapshot = NodeSnapshot(
                nodeId=node_id,
                healthStatus=NodeHealthStatus.ONLINE,
                lastHeartbeat=datetime.now(timezone.utc),
            )
            self.node_store.register(profile, snapshot)
            self.record_audit_event("node_registered", node_id)
            self.node_health_monitor.report(node_id, success=True)
            return profile
        if existing == profile:
            return existing
        if existing.metadata.get("managedBy") != "bootstrap":
            # Older local bootstrap records predate the ownership marker. Adopt
            # only an otherwise identical device profile without credentials.
            legacy_local = (
                existing.placement is Placement.DEVICE
                and existing.trust is TrustLevel.HOST_TRUSTED
                and existing.owner_scope is None
                and not existing.metadata
                and metadata == {"managedBy": "bootstrap"}
                and existing.model_copy(update={"metadata": metadata}) == profile
            )
            if legacy_local:
                try:
                    self.node_store.get_credential(node_id)
                except KeyError:
                    return self.node_store.update_profile(profile)
            raise ValueError(f"node conflicts with a non-bootstrap registration: {node_id}")
        return self.node_store.update_profile(profile)

    def register_remote_node(
        self, profile: NodeProfile, snapshot: NodeSnapshot, *, registration_id: str | None = None
    ) -> IssuedNodeCredential:
        """登记远程节点并生成只能在注册响应中读取一次的凭据。"""
        if profile.placement is Placement.DEVICE and profile.trust is TrustLevel.HOST_TRUSTED:
            raise ValueError("remote device node cannot claim host_trusted trust")
        if not profile.owner_scope:
            raise ValueError("remote node ownerScope is required")
        registration_id = registration_id or compute_registration_id(
            profile.node_id, profile.owner_scope, profile
        )
        metadata = dict(profile.metadata)
        metadata["registrationId"] = registration_id
        profile = profile.model_copy(update={"metadata": metadata})
        try:
            existing = self.node_store.get_profile(profile.node_id)
        except KeyError:
            existing = None
        if existing is not None:
            if existing.metadata.get("registrationId") != registration_id or existing != profile:
                raise ResourceConfigMismatchError(
                    f"node registration conflicts with existing profile: {profile.node_id}"
                )
            credential = self.node_store.get_credential(profile.node_id)
            return IssuedNodeCredential(
                node_id=profile.node_id, credential_id=credential.credential_id,
                owner_scope=credential.owner_scope, secret="", created=False,
            )
        secret = secrets.token_urlsafe(32)
        record = ResourceCredentialRecord(
            resource_id=profile.node_id,
            credential_id=f"nc_{uuid.uuid4().hex}",
            owner_scope=profile.owner_scope,
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now(timezone.utc),
        )
        self.node_store.register_remote(profile, snapshot, record)
        self.record_audit_event("node_registered", profile.node_id)
        return IssuedNodeCredential(
            node_id=profile.node_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def node(self, node_id: str) -> NodeProfile:
        return self.node_store.get_profile(node_id)

    def nodes(self) -> list[NodeProfile]:
        return self.node_store.list_profiles()

    def node_snapshot(self, node_id: str) -> VersionedNodeSnapshot:
        return self.node_store.get_snapshot(node_id)

    def set_node_enabled(self, node_id: str, *, enabled: bool) -> NodeProfile:
        profile = self.node_store.get_profile(node_id)
        return self.node_store.update_profile(
            profile.model_copy(update={"enabled": enabled})
        )

    def node_health(self, node_id: str, *, now: datetime | None = None) -> NodeHealth:
        snapshot = self.node_store.get_snapshot(node_id).snapshot
        # 持久化快照是跨 worker 的事实源；监控器只在本地状态更新时提供刷新值。
        live = self.node_health_monitor.health(node_id, now=now)
        if (
            live.last_heartbeat is not None
            and (snapshot.last_heartbeat is None or live.last_heartbeat >= snapshot.last_heartbeat)
        ):
            base_status = live.status
            heartbeat = live.last_heartbeat
            failures = live.consecutive_failures
        else:
            base_status = snapshot.health_status
            heartbeat = snapshot.last_heartbeat
            failures = snapshot.consecutive_failures
        if heartbeat is None:
            return NodeHealth(
                node_id=node_id, status=NodeHealthStatus.UNKNOWN,
                last_heartbeat=None, consecutive_failures=failures,
            )
        current = now if now is not None else datetime.now(timezone.utc)
        age = current.astimezone(timezone.utc) - heartbeat.astimezone(timezone.utc)
        if age > self.node_health_monitor.offline_threshold:
            status = NodeHealthStatus.OFFLINE
        elif age > self.node_health_monitor.stale_threshold:
            status = NodeHealthStatus.STALE
        else:
            status = base_status
        return NodeHealth(
            node_id=node_id,
            status=status,
            last_heartbeat=heartbeat,
            consecutive_failures=failures,
        )

    def get_node_health(self, node_id: str, *, now: datetime | None = None) -> NodeHealth:
        """Return the durable Node health projection used by schedulers.

        The method deliberately owns the memory-monitor plus persisted-snapshot
        fallback, so callers never mistake one process' local cache for global
        resource truth.
        """
        return self.node_health(node_id, now=now)

    def _record_node_time_anomaly(self, node_id: str) -> None:
        """Persist clock anomalies so suspicious state survives worker restarts."""
        current = self.node_store.get_snapshot(node_id)
        count = current.snapshot.time_anomaly_count + 1
        status = (
            NodeHealthStatus.SUSPICIOUS
            if count >= _SUSPICIOUS_TIME_ANOMALY_LIMIT
            else current.snapshot.health_status
        )
        self.node_store.update_snapshot(
            current.snapshot.model_copy(update={
                "time_anomaly_count": count,
                "health_status": status,
            }),
            expected_version=current.version,
        )

    @_audit_observation
    def observe_node(
        self,
        node_id: str,
        *,
        observation_sequence: int,
        cpu_utilization: float = 0.0,
        gpu_utilization: float = 0.0,
        available_memory_mb: int = 0,
        queued_tasks: int = 0,
        latency_ms: float | None = None,
        observed_at: datetime | None = None,
        success: bool = True,
    ) -> NodeHealth:
        """接收一次已签名的远程节点观测并持久化快照与健康。"""
        self.node_store.get_profile(node_id)
        current = self.node_store.get_snapshot(node_id)
        if observation_sequence <= current.snapshot.observation_sequence:
            raise StaleResourceObservation(
                f"stale observation for {node_id}: "
                f"received {observation_sequence}, "
                f"current {current.snapshot.observation_sequence}"
            )
        timestamp = observed_at if observed_at is not None else datetime.now(timezone.utc)
        current_time = datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ResourceObservationTimeInvalidError("node observation timestamp must be timezone-aware")
        timestamp = timestamp.astimezone(timezone.utc)
        if timestamp > current_time + _MAX_OBSERVATION_CLOCK_SKEW:
            self._record_node_time_anomaly(node_id)
            raise ResourceObservationTimeInvalidError(
                f"node observation timestamp is too far in the future: {timestamp.isoformat()}"
            )
        stale = timestamp < current_time - _MAX_OBSERVATION_DELAY
        if timestamp < current.snapshot.observed_at - _MAX_OBSERVATION_CLOCK_SKEW:
            self._record_node_time_anomaly(node_id)
            logger.warning(
                "node observation time regressed",
                extra={"node_id": node_id, "sequence": observation_sequence},
            )
        load = max(cpu_utilization, gpu_utilization)
        consecutive_failures = 0 if success else current.snapshot.consecutive_failures + 1
        snapshot = current.snapshot.model_copy(update={
            "observation_sequence": observation_sequence,
            "observed_at": timestamp,
            "cpu_utilization": cpu_utilization,
            "gpu_utilization": gpu_utilization,
            "available_memory_mb": available_memory_mb,
            "queued_tasks": queued_tasks,
            "latency_ms": latency_ms,
            "health_status": NodeHealthStatus.STALE if stale else infer_load_status(queued_tasks, load),
            "last_heartbeat": timestamp,
            "consecutive_failures": consecutive_failures,
            "time_anomaly_count": 0,
        })
        self.node_store.update_snapshot(snapshot, expected_version=current.version)
        return self.node_health_monitor.report(
            node_id,
            observed_at=timestamp,
            queued_tasks=queued_tasks,
            utilization=load,
            success=success,
            status=NodeHealthStatus.STALE if stale else None,
        )

    @_audit_observation
    def heartbeat_node(
        self,
        node_id: str,
        *,
        cpu_utilization: float = 0.0,
        gpu_utilization: float = 0.0,
        available_memory_mb: int = 0,
        queued_tasks: int = 0,
        latency_ms: float | None = None,
        success: bool = True,
        observed_at: datetime | None = None,
    ) -> NodeHealth:
        """进程内节点心跳：刷新快照动态字段与健康投影。"""
        timestamp = observed_at if observed_at is not None else datetime.now(timezone.utc)
        current = self.node_store.get_snapshot(node_id)
        load = max(cpu_utilization, gpu_utilization)
        consecutive_failures = 0 if success else current.snapshot.consecutive_failures + 1
        snapshot = current.snapshot.model_copy(update={
            "cpu_utilization": cpu_utilization,
            "gpu_utilization": gpu_utilization,
            "available_memory_mb": available_memory_mb,
            "queued_tasks": queued_tasks,
            "latency_ms": latency_ms,
            "health_status": infer_load_status(queued_tasks, load),
            "last_heartbeat": timestamp,
            "observed_at": timestamp,
            "observation_sequence": current.snapshot.observation_sequence + 1,
            "consecutive_failures": consecutive_failures,
        })
        self.node_store.update_snapshot(snapshot, expected_version=current.version)
        return self.node_health_monitor.report(
            node_id,
            observed_at=timestamp,
            queued_tasks=queued_tasks,
            utilization=load,
            success=success,
        )

    def node_credential(self, node_id: str) -> ResourceCredentialRecord:
        self.node_store.get_profile(node_id)
        return self.node_store.get_credential(node_id)

    def node_credential_hmac_key(self, node_id: str, credential_id: str) -> bytes:
        record = self.node_credential(node_id)
        if record.credential_id != credential_id:
            raise ValueError("node credential is invalid")
        secret = self.secret_box.decrypt(record.encrypted_secret)
        return hashlib.sha256(secret.encode("utf-8")).digest()

    def verify_node_credential(
        self, node_id: str, credential_id: str, secret: str
    ) -> ResourceCredentialRecord:
        try:
            profile = self.node_store.get_profile(node_id)
            record = self.node_store.get_credential(node_id)
        except KeyError as error:
            raise ValueError("node credential not found") from error
        expected_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if (
            record.credential_id != credential_id
            or record.owner_scope != profile.owner_scope
            or not hmac.compare_digest(record.secret_digest, expected_digest)
        ):
            raise ValueError("node credential is invalid")
        return record

    def consume_node_nonce(
        self,
        node_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> bool:
        self.node_store.get_profile(node_id)
        current = now or datetime.now(timezone.utc)
        return self.node_store.consume_nonce(node_id, nonce, expires_at, now=current)

    # ------------------------------------------------------------------
    # Runtime 层：承载实体（执行后端 / 模型服务 / 工具服务）
    # ------------------------------------------------------------------

    def register_runtime(
        self, profile: RuntimeProfile, snapshot: RuntimeSnapshot | None = None
    ) -> VersionedRuntimeSnapshot:
        """登记或刷新进程内引导的 Runtime；带凭据的远程登记不允许走此路径。

        引导路径（本进程拥有该 Runtime 的真实存活信号）允许更新能力集等
        画像字段；capacity 变化会按已占用量重新缩放松照槽位。
        """
        self._validate_runtime_host(profile)
        initial = snapshot or RuntimeSnapshot(
            runtimeId=profile.runtime_id,
            availableSlots=profile.capacity,
            utilization=0.0,
            healthStatus=HealthStatus.UNKNOWN,
        )
        if profile.runtime_id != initial.runtime_id:
            raise ValueError("profile and snapshot runtime_id must match")
        try:
            existing = self.store.get_profile(profile.runtime_id)
        except KeyError:
            versioned = self.store.register(profile, initial)
            self.record_audit_event("runtime_registered", profile.runtime_id)
            self._sync_runtime_model_endpoints(profile)
            return versioned
        if existing == profile:
            self._sync_runtime_model_endpoints(profile)
            return self.store.get_snapshot(profile.runtime_id)
        if not self._is_bootstrap_owned(existing):
            raise ValueError(
                f"runtime conflicts with credential-protected registration: {profile.runtime_id}"
            )
        if profile.capacity != existing.capacity:
            versioned = self.store.update_capacity(
                profile.runtime_id, profile.capacity, expected_capacity=existing.capacity
            )
            if existing != profile.model_copy(update={"capacity": profile.capacity}):
                self.store.update_profile(profile)
            self._sync_runtime_model_endpoints(profile)
            return versioned
        self.store.update_profile(profile)
        self._sync_runtime_model_endpoints(profile)
        return self.store.get_snapshot(profile.runtime_id)

    def register_remote_runtime(
        self,
        profile: RuntimeProfile,
        snapshot: RuntimeSnapshot,
        *,
        credential_id: str | None = None,
        secret: str | None = None,
        registration_id: str | None = None,
    ) -> IssuedResourceCredential:
        """登记远程 Runtime 并生成只能在注册响应中读取一次的凭据。"""
        if profile.endpoint is None or profile.endpoint.protocol == "local":
            raise ValueError("remote runtime requires a callable execution endpoint")
        supported_adapter = profile.adapter in {None, "agentos_http", "http", "https"}
        if profile.kind is RuntimeKind.MODEL_SERVER:
            supported_adapter = supported_adapter or profile.adapter == "agentos_model_http"
        if profile.endpoint.protocol not in {"http", "https"} or not supported_adapter:
            raise ValueError("remote runtime requires a supported AgentOS HTTP(S) adapter")
        parsed_endpoint = urlsplit(profile.endpoint.address)
        if parsed_endpoint.scheme.lower() != profile.endpoint.protocol or not parsed_endpoint.netloc:
            raise ValueError("remote runtime endpoint scheme must match its protocol")
        if not profile.owner_scope:
            raise ValueError("remote runtime ownerScope is required")
        if profile.kind is RuntimeKind.MODEL_SERVER and (
            not (profile.provider or "").strip()
            or not profile.model_ids
            or any(not model_id.strip() for model_id in profile.model_ids)
        ):
            raise ValueError("remote model server requires a provider and at least one modelId")
        self._validate_runtime_host(profile)
        host = self.node_store.get_profile(profile.node_id)
        if host.owner_scope and host.owner_scope != profile.owner_scope:
            raise ValueError("remote runtime ownerScope must match its host node")
        registration_id = registration_id or compute_registration_id(
            profile.runtime_id, profile.owner_scope, profile
        )
        metadata = dict(profile.metadata)
        metadata["registrationId"] = registration_id
        profile = profile.model_copy(update={"metadata": metadata})
        try:
            existing = self.store.get_profile(profile.runtime_id)
        except KeyError:
            existing = None
        if existing is not None:
            if existing.metadata.get("registrationId") != registration_id or existing != profile:
                raise ResourceConfigMismatchError(
                    f"runtime registration conflicts with existing profile: {profile.runtime_id}"
                )
            credential = self.store.get_credential(profile.runtime_id)
            self._sync_runtime_model_endpoints(profile)
            return IssuedResourceCredential(
                resource_id=profile.runtime_id, credential_id=credential.credential_id,
                owner_scope=credential.owner_scope, secret="", created=False,
            )
        if (credential_id is None) != (secret is None):
            raise ValueError("credential_id and secret must be supplied together")
        credential_id = credential_id.strip() if credential_id is not None else f"rc_{uuid.uuid4().hex}"
        secret = secret.strip() if secret is not None else secrets.token_urlsafe(32)
        if not credential_id or not secret:
            raise ValueError("remote credential_id and secret must not be empty")
        record = ResourceCredentialRecord(
            resource_id=profile.runtime_id,
            credential_id=credential_id,
            owner_scope=profile.owner_scope,
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now(timezone.utc),
        )
        self.store.register_remote(profile, snapshot, record)
        self.record_audit_event("runtime_registered", profile.runtime_id)
        self._sync_runtime_model_endpoints(profile)
        return IssuedResourceCredential(
            resource_id=profile.runtime_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def _validate_runtime_host(self, profile: RuntimeProfile) -> None:
        node = self.node_store.get_profile(profile.node_id)
        if node.placement is not profile.placement:
            raise ValueError(
                f"runtime placement {profile.placement.value} must match host node "
                f"{node.node_id} placement {node.placement.value}"
            )
        if profile.trust.rank > node.trust.rank:
            raise ValueError(
                f"runtime trust {profile.trust.value} exceeds host node "
                f"{node.node_id} trust {node.trust.value}"
            )
        if not node.enabled:
            raise ValueError(f"host node is disabled: {node.node_id}")

    def _is_bootstrap_owned(self, existing: RuntimeProfile) -> bool:
        """引导路径可更新无凭据 Runtime，或显式标记为引导管理的 Runtime。

        远程 API 登记的 Runtime（有凭据且非引导标记）只能通过显式更新
        路径修改，防止进程内代码静默改写外部注册身份。
        """
        if existing.metadata.get("managedBy") == "bootstrap":
            return True
        return not self._has_runtime_credential(existing.runtime_id)

    def _has_runtime_credential(self, runtime_id: str) -> bool:
        try:
            self.store.get_credential(runtime_id)
        except KeyError:
            return False
        return True

    def runtime(self, runtime_id: str) -> RuntimeProfile:
        return self.store.get_profile(runtime_id)

    def runtimes(self) -> list[RuntimeProfile]:
        return self.store.list_profiles()

    def unregister_marketplace_runtime(self, runtime_id: str) -> None:
        """撤销仅由资源商店创建的 Runtime，防止误删用户手动登记资源。"""
        profile = self.store.get_profile(runtime_id)
        if profile.metadata.get("managedBy") != "marketplace":
            raise ValueError("only marketplace-managed runtimes can be unregistered")
        self.store.delete_runtime(runtime_id)

    def runtime_snapshot(self, runtime_id: str) -> VersionedRuntimeSnapshot:
        return self.store.get_snapshot(runtime_id)

    def set_runtime_enabled(self, runtime_id: str, *, enabled: bool) -> RuntimeProfile:
        profile = self.store.get_profile(runtime_id)
        updated = self.store.update_profile(profile.model_copy(update={"enabled": enabled}))
        for endpoint in self.store.list_model_endpoints():
            if endpoint.runtime_id == runtime_id and endpoint.enabled != enabled:
                self.store.upsert_model_endpoint(endpoint.model_copy(update={"enabled": enabled}))
        return updated

    def _sync_runtime_model_endpoints(self, profile: RuntimeProfile) -> None:
        """将模型服务的静态声明收敛到模型路由目录。

        本机与远程 Runtime 必须走同一投影逻辑。更新/降级 Runtime 时，清理
        仅由本方法创建且已不再声明的端点，避免旧模型继续被路由。
        """
        managed_endpoints = [
            endpoint for endpoint in self.store.list_model_endpoints()
            if endpoint.runtime_id == profile.runtime_id
            and endpoint.metadata.get("_resourcePlaneManagedBy") == "runtime-registration"
        ]
        if profile.kind is not RuntimeKind.MODEL_SERVER or not (profile.provider or "").strip():
            for endpoint in managed_endpoints:
                self.store.delete_model_endpoint(endpoint.endpoint_id)
            return
        endpoint_ids: set[str] = set()
        for raw_model_id in profile.model_ids:
            model_id = raw_model_id.strip()
            if not model_id:
                continue
            endpoint_id = f"model:{profile.runtime_id}:{model_id}"
            endpoint_ids.add(endpoint_id)
            endpoint = ModelEndpointProfile(
                endpointId=endpoint_id,
                runtimeId=profile.runtime_id,
                provider=profile.provider,
                sourceType=profile.source_type,
                adapter=profile.adapter,
                model=model_id,
                placement=profile.placement,
                ownerScope=profile.owner_scope,
                costMetadata=profile.cost_metadata,
                labels=profile.labels,
                enabled=profile.enabled,
                metadata={"_resourcePlaneManagedBy": "runtime-registration"},
            )
            self.store.upsert_model_endpoint(endpoint)
        for endpoint in managed_endpoints:
            if endpoint.endpoint_id not in endpoint_ids:
                self.store.delete_model_endpoint(endpoint.endpoint_id)

    def update_runtime_capacity(
        self, runtime_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedRuntimeSnapshot:
        return self.store.update_capacity(runtime_id, capacity, expected_capacity=expected_capacity)

    def heartbeat_runtime(
        self,
        runtime_id: str,
        *,
        received_at: datetime | None = None,
        source: Literal["local", "external"] = "local",
    ) -> RuntimeHealth:
        """记录 Runtime 存活信号；带端点的远程 Runtime 必须由外部上报。"""
        profile = self.store.get_profile(runtime_id)
        if profile.endpoint is not None and source != "external":
            raise ValueError("remote runtime heartbeat must come from an external heartbeat")
        return self.health_monitor.heartbeat(runtime_id, received_at=received_at)

    @_audit_observation
    def observe_execution(
        self,
        runtime_id: str,
        *,
        success: bool,
        latency_ms: float,
        observed_at: datetime | None = None,
    ) -> RuntimeHealth:
        """记录一次执行结果：健康 EMA 与快照时延/可靠性同步更新。

        执行结果是执行链路自己的真实信号，不要求远端层级；利用率与槽位
        仍归调度器记账，这里不做任何推算。
        """
        self.store.get_profile(runtime_id)
        health = self.health_monitor.observe(
            runtime_id, success=success, latency_ms=latency_ms, observed_at=observed_at
        )
        timestamp = observed_at or datetime.now(timezone.utc)
        last_error: Exception | None = None
        for attempt in range(_MAX_OBSERVATION_WRITE_RETRIES):
            current = self.store.get_snapshot(runtime_id)
            # model_copy(update=) 只认字段名，不认别名；别名键会被静默忽略。
            updated = current.snapshot.model_copy(update={
                "observed_at": timestamp,
                "observation_sequence": current.snapshot.observation_sequence + 1,
                "latency_ms": latency_ms,
                "reliability": health.reliability,
                "health_status": (
                    HealthStatus.ONLINE if success else current.snapshot.health_status
                ),
            })
            try:
                self.store.update_snapshot(updated, expected_version=current.version)
                return health
            except (StaleResourceObservation, VersionConflict) as error:
                raise ResourceVersionConflictError(
                    f"observation sequence conflict for {runtime_id}"
                ) from error
            except sqlite3.OperationalError as error:
                last_error = error
                if "locked" not in str(error).lower() or attempt == _MAX_OBSERVATION_WRITE_RETRIES - 1:
                    self.set_runtime_health(runtime_id, healthy=False)
                    raise ResourceDatabaseLockedError(
                        f"resource observation write failed for {runtime_id}"
                    ) from error
                time.sleep(0.01 * (2 ** attempt))
            except OSError as error:
                last_error = error
                if attempt == _MAX_OBSERVATION_WRITE_RETRIES - 1:
                    self.set_runtime_health(runtime_id, healthy=False)
                    raise ResourceObservationPersistenceError(
                        f"resource observation I/O failed for {runtime_id}"
                    ) from error
                time.sleep(0.01 * (2 ** attempt))
            except Exception as error:
                last_error = error
                break
        self.set_runtime_health(runtime_id, healthy=False)
        raise ResourceObservationPersistenceError(
            f"resource observation persistence failed for {runtime_id}"
        ) from last_error

    @_audit_observation
    def observe_remote_runtime(
        self,
        runtime_id: str,
        *,
        available_slots: int,
        utilization: float,
        latency_ms: float | None = None,
        observed_at: datetime | None = None,
        observation_sequence: int = 0,
    ) -> RuntimeHealth:
        """接收远程 Runtime 的一次完整观测，并同步快照与存活信号。"""
        profile = self.store.get_profile(runtime_id)
        if profile.endpoint is None:
            raise ValueError("remote observation requires an endpoint-attached runtime")
        current = self.store.get_snapshot(runtime_id)
        if observation_sequence <= current.snapshot.observation_sequence:
            raise StaleResourceObservation(
                f"stale observation for {runtime_id}: "
                f"received {observation_sequence}, "
                f"current {current.snapshot.observation_sequence}"
            )
        timestamp = observed_at or datetime.now(timezone.utc)
        current_time = datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ResourceObservationTimeInvalidError("remote observation timestamp must be timezone-aware")
        timestamp = timestamp.astimezone(timezone.utc)
        if timestamp > current_time + _MAX_OBSERVATION_CLOCK_SKEW:
            raise ResourceObservationTimeInvalidError(
                f"remote observation timestamp is too far in the future: {timestamp.isoformat()}"
            )
        stale = timestamp < current_time - _MAX_OBSERVATION_DELAY
        if timestamp < current.snapshot.observed_at - _MAX_OBSERVATION_CLOCK_SKEW:
            logger.warning(
                "remote resource observation time regressed",
                extra={"runtime_id": runtime_id, "sequence": observation_sequence},
            )
        updated = RuntimeSnapshot(
            runtimeId=runtime_id,
            observationSequence=observation_sequence,
            observedAt=timestamp,
            availableSlots=available_slots,
            utilization=utilization,
            healthStatus=HealthStatus.DEGRADED if stale else HealthStatus.ONLINE,
            latencyMs=latency_ms,
        )
        self.store.update_snapshot(updated, expected_version=current.version)
        if latency_ms is None:
            return self.health_monitor.heartbeat(runtime_id, received_at=timestamp)
        return self.health_monitor.observe(
            runtime_id, success=True, latency_ms=latency_ms, observed_at=timestamp
        )

    def set_runtime_health(self, runtime_id: str, *, healthy: bool) -> RuntimeHealth:
        self.store.get_profile(runtime_id)
        return self.health_monitor.set_health(runtime_id, healthy=healthy)

    def runtime_candidates(
        self,
        required_capabilities: list[str] | tuple[str, ...] | set[str],
        *,
        labels: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> list[RuntimeCandidate]:
        """返回具备所需能力、健康且仍有槽位的稳定排序候选集（不含策略约束）。"""
        candidates: list[RuntimeCandidate] = []
        for profile in self.store.list_profiles():
            versioned = self.store.get_snapshot(profile.runtime_id)
            health = self.health_monitor.health(profile.runtime_id, now=now)
            if not is_runtime_available(
                profile, versioned.snapshot, health, required_capabilities, labels
            ):
                continue
            candidates.append(
                RuntimeCandidate(
                    profile=profile,
                    snapshot=versioned,
                    health=health,
                    score=health_score(health, versioned.snapshot.utilization),
                )
            )
        return sorted(
            candidates, key=lambda candidate: (-candidate.score, candidate.profile.runtime_id)
        )

    # ------------------------------------------------------------------
    # Runtime 凭据：签名的远程执行与观测
    # ------------------------------------------------------------------

    def issue_runtime_credential(self, runtime_id: str) -> IssuedResourceCredential:
        profile = self.store.get_profile(runtime_id)
        if profile.endpoint is None or profile.endpoint.protocol == "local":
            raise ValueError("runtime credentials require a remote endpoint")
        if not profile.owner_scope:
            raise ValueError("remote runtime ownerScope is required")
        return self._new_runtime_credential(profile)

    def rotate_runtime_credential(self, runtime_id: str) -> IssuedResourceCredential:
        profile = self.store.get_profile(runtime_id)
        if profile.metadata.get("credentialLifecycle") == "process":
            # 进程绑定凭据必须由进程管理方协调更新；禁止只改数据库导致已启动服务失联。
            raise ValueError("process-bound credentials require managed service reinstallation")
        if profile.endpoint is None or profile.endpoint.protocol == "local":
            raise ValueError("runtime credentials require a remote endpoint")
        if not profile.owner_scope:
            raise ValueError("remote runtime ownerScope is required")
        issued = self._new_runtime_credential_for_rotation(profile)
        self.record_audit_event("credential_rotated", runtime_id)
        return issued

    def record_audit_event(self, kind: str, resource_id: str, **metadata: str) -> None:
        """内部可信调用方仅传分类信息；审计不可用时保留日志且不改变已提交业务。"""
        try:
            self.audit_store.append(ResourceAuditEvent(kind, resource_id, datetime.now(timezone.utc), metadata))
        except Exception:
            logger.exception("resource audit persistence failed", extra={"kind": kind, "resource_id": resource_id})

    def audit_events(self, resource_id: str | None = None, *, limit: int = 100):
        return self.audit_store.list(resource_id, limit=limit)

    def audit_counts(self, resource_id: str | None = None) -> dict[str, int]:
        return self.audit_store.counts(resource_id)

    def _new_runtime_credential(self, profile: RuntimeProfile) -> IssuedResourceCredential:
        secret = secrets.token_urlsafe(32)
        record = ResourceCredentialRecord(
            resource_id=profile.runtime_id,
            credential_id=f"rc_{uuid.uuid4().hex}",
            owner_scope=profile.owner_scope or "",
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now(timezone.utc),
        )
        self.store.save_credential(record)
        return IssuedResourceCredential(
            resource_id=profile.runtime_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def _new_runtime_credential_for_rotation(self, profile: RuntimeProfile) -> IssuedResourceCredential:
        secret = secrets.token_urlsafe(32)
        record = ResourceCredentialRecord(
            resource_id=profile.runtime_id,
            credential_id=f"rc_{uuid.uuid4().hex}",
            owner_scope=profile.owner_scope or "",
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now(timezone.utc),
        )
        self.store.rotate_credential(record)
        return IssuedResourceCredential(
            resource_id=profile.runtime_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def verify_runtime_credential(
        self, runtime_id: str, credential_id: str, secret: str
    ) -> ResourceCredentialRecord:
        try:
            profile = self.store.get_profile(runtime_id)
            record = self.store.get_credential(runtime_id)
        except KeyError as error:
            raise ValueError("resource credential not found") from error
        expected_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if (
            record.credential_id != credential_id
            or record.owner_scope != profile.owner_scope
            or not hmac.compare_digest(record.secret_digest, expected_digest)
        ):
            raise ValueError("resource credential is invalid")
        return record

    def runtime_credential(self, runtime_id: str) -> ResourceCredentialRecord:
        self.store.get_profile(runtime_id)
        return self.store.get_credential(runtime_id)

    def runtime_credential_hmac_key(self, runtime_id: str, credential_id: str) -> bytes:
        record = self.runtime_credential(runtime_id)
        if record.credential_id != credential_id:
            raise ValueError("resource credential is invalid")
        secret = self.secret_box.decrypt(record.encrypted_secret)
        return hashlib.sha256(secret.encode("utf-8")).digest()

    def current_signing_credential(self, runtime_id: str) -> tuple[str, str]:
        """Return the current credential for an outbound resource request.

        This is deliberately read on every execution rather than copied into an
        Adapter at construction time, so credential rotation takes effect on the
        next request.  The plaintext exists only across this internal signing
        seam and is never included in a profile or response model.
        """
        record = self.runtime_credential(runtime_id)
        return record.credential_id, self.secret_box.decrypt(record.encrypted_secret)

    def current_signing_credential_or_none(self, runtime_id: str) -> tuple[str | None, str | None]:
        """引导路径的容错版凭据读取；未登记凭据时返回 ``(None, None)``。"""
        try:
            credential_id, secret = self.current_signing_credential(runtime_id)
        except KeyError:
            return None, None
        return credential_id, secret

    def consume_nonce(
        self,
        runtime_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> bool:
        self.store.get_profile(runtime_id)
        current = now or datetime.now(timezone.utc)
        # 将存储层唯一性结果直接返回给鉴权器，避免服务层维护第二份 nonce 状态。
        return self.store.consume_nonce(runtime_id, nonce, expires_at, now=current)

    # ------------------------------------------------------------------
    # ModelEndpoint 层：可绑定的模型路由
    # ------------------------------------------------------------------

    def upsert_model_endpoint(
        self, endpoint: ModelEndpointProfile
    ) -> tuple[ModelEndpointProfile, bool]:
        return self.store.upsert_model_endpoint(endpoint)

    def model_endpoint(self, endpoint_id: str) -> ModelEndpointProfile:
        return self.store.get_model_endpoint(endpoint_id)

    def model_endpoints(self) -> list[ModelEndpointProfile]:
        return self.store.list_model_endpoints()

    def delete_model_endpoint(self, endpoint_id: str) -> None:
        self.store.delete_model_endpoint(endpoint_id)

    def sync_model_endpoints(
        self, routes: list[dict], *, describe_model=None
    ) -> dict[str, int]:
        """把模型注册表的当前路由投影为模型端点目录。

        ``routes`` 的每一项至少包含 ``provider`` 与 ``model``；
        ``describe_model(provider, model)`` 可选，返回 ``ModelCapabilityEnvelope``
        用于补齐上下文窗口与特性声明。由本方法建立且不在 ``routes``
        中的端点会被移除（配置驱动收敛）。
        """
        keep: set[str] = set()
        replaced = 0
        removed = 0
        for route in routes:
            provider = str(route.get("provider") or "").strip()
            model = str(route.get("model") or "").strip()
            if not provider or not model:
                continue
            endpoint_id = str(
                route.get("endpointId") or route.get("endpoint_id") or f"model:{provider}/{model}"
            ).strip()
            if not endpoint_id:
                continue
            envelope = None
            if describe_model is not None:
                try:
                    envelope = describe_model(provider, model)
                except Exception:
                    envelope = None
            features: dict[str, bool] = {}
            context_window = None
            max_output = None
            placement = Placement(route.get("placement") or Placement.CLOUD)
            if envelope is not None:
                context_window = route.get("contextWindowTokens", envelope.context_window_tokens)
                max_output = route.get("maxOutputTokens", envelope.max_output_tokens)
                feature_set = envelope.features
                features = {
                    key: value
                    for key, value in {
                        "json_schema": feature_set.json_schema,
                        "streaming": feature_set.streaming,
                        "tools": feature_set.tools,
                        "thinking": feature_set.thinking,
                        "prompt_caching": feature_set.prompt_caching,
                    }.items()
                    if value is not None
                }
            route_features = route.get("features")
            if isinstance(route_features, dict):
                features.update(route_features)
            context_window = route.get("contextWindowTokens", route.get("context_window_tokens", context_window))
            max_output = route.get("maxOutputTokens", route.get("max_output_tokens", max_output))
            metadata = dict(route.get("metadata") or {})
            metadata["_resourcePlaneSync"] = "model-registry"
            endpoint = ModelEndpointProfile(
                endpointId=endpoint_id,
                runtimeId=route.get("runtimeId") or route.get("runtime_id"),
                provider=provider,
                model=model,
                modelVersion=(str(route.get("modelVersion") or route.get("version")) if route.get("modelVersion") or route.get("version") else None),
                sourceType=(str(route.get("sourceType") or route.get("source_type") or "model_registry")),
                adapter=(str(route.get("adapter")) if route.get("adapter") else None),
                placement=placement,
                ownerScope=route.get("ownerScope") or route.get("owner_scope"),
                tier=route.get("tier"),
                contextWindowTokens=context_window,
                maxOutputTokens=max_output,
                features=ModelFeatureSet.model_validate(features),
                costMetadata=route.get("costMetadata") or route.get("cost_metadata") or {},
                labels=route.get("labels") or {},
                enabled=route.get("enabled", True),
                metadata=metadata,
            )
            _, changed = self.store.upsert_model_endpoint(endpoint)
            if changed:
                replaced += 1
            keep.add(endpoint_id)
        for existing in self.store.list_model_endpoints():
            if (
                (existing.metadata.get("_resourcePlaneSync") == "model-registry"
                 or existing.metadata.get("source") == "model-registry-sync")
                and existing.endpoint_id not in keep
            ):
                self.store.delete_model_endpoint(existing.endpoint_id)
                removed += 1
        return {"kept": len(keep), "replaced": replaced, "removed": removed}

    def model_candidates(
        self,
        demand: ModelDemand | None,
        *,
        owner_scope: str | None = None,
        now: datetime | None = None,
    ) -> list[ModelEndpointCandidate]:
        """按模型需求返回可用端点候选；特征未声明的端点按不支持处理。"""
        demand = demand or ModelDemand()
        allowed = set(demand.allowed_endpoint_ids)
        excluded = set(demand.excluded_endpoint_ids)
        preferred = {value.casefold() for value in demand.preferred_model_ids}
        allowed_providers = {value.casefold() for value in demand.allowed_providers}
        excluded_providers = {value.casefold() for value in demand.excluded_providers}
        allowed_models = {value.casefold() for value in demand.allowed_models}
        excluded_models = {value.casefold() for value in demand.excluded_models}
        required_features = set(demand.required_features)
        candidates: list[ModelEndpointCandidate] = []
        for endpoint in self.store.list_model_endpoints():
            if not endpoint.enabled:
                continue
            if endpoint.runtime_id is not None:
                try:
                    host_runtime = self.store.get_profile(endpoint.runtime_id)
                    host_node = self.node_store.get_profile(host_runtime.node_id)
                except KeyError:
                    continue
                host_health = self.health_monitor.health(host_runtime.runtime_id, now=now)
                node_health = self.get_node_health(host_node.node_id, now=now)
                if (
                    not host_runtime.enabled
                    or not host_node.enabled
                    or not host_health.healthy
                    or node_health.status in {
                        NodeHealthStatus.UNKNOWN,
                        NodeHealthStatus.STALE,
                        NodeHealthStatus.OFFLINE,
                        NodeHealthStatus.SUSPICIOUS,
                    }
                ):
                    continue
                endpoint_owner_scope = host_runtime.owner_scope
            else:
                endpoint_owner_scope = endpoint.owner_scope
            # 没有 ownerScope 的注册表端点代表显式共享服务；有归属的端点
            # 必须由同一归属范围的执行需求使用，避免跨租户模型路由。
            if owner_scope and endpoint_owner_scope not in {None, owner_scope}:
                continue
            if allowed and endpoint.endpoint_id not in allowed:
                continue
            if endpoint.endpoint_id in excluded:
                continue
            provider = endpoint.provider.casefold()
            model = endpoint.model.casefold()
            qualified_model = f"{provider}/{model}"
            if provider in excluded_providers or (allowed_providers and provider not in allowed_providers):
                continue
            if model in excluded_models or qualified_model in excluded_models:
                continue
            if allowed_models and model not in allowed_models and qualified_model not in allowed_models:
                continue
            feature_map = endpoint.features.model_dump()
            if any(feature_map.get(feature) is not True for feature in required_features):
                continue
            if demand.min_context_tokens > 0 and (
                endpoint.context_window_tokens is None
                or endpoint.context_window_tokens < demand.min_context_tokens
            ):
                continue
            score = 1.0 + (0.1 if model in preferred or qualified_model in preferred else 0.0)
            candidates.append(ModelEndpointCandidate(endpoint=endpoint, score=score))
        return sorted(
            candidates,
            key=lambda item: (-item.score, item.endpoint.endpoint_id),
        )


__all__ = [
    # 生命周期审计由 ResourceAuditStore 持久化；audit_counts 提供按事件类型聚合计数。
    "IssuedNodeCredential",
    "IssuedResourceCredential",
    "ResourcePlane",
    "SQLiteResourceStore",
]

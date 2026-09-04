"""面向调度器的资源登记、观测和候选查询服务。"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from typing import Literal

from contracts.resource import (
    BindingRequirement,
    DeploymentTier,
    ResourceHealthStatus,
    ResourceProfile,
    ResourceSnapshot,
)

from .algorithms import health_score, is_resource_available
from .crypto import ResourceSecretBox
from .health import ResourceHealthMonitor
from .models import ResourceCandidate, ResourceHealth, VersionedResourceSnapshot
from .registry import ResourceRegistry
from .store import InMemoryResourceStore, ResourceCredentialRecord, ResourceStore


@dataclass(frozen=True)
class IssuedResourceCredential:
    """注册响应中一次性返回的资源密钥。"""

    resource_id: str
    credential_id: str
    owner_scope: str
    secret: str


class ResourceService:
    """以单个协调入口向调度器暴露可立即分配的资源候选。"""

    def __init__(
        self,
        store: ResourceStore | None = None,
        health_monitor: ResourceHealthMonitor | None = None,
        *,
        heartbeat_timeout: timedelta = timedelta(seconds=60),
        credential_key: str | bytes | None = None,
    ) -> None:
        self.store = store or InMemoryResourceStore()
        self.registry = ResourceRegistry(self.store)
        self.health_monitor = health_monitor or ResourceHealthMonitor(
            heartbeat_timeout=heartbeat_timeout
        )
        self.secret_box = ResourceSecretBox(credential_key)

    def register(self, profile: ResourceProfile, snapshot: ResourceSnapshot) -> VersionedResourceSnapshot:
        """登记一个可调度资源及其首个负载快照。"""
        return self.store.register(profile, snapshot)

    register_resource = register

    def register_remote(
        self, profile: ResourceProfile, snapshot: ResourceSnapshot
    ) -> IssuedResourceCredential:
        """登记远程资源并生成只能在注册响应中读取一次的凭据。"""
        if profile.deployment_tier is DeploymentTier.LOCAL:
            raise ValueError("remote resource must use a non-local deployment tier")
        if not profile.owner_scope:
            raise ValueError("remote resource owner_scope is required")
        if profile.execution_endpoint is None or profile.execution_endpoint.protocol == "local":
            raise ValueError("remote resource execution endpoint is required")
        secret = secrets.token_urlsafe(32)
        record = ResourceCredentialRecord(
            resource_id=profile.resource_id,
            credential_id=f"rc_{uuid.uuid4().hex}",
            owner_scope=profile.owner_scope,
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now().astimezone(),
        )
        self.store.register_remote(profile, snapshot, record)
        return IssuedResourceCredential(
            resource_id=profile.resource_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def update_snapshot(
        self, snapshot: ResourceSnapshot, *, expected_version: int | None = None
    ) -> VersionedResourceSnapshot:
        """更新动态负载观测；版本冲突交给存储层显式报告。"""
        return self.store.update_snapshot(snapshot, expected_version=expected_version)

    def update_capacity(
        self, resource_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedResourceSnapshot:
        """以 CAS 同步已登记资源的声明容量和动态空闲槽位。"""
        return self.store.update_capacity(
            resource_id,
            capacity,
            expected_capacity=expected_capacity,
        )

    def snapshot(self, resource_id: str) -> VersionedResourceSnapshot:
        """读取调度决策所需的最新版本快照。"""
        return self.store.get_snapshot(resource_id)

    def profile(self, resource_id: str) -> ResourceProfile:
        """Read the authoritative static profile."""
        return self.store.get_profile(resource_id)

    def profiles(self) -> list[ResourceProfile]:
        """List authoritative profiles in stable order."""
        return self.store.list_profiles()

    def issue_credential(self, resource_id: str) -> IssuedResourceCredential:
        """为远程资源生成一次性可交付的资源密钥。"""
        profile = self.registry.get(resource_id)
        if profile.deployment_tier is DeploymentTier.LOCAL:
            raise ValueError("resource credentials require a remote resource")
        if not profile.owner_scope:
            raise ValueError("remote resource owner_scope is required")
        if profile.execution_endpoint is None or profile.execution_endpoint.protocol == "local":
            raise ValueError("remote resource execution endpoint is required")
        secret = secrets.token_urlsafe(32)
        record = ResourceCredentialRecord(
            resource_id=resource_id,
            credential_id=f"rc_{uuid.uuid4().hex}",
            owner_scope=profile.owner_scope,
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now().astimezone(),
        )
        self.store.save_credential(record)
        return IssuedResourceCredential(
            resource_id=resource_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def rotate_credential(self, resource_id: str) -> IssuedResourceCredential:
        """原子轮换远程资源凭据，并使旧凭据立即失效。"""
        profile = self.registry.get(resource_id)
        if profile.deployment_tier is DeploymentTier.LOCAL:
            raise ValueError("resource credentials require a remote resource")
        if not profile.owner_scope:
            raise ValueError("remote resource owner_scope is required")
        if profile.execution_endpoint is None or profile.execution_endpoint.protocol == "local":
            raise ValueError("remote resource execution endpoint is required")
        secret = secrets.token_urlsafe(32)
        record = ResourceCredentialRecord(
            resource_id=resource_id,
            credential_id=f"rc_{uuid.uuid4().hex}",
            owner_scope=profile.owner_scope,
            secret_digest=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            encrypted_secret=self.secret_box.encrypt(secret),
            created_at=datetime.now().astimezone(),
        )
        self.store.rotate_credential(record)
        return IssuedResourceCredential(
            resource_id=resource_id,
            credential_id=record.credential_id,
            owner_scope=record.owner_scope,
            secret=secret,
        )

    def verify_credential(
        self, resource_id: str, credential_id: str, secret: str
    ) -> ResourceCredentialRecord:
        """校验资源凭据并返回不含明文密钥的记录。"""
        profile = self.registry.get(resource_id)
        try:
            record = self.store.get_credential(resource_id)
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

    def credential(self, resource_id: str) -> ResourceCredentialRecord:
        """Read resource credential metadata without exposing a secret."""
        self.registry.get(resource_id)
        return self.store.get_credential(resource_id)

    def credential_hmac_key(self, resource_id: str, credential_id: str) -> bytes:
        """Decrypt a valid credential only at the signing verification seam."""
        record = self.credential(resource_id)
        if record.credential_id != credential_id:
            raise ValueError("resource credential is invalid")
        secret = self.secret_box.decrypt(record.encrypted_secret)
        return hashlib.sha256(secret.encode("utf-8")).digest()

    def current_signing_credential(self, resource_id: str) -> tuple[str, str]:
        """Return the current credential for an outbound resource request.

        This is deliberately read on every execution rather than copied into an
        Adapter at construction time, so credential rotation takes effect on
        the next request.  The plaintext exists only across this internal
        signing seam and is never included in a profile or response model.
        """
        record = self.credential(resource_id)
        return record.credential_id, self.secret_box.decrypt(record.encrypted_secret)

    def consume_nonce(
        self,
        resource_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> bool:
        self.registry.get(resource_id)
        current = now or datetime.now().astimezone()
        return self.store.consume_nonce(resource_id, nonce, expires_at, now=current)

    def heartbeat(
        self,
        resource_id: str,
        *,
        received_at: datetime | None = None,
        source: Literal["local", "external"] = "local",
    ) -> ResourceHealth:
        """记录已登记资源的存活信号，远程资源必须由外部节点主动上报。"""
        profile = self.registry.get(resource_id)
        if profile.deployment_tier is not DeploymentTier.LOCAL and source != "external":
            raise ValueError("remote resource heartbeat must come from an external heartbeat")
        return self.health_monitor.heartbeat(resource_id, received_at=received_at)

    def observe(
        self,
        resource_id: str,
        *,
        success: bool,
        latency_ms: float,
        observed_at: datetime | None = None,
    ) -> ResourceHealth:
        """记录执行结果，供后续调度在可靠性和时延上作出更好选择。"""
        self.registry.get(resource_id)
        return self.health_monitor.observe(
            resource_id,
            success=success,
            latency_ms=latency_ms,
            observed_at=observed_at,
        )

    def observe_remote(
        self,
        resource_id: str,
        *,
        available_slots: int,
        utilization: float,
        latency_ms: float | None = None,
        observed_at: datetime | None = None,
        observation_sequence: int = 0,
    ) -> ResourceHealth:
        """接收远程资源的一次完整观测，并同步快照与存活信号。"""
        profile = self.registry.get(resource_id)
        if profile.deployment_tier is DeploymentTier.LOCAL:
            raise ValueError("remote observation requires a non-local resource")
        current = self.store.get_snapshot(resource_id)
        timestamp = observed_at or datetime.now().astimezone()
        updated = ResourceSnapshot(
            resourceId=resource_id,
            observationSequence=observation_sequence,
            observedAt=timestamp,
            availableSlots=available_slots,
            utilization=utilization,
            healthStatus=ResourceHealthStatus.ONLINE,
            latencyMs=latency_ms,
        )
        self.store.update_snapshot(updated, expected_version=current.version)
        if latency_ms is None:
            return self.heartbeat(resource_id, received_at=timestamp, source="external")
        return self.health_monitor.observe(
            resource_id,
            success=True,
            latency_ms=latency_ms,
            observed_at=timestamp,
        )

    def set_health(self, resource_id: str, *, healthy: bool) -> ResourceHealth:
        """Record a compatibility adapter's explicit health observation."""
        self.registry.get(resource_id)
        return self.health_monitor.set_health(resource_id, healthy=healthy)

    def candidates(
        self,
        required_capabilities: list[str] | tuple[str, ...] | set[str],
        *,
        labels: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> list[ResourceCandidate]:
        """返回具备所需能力、健康且仍有槽位的稳定排序候选集。"""
        candidates: list[ResourceCandidate] = []
        for profile in self.registry.all():
            versioned = self.store.get_snapshot(profile.resource_id)
            health = self.health_monitor.health(profile.resource_id, now=now)
            if not is_resource_available(
                profile, versioned.snapshot, health, required_capabilities, labels
            ):
                continue
            candidates.append(
                ResourceCandidate(
                    profile=profile,
                    snapshot=versioned,
                    health=health,
                    score=health_score(health, versioned.snapshot.utilization),
                )
            )
        return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.profile.resource_id))

    get_candidates = candidates

    def find_candidates(
        self, requirement: BindingRequirement, *, now: datetime | None = None
    ) -> list[ResourceCandidate]:
        """Resolve a frozen requirement without creating a concrete binding."""
        allowed = set(requirement.allowed_resource_ids)
        excluded = set(requirement.excluded_resource_ids)
        selected = self.candidates(
            requirement.required_capabilities,
            labels=requirement.labels,
            now=now,
        )
        return [
            candidate
            for candidate in selected
            if (not allowed or candidate.profile.resource_id in allowed)
            and candidate.profile.resource_id not in excluded
            and (not requirement.resource_types or candidate.profile.resource_type in requirement.resource_types)
            and (requirement.domain is None or not candidate.profile.domains or requirement.domain in candidate.profile.domains or "general" in candidate.profile.domains)
            and (requirement.data_zone is None or candidate.profile.data_zone == requirement.data_zone)
            and (requirement.owner_scope is None or candidate.profile.owner_scope == requirement.owner_scope)
            and (
                requirement.max_cost is None
                or candidate.profile.cost_metadata.get("unit", 0.0) <= requirement.max_cost
            )
        ]

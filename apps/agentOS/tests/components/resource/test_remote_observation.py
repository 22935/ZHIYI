"""远程 Runtime 观测合同：外部观测是唯一权威，序列号防回退。

带端点的 Runtime 的存活与负载只认外部上报（heartbeat source=external /
observe_remote_runtime），进程内代码不得替远端刷新状态。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from components.resource.application.resource_plane import ResourcePlane
from components.resource.errors import ResourceObservationTimeInvalidError
from components.resource.infrastructure.runtime_store import SQLiteResourceStore, StaleResourceObservation
from contracts.resource import (
    HealthStatus,
    Placement,
    ResourceEndpoint,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)


def _plane(**overrides) -> ResourcePlane:
    values = dict(
        heartbeat_timeout=timedelta(minutes=5),
    )
    values.update(overrides)
    return ResourcePlane(**values)


def _remote_profile(plane: ResourcePlane, runtime_id: str = "runtime:edge-exec-1") -> RuntimeProfile:
    plane.ensure_node("node:edge-1", placement=Placement.EDGE, trust=TrustLevel.TRUSTED)
    profile = RuntimeProfile(
        runtimeId=runtime_id,
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-1",
        placement=Placement.EDGE,
        capabilities=["repo.read"],
        trust=TrustLevel.TRUSTED,
        endpoint=ResourceEndpoint(protocol="https", address=f"https://edge-1/{runtime_id}"),
        ownerScope="scope-a",
        capacity=4,
    )
    snapshot = RuntimeSnapshot(
        runtimeId=runtime_id,
        availableSlots=4,
        utilization=0.0,
        healthStatus=HealthStatus.UNKNOWN,
    )
    plane.register_remote_runtime(profile, snapshot)
    return profile


def test_remote_heartbeat_is_authoritative_and_expires_without_refresh() -> None:
    plane = _plane(heartbeat_timeout=timedelta(minutes=5))
    _remote_profile(plane)

    now = datetime.now(timezone.utc)
    health = plane.heartbeat_runtime("runtime:edge-exec-1", received_at=now, source="external")
    assert health.healthy
    assert plane.health_monitor.health("runtime:edge-exec-1", now=now + timedelta(minutes=1)).healthy
    # 无持续心跳时健康随时间自然过期。
    later = now + timedelta(minutes=6)
    assert not plane.health_monitor.health("runtime:edge-exec-1", now=later).healthy


def test_local_runtime_cannot_refresh_remote_resource() -> None:
    plane = _plane()
    _remote_profile(plane)
    with pytest.raises(ValueError):
        plane.heartbeat_runtime("runtime:edge-exec-1", source="local")


def test_remote_observation_updates_snapshot_and_health_atomically() -> None:
    plane = _plane()
    _remote_profile(plane)

    health = plane.observe_remote_runtime(
        "runtime:edge-exec-1",
        available_slots=2,
        utilization=0.5,
        latency_ms=180.0,
        observation_sequence=1,
    )
    versioned = plane.runtime_snapshot("runtime:edge-exec-1")
    assert versioned.version == 2
    assert versioned.snapshot.available_slots == 2
    assert versioned.snapshot.utilization == pytest.approx(0.5)
    assert versioned.snapshot.latency_ms == pytest.approx(180.0)
    assert health.healthy
    assert health.latency_ms == pytest.approx(180.0)


def test_remote_observation_rejects_older_sequence_without_mutating_snapshot() -> None:
    plane = _plane()
    _remote_profile(plane)
    plane.observe_remote_runtime(
        "runtime:edge-exec-1",
        available_slots=1,
        utilization=0.75,
        observation_sequence=5,
    )
    before = plane.runtime_snapshot("runtime:edge-exec-1")

    with pytest.raises(StaleResourceObservation):
        plane.observe_remote_runtime(
            "runtime:edge-exec-1",
            available_slots=4,
            utilization=0.0,
            observation_sequence=4,
        )
    assert plane.runtime_snapshot("runtime:edge-exec-1") == before


def test_sqlite_remote_observation_rejects_older_sequence(tmp_path: Path) -> None:
    plane = ResourcePlane(store=SQLiteResourceStore(tmp_path / "plane.sqlite3"))
    _remote_profile(plane, "runtime:edge-exec-2")
    plane.observe_remote_runtime(
        "runtime:edge-exec-2",
        available_slots=3,
        utilization=0.25,
        observation_sequence=2,
    )
    with pytest.raises(StaleResourceObservation):
        plane.observe_remote_runtime(
            "runtime:edge-exec-2",
            available_slots=4,
            utilization=0.0,
            observation_sequence=2,
        )
    plane.store.close()


def test_remote_observation_requires_endpoint_runtime() -> None:
    plane = _plane()
    plane.ensure_node("node:device:local", placement=Placement.DEVICE)
    plane.register_runtime(RuntimeProfile(
        runtimeId="runtime:embedded",
        nodeId="node:device:local",
        placement=Placement.DEVICE,
        capabilities=["exec.agents"],
    ))
    with pytest.raises(ValueError):
        plane.observe_remote_runtime(
            "runtime:embedded",
            available_slots=1,
            utilization=0.0,
            observation_sequence=1,
        )


def test_remote_observation_rejects_future_timestamp() -> None:
    plane = _plane()
    _remote_profile(plane)
    with pytest.raises(ResourceObservationTimeInvalidError):
        plane.observe_remote_runtime(
            "runtime:edge-exec-1", available_slots=1, utilization=0.0,
            observation_sequence=1, observed_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )


def test_old_remote_observation_is_persisted_as_degraded() -> None:
    plane = _plane()
    _remote_profile(plane)
    plane.observe_remote_runtime(
        "runtime:edge-exec-1", available_slots=1, utilization=0.0,
        observation_sequence=1, observed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    assert plane.runtime_snapshot("runtime:edge-exec-1").snapshot.health_status is HealthStatus.DEGRADED


def test_execution_observation_returns_after_successful_snapshot_write() -> None:
    plane = _plane()
    profile = _remote_profile(plane)

    health = plane.observe_execution(profile.runtime_id, success=True, latency_ms=12.0)

    assert health.healthy
    snapshot = plane.runtime_snapshot(profile.runtime_id).snapshot
    assert snapshot.observation_sequence == 1
    assert snapshot.latency_ms == pytest.approx(12.0)

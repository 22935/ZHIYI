"""NodeStore 的持久化合同与节点健康重启恢复。

Node 是部署实体：其画像、快照、凭据与 nonce 都必须跨进程重启保持。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from components.resource.infrastructure.node_store import InMemoryNodeStore, SQLiteNodeStore
from components.resource.application.resource_plane import ResourcePlane
from components.resource.errors import ResourceObservationTimeInvalidError
from components.resource.domain.credentials import ResourceCredentialRecord
from components.resource.infrastructure.runtime_store import (
    SQLiteResourceStore,
    StaleResourceObservation,
)
from contracts.resource import (
    NodeHealthStatus,
    NodeProfile,
    NodeSnapshot,
    Placement,
    TrustLevel,
)


def _node(node_id: str = "node:edge-1", **overrides) -> NodeProfile:
    values = dict(
        nodeId=node_id,
        placement=Placement.EDGE,
        trust=TrustLevel.TRUSTED,
        ownerScope="scope-a",
    )
    values.update(overrides)
    return NodeProfile(**values)


def _snapshot(node_id: str, *, seq: int = 1, failures: int = 0) -> NodeSnapshot:
    return NodeSnapshot(
        nodeId=node_id,
        observationSequence=seq,
        healthStatus=NodeHealthStatus.ONLINE,
        lastHeartbeat=datetime.now(timezone.utc),
        consecutiveFailures=failures,
    )


def _credential(node_id: str) -> ResourceCredentialRecord:
    return ResourceCredentialRecord(
        resource_id=node_id,
        credential_id=f"nc_{node_id}",
        owner_scope="scope-a",
        secret_digest="0" * 64,
        encrypted_secret="sealed-secret",
        created_at=datetime.now(timezone.utc),
    )


def test_node_store_persists_profile_snapshot_credential_and_nonce(tmp_path: Path) -> None:
    db_path = tmp_path / "nodes.sqlite3"
    store = SQLiteNodeStore(db_path)
    store.register(_node("node:edge-1"), _snapshot("node:edge-1"))
    store.save_credential(_credential("node:edge-1"))
    now = datetime.now(timezone.utc)
    assert store.consume_nonce("node:edge-1", "nonce-1", now + timedelta(minutes=5), now=now)
    store.close()

    reopened = SQLiteNodeStore(db_path)
    assert reopened.get_profile("node:edge-1").placement is Placement.EDGE
    assert reopened.get_snapshot("node:edge-1").snapshot.observation_sequence == 1
    assert reopened.get_credential("node:edge-1").credential_id == "nc_node:edge-1"
    # 已消费的 nonce 重启后依然是已消费状态。
    assert not reopened.consume_nonce("node:edge-1", "nonce-1", now + timedelta(minutes=5), now=now)
    reopened.close()


def test_node_store_expires_old_nonces_on_consume(tmp_path: Path) -> None:
    store = SQLiteNodeStore(tmp_path / "nodes.sqlite3")
    store.register(_node("node:edge-1"), _snapshot("node:edge-1"))
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=1)
    assert store.consume_nonce("node:edge-1", "nonce-1", expiry, now=now)
    later = now + timedelta(minutes=2)
    # 过期清理后同一 nonce 可以再次使用。
    assert store.consume_nonce("node:edge-1", "nonce-1", expiry + timedelta(minutes=5), now=later)
    store.close()


def test_node_store_update_profile_persists(tmp_path: Path) -> None:
    db_path = tmp_path / "nodes.sqlite3"
    store = SQLiteNodeStore(db_path)
    store.register(_node("node:edge-1"), _snapshot("node:edge-1"))
    store.close()

    reopened = SQLiteNodeStore(db_path)
    updated = reopened.update_profile(
        _node("node:edge-1", displayName="边缘节点一号", labels={"rack": "b7"})
    )
    reopened.close()
    assert updated.display_name == "边缘节点一号"

    again = SQLiteNodeStore(db_path)
    assert again.get_profile("node:edge-1").labels == {"rack": "b7"}
    again.close()


def test_node_health_recovers_from_persisted_snapshot_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "nodes.sqlite3"
    plane = ResourcePlane(
        store=SQLiteResourceStore(tmp_path / "plane.sqlite3"),
        node_store=SQLiteNodeStore(db_path),
    )
    plane.ensure_node("node:edge-1", placement=Placement.EDGE, trust=TrustLevel.TRUSTED)
    plane.observe_node(
        "node:edge-1",
        observation_sequence=1,
        cpu_utilization=0.2,
        success=True,
    )
    assert plane.node_health("node:edge-1").status is NodeHealthStatus.ONLINE
    plane.node_store.close()
    plane.store.close()

    restarted = ResourcePlane(
        store=SQLiteResourceStore(tmp_path / "plane.sqlite3"),
        node_store=SQLiteNodeStore(db_path),
    )
    # 进程内监测器为空，但健康必须能从持久化快照恢复而不是全部回 UNKNOWN。
    health = restarted.node_health("node:edge-1")
    assert health.status in {NodeHealthStatus.ONLINE, NodeHealthStatus.STALE}
    assert health.last_heartbeat is not None
    restarted.node_store.close()
    restarted.store.close()


def test_node_health_is_shared_through_persisted_snapshot_between_processes(tmp_path: Path) -> None:
    db_path = tmp_path / "nodes.sqlite3"
    writer = ResourcePlane(node_store=SQLiteNodeStore(db_path))
    writer.ensure_node("node:edge-1", placement=Placement.EDGE)
    now = datetime.now(timezone.utc)
    writer.observe_node("node:edge-1", observation_sequence=1, observed_at=now)

    reader = ResourcePlane(node_store=SQLiteNodeStore(db_path))
    health = reader.get_node_health("node:edge-1", now=now + timedelta(seconds=1))

    assert health.status is NodeHealthStatus.ONLINE
    assert health.last_heartbeat == now
    writer.node_store.close()
    reader.node_store.close()


def test_node_health_persists_consecutive_failures(tmp_path: Path) -> None:
    db_path = tmp_path / "nodes.sqlite3"
    plane = ResourcePlane(
        store=SQLiteResourceStore(tmp_path / "plane.sqlite3"),
        node_store=SQLiteNodeStore(db_path),
    )
    plane.ensure_node("node:edge-1", placement=Placement.EDGE)
    plane.observe_node("node:edge-1", observation_sequence=1, success=False)
    plane.observe_node("node:edge-1", observation_sequence=2, success=False)
    plane.node_store.close()
    plane.store.close()

    restarted = ResourcePlane(
        store=SQLiteResourceStore(tmp_path / "plane.sqlite3"),
        node_store=SQLiteNodeStore(db_path),
    )
    snapshot = restarted.node_snapshot("node:edge-1").snapshot
    # 失败计数必须跨重启保留；状态分级仍由心跳年龄与负载决定。
    assert snapshot.consecutive_failures == 2
    assert restarted.node_health("node:edge-1").consecutive_failures == 2
    restarted.node_store.close()
    restarted.store.close()


def test_node_observation_rejects_future_timestamp() -> None:
    plane = ResourcePlane()
    plane.ensure_node("node:edge-1", placement=Placement.EDGE)
    with pytest.raises(ResourceObservationTimeInvalidError):
        plane.observe_node(
            "node:edge-1", observation_sequence=1,
            observed_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )


def test_repeated_node_clock_anomalies_mark_node_suspicious() -> None:
    plane = ResourcePlane()
    plane.ensure_node("node:edge-1", placement=Placement.EDGE)
    for _ in range(3):
        with pytest.raises(ResourceObservationTimeInvalidError):
            plane.observe_node(
                "node:edge-1", observation_sequence=1,
                observed_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            )
    assert plane.node_snapshot("node:edge-1").snapshot.health_status is NodeHealthStatus.SUSPICIOUS


def test_in_memory_node_store_matches_sqlite_contract() -> None:
    store = InMemoryNodeStore()
    store.register(_node("node:edge-1"), _snapshot("node:edge-1"))
    assert store.get_profile("node:edge-1").node_id == "node:edge-1"
    updated = store.update_snapshot(
        _snapshot("node:edge-1", seq=2), expected_version=1
    )
    assert updated.version == 2
    store.save_credential(_credential("node:edge-1"))
    assert store.get_credential("node:edge-1").credential_id == "nc_node:edge-1"


def test_legacy_local_bootstrap_is_adopted_without_losing_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "legacy-nodes.sqlite3"
    store = SQLiteNodeStore(path)
    node_id = "node:device:local"
    store.register(NodeProfile(nodeId=node_id, placement=Placement.DEVICE,
        trust=TrustLevel.HOST_TRUSTED, displayName="本机设备节点"), _snapshot(node_id, seq=7))
    store.close()
    reopened = SQLiteNodeStore(path)
    plane = ResourcePlane(node_store=reopened)
    profile = plane.ensure_node(node_id, display_name="本机设备节点")
    assert profile.metadata == {"managedBy": "bootstrap"}
    assert reopened.get_snapshot(node_id).snapshot.observation_sequence == 7
    assert plane.ensure_node(node_id, display_name="本机设备节点") == profile
    reopened.close()
    persisted = SQLiteNodeStore(path)
    assert persisted.get_profile(node_id).metadata == {"managedBy": "bootstrap"}
    persisted.close()


@pytest.mark.parametrize("conflict", ["credential", "trust", "owner", "metadata"])
def test_bootstrap_does_not_adopt_conflicting_local_node(conflict: str) -> None:
    store = InMemoryNodeStore()
    node_id = "node:device:local"
    changes = {"trust": {"trust": TrustLevel.UNTRUSTED},
        "owner": {"ownerScope": "external"}, "metadata": {"metadata": {"managedBy": "external"}}}
    profile = NodeProfile(nodeId=node_id, placement=Placement.DEVICE,
        displayName="本机设备节点", **({"trust": TrustLevel.HOST_TRUSTED} | changes.get(conflict, {})))
    store.register(profile, _snapshot(node_id))
    if conflict == "credential":
        store.save_credential(_credential(node_id))
    with pytest.raises(ValueError, match="non-bootstrap"):
        ResourcePlane(node_store=store).ensure_node(node_id, display_name="本机设备节点")
    assert store.get_profile(node_id) == profile


def test_store_rejects_non_increasing_observation_sequence(tmp_path: Path) -> None:
    """存储边界自身必须拒绝等序/退序观察，而不只依赖 Service 的前置检查。"""
    path = tmp_path / "nodes.sqlite3"
    store = SQLiteNodeStore(path)
    node_id = "node:device:local"
    store.register(
        NodeProfile(nodeId=node_id, placement=Placement.DEVICE,
                    trust=TrustLevel.HOST_TRUSTED, displayName="本机设备节点"),
        _snapshot(node_id, seq=3),
    )

    for seq in (3, 2):
        with pytest.raises(StaleResourceObservation):
            store.update_snapshot(_snapshot(node_id, seq=seq))

    assert store.get_snapshot(node_id).snapshot.observation_sequence == 3
    assert store.update_snapshot(_snapshot(node_id, seq=4)).version == 2
    store.close()

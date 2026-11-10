"""RuntimeStore 的存储合同：登记、版本 CAS、凭据与模型端点。

InMemory 与 SQLite 两个实现必须满足同一份合同；SQLite 额外验证跨进程
重启的持久化语义与旧表自愈。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from components.resource.domain.credentials import ResourceCredentialRecord
from components.resource.infrastructure.runtime_store import (
    InMemoryResourceStore,
    SQLiteResourceStore,
    StaleResourceObservation,
    VersionConflict,
)
from contracts.resource import (
    HealthStatus,
    ModelEndpointProfile,
    Placement,
    ResourceEndpoint,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)


def _profile(runtime_id: str = "runtime:worker-1", **overrides) -> RuntimeProfile:
    values = dict(
        runtimeId=runtime_id,
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-1",
        placement=Placement.EDGE,
        capabilities=["repo.read"],
        trust=TrustLevel.TRUSTED,
        endpoint=ResourceEndpoint(protocol="https", address="https://edge-1.internal/exec"),
        ownerScope="scope-a",
        capacity=2,
    )
    values.update(overrides)
    return RuntimeProfile(**values)


def _snapshot(runtime_id: str, *, seq: int = 0, slots: int = 2) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        runtimeId=runtime_id,
        availableSlots=slots,
        utilization=0.0,
        healthStatus=HealthStatus.ONLINE,
        observationSequence=seq,
    )


def _credential(runtime_id: str, *, credential_id: str | None = None) -> ResourceCredentialRecord:
    return ResourceCredentialRecord(
        resource_id=runtime_id,
        credential_id=credential_id or f"rc_{runtime_id}",
        owner_scope="scope-a",
        secret_digest="0" * 64,
        encrypted_secret="sealed-secret",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryResourceStore()
        return
    sqlite_store = SQLiteResourceStore(tmp_path / "plane.sqlite3")
    yield sqlite_store
    sqlite_store.close()


def test_runtime_store_contract_create_get_list_duplicate_and_cas(store) -> None:
    first = store.register(_profile("runtime:a"), _snapshot("runtime:a"))
    second = store.register(_profile("runtime:b"), _snapshot("runtime:b"))
    assert first.version == 1 and second.version == 1

    assert store.get_profile("runtime:a").capabilities == ["repo.read"]
    assert [profile.runtime_id for profile in store.list_profiles()] == ["runtime:a", "runtime:b"]

    with pytest.raises(ValueError):
        store.register(_profile("runtime:a"), _snapshot("runtime:a"))

    updated = store.update_snapshot(
        _snapshot("runtime:a", seq=1, slots=1), expected_version=1
    )
    assert updated.version == 2
    with pytest.raises(VersionConflict):
        store.update_snapshot(_snapshot("runtime:a", seq=2), expected_version=1)
    with pytest.raises(StaleResourceObservation):
        store.update_snapshot(_snapshot("runtime:a", seq=0))

    with pytest.raises(VersionConflict):
        store.update_capacity("runtime:a", 8, expected_capacity=99)
    rescaled = store.update_capacity("runtime:a", 8, expected_capacity=2)
    # 一个已占槽位在扩容后仍保持占用，利用率按新容量重算。
    assert rescaled.snapshot.available_slots == 7
    assert rescaled.snapshot.utilization == pytest.approx(1 / 8)
    assert store.get_profile("runtime:a").capacity == 8

    with pytest.raises(KeyError):
        store.update_profile(_profile("runtime:other"))


def test_sqlite_restart_keeps_profile_but_downgrades_snapshot_health(tmp_path: Path) -> None:
    db_path = tmp_path / "plane.sqlite3"
    store = SQLiteResourceStore(db_path)
    store.register(_profile("runtime:a"), _snapshot("runtime:a"))
    store.update_snapshot(_snapshot("runtime:a", seq=3, slots=1))
    store.close()

    reopened = SQLiteResourceStore(db_path)
    profile = reopened.get_profile("runtime:a")
    versioned = reopened.get_snapshot("runtime:a")
    reopened.close()
    assert profile.capabilities == ["repo.read"]
    assert versioned.version == 2
    # 重启后没有活跃健康信号来源，快照健康降级为 UNKNOWN 而不是沿用旧值。
    assert versioned.snapshot.health_status is HealthStatus.UNKNOWN
    assert versioned.snapshot.observation_sequence == 3


def test_runtime_store_rotates_credential_without_changing_profile_or_snapshot(store) -> None:
    store.register_remote(_profile("runtime:a"), _snapshot("runtime:a"), _credential("runtime:a"))
    before_profile = store.get_profile("runtime:a")
    before_snapshot = store.get_snapshot("runtime:a")

    store.rotate_credential(_credential("runtime:a", credential_id="rc_rotated"))

    assert store.get_credential("runtime:a").credential_id == "rc_rotated"
    assert store.get_profile("runtime:a") == before_profile
    assert store.get_snapshot("runtime:a") == before_snapshot


def test_runtime_store_rotation_requires_an_existing_credential(store) -> None:
    store.register(_profile("runtime:a"), _snapshot("runtime:a"))
    with pytest.raises(KeyError):
        store.rotate_credential(_credential("runtime:a", credential_id="rc_new"))


def test_runtime_store_register_remote_writes_profile_snapshot_and_credential_as_one_unit(store) -> None:
    versioned = store.register_remote(
        _profile("runtime:a"), _snapshot("runtime:a"), _credential("runtime:a")
    )
    assert versioned.version == 1
    assert store.get_credential("runtime:a").credential_id == "rc_runtime:a"


def test_runtime_store_delete_removes_runtime_snapshot_models_credentials_and_nonces(store) -> None:
    profile = _profile("runtime:marketplace", kind=RuntimeKind.MODEL_SERVER, provider="demo", modelIds=["chat"])
    store.register_remote(profile, _snapshot(profile.runtime_id), _credential(profile.runtime_id))
    store.upsert_model_endpoint(ModelEndpointProfile(
        endpointId="model:runtime:marketplace:chat", runtimeId=profile.runtime_id,
        provider="demo", model="chat",
    ))
    now = datetime.now(timezone.utc)
    store.consume_nonce(profile.runtime_id, "once", now + timedelta(minutes=1), now=now)

    store.delete_runtime(profile.runtime_id)

    with pytest.raises(KeyError):
        store.get_profile(profile.runtime_id)
    with pytest.raises(KeyError):
        store.get_model_endpoint("model:runtime:marketplace:chat")
    with pytest.raises(KeyError):
        store.get_credential(profile.runtime_id)


def test_runtime_store_register_remote_rolls_back_when_credential_write_fails(store) -> None:
    store.register_remote(_profile("runtime:a"), _snapshot("runtime:a"), _credential("runtime:a"))
    with pytest.raises(ValueError):
        store.register_remote(
            _profile("runtime:b"),
            _snapshot("runtime:b"),
            _credential("runtime:b", credential_id="rc_runtime:a"),
        )
    with pytest.raises(KeyError):
        store.get_profile("runtime:b")


def test_model_endpoint_upsert_detects_changes_and_bumps_version(store) -> None:
    endpoint = ModelEndpointProfile(
        endpointId="model:zhipu/glm-4.6",
        provider="zhipu",
        model="glm-4.6",
        contextWindowTokens=200_000,
    )
    _, created = store.upsert_model_endpoint(endpoint)
    assert created

    _, unchanged = store.upsert_model_endpoint(endpoint)
    assert not unchanged

    updated, changed = store.upsert_model_endpoint(
        endpoint.model_copy(update={"context_window_tokens": 128_000})
    )
    assert changed and updated.version == 2

    store.delete_model_endpoint(endpoint.endpoint_id)
    with pytest.raises(KeyError):
        store.get_model_endpoint(endpoint.endpoint_id)


def test_sqlite_store_self_heals_by_dropping_legacy_resource_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "plane.sqlite3"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE resources (resource_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    legacy.execute(
        "INSERT INTO resources VALUES ('worker-1', ?)", ('{"resourceType": "worker"}',)
    )
    legacy.commit()
    legacy.close()

    store = SQLiteResourceStore(db_path)
    store.register(_profile("runtime:fresh"), _snapshot("runtime:fresh"))
    profiles = [profile.runtime_id for profile in store.list_profiles()]
    store.close()

    assert profiles == ["runtime:fresh"]
    check = sqlite3.connect(db_path)
    tables = {
        row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    check.close()
    assert "resources" not in tables


def test_nonce_can_be_consumed_only_once_until_expiry(store) -> None:
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=5)
    assert store.consume_nonce("runtime:a", "nonce-1", expiry, now=now)
    assert not store.consume_nonce("runtime:a", "nonce-1", expiry, now=now)
    # 不同 Runtime 的同名 nonce 互不干扰。
    assert store.consume_nonce("runtime:b", "nonce-1", expiry, now=now)
    # 过期 nonce 在下一次消费时被清理后可复用。
    later = expiry + timedelta(seconds=1)
    assert store.consume_nonce("runtime:a", "nonce-1", expiry + timedelta(minutes=6), now=later)

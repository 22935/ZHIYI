"""Shared resource-store contract and restart semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from components.resource.store import (
    InMemoryResourceStore,
    ResourceCredentialRecord,
    SQLiteResourceStore,
    VersionConflict,
)
from contracts.resource import ResourceHealthStatus, ResourceProfile, ResourceSnapshot, ResourceType


def _profile(resource_id: str) -> ResourceProfile:
    return ResourceProfile(
        resourceId=resource_id,
        resourceType=ResourceType.AGENT,
        capabilities=["analyse"],
        domains=["general"],
    )


def _snapshot(resource_id: str, *, slots: int = 1) -> ResourceSnapshot:
    return ResourceSnapshot(
        resourceId=resource_id,
        availableSlots=slots,
        utilization=0.0,
        healthStatus=ResourceHealthStatus.ONLINE,
    )


@pytest.fixture(params=("memory", "sqlite"))
def store(request, tmp_path: Path):
    value = (
        InMemoryResourceStore()
        if request.param == "memory"
        else SQLiteResourceStore(tmp_path / "resources.sqlite3")
    )
    yield value
    close = getattr(value, "close", None)
    if callable(close):
        close()


def test_resource_store_contract_create_get_list_duplicate_and_cas(store) -> None:
    original = _snapshot("b")
    first = store.register(_profile("b"), original)
    store.register(_profile("a"), _snapshot("a"))

    assert first.version == 1
    assert store.get_profile("b").resource_type is ResourceType.AGENT
    assert [item.resource_id for item in store.list_profiles()] == ["a", "b"]
    assert store.register(_profile("b"), original).version == 1

    updated = store.update_snapshot(_snapshot("b", slots=0), expected_version=1)
    assert updated.version == 2
    assert updated.snapshot.available_slots == 0
    scaled = store.update_capacity("b", 4, expected_capacity=1)
    assert scaled.version == 3
    assert scaled.snapshot.available_slots == 3
    assert scaled.snapshot.utilization == 0.25
    assert store.get_profile("b").capacity == 4
    with pytest.raises(VersionConflict):
        store.update_capacity("b", 5, expected_capacity=1)
    with pytest.raises(VersionConflict):
        store.update_snapshot(_snapshot("b"), expected_version=1)
    with pytest.raises(ValueError, match="already registered"):
        store.register(_profile("b").model_copy(update={"capacity": 2}), _snapshot("b"))


def test_sqlite_restart_keeps_profile_but_downgrades_snapshot_health(tmp_path: Path) -> None:
    path = tmp_path / "resources.sqlite3"
    first = SQLiteResourceStore(path)
    first.register(_profile("worker-1"), _snapshot("worker-1"))
    first.close()

    restarted = SQLiteResourceStore(path)
    try:
        assert restarted.get_profile("worker-1") == _profile("worker-1")
        restored = restarted.get_snapshot("worker-1")
        assert restored.version == 1
        assert restored.snapshot.health_status is ResourceHealthStatus.UNKNOWN
    finally:
        restarted.close()


def test_resource_store_rotates_credential_without_changing_profile_or_snapshot(store) -> None:
    profile = _profile("credential-rotation")
    original_snapshot = _snapshot("credential-rotation")
    store.register(profile, original_snapshot)
    original = ResourceCredentialRecord(
        resource_id="credential-rotation",
        credential_id="rc_old",
        owner_scope="tenant-a",
        secret_digest="old-digest",
        encrypted_secret="old-encrypted",
        created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    replacement = ResourceCredentialRecord(
        resource_id="credential-rotation",
        credential_id="rc_new",
        owner_scope="tenant-a",
        secret_digest="new-digest",
        encrypted_secret="new-encrypted",
        created_at=datetime(2026, 9, 3, 0, 1, tzinfo=timezone.utc),
    )
    store.save_credential(original)

    store.rotate_credential(replacement)

    assert store.get_credential("credential-rotation") == replacement
    assert store.get_profile("credential-rotation") == profile
    assert store.get_snapshot("credential-rotation").snapshot == original_snapshot
    assert store.get_snapshot("credential-rotation").version == 1


def test_resource_store_rotation_requires_an_existing_credential(store) -> None:
    profile = _profile("credential-without-current")
    snapshot = _snapshot("credential-without-current")
    store.register(profile, snapshot)
    replacement = ResourceCredentialRecord(
        resource_id="credential-without-current",
        credential_id="rc_new",
        owner_scope="tenant-a",
        secret_digest="new-digest",
        encrypted_secret="new-encrypted",
        created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )

    with pytest.raises(KeyError, match="credential not found"):
        store.rotate_credential(replacement)

    assert store.get_profile("credential-without-current") == profile
    assert store.get_snapshot("credential-without-current").snapshot == snapshot


def test_resource_store_register_remote_writes_profile_snapshot_and_credential_as_one_unit(store) -> None:
    profile = _profile("remote-atomic")
    snapshot = _snapshot("remote-atomic")
    credential = ResourceCredentialRecord(
        resource_id="remote-atomic",
        credential_id="rc-atomic",
        owner_scope="tenant-a",
        secret_digest="digest",
        encrypted_secret="encrypted",
        created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )

    registered = store.register_remote(profile, snapshot, credential)

    assert registered.version == 1
    assert store.get_profile("remote-atomic") == profile
    assert store.get_snapshot("remote-atomic").snapshot == snapshot
    assert store.get_credential("remote-atomic") == credential


def test_resource_store_register_remote_rolls_back_when_credential_write_fails(store) -> None:
    store.register(_profile("existing"), _snapshot("existing"))
    store.save_credential(ResourceCredentialRecord(
        resource_id="existing",
        credential_id="rc-duplicate",
        owner_scope="tenant-a",
        secret_digest="digest",
        encrypted_secret="encrypted",
        created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
    ))
    candidate = ResourceCredentialRecord(
        resource_id="remote-rollback",
        credential_id="rc-duplicate",
        owner_scope="tenant-a",
        secret_digest="digest-2",
        encrypted_secret="encrypted-2",
        created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
    )

    with pytest.raises((ValueError, KeyError)):
        store.register_remote(_profile("remote-rollback"), _snapshot("remote-rollback"), candidate)

    with pytest.raises(KeyError, match="unknown resource"):
        store.get_profile("remote-rollback")
    assert store.get_credential("existing").credential_id == "rc-duplicate"

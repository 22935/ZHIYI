"""资源平面生命周期审计行为。"""

from __future__ import annotations

from components.resource.application.resource_plane import ResourcePlane
from components.resource.infrastructure.audit_store import InMemoryResourceAuditStore
from contracts.resource import HealthStatus, Placement, ResourceEndpoint, RuntimeKind, RuntimeProfile, RuntimeSnapshot, TrustLevel


def _profile() -> RuntimeProfile:
    return RuntimeProfile(
        runtimeId="runtime:audit:test",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:audit:test",
        placement=Placement.EDGE,
        trust=TrustLevel.TRUSTED,
        ownerScope="tenant-a",
        capabilities=["tool.invoke"],
        endpoint=ResourceEndpoint(protocol="https", address="https://edge.example.test/execute"),
        capacity=1,
    )


def _snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        runtimeId="runtime:audit:test",
        availableSlots=1,
        utilization=0.0,
        healthStatus=HealthStatus.UNKNOWN,
    )


def test_resource_plane_records_registration_and_rotation_audit_events() -> None:
    plane = ResourcePlane(audit_store=InMemoryResourceAuditStore())
    plane.ensure_node(
        "node:audit:test",
        placement=Placement.EDGE,
        trust=TrustLevel.TRUSTED,
        owner_scope="tenant-a",
    )

    issued = plane.register_remote_runtime(_profile(), _snapshot())
    plane.rotate_runtime_credential(issued.resource_id)

    events = plane.audit_events(issued.resource_id)
    assert [(event.kind, event.resource_id) for event in events] == [
        ("runtime_registered", "runtime:audit:test"),
        ("credential_rotated", "runtime:audit:test"),
    ]
    assert all("secret" not in event.metadata for event in events)
    assert issued.secret not in repr(events)


def test_sqlite_audit_reopens_and_filters(tmp_path):
    from components.resource.infrastructure.audit_store import SQLiteResourceAuditStore
    from components.resource.domain.audit import ResourceAuditEvent
    from datetime import datetime, timezone
    path = tmp_path / "audit.db"
    store = SQLiteResourceAuditStore(path)
    store.append(ResourceAuditEvent("registered", "a", datetime.now(timezone.utc)))
    store.append(ResourceAuditEvent("registered", "b", datetime.now(timezone.utc)))
    store.close()
    store = SQLiteResourceAuditStore(path)
    assert [e.resource_id for e in store.list("a")] == ["a"]
    assert [e.resource_id for e in store.list(limit=1)] == ["b"]
    assert store.counts() == {"registered": 2}
    assert store.counts("a") == {"registered": 1}
    store.close()


def test_rejected_sequence_and_cas_conflict_are_audited(monkeypatch):
    import pytest
    from components.resource.infrastructure.runtime_store import StaleResourceObservation, VersionConflict
    plane = ResourcePlane()
    plane.ensure_node("node:audit:test", placement=Placement.EDGE, trust=TrustLevel.TRUSTED, owner_scope="tenant-a")
    plane.register_remote_runtime(_profile(), _snapshot())
    with pytest.raises(StaleResourceObservation):
        plane.observe_remote_runtime("runtime:audit:test", available_slots=1, utilization=0, observation_sequence=0)
    def conflict(*args, **kwargs):
        raise VersionConflict("conflict")
    monkeypatch.setattr(plane.store, "update_snapshot", conflict)
    with pytest.raises(VersionConflict):
        plane.observe_remote_runtime("runtime:audit:test", available_slots=1, utilization=0, observation_sequence=1)
    assert [e.kind for e in plane.audit_events("runtime:audit:test")][-2:] == ["observation_rejected", "snapshot_conflict"]


def test_audit_store_failure_does_not_mask_committed_registration():
    class UnavailableAuditStore:
        def append(self, event):
            raise OSError("unavailable")
    plane = ResourcePlane(audit_store=UnavailableAuditStore())
    plane.ensure_node("node:audit:test", placement=Placement.EDGE, trust=TrustLevel.TRUSTED, owner_scope="tenant-a")
    issued = plane.register_remote_runtime(_profile(), _snapshot())
    assert plane.runtime(issued.resource_id).runtime_id == issued.resource_id

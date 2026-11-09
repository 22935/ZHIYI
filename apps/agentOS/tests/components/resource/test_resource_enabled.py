"""Runtime 启停合同：调度开关只影响候选资格，不改观测与凭据。"""

import pytest

from components.scheduler.binder import ResourceBinder
from components.resource.application.resource_plane import ResourcePlane
from contracts.resource import (
    ExecutionRequirement,
    Placement,
    RuntimeKind,
    RuntimeProfile,
    TrustLevel,
)


def _plane_with_runtime(capacity: int = 2) -> ResourcePlane:
    plane = ResourcePlane()
    plane.ensure_node("node:edge-1", placement=Placement.EDGE, trust=TrustLevel.TRUSTED)
    plane.register_runtime(RuntimeProfile(
        runtimeId="runtime:edge-exec-1",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-1",
        placement=Placement.EDGE,
        capabilities=["repo.read"],
        trust=TrustLevel.TRUSTED,
        capacity=capacity,
    ))
    return plane


def _mark_healthy(plane: ResourcePlane) -> None:
    plane.heartbeat_runtime("runtime:edge-exec-1")


def test_set_enabled_flips_profile_without_touching_snapshot_or_credential() -> None:
    plane = _plane_with_runtime()
    _mark_healthy(plane)
    before = plane.runtime_snapshot("runtime:edge-exec-1")

    updated = plane.set_runtime_enabled("runtime:edge-exec-1", enabled=False)

    assert updated.enabled is False
    assert plane.runtime("runtime:edge-exec-1").enabled is False
    # 启停是管理动作：观测快照与版本不受影响。
    assert plane.runtime_snapshot("runtime:edge-exec-1") == before


def test_disabled_runtime_is_not_a_scheduling_candidate() -> None:
    plane = _plane_with_runtime()
    _mark_healthy(plane)
    assert plane.runtime_candidates(["repo.read"])

    plane.set_runtime_enabled("runtime:edge-exec-1", enabled=False)
    assert plane.runtime_candidates(["repo.read"]) == []

    binder = ResourceBinder(plane)
    decisions = binder.evaluate(ExecutionRequirement(requiredCapabilities=["repo.read"]))
    assert decisions and decisions[0].accepted is False
    assert "DISABLED" in decisions[0].reasons


def test_set_enabled_round_trip_restores_scheduling() -> None:
    plane = _plane_with_runtime()
    _mark_healthy(plane)
    plane.set_runtime_enabled("runtime:edge-exec-1", enabled=False)
    plane.set_runtime_enabled("runtime:edge-exec-1", enabled=True)
    assert plane.runtime_candidates(["repo.read"])


def test_set_enabled_unknown_runtime_raises_key_error() -> None:
    plane = ResourcePlane()
    with pytest.raises(KeyError):
        plane.set_runtime_enabled("runtime:missing", enabled=False)

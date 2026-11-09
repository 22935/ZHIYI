"""执行观测合同：执行结果是 Runtime 自己的真实信号。

成功/失败与耗时由执行链路上报，健康 EMA 与快照时延/可靠性同步更新；
利用率与槽位仍归调度器记账，观测不做任何推算。
"""

import pytest

from components.resource.application.resource_plane import ResourcePlane
from contracts.resource import Placement, RuntimeKind, RuntimeProfile, TrustLevel


def _plane() -> ResourcePlane:
    plane = ResourcePlane()
    plane.ensure_node("node:device:local", placement=Placement.DEVICE)
    plane.register_runtime(RuntimeProfile(
        runtimeId="runtime:embedded",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:device:local",
        placement=Placement.DEVICE,
        capabilities=["exec.agents"],
        trust=TrustLevel.HOST_TRUSTED,
        capacity=2,
    ))
    return plane


def test_successful_execution_updates_snapshot_latency_and_reliability() -> None:
    plane = _plane()
    health = plane.observe_execution("runtime:embedded", success=True, latency_ms=250.0)
    snapshot = plane.runtime_snapshot("runtime:embedded").snapshot

    assert health.healthy
    assert snapshot.latency_ms == pytest.approx(250.0)
    assert snapshot.reliability is not None and snapshot.reliability > 0


def test_failed_execution_lowers_reliability_without_faking_online() -> None:
    plane = _plane()
    for _ in range(5):
        health = plane.observe_execution("runtime:embedded", success=False, latency_ms=50.0)

    assert health.reliability < 1.0
    # 失败不会把快照健康伪造为 ONLINE；快照只在真实外部观测时转 ONLINE。
    snapshot = plane.runtime_snapshot("runtime:embedded").snapshot
    from contracts.resource import HealthStatus
    assert snapshot.health_status is not HealthStatus.ONLINE


def test_observation_is_treated_as_activity_signal() -> None:
    plane = _plane()
    before = plane.health_monitor.health("runtime:embedded").last_heartbeat
    assert before is None

    plane.observe_execution("runtime:embedded", success=True, latency_ms=10.0)

    after = plane.health_monitor.health("runtime:embedded").last_heartbeat
    assert after is not None


def test_observe_execution_rejects_unknown_runtime() -> None:
    plane = _plane()
    with pytest.raises(KeyError):
        plane.observe_execution("runtime:missing", success=True, latency_ms=1.0)

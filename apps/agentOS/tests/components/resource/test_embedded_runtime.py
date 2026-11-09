"""进程内 Agent 运行时的资源投影合同。

逻辑 Agent 不是资源：本进程可调用的 Agent 集合整体构成一个 EXECUTION_BACKEND
Runtime，能力为并集、容量为各 Agent 声明容量之和，注册表变化时可重复同步。
"""

from dataclasses import dataclass, field

from components.resource.runtime.embedded_runtime import (
    EMBEDDED_AGENTS_BASE_CAPABILITY,
    EMBEDDED_AGENTS_RUNTIME_ID,
    register_embedded_agents_runtime,
)
from components.resource.application.resource_plane import ResourcePlane
from contracts.resource import Placement, RuntimeKind, TrustLevel


@dataclass
class _AgentProfile:
    agent_id: str
    capabilities: tuple[str, ...] = ()
    capacity: int = 1


@dataclass
class _FakeAgent:
    profile: _AgentProfile


def test_embedded_runtime_aggregates_capabilities_and_capacity() -> None:
    plane = ResourcePlane()
    agents = [
        _FakeAgent(_AgentProfile("analyst", ("analyse.contract",), 2)),
        _FakeAgent(_AgentProfile("writer", ("write.report",), 1)),
    ]

    profile = register_embedded_agents_runtime(plane, agents)

    assert profile.runtime_id == EMBEDDED_AGENTS_RUNTIME_ID
    assert profile.kind is RuntimeKind.EXECUTION_BACKEND
    assert profile.placement is Placement.DEVICE
    assert profile.trust is TrustLevel.HOST_TRUSTED
    assert EMBEDDED_AGENTS_BASE_CAPABILITY in profile.capabilities
    assert "analyse.contract" in profile.capabilities
    assert "write.report" in profile.capabilities
    # BindingManifest 对单 Agent 步骤以 agent:<role> 锚定角色，嵌入式后端必须暴露它。
    assert "agent:analyst" in profile.capabilities
    assert "agent:reviewer" not in profile.capabilities
    assert profile.capacity == 3
    assert plane.runtime(EMBEDDED_AGENTS_RUNTIME_ID) == profile


def test_embedded_runtime_resyncs_when_registry_changes() -> None:
    plane = ResourcePlane()
    register_embedded_agents_runtime(plane, [
        _FakeAgent(_AgentProfile("analyst", ("analyse.contract",), 2)),
    ])
    profile = register_embedded_agents_runtime(plane, [
        _FakeAgent(_AgentProfile("analyst", ("analyse.contract",), 2)),
        _FakeAgent(_AgentProfile("reviewer", ("review.legal",), 1)),
    ])

    assert "review.legal" in profile.capabilities
    assert profile.capacity == 3
    assert plane.runtime(EMBEDDED_AGENTS_RUNTIME_ID).capabilities == profile.capabilities


def test_embedded_runtime_is_a_scheduling_candidate_for_declared_capabilities() -> None:
    plane = ResourcePlane()
    register_embedded_agents_runtime(plane, [
        _FakeAgent(_AgentProfile("analyst", ("analyse.contract",), 1)),
    ])
    plane.heartbeat_runtime(EMBEDDED_AGENTS_RUNTIME_ID)

    candidates = plane.runtime_candidates(["analyse.contract"])
    assert [candidate.profile.runtime_id for candidate in candidates] == [EMBEDDED_AGENTS_RUNTIME_ID]
    # 未声明的能力不构成候选资格。
    assert plane.runtime_candidates(["shell.exec"]) == []

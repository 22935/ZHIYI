"""进程内逻辑 Agent 运行时：作为 EXECUTION_BACKEND 注册进资源平面。

逻辑 Agent（Role）不是资源；本进程内可调用的 Agent 集合整体构成一个
执行后端。绑定选择的是这个后端，"具体由哪个逻辑 Agent 执行"仍由执行器
按 Planner 提示与能力解析，两层决策互不越界。

该适配器只将当前进程可见的 Agent 注册表投影为一个可调度 Runtime，不改变
具体 Agent 的调用路由或生命周期管理。
"""

from __future__ import annotations

from contracts.resource import (
    HealthStatus,
    Placement,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)

from .local_runtime import DEFAULT_LOCAL_RUNTIME_NODE_ID
from .service import ResourcePlane

EMBEDDED_AGENTS_RUNTIME_ID = "runtime:embedded-agents"
EMBEDDED_AGENTS_BASE_CAPABILITY = "exec.agents"


def register_embedded_agents_runtime(
    plane: ResourcePlane,
    agents,
) -> RuntimeProfile:
    """把当前进程内 Agent 注册表投影为一个 Device 执行后端。

    能力集是全部可见逻辑 Agent 能力的并集，容量是各 Agent 声明容量之和；
    每个逻辑 Agent 同时以 ``agent:<role>`` 能力暴露，与 BindingManifest
    对单 Agent 步骤的角色锚点（``agent:<planned_agent_id>``）对接。注册表
    变化时重复调用即可完成同步（引导路径允许更新）。
    """
    # 基础能力标识让调度器能够选择整个嵌入式执行后端。
    capabilities: set[str] = {EMBEDDED_AGENTS_BASE_CAPABILITY}
    capacity = 0
    for agent in agents:
        profile = getattr(agent, "profile", None)
        if profile is None:
            continue
        capabilities.update(
            str(item).strip().lower()
            for item in (profile.capabilities or [])
            if str(item).strip()
        )
        agent_id = str(
            getattr(profile, "agent_id", "") or getattr(profile, "agent_name", "") or ""
        ).strip()
        if agent_id:
            capabilities.add(f"agent:{agent_id.lower()}")
        # 容量至少为一，兼容未声明容量的旧 Agent 画像。
        capacity += max(1, int(getattr(profile, "capacity", 1) or 1))
    profile = RuntimeProfile(
        runtimeId=EMBEDDED_AGENTS_RUNTIME_ID,
        kind=RuntimeKind.EXECUTION_BACKEND,
        displayName="进程内 Agent 运行时",
        nodeId=DEFAULT_LOCAL_RUNTIME_NODE_ID,
        placement=Placement.DEVICE,
        capabilities=sorted(capabilities),
        trust=TrustLevel.HOST_TRUSTED,
        capacity=max(1, capacity),
        enabled=True,
        metadata={"managedBy": "bootstrap", "runtime": "embedded-agents"},
    )
    plane.ensure_node(
        DEFAULT_LOCAL_RUNTIME_NODE_ID,
        placement=Placement.DEVICE,
        display_name="本机设备节点",
        trust=TrustLevel.HOST_TRUSTED,
    )
    # 进程存活即设备节点存活：每次注册同步刷新节点心跳。
    plane.heartbeat_node(DEFAULT_LOCAL_RUNTIME_NODE_ID)
    snapshot = RuntimeSnapshot(
        runtimeId=EMBEDDED_AGENTS_RUNTIME_ID,
        availableSlots=profile.capacity,
        utilization=0.0,
        healthStatus=HealthStatus.UNKNOWN,
    )
    plane.register_runtime(profile, snapshot)
    return profile


# TODO(agent-registry): 注册表支持热更新后，应补充已移除 Agent 能力的回收和正在执行任务的迁移策略。


__all__ = [
    "EMBEDDED_AGENTS_BASE_CAPABILITY",
    "EMBEDDED_AGENTS_RUNTIME_ID",
    "register_embedded_agents_runtime",
]

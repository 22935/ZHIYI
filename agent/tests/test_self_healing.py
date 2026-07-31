"""自愈恢复（故障注入 + 检查点 + 局部重规划）端到端测试。

验证赛题“接受动态注入的异常、无人工干预下自主完成闭环”：
在指定节点注入 timeout/crash/empty_evidence 故障，ACG 执行器经检查点恢复
与局部重规划自动续跑至完成，并留下可审计的恢复轨迹。
"""

from __future__ import annotations

import asyncio

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.core.execution.fault_injection import FaultInjector, FaultType, InjectedFault
from agentos.core.models.types import (
    TraceEventType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry


class _Agent(BaseAgent):
    def __init__(self, name, calls):
        super().__init__(AgentProfile(agentName=name, domain="test", capabilities=[name]))
        self.calls = calls

    async def run(self, context):
        self.calls.append(context.step.step_id)
        return AgentOutput(output={"step": context.step.step_id}, summary="ok")


def _runtime(fault_config=None):
    steps = [
        WorkflowStepDefinition(stepId="a", name="A", agentName="a", nextStepId="b"),
        WorkflowStepDefinition(stepId="b", name="B", agentName="b", nextStepId="c"),
        WorkflowStepDefinition(stepId="c", name="C", agentName="c"),
    ]
    registry = AgentRegistry()
    calls: list[str] = []
    for name in ["a", "b", "c"]:
        registry.register(_Agent(name, calls))
    wf_registry = WorkflowRegistry()
    wf_registry.register(
        WorkflowDefinition(
            workflowId="wf", name="w", domain="test", intent="demo", runtimeEngine="acg", steps=steps
        )
    )
    runtime = WorkflowRuntime(agent_registry=registry, workflow_registry=wf_registry)
    task_input = {"faultInjection": fault_config} if fault_config else {}
    return runtime, calls, task_input


# ---------- FaultInjector 单元 ----------
def test_fault_injector_fires_then_heals():
    inj = FaultInjector.from_config({"step_id": "x", "fault_type": "timeout", "max_triggers": 1})
    assert inj.active
    assert inj.should_fire("x")
    try:
        inj.fire("x")
        assert False, "should raise"
    except InjectedFault as e:
        assert e.fault_type == FaultType.TIMEOUT
    # 达上限后自愈：不再触发
    assert not inj.should_fire("x")
    inj.fire("x")  # 不抛


def test_fault_injector_inactive_without_config():
    assert not FaultInjector.from_config(None).active
    assert not FaultInjector.from_config({}).active


# ---------- 端到端自愈 ----------
def _assert_self_heals_to_completion(fault_type: str):
    async def _run():
        runtime, calls, task_input = _runtime(
            {"step_id": "b", "fault_type": fault_type, "max_triggers": 1}
        )
        task = runtime.create_task(title="x", domain="test", intent="demo", input=task_input)
        run = await runtime.start(task.task_id, workflow_id="wf")

        assert run.status == WorkflowStatus.COMPLETED
        assert calls == ["a", "b", "c"]  # b 在自愈后重跑
        assert run.recovery_count >= 1
        recovered = [e for e in run.trace if e.event_type == TraceEventType.RUN_RECOVERED]
        assert recovered
        assert recovered[0].payload["strategy"] == "local_replan"
        # 检查点应已创建
        assert any(c.step_id == "b" for c in run.checkpoints)

    asyncio.run(_run())


def test_self_heal_timeout():
    _assert_self_heals_to_completion("timeout")


def test_self_heal_crash():
    _assert_self_heals_to_completion("crash")


def test_self_heal_empty_evidence():
    _assert_self_heals_to_completion("empty_evidence")


def test_no_fault_runs_clean():
    async def _run():
        runtime, calls, _ = _runtime(None)
        task = runtime.create_task(title="x", domain="test", intent="demo", input={})
        run = await runtime.start(task.task_id, workflow_id="wf")
        assert run.status == WorkflowStatus.COMPLETED
        assert run.recovery_count == 0
        assert not [e for e in run.trace if e.event_type == TraceEventType.RUN_RECOVERED]

    asyncio.run(_run())

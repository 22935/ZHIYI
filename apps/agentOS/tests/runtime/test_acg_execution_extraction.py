"""PR-8C.2 执行边界提取的特征化测试：Trace Parity、依赖方向与残留守护。

抽象事件序列基线取自提取前的干净实现（同一 fixture 三轮运行完全一致）；
只比较 (event_type, step_id) 对，不比较时间戳、UUID 或易变载荷。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from runtime.workflow_runtime import ExecutionRuntime
from components.executor.value_store import InMemoryExecutionValueStore
from components.memory.store import MemoryStore
from components.mission_manager.store import WorkflowRegistry
from contracts.workflow import (
    ReviewDecision,
    ReviewDecisionType,
    WorkflowDefinition,
    WorkflowStepDefinition,
)
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from support.stores.memory_workflow_store import MemoryWorkflowStore
from support.acg.models import (
    ACGBlueprint,
    ACGEdge,
    ControlNode,
    ControlType,
    ConsensusSpec,
    EdgeType,
    StepNode,
)
from support.acg.planning import ACGResourcePlan, AgentBindingSpec


RUNTIME_SOURCE = Path(__file__).parents[2] / "src" / "runtime"


class _RunAgent(BaseAgent):
    async def run(self, context):
        if context.step.step_id == "extract":
            return AgentOutput(output={"title": "AgentOS", "secret": "hidden"}, summary="extracted")
        return AgentOutput(output={"summary": context.context_pack.data.get("title", "reviewed")}, summary="summarized")


class _VoteAgent(BaseAgent):
    async def run(self, context):
        if context.step.step_id == "left":
            return AgentOutput(output={"vote": True}, summary="approve")
        if context.step.step_id == "right":
            return AgentOutput(output={"vote": False}, summary="reject")
        return AgentOutput(output={"summary": "delivered"}, summary="delivered")


def _runtime_with(workflow: WorkflowDefinition, agent: BaseAgent) -> ExecutionRuntime:
    agents = AgentRegistry()
    agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(workflow)
    # Parity 断言比较完整事件序列，必须隔离跨运行可读的默认 SQLite 记忆库，
    # 否则热库上的历史召回会让序列依赖本机 data/ 目录的累积状态。
    return ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        memory_store=MemoryStore(),
        execution_value_store=InMemoryExecutionValueStore(),
    )


def _sequence(run) -> list[tuple[str, str | None]]:
    return [(event.event_type.value, event.step_id) for event in run.trace]


SEQUENTIAL_EXPECTED = [
    ('task_status_changed', None),
    ('step_scheduled', None),
    ('step_succeeded', 'extract'),
    ('data_consumed', 'extract'),
    ('data_produced', 'extract'),
    ('data_consumed', 'extract'),
    ('data_consumed', 'extract'),
    ('data_produced', 'extract'),
    ('checkpoint_created', None),
    ('step_scheduled', None),
    ('step_succeeded', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_produced', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_produced', 'summarize'),
    ('data_produced', None),
    ('checkpoint_created', None),
    ('run_completed', None),
]

PARALLEL_EXPECTED = [
    ('task_status_changed', None),
    ('step_scheduled', None),
    ('step_succeeded', 'extract'),
    ('data_consumed', 'extract'),
    ('data_produced', 'extract'),
    ('data_consumed', 'extract'),
    ('data_consumed', 'extract'),
    ('data_produced', 'extract'),
    ('checkpoint_created', None),
    ('step_scheduled', None),
    ('step_succeeded', 'branch_b'),
    ('data_consumed', 'branch_b'),
    ('data_produced', 'branch_b'),
    ('data_consumed', 'branch_b'),
    ('data_consumed', 'branch_b'),
    ('data_consumed', 'branch_b'),
    ('data_produced', 'branch_b'),
    ('checkpoint_created', None),
    ('step_scheduled', None),
    ('step_succeeded', 'branch_c'),
    ('data_consumed', 'branch_c'),
    ('data_produced', 'branch_c'),
    ('data_consumed', 'branch_c'),
    ('data_consumed', 'branch_c'),
    ('data_consumed', 'branch_c'),
    ('data_consumed', 'branch_c'),
    ('data_produced', 'branch_c'),
    ('checkpoint_created', None),
    ('step_scheduled', None),
    ('step_succeeded', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_produced', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_consumed', 'summarize'),
    ('data_produced', 'summarize'),
    ('data_produced', None),
    ('checkpoint_created', None),
    ('run_completed', None),
]

REVIEW_INTERRUPTED_EXPECTED = [
    ('task_status_changed', None),
    ('step_scheduled', None),
    ('step_succeeded', 'left'),
    ('data_consumed', 'left'),
    ('data_produced', 'left'),
    ('data_consumed', 'left'),
    ('data_consumed', 'left'),
    ('data_produced', 'left'),
    ('step_succeeded', 'right'),
    ('data_consumed', 'right'),
    ('data_produced', 'right'),
    ('data_consumed', 'right'),
    ('data_consumed', 'right'),
    ('data_produced', 'right'),
    ('review_required', None),
    ('checkpoint_created', None),
]

REVIEW_RESUMED_DELTA_EXPECTED = [
    ('review_decided', 'join'),
    ('step_scheduled', None),
    ('step_succeeded', 'deliver'),
    ('data_consumed', 'deliver'),
    ('data_produced', 'deliver'),
    ('data_consumed', 'deliver'),
    ('data_consumed', 'deliver'),
    ('data_produced', 'deliver'),
    ('data_produced', None),
    ('checkpoint_created', None),
    ('run_completed', None),
]


def test_sequential_acg_trace_parity() -> None:
    runtime = _runtime_with(WorkflowDefinition(
        workflowId="acg-run", name="ACG run", domain="general", runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(
                stepId="extract", name="extract", agentName="runner",
                outputSpec={"type": "object", "properties": {"title": {"type": "string"}}},
            ),
            WorkflowStepDefinition(
                stepId="summarize", name="summarize", agentName="runner",
                input={"from": {"extract": ["title"]}},
                outputSpec={"type": "object", "properties": {"summary": {"type": "string"}}},
            ),
        ],
    ), _RunAgent(AgentProfile(agentName="runner", domain="general")))
    task = runtime.create_mission("sequential", workflow_id="acg-run")
    _, run = runtime.prepare_run(task.mission_id)

    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert completed.status.value == "completed"
    assert _sequence(completed) == SEQUENTIAL_EXPECTED


def test_parallel_dag_trace_parity() -> None:
    runtime = _runtime_with(WorkflowDefinition(
        workflowId="parallel-run", name="parallel", domain="general", runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(
                stepId="extract", name="extract", agentName="runner",
                outputSpec={"type": "object", "properties": {"title": {"type": "string"}}},
            ),
            WorkflowStepDefinition(
                stepId="branch_b", name="branch_b", agentName="runner",
                input={"from": {"extract": ["title"]}},
                outputSpec={"type": "object", "properties": {"summary": {"type": "string"}}},
            ),
            WorkflowStepDefinition(
                stepId="branch_c", name="branch_c", agentName="runner",
                input={"from": {"extract": ["title"]}},
                outputSpec={"type": "object", "properties": {"summary": {"type": "string"}}},
            ),
            WorkflowStepDefinition(
                stepId="summarize", name="summarize", agentName="runner",
                input={"from": {"branch_b": ["summary"], "branch_c": ["summary"]}},
                outputSpec={"type": "object", "properties": {"summary": {"type": "string"}}},
            ),
        ],
    ), _RunAgent(AgentProfile(agentName="runner", domain="general")))
    task = runtime.create_mission("parallel", workflow_id="parallel-run")
    _, run = runtime.prepare_run(task.mission_id)

    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert completed.status.value == "completed"
    assert _sequence(completed) == PARALLEL_EXPECTED


def test_review_interrupt_and_resume_trace_parity() -> None:
    runtime = _runtime_with(WorkflowDefinition(
        workflowId="control-review", name="control review", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="bootstrap", name="bootstrap", agentName="voter")],
    ), _VoteAgent(AgentProfile(agentName="voter", domain="general")))
    blueprint = ACGBlueprint(
        graphId="acg-control-review",
        nodes=[
            StepNode(nodeId="left", outputSpec={"type": "object", "properties": {"vote": {"type": "boolean"}}, "required": ["vote"]}),
            StepNode(nodeId="right", outputSpec={"type": "object", "properties": {"vote": {"type": "boolean"}}, "required": ["vote"]}),
            ControlNode(nodeId="join", controlType=ControlType.CONSENSUS,
                        consensusSpec=ConsensusSpec(participantStepIds=["left", "right"], quorum=2, strategy="majority")),
            StepNode(nodeId="deliver", outputSpec={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}),
        ],
        resourcePlan=ACGResourcePlan(bindings=(
            AgentBindingSpec(stepId="left", plannedAgentId="voter"),
            AgentBindingSpec(stepId="right", plannedAgentId="voter"),
            AgentBindingSpec(stepId="deliver", plannedAgentId="voter"),
        )),
        edges=[
            ACGEdge(sourceId="left", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="right", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="join", targetId="deliver", edgeType=EdgeType.DEPENDENCY),
        ],
    )
    runtime._build_acg_blueprint = lambda *_args, **_kwargs: (blueprint, None, ())
    task = runtime.create_mission("review", workflow_id="control-review")
    _, run = runtime.prepare_run(task.mission_id)

    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status.value == "waiting_review"
    assert _sequence(paused) == REVIEW_INTERRUPTED_EXPECTED

    interrupted_len = len(_sequence(paused))
    resumed = asyncio.run(runtime.apply_review(ReviewDecision(
        runId=run.run_id,
        stepId="join",
        decision=ReviewDecisionType.APPROVED,
        operationId="approve-control",
    )))

    assert resumed.status.value == "completed"
    assert _sequence(resumed)[interrupted_len:] == REVIEW_RESUMED_DELTA_EXPECTED


def test_acg_execution_service_import_boundary() -> None:
    import ast

    source = (RUNTIME_SOURCE / "acg_execution.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "runtime.workflow_runtime" not in imported_modules
    assert "components.planner" not in imported_modules
    for forbidden_name in ("WorkflowRuntime", "ExecutionRuntime", "SemanticPatchRequest", "TaskPlanPatch"):
        assert forbidden_name not in imported_names

    # Planner 语义补丁 API 连文本引用都不应出现，防止后续以字符串形式回引。
    for forbidden_text in ("SemanticPatchRequest", "TaskPlanPatch"):
        assert forbidden_text not in source


def test_workflow_runtime_has_no_acg_execution_residual() -> None:
    source = (RUNTIME_SOURCE / "workflow_runtime.py").read_text(encoding="utf-8")

    for forbidden in (
        "graph.astream(",
        "graph.astream_after_resume(",
        "schedule_ready(",
        "ExecutionBinding(",
        '"node_completed"',
        '"superstep_completed"',
        "ACGNodeRunner(",
    ):
        assert forbidden not in source, f"workflow_runtime.py must not retain {forbidden}"


def test_successful_execution_observes_resource_health() -> None:
    runtime = _runtime_with(WorkflowDefinition(
        workflowId="observed-run", name="observed", domain="general", runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(
                stepId="extract", name="extract", agentName="runner",
                outputSpec={"type": "object", "properties": {"title": {"type": "string"}}},
            ),
        ],
    ), _RunAgent(AgentProfile(agentName="runner", domain="general")))
    task = runtime.create_mission("observed", workflow_id="observed-run")
    _, run = runtime.prepare_run(task.mission_id)

    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert completed.status.value == "completed"
    plane = runtime.resource_plane
    from components.resource.runtime.embedded_runtime import EMBEDDED_AGENTS_RUNTIME_ID

    snapshot = plane.runtime_snapshot(EMBEDDED_AGENTS_RUNTIME_ID)
    # 目录行的延迟/可靠性来自执行观测；观测时间是真实回写而非注册时刻。
    assert snapshot.snapshot.latency_ms is not None
    assert snapshot.snapshot.latency_ms >= 0
    assert snapshot.snapshot.reliability is not None
    assert snapshot.snapshot.observed_at is not None
    assert snapshot.snapshot.utilization == 0.0  # 利用率归调度器记账，这里不得伪造
    health = plane.health_monitor.health(EMBEDDED_AGENTS_RUNTIME_ID)
    assert health.latency_ms is not None
    list_events = getattr(plane.health_monitor.store, "list_events", None)
    if list_events is not None:  # SQLite 生产库持久化事件；内存测试库允许无历史查询
        assert list_events(EMBEDDED_AGENTS_RUNTIME_ID), "execution observation must persist a health event for the trend sparkline"

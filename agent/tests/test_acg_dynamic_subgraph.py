from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, StepNode
from agentos.core.models.types import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.recovery import (
    RecoveryNodeTemplate,
    RecoveryRecipe,
    RecoveryRecipeRegistry,
    RuntimeEventStatus,
    RuntimeEventType,
)
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.progress import ProgressAssembler
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from app.api.agentos_core import create_router


class _HistoryStore(MemoryWorkflowStore):
    def __init__(self):
        super().__init__()
        self.history = []

    def save_run(self, run):
        self.history.append(run.model_copy(deep=True))
        super().save_run(run)


class _StaticAgent(BaseAgent):
    def __init__(self, name: str, domain: str, capability: str, calls: list[str]):
        super().__init__(
            AgentProfile(agentName=name, domain=domain, capabilities=[capability])
        )
        self.calls = calls

    async def run(self, context):
        self.calls.append(context.step.step_id)
        return AgentOutput(
            output={"kind": self.profile.capabilities[0], "accepted": True}
        )


class _GapAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        domain: str,
        capability: str,
        reason_code: str,
        calls: list[str],
    ):
        super().__init__(
            AgentProfile(agentName=name, domain=domain, capabilities=[capability])
        )
        self.reason_code = reason_code
        self.calls = calls
        self.invocations = 0
        self.saw_recovery_output = False

    async def run(self, context):
        self.calls.append(context.step.step_id)
        self.invocations += 1
        if self.invocations == 1:
            return AgentOutput(
                output={
                    "draft": True,
                    "runtimeSignals": [
                        {
                            "type": "EVIDENCE_MISSING",
                            "code": self.reason_code,
                            "targetNodeId": context.step.step_id,
                            "details": {"requiredEvidenceTypes": ["external_evidence"]},
                        }
                    ],
                }
            )
        observed = list(context.memory.observations.values())
        self.saw_recovery_output = any(
            item.get("kind") == "evidence_validation" for item in observed
        )
        return AgentOutput(output={"accepted": True, "usedRecoveryEvidence": True})


def _recipe(reason_code: str, retrieval_logical_name: str) -> RecoveryRecipeRegistry:
    return RecoveryRecipeRegistry(
        [
            RecoveryRecipe(
                recipeId="evidence_retrieval_and_validation.v1",
                version="1",
                triggerEventTypes=[RuntimeEventType.EVIDENCE_MISSING],
                triggerReasonCodes=[reason_code],
                requiredCapabilities=["evidence_retrieval", "evidence_validation"],
                nodeTemplates=[
                    RecoveryNodeTemplate(
                        logicalName=retrieval_logical_name,
                        name="Evidence retrieval",
                        capability="evidence_retrieval",
                    ),
                    RecoveryNodeTemplate(
                        logicalName="evidence_validation",
                        name="Evidence validation",
                        capability="evidence_validation",
                    ),
                ],
            )
        ]
    )


def _run_scenario(
    *,
    domain: str,
    prefix: str,
    reason_code: str,
    retrieval_name: str,
    include_recovery_agents: bool = True,
):
    calls: list[str] = []
    agents = AgentRegistry()
    parse_id = f"{prefix}_parse"
    target_id = f"{prefix}_review"
    report_id = "report"
    gap_agent = _GapAgent("reviewer", domain, "review", reason_code, calls)
    registered_agents = [
        _StaticAgent("parser", domain, "parse", calls),
        gap_agent,
        _StaticAgent("reporter", domain, "report", calls),
    ]
    if include_recovery_agents:
        registered_agents.extend(
            [
                _StaticAgent("retriever", domain, "evidence_retrieval", calls),
                _StaticAgent("validator", domain, "evidence_validation", calls),
            ]
        )
    for agent in registered_agents:
        agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId=f"{prefix}_workflow",
            name=f"{prefix} workflow",
            domain=domain,
            intent="review",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(stepId=parse_id, name="Parse", agentName="parser"),
                WorkflowStepDefinition(stepId=target_id, name="Review", agentName="reviewer"),
                WorkflowStepDefinition(stepId=report_id, name="Report", agentName="reporter"),
            ],
        )
    )
    runtime = WorkflowRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        recovery_recipe_registry=_recipe(reason_code, retrieval_name),
    )
    blueprint = ACGBlueprint(
        graphId=f"{prefix}_graph",
        nodes=[
            StepNode(nodeId=parse_id, name="Parse", agentName="parser", capability="parse"),
            StepNode(nodeId=target_id, name="Review", agentName="reviewer", capability="review"),
            StepNode(nodeId=report_id, name="Report", agentName="reporter", capability="report"),
        ],
        edges=[
            ACGEdge(edgeId=f"{parse_id}_{target_id}", sourceId=parse_id, targetId=target_id),
            ACGEdge(edgeId=f"{target_id}_{report_id}", sourceId=target_id, targetId=report_id),
        ],
    )

    async def execute():
        task = runtime.create_task(
            title=f"{prefix} review",
            domain=domain,
            intent="review",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        return await runtime.start(task.task_id, workflow_id=f"{prefix}_workflow")

    run = asyncio.run(execute())
    return runtime, run, calls, gap_agent, target_id


@pytest.mark.parametrize(
    ("domain", "prefix", "reason_code", "retrieval_name"),
    [
        ("legal_test", "document", "LEGAL_BASIS_MISSING", "evidence_retrieval"),
        (
            "code_test",
            "code",
            "DEPENDENCY_VULNERABILITY_DATA_MISSING",
            "dependency_evidence_retrieval",
        ),
    ],
)
def test_cross_domain_outcome_event_patch_executes_inserted_subgraph(
    domain, prefix, reason_code, retrieval_name
):
    runtime, run, calls, gap_agent, target_id = _run_scenario(
        domain=domain,
        prefix=prefix,
        reason_code=reason_code,
        retrieval_name=retrieval_name,
    )
    graph = run.runtime_graph
    assert graph is not None
    dynamic_nodes = [node for node in graph.nodes if node.created_graph_version == 2]
    event = graph.runtime_events[0]
    progress = ProgressAssembler().assemble(run)
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)
    view = client.get(f"/ai/core/workflows/runs/{run.run_id}/acg").json()
    detail = client.get(f"/ai/core/workflows/runs/{run.run_id}").json()

    assert run.status == WorkflowStatus.COMPLETED
    assert graph.graph_version == 2
    assert len(dynamic_nodes) == 2
    assert all(node.status.value == "completed" for node in dynamic_nodes)
    assert event.status == RuntimeEventStatus.PROCESSED
    assert graph.event_to_patch[event.event_id] == graph.applied_patch_ids[0]
    assert len(graph.get_node(target_id).attempts) == 2
    assert graph.get_node(target_id).attempts[0].logical_completion_accepted is False
    assert graph.get_node(target_id).attempts[0].output["runtimeSignals"]
    assert graph.get_node(target_id).attempts[1].logical_completion_accepted is True
    assert gap_agent.saw_recovery_output is True
    assert calls.count(target_id) == 2
    assert calls[-1] == "report"
    assert len(run.steps) == 5
    assert progress.total_steps == 5
    assert progress.graph_version == 2
    assert progress.dynamic_step_count == 2
    assert run.checkpoints[-1].state_snapshot["runtimeGraph"]["graphVersion"] == 2
    assert view["graphVersion"] == 2
    assert view["dynamicStepCount"] == 2
    assert len(view["acgBlueprint"]["nodes"]) == 5
    assert len(view["appliedPatches"]) == 1
    assert view["runtimeEvents"][0]["status"] == "PROCESSED"
    assert detail["graphVersion"] == 2
    assert detail["dynamicStepCount"] == 2


def test_barrier_applies_only_one_structural_patch_and_next_round_drains_pending_event():
    domain = "parallel_test"
    reason = "SHARED_EVIDENCE_GAP"
    calls: list[str] = []
    agents = AgentRegistry()
    left = _GapAgent("left_reviewer", domain, "review", reason, calls)
    right = _GapAgent("right_reviewer", domain, "review", reason, calls)
    for agent in [
        _StaticAgent("parser", domain, "parse", calls),
        left,
        right,
        _StaticAgent("reporter", domain, "report", calls),
        _StaticAgent("retriever", domain, "evidence_retrieval", calls),
        _StaticAgent("validator", domain, "evidence_validation", calls),
    ]:
        agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="parallel_dynamic",
            name="Parallel dynamic",
            domain=domain,
            intent="review",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(stepId="parse", name="Parse", agentName="parser"),
                WorkflowStepDefinition(stepId="left", name="Left", agentName="left_reviewer"),
                WorkflowStepDefinition(stepId="right", name="Right", agentName="right_reviewer"),
                WorkflowStepDefinition(stepId="report", name="Report", agentName="reporter"),
            ],
        )
    )
    store = _HistoryStore()
    runtime = WorkflowRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=store,
        recovery_recipe_registry=_recipe(reason, "evidence_retrieval"),
    )
    blueprint = ACGBlueprint(
        graphId="parallel_graph",
        nodes=[
            StepNode(nodeId="parse", agentName="parser", capability="parse"),
            StepNode(nodeId="left", agentName="left_reviewer", capability="review"),
            StepNode(nodeId="right", agentName="right_reviewer", capability="review"),
            StepNode(nodeId="report", agentName="reporter", capability="report"),
        ],
        edges=[
            ACGEdge(edgeId="parse_left", sourceId="parse", targetId="left"),
            ACGEdge(edgeId="parse_right", sourceId="parse", targetId="right"),
            ACGEdge(edgeId="left_report", sourceId="left", targetId="report"),
            ACGEdge(edgeId="right_report", sourceId="right", targetId="report"),
        ],
    )

    async def execute():
        task = runtime.create_task(
            title="parallel",
            domain=domain,
            intent="review",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        return await runtime.start(task.task_id, workflow_id="parallel_dynamic")

    run = asyncio.run(execute())
    barrier_v2 = [
        snapshot
        for snapshot in store.history
        if snapshot.runtime_graph is not None
        and snapshot.runtime_graph.graph_version == 2
        and len(snapshot.runtime_graph.runtime_events) == 2
    ]

    assert run.status == WorkflowStatus.COMPLETED
    assert run.runtime_graph.graph_version == 3
    assert len(run.runtime_graph.applied_patches) == 2
    assert barrier_v2
    assert len(barrier_v2[-1].runtime_graph.pending_runtime_event_ids) == 1
    assert run.runtime_graph.pending_runtime_event_ids == []
    assert all(event.status == RuntimeEventStatus.PROCESSED for event in run.runtime_graph.runtime_events)
    assert len(run.runtime_graph.get_node("left").attempts) == 2
    assert len(run.runtime_graph.get_node("right").attempts) == 2


def test_missing_recipe_capability_rejects_patch_without_losing_attempt_facts():
    _, run, _, _, target_id = _run_scenario(
        domain="missing_capability_test",
        prefix="missing",
        reason_code="EXTERNAL_SOURCE_MISSING",
        retrieval_name="evidence_retrieval",
        include_recovery_agents=False,
    )
    graph = run.runtime_graph
    target = graph.get_node(target_id)

    assert run.status == WorkflowStatus.FAILED
    assert graph.graph_version == 1
    assert graph.applied_patch_ids == []
    assert graph.runtime_events[0].status == RuntimeEventStatus.REJECTED
    assert graph.runtime_events[0].status_reason == "AgentNotFound"
    assert target.status.value == "failed"
    assert target.attempts[0].output["runtimeSignals"]
    assert target.attempts[0].logical_completion_accepted is False

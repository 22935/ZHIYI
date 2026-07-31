from __future__ import annotations

import asyncio

import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import (
    ACGBlueprint,
    ACGEdge,
    ControlNode,
    ControlType,
    EdgeActivation,
    StepNode,
)
from agentos.core.models.types import (
    StepStatus,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.progress import ProgressAssembler
from agentos.core.workflow.registry import WorkflowRegistry


class _OutputAgent(BaseAgent):
    def __init__(
        self, name: str, domain: str, output: dict, calls: list[str], *, fail_once: bool = False
    ):
        super().__init__(
            AgentProfile(agentName=name, domain=domain, capabilities=[name])
        )
        self.output = output
        self.calls = calls
        self.fail_once = fail_once

    async def run(self, context):
        self.calls.append(self.profile.agent_name)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("one-shot final failure")
        return AgentOutput(output=dict(self.output))


def _run_branch(
    *, domain: str, decision_key: str, decision_value: str, deep_value: str,
    fail_final_once: bool = False,
):
    calls: list[str] = []
    names = ["classify", "deep", "review", "direct", "final"]
    agents = AgentRegistry()
    for name in names:
        output = {decision_key: decision_value} if name == "classify" else {"result": name}
        agents.register(
            _OutputAgent(
                name,
                domain,
                output,
                calls,
                fail_once=fail_final_once and name == "final",
            )
        )
    workflow = WorkflowDefinition(
        workflowId="conditional_workflow",
        name="Conditional workflow",
        domain=domain,
        intent="review",
        runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(stepId=name, name=name, agentName=name, capability=name)
            for name in names
        ],
    )
    workflows = WorkflowRegistry()
    workflows.register(workflow)
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    blueprint = ACGBlueprint(
        graphId="conditional_runtime_graph",
        nodes=[
            StepNode(nodeId="classify", agentName="classify", capability="classify"),
            ControlNode(
                nodeId="route",
                controlType=ControlType.IF,
                conditionSpec={
                    "sourceNodeId": "classify",
                    "jsonPointer": f"/{decision_key}",
                    "operator": "EQUALS",
                    "cases": {deep_value: "edge_deep", "low": "edge_direct"},
                    "defaultEdgeId": "edge_direct",
                    "valueType": "string",
                },
                branchEdgeIds=["edge_deep", "edge_direct"],
                joinNodeId="join",
            ),
            StepNode(nodeId="deep", agentName="deep", capability="deep"),
            StepNode(nodeId="review", agentName="review", capability="review"),
            StepNode(nodeId="direct", agentName="direct", capability="direct"),
            ControlNode(nodeId="join", controlType=ControlType.PARALLEL),
            StepNode(nodeId="final", agentName="final", capability="final"),
        ],
        edges=[
            ACGEdge(edgeId="classify_route", sourceId="classify", targetId="route"),
            ACGEdge(edgeId="edge_deep", sourceId="route", targetId="deep"),
            ACGEdge(edgeId="deep_review", sourceId="deep", targetId="review"),
            ACGEdge(edgeId="review_join", sourceId="review", targetId="join"),
            ACGEdge(edgeId="edge_direct", sourceId="route", targetId="direct"),
            ACGEdge(edgeId="direct_join", sourceId="direct", targetId="join"),
            ACGEdge(edgeId="join_final", sourceId="join", targetId="final"),
        ],
    )
    snapshot = blueprint.model_dump(by_alias=True, mode="json")

    async def execute():
        task = runtime.create_task(
            title="conditional",
            domain=domain,
            intent="review",
            input={"acgBlueprint": snapshot},
        )
        return await runtime.start(task.task_id, workflow_id=workflow.workflow_id)

    run = asyncio.run(execute())
    assert blueprint.model_dump(by_alias=True, mode="json") == snapshot
    return runtime, run, calls


@pytest.mark.parametrize(
    ("domain", "key", "value", "deep_case", "selected", "skipped"),
    [
        ("legal_conditional_high", "riskLevel", "high", "high", ["deep", "review"], ["direct"]),
        ("legal_conditional_low", "riskLevel", "low", "high", ["direct"], ["deep", "review"]),
        ("code_conditional", "severity", "critical", "critical", ["deep", "review"], ["direct"]),
    ],
)
def test_conditional_branch_executes_only_selected_path(
    domain, key, value, deep_case, selected, skipped
):
    _, run, calls = _run_branch(
        domain=domain,
        decision_key=key,
        decision_value=value,
        deep_value=deep_case,
    )
    graph = run.runtime_graph
    decision = graph.branch_decisions[0]
    progress = ProgressAssembler().assemble(run)

    assert run.status == WorkflowStatus.COMPLETED
    assert graph.graph_version == 2
    assert len(graph.nodes) == 7 and len(graph.edges) == 7
    assert decision.selected_edge_ids == (["edge_deep"] if "deep" in selected else ["edge_direct"])
    assert decision.terminated_edge_ids == (["edge_direct"] if "deep" in selected else ["edge_deep"])
    for node_id in selected:
        assert graph.get_node(node_id).status == StepStatus.COMPLETED
        assert node_id in calls
    for node_id in skipped:
        assert graph.get_node(node_id).status == StepStatus.SKIPPED_BY_CONDITION
        assert node_id not in calls
    assert graph.get_node("join").status == StepStatus.COMPLETED
    assert graph.get_node("final").status == StepStatus.COMPLETED
    assert calls[-1] == "final"
    assert progress.total_steps == 5
    assert progress.completed_steps == 5 - len(skipped)
    assert progress.skipped_by_condition_count == len(skipped)
    assert progress.conditional_decision_count == 1
    assert progress.percent == 100.0
    assert next(edge for edge in graph.edges if edge.edge_id in decision.selected_edge_ids).activation == EdgeActivation.ACTIVE
    assert next(edge for edge in graph.edges if edge.edge_id in decision.terminated_edge_ids).activation == EdgeActivation.TERMINATED
    assert run.checkpoints[-1].state_snapshot["runtimeGraph"]["branchDecisions"]


def test_conditional_checkpoint_resume_keeps_decision_and_does_not_repatch():
    runtime, run, calls = _run_branch(
        domain="conditional_resume",
        decision_key="riskLevel",
        decision_value="high",
        deep_value="high",
        fail_final_once=True,
    )
    assert run.status == WorkflowStatus.FAILED
    checkpoint = next(
        item
        for item in run.checkpoints
        if item.state_snapshot.get("conditionalDecisionCount") == 1
        and item.state_snapshot["runtimeGraph"]["nodes"][2]["status"] == "pending"
    )

    recovered = asyncio.run(
        runtime.resume_from_checkpoint(run_id=run.run_id, checkpoint_id=checkpoint.checkpoint_id)
    )

    assert recovered.status == WorkflowStatus.COMPLETED
    assert recovered.runtime_graph.graph_version == 2
    assert len(recovered.runtime_graph.branch_decisions) == 1
    assert recovered.runtime_graph.get_node("direct").status == StepStatus.SKIPPED_BY_CONDITION
    assert len(recovered.runtime_graph.applied_patches) == 1
    assert calls.count("classify") == 1

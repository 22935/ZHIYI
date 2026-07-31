import pytest

from agentos.agents import AgentRegistry
from agentos.core.acg import (
    ACGBlueprint,
    ACGEdge,
    ControlNode,
    ControlType,
    EdgeActivation,
    StepNode,
    validate_blueprint,
)
from agentos.core.conditions import ConditionEvaluator
from agentos.core.governance.checkpoint import CheckpointStore
from agentos.core.governance.trace import TraceStore
from agentos.core.models.types import (
    StepStatus,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from agentos.core.recovery import (
    DeterministicProposalFactory,
    PatchValidationError,
    RuntimeController,
    PatchConflictError,
    RuntimeGraphPatchCompiler,
)
from agentos.core.run_locks import RunLockManager
from agentos.core.runtime_graph import RuntimeGraph
from agentos.stores.memory_workflow_store import MemoryWorkflowStore


def conditional_blueprint() -> ACGBlueprint:
    return ACGBlueprint(
        graphId="conditional_graph",
        nodes=[
            StepNode(nodeId="source", agentName="source"),
            ControlNode(
                nodeId="route",
                controlType=ControlType.IF,
                conditionSpec={
                    "sourceNodeId": "source",
                    "jsonPointer": "/riskLevel",
                    "operator": "EQUALS",
                    "cases": {"high": "edge_high", "low": "edge_low"},
                    "defaultEdgeId": "edge_low",
                    "valueType": "string",
                },
                branchEdgeIds=["edge_high", "edge_low"],
                joinNodeId="join",
            ),
            StepNode(nodeId="high", agentName="high"),
            StepNode(nodeId="high_review", agentName="high_review"),
            StepNode(nodeId="low", agentName="low"),
            ControlNode(nodeId="join", controlType=ControlType.PARALLEL),
            StepNode(nodeId="after", agentName="after"),
        ],
        edges=[
            ACGEdge(edgeId="source_route", sourceId="source", targetId="route"),
            ACGEdge(edgeId="edge_high", sourceId="route", targetId="high"),
            ACGEdge(edgeId="high_review", sourceId="high", targetId="high_review"),
            ACGEdge(edgeId="high_join", sourceId="high_review", targetId="join"),
            ACGEdge(edgeId="edge_low", sourceId="route", targetId="low"),
            ACGEdge(edgeId="low_join", sourceId="low", targetId="join"),
            ACGEdge(edgeId="join_after", sourceId="join", targetId="after"),
        ],
    )


def _compiled():
    blueprint = conditional_blueprint()
    validate_blueprint(blueprint)
    graph = RuntimeGraph.from_blueprint(run_id="run_conditional", blueprint=blueprint)
    source = graph.get_node("source")
    source.status = StepStatus.COMPLETED
    source.output = {"riskLevel": "high"}
    source.output_version = 1
    control = blueprint.get_node("route")
    evaluation = ConditionEvaluator().evaluate(
        control.condition_spec,
        source.output,
        graph,
        control_node_id=control.node_id,
        join_node_id=control.join_node_id,
        branch_edge_ids=control.branch_edge_ids,
    )
    proposal = DeterministicProposalFactory().propose_conditional(evaluation, graph)
    patch = RuntimeGraphPatchCompiler().compile(proposal, graph)
    return blueprint, graph, proposal, patch


def test_if_edges_start_inactive_and_patch_ids_are_stable():
    _, graph, proposal, patch = _compiled()
    _, second_graph, second_proposal, second_patch = _compiled()

    activations = {edge.edge_id: edge.activation for edge in graph.edges}
    assert activations["edge_high"] == EdgeActivation.INACTIVE
    assert activations["edge_low"] == EdgeActivation.INACTIVE
    assert activations["source_route"] == EdgeActivation.ACTIVE
    assert proposal.proposal_id == second_proposal.proposal_id
    assert patch.patch_id == second_patch.patch_id
    assert graph.ready_set() == []
    assert second_graph.graph_version == 1


async def test_conditional_patch_activates_one_branch_skips_other_and_preserves_shape():
    blueprint, graph, _, patch = _compiled()
    before_nodes = [node.node_id for node in graph.nodes]
    before_edges = [edge.edge_id for edge in graph.edges]
    run = WorkflowRun(
        runId="run_conditional",
        taskId="task_conditional",
        workflowId="workflow_conditional",
        domain="test",
        runtimeEngine="acg",
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[
            WorkflowStep(stepId=node.node_id, name=node.node_id, agentName=node.agent_name)
            for node in blueprint.step_nodes()
        ],
    )
    store = MemoryWorkflowStore()
    store.save_run(run)
    controller = RuntimeController(
        workflow_store=store,
        agent_registry=AgentRegistry(),
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
        lock_manager=RunLockManager(),
    )

    result = await controller.apply_patch(run.run_id, patch)
    replay = await controller.apply_patch(run.run_id, patch)
    persisted = store.get_run(run.run_id)
    applied = persisted.runtime_graph

    assert result.graph_version == 2
    assert replay.applied is False and replay.idempotent_replay is True
    assert [node.node_id for node in applied.nodes] == before_nodes
    assert [edge.edge_id for edge in applied.edges] == before_edges
    assert next(edge for edge in applied.edges if edge.edge_id == "edge_high").activation == EdgeActivation.ACTIVE
    assert next(edge for edge in applied.edges if edge.edge_id == "edge_low").activation == EdgeActivation.TERMINATED
    assert applied.get_node("route").status == StepStatus.COMPLETED
    assert applied.get_node("low").status == StepStatus.SKIPPED_BY_CONDITION
    assert applied.get_node("join").status == StepStatus.PENDING
    assert [node.node_id for node in applied.ready_set()] == ["high"]
    assert len(applied.branch_decisions) == 1
    assert applied.branch_decisions[0].skipped_node_ids == ["low"]
    assert persisted.checkpoints[-1].state_snapshot["conditionalDecisionCount"] == 1


def test_conditional_validator_rejects_stale_output_hash_and_started_branch():
    _, graph, _, patch = _compiled()
    validator = RuntimeController(
        workflow_store=MemoryWorkflowStore(),
        agent_registry=AgentRegistry(),
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
    ).validator

    with pytest.raises(PatchValidationError) as stale:
        validator.validate(graph, patch.model_copy(update={"base_graph_version": 2}), domain="")
    assert stale.value.code == "GRAPH_VERSION_CONFLICT"

    with pytest.raises(PatchValidationError) as version:
        validator.validate(
            graph,
            patch.model_copy(update={"expected_source_output_version": 2}),
            domain="",
        )
    assert version.value.code == "SOURCE_OUTPUT_VERSION_CONFLICT"

    with pytest.raises(PatchValidationError) as input_hash:
        validator.validate(graph, patch.model_copy(update={"input_hash": "stale"}), domain="")
    assert input_hash.value.code == "CONDITION_INPUT_HASH_CONFLICT"

    started = graph.model_copy(deep=True)
    started.get_node("low").status = StepStatus.RUNNING
    with pytest.raises(PatchValidationError) as branch:
        validator.validate(started, patch, domain="")
    assert branch.value.code == "BRANCH_ALREADY_STARTED"


def test_blueprint_rejects_shared_nodes_nested_if_and_loop():
    shared = conditional_blueprint()
    shared.edges.append(ACGEdge(edgeId="low_to_high_review", sourceId="low", targetId="high_review"))
    with pytest.raises(ValueError, match="CONDITIONAL_BRANCH_SHARED_NODE"):
        validate_blueprint(shared)

    loop = conditional_blueprint()
    loop.nodes.append(ControlNode(nodeId="loop", controlType=ControlType.LOOP))
    with pytest.raises(ValueError, match="unsupported control node"):
        validate_blueprint(loop)


async def test_cancelled_run_cannot_activate_condition():
    blueprint, graph, _, patch = _compiled()
    run = WorkflowRun(
        runId="run_conditional",
        taskId="task_conditional",
        workflowId="workflow_conditional",
        domain="test",
        runtimeEngine="acg",
        status=WorkflowStatus.CANCELLED,
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[WorkflowStep(stepId="source", name="source", agentName="source")],
    )
    store = MemoryWorkflowStore()
    store.save_run(run)
    controller = RuntimeController(
        workflow_store=store,
        agent_registry=AgentRegistry(),
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
    )

    with pytest.raises(PatchConflictError) as error:
        await controller.apply_patch(run.run_id, patch)
    assert error.value.code == "RUN_CANCELLED"
    assert store.get_run(run.run_id).runtime_graph.graph_version == 1

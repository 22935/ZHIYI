import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, StepNode
from agentos.core.governance.checkpoint import CheckpointStore
from agentos.core.governance.trace import TraceStore
from agentos.core.models.types import StepStatus, WorkflowRun, WorkflowStep
from agentos.core.recovery import (
    CandidateResolver,
    DeterministicProposalFactory,
    PatchValidationError,
    RecoveryRecipeRegistry,
    RuntimeController,
    RuntimeEvent,
    RuntimeEventPolicy,
    RuntimeEventType,
    RuntimeGraphPatchCompiler,
)
from agentos.core.run_locks import RunLockManager
from agentos.core.runtime_graph import RuntimeAttempt, RuntimeGraph
from agentos.stores.memory_workflow_store import MemoryWorkflowStore


class _Agent(BaseAgent):
    def __init__(self, name):
        super().__init__(
            AgentProfile(agentName=name, domain="test", capabilities=["work"])
        )

    async def run(self, context):
        return AgentOutput(output={})


def _setup():
    agents = AgentRegistry()
    agents.register(_Agent("primary"))
    agents.register(_Agent("alternate"))
    blueprint = ACGBlueprint(
        graphId="graph_1",
        nodes=[
            StepNode(nodeId="prepare", agentName="primary", capability="work"),
            StepNode(
                nodeId="target",
                agentName="primary",
                capability="work",
                retryLimit=2,
            ),
        ],
        edges=[ACGEdge(edgeId="prepare_target", sourceId="prepare", targetId="target")],
    )
    graph = RuntimeGraph.from_blueprint(
        run_id="run_1", blueprint=blueprint, agent_registry=agents, domain="test"
    )
    node = graph.get_node("target")
    attempt = RuntimeAttempt(
        attemptNumber=1,
        graphVersion=1,
        bindingId=node.current_binding["bindingId"],
        agentName="primary",
        status=StepStatus.FAILED,
        error="unavailable",
    )
    node.attempts.append(attempt)
    node.status = StepStatus.RETRYING
    event = RuntimeEvent(
        eventId="event_binding",
        idempotencyKey="event_binding_key",
        runId="run_1",
        graphId="graph_1",
        graphVersion=1,
        eventType=RuntimeEventType.BINDING_UNAVAILABLE,
        runtimeNodeId="target",
        attemptId=attempt.attempt_id,
        bindingId=attempt.binding_id,
        payload={
            "reasonCode": "BINDING_UNAVAILABLE",
            "targetNodeId": "target",
            "failedBindingId": attempt.binding_id,
            "excludedBindingIds": [attempt.binding_id],
            "capability": "work",
        },
    )
    decision = RuntimeEventPolicy(RecoveryRecipeRegistry.with_defaults()).decide(event, graph)
    factory = DeterministicProposalFactory()
    proposal = factory.propose(
        event,
        decision,
        graph,
        RecoveryRecipeRegistry.with_defaults(),
        CandidateResolver(agents),
        domain="test",
    )
    patch = RuntimeGraphPatchCompiler().compile(proposal, graph)
    return agents, blueprint, graph, event, proposal, patch


def test_binding_proposal_patch_ids_are_stable_and_payload_is_mutually_exclusive():
    _, _, graph, event, proposal, patch = _setup()
    agents, _, _, _, _, _ = _setup()
    second_proposal = DeterministicProposalFactory().propose(
        event,
        RuntimeEventPolicy(RecoveryRecipeRegistry.with_defaults()).decide(event, graph),
        graph,
        RecoveryRecipeRegistry.with_defaults(),
        CandidateResolver(agents),
        domain="test",
    )
    second_patch = RuntimeGraphPatchCompiler().compile(second_proposal, graph)

    assert proposal.proposal_id == second_proposal.proposal_id
    assert patch.patch_id == second_patch.patch_id
    assert patch.new_binding.agent_name == "alternate"
    assert patch.add_nodes == [] and patch.add_edges == []
    assert patch.target_node_id is None


async def test_binding_patch_changes_only_binding_and_version_without_creating_attempt():
    agents, blueprint, graph, event, _, patch = _setup()
    before_nodes = [node.spec for node in graph.nodes]
    before_edges = [edge.model_dump(by_alias=True, mode="json") for edge in graph.edges]
    run = WorkflowRun(
        runId="run_1",
        taskId="task_1",
        workflowId="workflow_1",
        domain="test",
        runtimeEngine="acg",
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[
            WorkflowStep(stepId="prepare", name="Prepare", agentName="primary"),
            WorkflowStep(stepId="target", name="Target", agentName="primary"),
        ],
    )
    store = MemoryWorkflowStore()
    store.save_run(run)
    controller = RuntimeController(
        workflow_store=store,
        agent_registry=agents,
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
        lock_manager=RunLockManager(),
    )

    result = await controller.apply_patch("run_1", patch)
    persisted = store.get_run("run_1")
    node = persisted.runtime_graph.get_node("target")

    assert result.graph_version == 2
    assert node.current_binding["agentName"] == "alternate"
    assert node.binding_switch_count == 1
    assert len(node.binding_history) == 2
    assert len(node.attempts) == 1
    assert [item.spec for item in persisted.runtime_graph.nodes] == before_nodes
    assert [edge.model_dump(by_alias=True, mode="json") for edge in persisted.runtime_graph.edges] == before_edges
    assert persisted.get_step("target").agent_name == "alternate"
    assert persisted.checkpoints[-1].state_snapshot["runtimeGraph"]["graphVersion"] == 2
    assert event.event_id in persisted.runtime_graph.processed_event_ids


async def test_binding_patch_save_failure_does_not_pollute_caller_or_persisted_run():
    agents, blueprint, graph, _, _, patch = _setup()
    run = WorkflowRun(
        runId="run_1",
        taskId="task_1",
        workflowId="workflow_1",
        domain="test",
        runtimeEngine="acg",
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[WorkflowStep(stepId="target", name="Target", agentName="primary")],
    )

    class _FailingStore(MemoryWorkflowStore):
        fail = False

        def save_run(self, candidate):
            if self.fail:
                raise OSError("simulated durable write failure")
            super().save_run(candidate)

    store = _FailingStore()
    store.save_run(run)
    store.fail = True
    controller = RuntimeController(
        workflow_store=store,
        agent_registry=agents,
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
        lock_manager=RunLockManager(),
    )

    with pytest.raises(OSError, match="durable write failure"):
        await controller.apply_patch("run_1", patch)

    assert graph.graph_version == 1
    assert graph.get_node("target").current_binding["agentName"] == "primary"
    persisted = store.get_run("run_1")
    assert persisted.runtime_graph.graph_version == 1
    assert persisted.runtime_graph.get_node("target").current_binding["agentName"] == "primary"


def test_binding_validator_rejects_attempt_and_capability_conflicts():
    agents, _, graph, _, _, patch = _setup()
    validator = RuntimeController(
        workflow_store=MemoryWorkflowStore(),
        agent_registry=agents,
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
    ).validator

    with pytest.raises(PatchValidationError) as attempt_error:
        validator.validate(
            graph,
            patch.model_copy(update={"expected_attempt_id": "stale"}),
            domain="test",
        )
    assert attempt_error.value.code == "EXPECTED_ATTEMPT_CONFLICT"

    invalid = patch.model_copy(deep=True)
    invalid.new_binding.capability = "other"
    with pytest.raises(PatchValidationError) as capability_error:
        validator.validate(graph, invalid, domain="test")
    assert capability_error.value.code == "BINDING_CAPABILITY_MISMATCH"

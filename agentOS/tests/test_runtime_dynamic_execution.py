from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, StepNode
from agentos.core.governance.checkpoint import CheckpointStore
from agentos.core.governance.trace import TraceStore
from agentos.core.models.types import StepStatus, WorkflowRun, WorkflowStep
from agentos.core.recovery import (
    CandidateResolver,
    DeterministicProposalFactory,
    RecoveryRecipeRegistry,
    RuntimeController,
    RuntimeEvent,
    RuntimeEventPolicy,
    RuntimeEventStatus,
    RuntimeEventType,
    RuntimeGraphPatchCompiler,
)
from agentos.core.run_locks import RunLockManager
from agentos.core.runtime_graph import RuntimeGraph
from agentos.stores.memory_workflow_store import MemoryWorkflowStore


class _Agent(BaseAgent):
    def __init__(self, name: str, capability: str):
        super().__init__(AgentProfile(agentName=name, domain="test", capabilities=[capability]))

    async def run(self, context):
        return AgentOutput(output={})


async def test_patch_checkpoint_persists_event_mapping_and_new_ready_node_once():
    agents = AgentRegistry()
    for name, capability in [
        ("worker", "work"),
        ("retriever", "evidence_retrieval"),
        ("validator", "evidence_validation"),
    ]:
        agents.register(_Agent(name, capability))
    blueprint = ACGBlueprint(
        graphId="graph_1",
        nodes=[
            StepNode(nodeId="prepare", agentName="worker", capability="work"),
            StepNode(nodeId="target", agentName="worker", capability="work"),
        ],
        edges=[ACGEdge(edgeId="prepare_target", sourceId="prepare", targetId="target")],
    )
    graph = RuntimeGraph.from_blueprint(
        run_id="run_1", blueprint=blueprint, agent_registry=agents, domain="test"
    )
    graph.get_node("prepare").status = StepStatus.COMPLETED
    graph.get_node("target").status = StepStatus.RETRYING
    event = RuntimeEvent(
        eventId="event_1",
        idempotencyKey="event_key",
        runId="run_1",
        graphId="graph_1",
        graphVersion=1,
        eventType=RuntimeEventType.EVIDENCE_MISSING,
        runtimeNodeId="target",
        attemptId="attempt_1",
        payload={"reasonCode": "EVIDENCE_MISSING", "targetNodeId": "target"},
    )
    graph.runtime_events.append(event)
    graph.pending_runtime_event_ids.append(event.event_id)
    run = WorkflowRun(
        runId="run_1",
        taskId="task_1",
        workflowId="workflow_1",
        domain="test",
        runtimeEngine="acg",
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[
            WorkflowStep(stepId="prepare", name="Prepare", agentName="worker"),
            WorkflowStep(stepId="target", name="Target", agentName="worker"),
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
    recipes = RecoveryRecipeRegistry.with_defaults()
    decision = RuntimeEventPolicy(recipes).decide(event, graph)
    proposal = DeterministicProposalFactory().propose(
        event, decision, graph, recipes, CandidateResolver(agents), domain="test"
    )
    patch = RuntimeGraphPatchCompiler().compile(proposal, graph)

    candidate, result = controller.apply_patch_to_candidate(run, patch)
    applied_event = candidate.runtime_graph.runtime_event_by_id(event.event_id)
    applied_event.status = RuntimeEventStatus.PROCESSED
    candidate.runtime_graph.pending_runtime_event_ids.clear()
    candidate.runtime_graph.event_to_patch[event.event_id] = patch.patch_id
    controller.create_patch_checkpoint(candidate, patch)
    store.save_run(candidate)
    reloaded = store.get_run("run_1")

    assert result.graph_version == 2
    assert reloaded.runtime_graph.graph_version == 2
    assert reloaded.runtime_graph.event_to_patch == {event.event_id: patch.patch_id}
    assert reloaded.runtime_graph.pending_runtime_event_ids == []
    assert len(reloaded.runtime_graph.ready_set()) == 1
    assert reloaded.runtime_graph.ready_set()[0].created_graph_version == 2
    snapshot = reloaded.checkpoints[-1].state_snapshot
    assert snapshot["runtimeGraph"]["eventToPatch"] == {event.event_id: patch.patch_id}
    assert snapshot["runtimeGraph"]["runtimeEvents"][0]["status"] == "PROCESSED"

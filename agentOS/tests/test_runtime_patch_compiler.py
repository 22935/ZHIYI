from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, EdgeType, StepNode
from agentos.core.models.types import StepStatus
from agentos.core.recovery import (
    CandidateResolver,
    DeterministicProposalFactory,
    RecoveryRecipeRegistry,
    RuntimeEvent,
    RuntimeEventPolicy,
    RuntimeEventType,
    RuntimeGraphPatchCompiler,
)
from agentos.core.runtime_graph import RuntimeGraph


class _Agent(BaseAgent):
    def __init__(self, name: str, capability: str):
        super().__init__(AgentProfile(agentName=name, domain="test", capabilities=[capability]))

    async def run(self, context):
        return AgentOutput(output={})


def _fixtures():
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
        edges=[
            ACGEdge(
                edgeId="prepare_target",
                sourceId="prepare",
                targetId="target",
                edgeType=EdgeType.DEPENDENCY,
            )
        ],
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
    recipes = RecoveryRecipeRegistry.with_defaults()
    decision = RuntimeEventPolicy(recipes).decide(event, graph)
    return agents, graph, event, recipes, decision


def test_proposal_patch_and_runtime_ids_are_stable_and_replace_current_incoming_edges():
    agents, graph, event, recipes, decision = _fixtures()
    factory = DeterministicProposalFactory()
    resolver = CandidateResolver(agents)
    compiler = RuntimeGraphPatchCompiler()

    first_proposal = factory.propose(
        event, decision, graph, recipes, resolver, domain="test"
    )
    second_proposal = factory.propose(
        event, decision, graph, recipes, resolver, domain="test"
    )
    first = compiler.compile(first_proposal, graph)
    second = compiler.compile(second_proposal, graph)

    assert first_proposal.proposal_id == second_proposal.proposal_id
    assert first.patch_id == second.patch_id
    assert [node.node_id for node in first.add_nodes] == [
        node.node_id for node in second.add_nodes
    ]
    assert first.replaced_incoming_edge_ids == ["prepare_target"]
    assert first.expected_node_states == {"target": StepStatus.RETRYING}
    assert first.metadata["recipeVersion"] == "1"
    assert any(edge.source_id == "prepare" for edge in first.add_edges)
    assert any(edge.target_id == "target" for edge in first.add_edges)

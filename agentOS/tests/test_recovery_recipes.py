import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.recovery import (
    CandidateResolver,
    DeterministicProposalFactory,
    EventPolicyAction,
    RecoveryRecipeRegistry,
    RuntimeEvent,
    RuntimeEventPolicy,
    RuntimeEventType,
)
from agentos.core.runtime_graph import RuntimeGraph


class _Agent(BaseAgent):
    def __init__(self, name: str, capabilities: list[str]):
        super().__init__(AgentProfile(agentName=name, domain="test", capabilities=capabilities))

    async def run(self, context):
        return AgentOutput(output={})


def _graph() -> RuntimeGraph:
    return RuntimeGraph.from_blueprint(
        run_id="run_1",
        blueprint=ACGBlueprint(
            graphId="graph_1",
            nodes=[StepNode(nodeId="target", agentName="worker", capability="work")],
        ),
    )


def _event(event_type=RuntimeEventType.EVIDENCE_MISSING, reason="EVIDENCE_MISSING"):
    return RuntimeEvent(
        eventId="event_1",
        idempotencyKey="idem_1",
        runId="run_1",
        graphId="graph_1",
        graphVersion=1,
        eventType=event_type,
        runtimeNodeId="target",
        attemptId="attempt_1",
        payload={"reasonCode": reason, "targetNodeId": "target"},
    )


def test_policy_selects_versioned_evidence_and_contract_recipes():
    registry = RecoveryRecipeRegistry.with_defaults()
    policy = RuntimeEventPolicy(registry)

    evidence = policy.decide(_event(), _graph())
    contract = policy.decide(
        _event(RuntimeEventType.INPUT_CONTRACT_VIOLATION, "MISSING_REQUIRED_FIELD"),
        _graph(),
    )

    assert evidence.action == EventPolicyAction.PROPOSE_PATCH
    assert evidence.recipe_id == "evidence_retrieval_and_validation.v1"
    assert evidence.recipe_version == "1"
    assert contract.recipe_id == "contract_repair.v1"

    agents = AgentRegistry()
    agents.register(_Agent("adapter", ["contract_adapter"]))
    proposal = DeterministicProposalFactory().propose(
        _event(RuntimeEventType.INPUT_CONTRACT_VIOLATION, "MISSING_REQUIRED_FIELD"),
        contract,
        _graph(),
        registry,
        CandidateResolver(agents),
        domain="test",
    )
    assert len(proposal.proposed_nodes) == 1
    assert proposal.proposed_nodes[0].capability == "contract_adapter"


def test_unknown_and_low_confidence_events_do_not_expand_graph():
    policy = RuntimeEventPolicy(RecoveryRecipeRegistry.with_defaults())
    unknown = policy.decide(_event(reason="UNKNOWN_GAP"), _graph())
    low = policy.decide(_event(RuntimeEventType.LOW_CONFIDENCE, "LOW_CONFIDENCE"), _graph())
    assert unknown.action == EventPolicyAction.IGNORE
    assert low.action == EventPolicyAction.IGNORE
    assert low.reason == "IGNORED_NO_RECIPE"


def test_recipe_scope_blocks_reapplication_and_missing_capability_is_rejected():
    recipes = RecoveryRecipeRegistry.with_defaults()
    graph = _graph()
    event = _event()
    policy = RuntimeEventPolicy(recipes)
    decision = policy.decide(event, graph)
    graph.applied_recipe_scopes.append(graph.recipe_scope(decision.recipe_id, "target"))
    assert policy.decide(event, graph).reason == "RECIPE_REAPPLICATION_BLOCKED"

    agents = AgentRegistry()
    agents.register(_Agent("worker", ["work"]))
    graph.applied_recipe_scopes.clear()
    with pytest.raises(KeyError):
        DeterministicProposalFactory().propose(
            event,
            decision,
            graph,
            recipes,
            CandidateResolver(agents),
            domain="test",
        )

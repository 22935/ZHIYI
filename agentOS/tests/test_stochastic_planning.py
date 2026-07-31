from __future__ import annotations

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import EdgeType, validate_blueprint
from agentos.core.planning import CapabilityCatalog, PlanningCapabilityDescriptor, PlanningEngine
from agentos.core.workflow.registry import WorkflowRegistry


class _Agent(BaseAgent):
    def __init__(self, name: str, capability: str, priority: int = 0):
        super().__init__(
            AgentProfile(
                agentName=name,
                domain="test",
                capabilities=[capability],
                bindingPriority=priority,
            )
        )

    async def run(self, context):
        return AgentOutput(output={}, summary="ok")


def _engine() -> PlanningEngine:
    schema = {"type": "object", "required": ["value"]}
    catalog = CapabilityCatalog(
        [
            PlanningCapabilityDescriptor(
                capabilityId="understand",
                displayName="Understand",
                aliases=["understand"],
                outputContract=schema,
                parallelizable=False,
                domainHints=["test"],
            ),
            PlanningCapabilityDescriptor(
                capabilityId="left",
                displayName="Left",
                aliases=["left"],
                dependsOn=["understand"],
                inputContract=schema,
                outputContract=schema,
                planningStage="analysis",
                domainHints=["test"],
            ),
            PlanningCapabilityDescriptor(
                capabilityId="right",
                displayName="Right",
                aliases=["right"],
                dependsOn=["understand"],
                inputContract=schema,
                outputContract=schema,
                planningStage="analysis",
                domainHints=["test"],
            ),
            PlanningCapabilityDescriptor(
                capabilityId="deliver",
                displayName="Deliver",
                aliases=["deliver"],
                dependsOn=["understand"],
                optionalDependencies=["left", "right"],
                inputContract=schema,
                outputContract=schema,
                parallelizable=False,
                domainHints=["test"],
            ),
        ]
    )
    catalog.validate()
    agents = AgentRegistry()
    for capability in ("understand", "left", "right", "deliver"):
        agents.register(_Agent(f"{capability}_primary", capability, priority=20))
    agents.register(_Agent("right_alternate", "right", priority=10))
    return PlanningEngine(
        workflow_registry=WorkflowRegistry(),
        agent_registry=agents,
        capability_catalog=catalog,
    )


def _signature(plan) -> tuple:
    blueprint = plan.blueprint
    nodes = tuple(
        sorted(
            (
                node.node_id,
                node.node_type.value,
                getattr(node, "capability", None),
                getattr(node, "agent_name", None),
            )
            for node in blueprint.nodes
        )
    )
    edges = tuple(
        sorted((edge.source_id, edge.target_id, edge.edge_type.value) for edge in blueprint.edges)
    )
    return nodes, edges


def _plan(seed: int, diversity: str = "balanced"):
    return _engine().plan(
        task_id="task_seeded",
        intent="understand left right deliver",
        domain="test",
        task_type="test",
        force_dynamic=True,
        deterministic_intent=True,
        planning_diversity=diversity,
        planning_seed=seed,
        capability_catalog_revision="catalog_test_v1",
    )


def test_same_seed_produces_same_valid_semantic_blueprint():
    first = _plan(284731)
    second = _plan(284731)

    validate_blueprint(first.blueprint)
    assert _signature(first) == _signature(second)
    assert first.selected_variant_id == second.selected_variant_id
    assert first.planning_seed == second.planning_seed == 284731
    assert first.capability_catalog_revision == "catalog_test_v1"


def test_different_seeds_produce_multiple_valid_variants():
    plans = [_plan(seed, "exploratory") for seed in range(16)]

    assert len({_signature(plan) for plan in plans}) > 1
    assert all(not plan.stochastic_fallback for plan in plans)
    for plan in plans:
        validate_blueprint(plan.blueprint)


def test_mandatory_dependencies_survive_every_seed_and_optional_edges_vary():
    mandatory_pairs = set()
    optional_presence = set()
    for seed in range(20):
        plan = _plan(seed, "exploratory")
        capability_by_node = {
            step.node_id: step.capability for step in plan.blueprint.step_nodes()
        }
        pairs = {
            (capability_by_node[edge.source_id], capability_by_node[edge.target_id])
            for edge in plan.blueprint.edges_of_type(EdgeType.COMMUNICATION)
        }
        mandatory_pairs.add(("understand", "left") in pairs and ("understand", "right") in pairs)
        optional_presence.add(("left", "deliver") in pairs or ("right", "deliver") in pairs)

    assert mandatory_pairs == {True}
    assert optional_presence == {False, True}


def test_stable_mode_preserves_preferred_binding_and_full_optional_dependencies():
    plan = _plan(42, "stable")
    capability_by_node = {
        step.node_id: step.capability for step in plan.blueprint.step_nodes()
    }
    pairs = {
        (capability_by_node[edge.source_id], capability_by_node[edge.target_id])
        for edge in plan.blueprint.edges_of_type(EdgeType.COMMUNICATION)
    }

    assert next(
        step.agent_name for step in plan.blueprint.step_nodes() if step.capability == "right"
    ) == "right_primary"
    assert {("left", "deliver"), ("right", "deliver")}.issubset(pairs)
    assert plan.planning_diversity == "stable"

import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, EdgeType, StepNode
from agentos.core.recovery import (
    PatchValidationError,
    PatchValidator,
    RuntimeGraphPatch,
)
from agentos.core.runtime_graph import (
    AppliedPatchRecord,
    RuntimeGraph,
    RuntimeNodeStatus,
)


class _Agent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="worker",
                domain="test",
                capabilities=["work", "remedy"],
                allowedSkills=["search"],
            )
        )

    async def run(self, context):
        return AgentOutput(output={})


def _registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(_Agent())
    return registry


def _blueprint(*, version: int = 7) -> ACGBlueprint:
    return ACGBlueprint(
        graphId="graph_1",
        taskId="task_1",
        version=version,
        nodes=[
            StepNode(
                nodeId="prepare", name="Prepare", agentName="worker", capability="work"
            ),
            StepNode(
                nodeId="target", name="Target", agentName="worker", capability="work"
            ),
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


def _patch(**updates) -> RuntimeGraphPatch:
    values = {
        "patchId": "patch_1",
        "idempotencyKey": "idem_1",
        "runId": "run_1",
        "graphId": "graph_1",
        "baseGraphVersion": 1,
        "operationType": "ADD_SUBGRAPH",
        "sourceEventId": "event_1",
        "proposalId": "proposal_1",
        "reason": "repair target input",
        "expectedNodeStates": {"target": "pending"},
        "budgetImpact": {"addedNodes": 1, "replanDepthIncrement": 1},
        "targetNodeId": "target",
        "replacedIncomingEdgeIds": ["prepare_target"],
        "addNodes": [
            StepNode(
                nodeId="remedy", name="Remedy", agentName="worker", capability="remedy"
            )
        ],
        "addEdges": [
            ACGEdge(edgeId="prepare_remedy", sourceId="prepare", targetId="remedy"),
            ACGEdge(edgeId="remedy_target", sourceId="remedy", targetId="target"),
        ],
    }
    values.update(updates)
    return RuntimeGraphPatch.model_validate(values)


def _graph() -> RuntimeGraph:
    return RuntimeGraph.from_blueprint(
        run_id="run_1",
        blueprint=_blueprint(),
        agent_registry=_registry(),
        domain="test",
    )


def test_runtime_graph_initialization_is_a_deep_immutable_blueprint_copy():
    blueprint = _blueprint(version=7)
    before = blueprint.model_dump(by_alias=True, mode="json")

    graph = RuntimeGraph.from_blueprint(
        run_id="run_1",
        blueprint=blueprint,
        agent_registry=_registry(),
        domain="test",
    )
    graph.nodes[0].spec["name"] = "changed only at runtime"
    graph.edges[0].metadata["runtime"] = True

    assert blueprint.model_dump(by_alias=True, mode="json") == before
    assert [node.node_id for node in graph.nodes] == ["prepare", "target"]
    assert [edge.edge_id for edge in graph.edges] == ["prepare_target"]
    assert graph.source_blueprint_version == 7
    assert graph.graph_version == 1
    assert graph.nodes[0].current_binding["allowedSkills"] == ["search"]


def test_patch_validator_accepts_insert_before_target_without_mutating_graph_or_blueprint():
    blueprint = _blueprint()
    blueprint_before = blueprint.model_dump(by_alias=True, mode="json")
    graph = RuntimeGraph.from_blueprint(
        run_id="run_1", blueprint=blueprint, agent_registry=_registry(), domain="test"
    )
    graph_before = graph.model_dump(by_alias=True, mode="json")

    candidate = PatchValidator(_registry()).validate(graph, _patch(), domain="test")

    assert graph.model_dump(by_alias=True, mode="json") == graph_before
    assert blueprint.model_dump(by_alias=True, mode="json") == blueprint_before
    assert candidate.graph_version == 1
    assert candidate.get_node("remedy").source_patch_id == "patch_1"
    assert {edge.edge_id for edge in candidate.effective_edges()} == {
        "prepare_remedy",
        "remedy_target",
    }
    assert candidate.edges[0].metadata["supersededByPatchId"] == "patch_1"


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        (
            {
                "addNodes": [
                    StepNode(nodeId="remedy", agentName="worker", capability="remedy"),
                    StepNode(
                        nodeId="remedy_2", agentName="worker", capability="remedy"
                    ),
                ],
                "addEdges": [
                    ACGEdge(
                        edgeId="prepare_remedy", sourceId="prepare", targetId="remedy"
                    ),
                    ACGEdge(edgeId="remedy_2", sourceId="remedy", targetId="remedy_2"),
                    ACGEdge(
                        edgeId="remedy_cycle", sourceId="remedy_2", targetId="remedy"
                    ),
                    ACGEdge(
                        edgeId="remedy_target", sourceId="remedy_2", targetId="target"
                    ),
                ],
                "budgetImpact": {"addedNodes": 2, "replanDepthIncrement": 1},
            },
            "INVALID_RUNTIME_GRAPH",
        ),
        (
            {
                "addEdges": [
                    ACGEdge(
                        edgeId="missing_remedy", sourceId="missing", targetId="remedy"
                    ),
                    ACGEdge(
                        edgeId="remedy_target", sourceId="remedy", targetId="target"
                    ),
                ]
            },
            "EDGE_ENDPOINT_NOT_FOUND",
        ),
        (
            {
                "addNodes": [
                    StepNode(nodeId="remedy", agentName="missing", capability="unknown")
                ]
            },
            "UNREGISTERED_CAPABILITY",
        ),
        (
            {
                "addNodes": [
                    StepNode(nodeId="prepare", agentName="worker", capability="remedy")
                ]
            },
            "NODE_ID_CONFLICT",
        ),
        (
            {
                "addEdges": [
                    ACGEdge(
                        edgeId="prepare_target", sourceId="prepare", targetId="remedy"
                    ),
                    ACGEdge(
                        edgeId="remedy_target", sourceId="remedy", targetId="target"
                    ),
                ]
            },
            "EDGE_ID_CONFLICT",
        ),
    ],
)
def test_patch_validator_rejects_invalid_graphs_capabilities_and_ids(updates, code):
    with pytest.raises(PatchValidationError) as caught:
        PatchValidator(_registry()).validate(_graph(), _patch(**updates), domain="test")
    assert caught.value.code == code


def test_patch_validator_rejects_completed_target():
    graph = _graph()
    graph.get_node("target").status = RuntimeNodeStatus.COMPLETED
    with pytest.raises(PatchValidationError) as caught:
        PatchValidator(_registry()).validate(graph, _patch(), domain="test")
    assert caught.value.code == "TARGET_STATE_CONFLICT"


def test_patch_validator_enforces_node_and_patch_budgets():
    graph = _graph()
    graph.patch_budget.max_added_nodes_per_patch = 0
    with pytest.raises(PatchValidationError) as caught:
        PatchValidator(_registry()).validate(graph, _patch(), domain="test")
    assert caught.value.code == "ADDED_NODE_BUDGET_EXCEEDED"

    graph = _graph()
    graph.applied_patch_ids = ["p1", "p2", "p3"]
    graph.applied_patches = [
        AppliedPatchRecord(
            patchId=f"p{index}",
            idempotencyKey=f"i{index}",
            contentHash=f"c{index}",
            semanticHash=f"s{index}",
            operationType="ADD_SUBGRAPH",
            baseGraphVersion=index,
            resultGraphVersion=index + 1,
            sourceEventId=f"e{index}",
        )
        for index in range(1, 4)
    ]
    with pytest.raises(PatchValidationError) as caught:
        PatchValidator(_registry()).validate(graph, _patch(), domain="test")
    assert caught.value.code == "PATCH_BUDGET_EXCEEDED"


def test_patch_validator_enforces_total_node_and_replan_depth_budgets():
    graph = _graph()
    graph.patch_budget.max_total_runtime_nodes = 2
    with pytest.raises(PatchValidationError) as caught:
        PatchValidator(_registry()).validate(graph, _patch(), domain="test")
    assert caught.value.code == "TOTAL_NODE_BUDGET_EXCEEDED"

    graph = _graph()
    graph.patch_budget.current_replan_depth = graph.patch_budget.max_replan_depth
    with pytest.raises(PatchValidationError) as caught:
        PatchValidator(_registry()).validate(graph, _patch(), domain="test")
    assert caught.value.code == "REPLAN_DEPTH_EXCEEDED"

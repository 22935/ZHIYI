"""Behavior snapshots that protect the ACG boundary extraction."""

from datetime import datetime, timezone

import pytest

from support.acg.validation import ACGValidationError
from support.acg.models import (
    ACGBlueprint,
    ACGEdge,
    EdgeType,
    StepNode,
    TaskSemanticProfile,
    build_default_capability_catalog,
    detect_cycle,
    ready_steps,
    topological_order,
    validate_blueprint,
)
from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec, EvidenceSpec, MemoryAccessSpec


def test_blueprint_serialization_contract_snapshot() -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    blueprint = ACGBlueprint(
        graphId="graph-1",
        missionId="mission-1",
        createdAt=timestamp,
        updatedAt=timestamp,
        nodes=[
            StepNode(
                nodeId="step-1", name="Execute",
            ),
            StepNode(nodeId="step-2", name="Finish"),
        ],
        edges=[
            ACGEdge(edgeId="edge-1", sourceId="step-1", targetId="step-2"),
        ],
        resourcePlan=ACGResourcePlan(
            bindings=(
                AgentBindingSpec(stepId="step-1", plannedAgentId="Agent"),
                AgentBindingSpec(stepId="step-2", plannedAgentId="Agent"),
            ),
            memory=(MemoryAccessSpec(stepId="step-1", memoryId="memory-1", access="read"),),
            evidence=(EvidenceSpec(evidenceId="evidence-1", source="test"),),
            communication=(),
        ),
        metadata={"source": "characterization"},
    )

    payload = blueprint.model_dump(by_alias=True, mode="json")

    assert payload["graphId"] == "graph-1"
    assert payload["createdAt"] == "2026-01-02T03:04:05Z"
    assert payload["updatedAt"] == "2026-01-02T03:04:05Z"
    assert [node["nodeType"] for node in payload["nodes"]] == ["step", "step"]
    assert payload["nodes"][0] == {
        "nodeId": "step-1", "nodeType": "step", "name": "Execute",
        "description": "", "metadata": {}, "stepType": "agent", "goal": "",
        "acceptanceCriteria": [], "sourceRefs": [], "logicalRole": "task",
        "inputSpec": {}, "outputSpec": {}, "capability": None,
        "timeout": 0, "retryLimit": 0, "priority": 0, "status": "draft",
        "reviewRequired": False, "stepId": "step-1", "stepName": "Execute",
    }
    assert [edge["edgeType"] for edge in payload["edges"]] == ["dependency"]
    assert payload["resourcePlan"]["bindings"][0]["plannedAgentId"] == "Agent"
    assert {edge["activation"] for edge in payload["edges"]} == {"active"}
    assert payload["metadata"] == {"source": "characterization"}


def test_workflow_promotion_was_removed() -> None:
    """轻量 workflow 提升通道已退役:公共 API 不再存在。"""
    import support.acg as acg_public
    import components.planner.lowering_input as lowering

    assert not hasattr(acg_public, "promote_workflow_to_acg")
    assert not hasattr(acg_public.models, "promote_workflow_to_acg")
    assert not hasattr(lowering, "promote_workflow_to_acg")
    import importlib.util

    try:
        legacy_found = (
            importlib.util.find_spec("support.acg.legacy.workflow_adapter") is not None
        )
    except ModuleNotFoundError:
        legacy_found = False
    assert not legacy_found


def test_capability_catalog_and_semantic_profile_snapshot() -> None:
    catalog = build_default_capability_catalog()
    available = catalog.available()

    assert tuple(item.capability_id for item in available) == tuple(
        item.capability_id for item in build_default_capability_catalog().available()
    )
    assert catalog.resolve("analysis").capability_id == "analysis"
    assert catalog.expand_dependencies(["artifact_generation"])[-1] == "artifact_generation"

    profile = TaskSemanticProfile(
        primaryGoal="Deliver", requiredCapabilities=["evidence_analysis"],
        estimatedComplexity="medium", domainHint="general", taskTypeHint="report",
    )
    assert profile.model_dump(by_alias=True, mode="json")["estimatedComplexity"] == "medium"
    assert profile.to_summary() == "[general/report] Deliver | caps=evidence_analysis"


def test_blueprint_graph_algorithm_snapshot() -> None:
    blueprint = ACGBlueprint(
        graphId="graph-1",
        nodes=[
            StepNode(nodeId="a"), StepNode(nodeId="b"),
        ],
        edges=[
            ACGEdge(edgeId="a-b", sourceId="a", targetId="b"),
        ],
        resourcePlan=ACGResourcePlan(bindings=(
            AgentBindingSpec(stepId="a", plannedAgentId="agent"),
            AgentBindingSpec(stepId="b", plannedAgentId="agent"),
        )),
    )

    validate_blueprint(blueprint)
    assert detect_cycle(blueprint) == []
    assert topological_order(blueprint) == ["a", "b"]
    assert ready_steps(blueprint, set()) == ["a"]
    assert ready_steps(blueprint, {"a"}) == ["b"]


@pytest.mark.parametrize("agent_count", [0, 2])
def test_validator_requires_exactly_one_agent_binding_spec(agent_count: int) -> None:
    bindings = tuple(
        AgentBindingSpec(stepId="step", plannedAgentId=f"agent-{index}")
        for index in range(agent_count)
    )
    blueprint = ACGBlueprint(
        nodes=[StepNode(nodeId="step")],
        resourcePlan=ACGResourcePlan(bindings=bindings),
    )

    with pytest.raises(ACGValidationError, match="exactly one AgentBindingSpec"):
        validate_blueprint(blueprint)

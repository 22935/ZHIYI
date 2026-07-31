import pytest

from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.conditions import (
    ConditionEvaluationError,
    ConditionEvaluator,
    ConditionSpec,
)
from agentos.core.models.types import StepStatus
from agentos.core.runtime_graph import RuntimeGraph


def _evaluate(spec: ConditionSpec, output):
    graph = RuntimeGraph.from_blueprint(
        run_id="run_condition",
        blueprint=ACGBlueprint(
            graphId="graph_condition",
            nodes=[StepNode(nodeId="source", agentName="source")],
        ),
    )
    source = graph.get_node("source")
    source.status = StepStatus.COMPLETED
    source.output = output
    source.output_version = 3
    return ConditionEvaluator().evaluate(
        spec,
        output,
        graph,
        control_node_id="route",
        join_node_id="join",
        branch_edge_ids=["edge_a", "edge_b"],
    )


@pytest.mark.parametrize(
    ("operator", "value_type", "output", "cases", "expected"),
    [
        ("EQUALS", "string", {"value": "high"}, {"high": "edge_a"}, "edge_a"),
        ("IN", "array", {"value": ["high", "urgent"]}, {"urgent": "edge_b"}, "edge_b"),
        ("EXISTS", "string", {"value": 0}, {"true": "edge_a"}, "edge_a"),
        ("BOOLEAN", "boolean", {"value": False}, {"false": "edge_b"}, "edge_b"),
    ],
)
def test_bounded_operators_select_declared_edge(
    operator, value_type, output, cases, expected
):
    result = _evaluate(
        ConditionSpec(
            sourceNodeId="source",
            jsonPointer="/value",
            operator=operator,
            cases=cases,
            defaultEdgeId="edge_b",
            valueType=value_type,
        ),
        output,
    )

    assert result.selected_edge_ids == [expected]
    assert set(result.selected_edge_ids + result.terminated_edge_ids) == {
        "edge_a",
        "edge_b",
    }
    assert len(result.input_hash) == 64


def test_missing_pointer_uses_default_and_without_default_fails_safely():
    default = ConditionSpec(
        sourceNodeId="source",
        jsonPointer="/missing",
        operator="EQUALS",
        cases={"high": "edge_a"},
        defaultEdgeId="edge_b",
    )
    assert _evaluate(default, {}).selected_edge_ids == ["edge_b"]

    with pytest.raises(ConditionEvaluationError) as error:
        _evaluate(default.model_copy(update={"default_edge_id": None}), {})
    assert error.value.code == "CONDITION_NO_MATCH"


def test_type_mismatch_is_rejected_without_expression_execution():
    spec = ConditionSpec(
        sourceNodeId="source",
        jsonPointer="/value",
        operator="BOOLEAN",
        cases={"true": "edge_a", "false": "edge_b"},
        valueType="boolean",
    )
    with pytest.raises(ConditionEvaluationError) as error:
        _evaluate(spec, {"value": "true"})
    assert error.value.code == "CONDITION_TYPE_MISMATCH"


def test_condition_spec_rejects_non_pointer_and_unknown_value_type():
    with pytest.raises(ValueError):
        ConditionSpec(
            sourceNodeId="source",
            jsonPointer="value",
            operator="EQUALS",
            cases={"x": "edge_a"},
        )
    with pytest.raises(ValueError):
        ConditionSpec(
            sourceNodeId="source",
            jsonPointer="/value",
            operator="EQUALS",
            cases={"x": "edge_a"},
            valueType="callable",
        )

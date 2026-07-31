"""ACG 数据模型与图算法的契约测试。

锁定脊椎数据结构的行为：节点解析、就绪集计算（并行识别）、环检测、
拓扑排序、悬空依赖检查。这些是执行器与规划器共同依赖的不变量。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentos.core.acg import (
    ACGBlueprint,
    ACGEdge,
    ACGValidationError,
    ControlNode,
    ControlType,
    EdgeType,
    EvidenceNode,
    MemoryNode,
    NodeType,
    StepNode,
    detect_cycle,
    find_dangling_dependencies,
    parse_node,
    ready_steps,
    topological_order,
    validate_blueprint,
)


def _diamond() -> ACGBlueprint:
    """A -> {B, C} -> D 的菱形并行图。"""
    bp = ACGBlueprint(objective="diamond")
    for nid in ["A", "B", "C", "D"]:
        bp.nodes.append(StepNode(nodeId=nid, name=nid, agentName="x"))
    bp.edges += [
        ACGEdge(sourceId="A", targetId="B", edgeType=EdgeType.DEPENDENCY),
        ACGEdge(sourceId="A", targetId="C", edgeType=EdgeType.DEPENDENCY),
        ACGEdge(sourceId="B", targetId="D", edgeType=EdgeType.DEPENDENCY),
        ACGEdge(sourceId="C", targetId="D", edgeType=EdgeType.DEPENDENCY),
    ]
    return bp


def test_parse_node_dispatches_by_type():
    step = parse_node({"nodeId": "s1", "nodeType": "step", "agentName": "a"})
    assert isinstance(step, StepNode)
    ctrl = parse_node({"nodeId": "c1", "nodeType": "control", "controlType": "parallel"})
    assert isinstance(ctrl, ControlNode)
    assert ctrl.control_type == ControlType.PARALLEL
    mem = parse_node({"nodeId": "m1", "nodeType": "memory"})
    assert isinstance(mem, MemoryNode)
    ev = parse_node({"nodeId": "e1", "nodeType": "evidence"})
    assert isinstance(ev, EvidenceNode)


def test_blueprint_counts_and_lookup():
    bp = _diamond()
    assert bp.node_count == 4
    assert bp.edge_count == 4
    assert bp.get_node("A").node_id == "A"
    assert bp.has_node("A") and not bp.has_node("Z")
    assert sorted(bp.dependency_sources("D")) == ["B", "C"]


def test_ready_steps_identifies_parallel_branch():
    bp = _diamond()
    assert ready_steps(bp, set()) == ["A"]
    assert sorted(ready_steps(bp, {"A"})) == ["B", "C"]  # 并行就绪
    assert ready_steps(bp, {"A", "B"}) == ["C"]  # C 仅依赖 A，仍就绪；D 还差 C
    assert ready_steps(bp, {"A", "B", "C"}) == ["D"]
    assert ready_steps(bp, {"A", "B", "C", "D"}) == []


def test_topological_order_valid_dag():
    bp = _diamond()
    order = topological_order(bp)
    assert order[0] == "A"
    assert order[-1] == "D"
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")


def test_validate_blueprint_passes_for_dag():
    validate_blueprint(_diamond())  # 不抛即通过


def test_detect_cycle_and_validation_raises():
    bp = _diamond()
    bp.edges.append(ACGEdge(sourceId="D", targetId="A", edgeType=EdgeType.DEPENDENCY))
    cycle = detect_cycle(bp)
    assert "A" in cycle and len(cycle) >= 3
    with pytest.raises(ACGValidationError):
        validate_blueprint(bp)
    with pytest.raises(ACGValidationError):
        topological_order(bp)


def test_dangling_dependency_detected():
    bp = ACGBlueprint(objective="dangling")
    bp.nodes.append(StepNode(nodeId="A", name="A", agentName="x"))
    bp.edges.append(ACGEdge(sourceId="A", targetId="ghost", edgeType=EdgeType.DEPENDENCY))
    assert len(find_dangling_dependencies(bp)) == 1
    with pytest.raises(ACGValidationError):
        validate_blueprint(bp)


def test_non_dependency_edges_do_not_affect_ready_set():
    """通信/记忆/证据边不应影响执行先后。"""
    bp = ACGBlueprint(objective="mixed-edges")
    bp.nodes += [
        StepNode(nodeId="A", name="A", agentName="x"),
        StepNode(nodeId="B", name="B", agentName="x"),
        MemoryNode(nodeId="m1", name="mem"),
    ]
    # 只有通信边和记忆写边，没有依赖边 → A、B 都应同时就绪
    bp.edges += [
        ACGEdge(sourceId="A", targetId="B", edgeType=EdgeType.COMMUNICATION),
        ACGEdge(sourceId="A", targetId="m1", edgeType=EdgeType.WRITE),
    ]
    assert sorted(ready_steps(bp, set())) == ["A", "B"]


def test_blueprint_roundtrip_serialization():
    bp = _diamond()
    bp.nodes.append(ControlNode(nodeId="par", controlType=ControlType.PARALLEL))
    dumped = bp.model_dump(by_alias=True, mode="json")
    restored = ACGBlueprint.model_validate(dumped)
    assert restored.node_count == bp.node_count
    assert isinstance(restored.get_node("par"), ControlNode)
    assert isinstance(restored.get_node("A"), StepNode)


def test_validation_rejects_empty_duplicate_and_invalid_edges():
    with pytest.raises(ACGValidationError, match="at least one Step"):
        validate_blueprint(ACGBlueprint(objective="empty"))

    duplicate = ACGBlueprint(
        objective="duplicate",
        nodes=[
            StepNode(nodeId="same", name="one", agentName="a"),
            StepNode(nodeId="same", name="two", agentName="a"),
        ],
    )
    with pytest.raises(ACGValidationError, match="duplicate node"):
        validate_blueprint(duplicate)

    invalid = ACGBlueprint(
        objective="invalid edge",
        nodes=[
            StepNode(nodeId="a", name="a", agentName="a"),
            StepNode(nodeId="b", name="b", agentName="b"),
        ],
        edges=[ACGEdge(sourceId="a", targetId="b", edgeType=EdgeType.SUPPORT)],
    )
    with pytest.raises(ACGValidationError, match="invalid endpoint types"):
        validate_blueprint(invalid)


def test_validation_rejects_unsupported_control_and_unsafe_communication():
    unsupported = ACGBlueprint(
        objective="unsupported",
        nodes=[
            StepNode(nodeId="a", name="a", agentName="a"),
            ControlNode(nodeId="loop", controlType=ControlType.LOOP),
        ],
    )
    with pytest.raises(ACGValidationError, match="unsupported control"):
        validate_blueprint(unsupported)

    unsafe = ACGBlueprint(
        objective="unsafe communication",
        nodes=[
            StepNode(nodeId="a", name="a", agentName="a"),
            StepNode(nodeId="b", name="b", agentName="b"),
        ],
        edges=[ACGEdge(sourceId="a", targetId="b", edgeType=EdgeType.COMMUNICATION)],
    )
    with pytest.raises(ACGValidationError, match="no execution dependency path"):
        validate_blueprint(unsafe)


def test_validation_rejects_invalid_contract_schema():
    blueprint = ACGBlueprint(
        objective="schema",
        nodes=[
            StepNode(
                nodeId="a",
                name="a",
                agentName="a",
                outputSpec={"type": "definitely-not-a-json-schema-type"},
            )
        ],
    )
    with pytest.raises(ACGValidationError, match="invalid JSON Schema"):
        validate_blueprint(blueprint)

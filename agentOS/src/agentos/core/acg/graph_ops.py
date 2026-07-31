"""ACG 图算法：环检测、拓扑排序、悬空依赖检查、就绪集计算。

这些算法服务两处：
1. 规划器在交付蓝图前做图级验证（非循环性、无悬空依赖）。
2. 执行器在运行时按 DEPENDENCY 边计算“就绪集”，驱动并行调度。

仅依赖 DEPENDENCY 边构建执行 DAG；其它边（通信、记忆读写、证据支撑）
不影响执行先后，由通信器/记忆器/审计器分别消费。
"""

from __future__ import annotations

from typing import Dict, List, Set

from agentos.core.acg.blueprint import ACGBlueprint
from agentos.core.acg.enums import ControlType, EdgeType, NodeType
from agentos.core.acg.nodes import ControlNode, StepNode
from agentos.core.conditions import (
    ConditionEvaluationError,
    conditional_branch_exclusive_nodes,
)
from agentos.core.data_contracts import check_contract_schema


class ACGValidationError(ValueError):
    """ACG 图结构非法（成环或悬空依赖）。"""


def _dependency_adjacency(blueprint: ACGBlueprint) -> Dict[str, List[str]]:
    """构建仅含 STEP/CONTROL 节点的 DEPENDENCY 邻接表（source -> [targets]）。"""
    executable_ids = {
        n.node_id for n in blueprint.nodes
        if n.node_type in {NodeType.STEP, NodeType.CONTROL}
    }
    adjacency: Dict[str, List[str]] = {nid: [] for nid in executable_ids}
    for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY):
        if edge.source_id in executable_ids and edge.target_id in executable_ids:
            adjacency[edge.source_id].append(edge.target_id)
    return adjacency


def detect_cycle(blueprint: ACGBlueprint) -> List[str]:
    """检测 DEPENDENCY 子图是否成环。返回构成环的节点 id 列表（无环则空）。"""
    adjacency = _dependency_adjacency(blueprint)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {nid: WHITE for nid in adjacency}
    stack: List[str] = []

    def visit(node_id: str) -> List[str]:
        color[node_id] = GRAY
        stack.append(node_id)
        for nxt in adjacency.get(node_id, []):
            if color.get(nxt, WHITE) == GRAY:
                # 回边：截取从 nxt 到当前的栈片段作为环
                idx = stack.index(nxt)
                return stack[idx:] + [nxt]
            if color.get(nxt, WHITE) == WHITE:
                found = visit(nxt)
                if found:
                    return found
        color[node_id] = BLACK
        stack.pop()
        return []

    for nid in adjacency:
        if color[nid] == WHITE:
            cycle = visit(nid)
            if cycle:
                return cycle
    return []


def topological_order(blueprint: ACGBlueprint) -> List[str]:
    """Kahn 算法对 DEPENDENCY 子图做拓扑排序。成环则抛 ACGValidationError。"""
    adjacency = _dependency_adjacency(blueprint)
    indegree: Dict[str, int] = {nid: 0 for nid in adjacency}
    for targets in adjacency.values():
        for t in targets:
            indegree[t] = indegree.get(t, 0) + 1

    queue = [nid for nid, deg in indegree.items() if deg == 0]
    order: List[str] = []
    while queue:
        queue.sort()  # 稳定输出，便于测试
        node_id = queue.pop(0)
        order.append(node_id)
        for nxt in adjacency.get(node_id, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(adjacency):
        raise ACGValidationError(f"ACG contains a cycle; topological sort impossible. cycle={detect_cycle(blueprint)}")
    return order


def find_dangling_dependencies(blueprint: ACGBlueprint) -> List[str]:
    """返回引用了不存在节点的 DEPENDENCY 边 id 列表。"""
    dangling: List[str] = []
    for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY):
        if not blueprint.has_node(edge.source_id) or not blueprint.has_node(edge.target_id):
            dangling.append(edge.edge_id)
    return dangling


def _has_dependency_path(blueprint: ACGBlueprint, source_id: str, target_id: str) -> bool:
    adjacency = _dependency_adjacency(blueprint)
    seen: Set[str] = set()
    frontier = [source_id]
    while frontier:
        current = frontier.pop()
        if current == target_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(adjacency.get(current, []))
    return False


def _validate_edge_endpoints(blueprint: ACGBlueprint) -> None:
    allowed = {
        EdgeType.DEPENDENCY: ({NodeType.STEP, NodeType.CONTROL}, {NodeType.STEP, NodeType.CONTROL}),
        EdgeType.COMMUNICATION: ({NodeType.STEP}, {NodeType.STEP}),
        EdgeType.CONTROL_FLOW: ({NodeType.CONTROL}, {NodeType.STEP, NodeType.CONTROL}),
        EdgeType.EXECUTION: ({NodeType.AGENT}, {NodeType.STEP}),
        EdgeType.WRITE: ({NodeType.STEP}, {NodeType.MEMORY}),
        EdgeType.READ: ({NodeType.MEMORY}, {NodeType.STEP}),
        EdgeType.SUPPORT: ({NodeType.EVIDENCE}, {NodeType.STEP}),
    }
    node_types = {node.node_id: node.node_type for node in blueprint.nodes}
    for edge in blueprint.edges:
        if edge.source_id not in node_types or edge.target_id not in node_types:
            raise ACGValidationError(
                f"ACG edge {edge.edge_id} references missing endpoint: "
                f"{edge.source_id} -> {edge.target_id}"
            )
        source_types, target_types = allowed[edge.edge_type]
        if node_types[edge.source_id] not in source_types or node_types[edge.target_id] not in target_types:
            raise ACGValidationError(
                f"ACG edge {edge.edge_id} has invalid endpoint types for {edge.edge_type.value}: "
                f"{node_types[edge.source_id].value} -> {node_types[edge.target_id].value}"
            )
        if edge.edge_type == EdgeType.DEPENDENCY and edge.source_id == edge.target_id:
            raise ACGValidationError(f"ACG dependency edge {edge.edge_id} cannot target itself")


def _validate_conditional_control(blueprint: ACGBlueprint, node: ControlNode) -> None:
    if node.condition_spec is None or not node.join_node_id:
        raise ACGValidationError(f"IF control {node.node_id} requires conditionSpec and joinNodeId")
    if not 2 <= len(node.branch_edge_ids) <= 4:
        raise ACGValidationError(f"IF control {node.node_id} requires 2..4 branch edges")
    if len(set(node.branch_edge_ids)) != len(node.branch_edge_ids):
        raise ACGValidationError(f"IF control {node.node_id} has duplicate branchEdgeIds")
    if not blueprint.has_node(node.condition_spec.source_node_id):
        raise ACGValidationError(f"IF source node missing: {node.condition_spec.source_node_id}")
    if not blueprint.has_node(node.join_node_id):
        raise ACGValidationError(f"IF join node missing: {node.join_node_id}")
    source_node = blueprint.get_node(node.condition_spec.source_node_id)
    if source_node.node_type != NodeType.STEP:
        raise ACGValidationError(f"IF source must be a Step: {source_node.node_id}")
    join_node = blueprint.get_node(node.join_node_id)
    if not isinstance(join_node, ControlNode) or join_node.control_type in {
        ControlType.IF,
        ControlType.LOOP,
    }:
        raise ACGValidationError(f"IF join must be an unconditional Control: {node.join_node_id}")
    incoming = blueprint.incoming(node.node_id, EdgeType.DEPENDENCY)
    if len(incoming) != 1 or incoming[0].source_id != node.condition_spec.source_node_id:
        raise ACGValidationError(f"IF control {node.node_id} requires its single declared source")
    outgoing = [
        edge
        for edge in blueprint.outgoing(node.node_id)
        if edge.edge_type in {EdgeType.DEPENDENCY, EdgeType.CONTROL_FLOW}
    ]
    if {edge.edge_id for edge in outgoing} != set(node.branch_edge_ids):
        raise ACGValidationError(f"IF control {node.node_id} has undeclared branch edges")
    declared = set(node.branch_edge_ids)
    case_edges = set(node.condition_spec.cases.values())
    if not case_edges or not case_edges.issubset(declared):
        raise ACGValidationError(f"IF control {node.node_id} has invalid condition cases")
    if node.condition_spec.default_edge_id and node.condition_spec.default_edge_id not in declared:
        raise ACGValidationError(f"IF control {node.node_id} has invalid defaultEdgeId")
    selectable = case_edges | (
        {node.condition_spec.default_edge_id} if node.condition_spec.default_edge_id else set()
    )
    if selectable != declared:
        raise ACGValidationError(f"IF control {node.node_id} has an unreachable branch")
    try:
        exclusive = conditional_branch_exclusive_nodes(blueprint, node)
    except ConditionEvaluationError as exc:
        raise ACGValidationError(f"{exc.code}: {exc}") from exc
    for node_ids in exclusive.values():
        for node_id in node_ids:
            branch_node = blueprint.get_node(node_id)
            if isinstance(branch_node, ControlNode) and branch_node.control_type in {
                ControlType.IF,
                ControlType.LOOP,
            }:
                raise ACGValidationError(f"nested IF/LOOP is unsupported: {branch_node.node_id}")


def validate_blueprint(blueprint: ACGBlueprint) -> None:
    """规划器交付前的图级验证。非法则抛 ACGValidationError。"""
    step_nodes = blueprint.step_nodes()
    if not step_nodes:
        raise ACGValidationError("ACG must contain at least one Step node")

    node_ids = [node.node_id for node in blueprint.nodes]
    duplicate_nodes = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
    if duplicate_nodes:
        raise ACGValidationError(f"ACG has duplicate node ids: {duplicate_nodes}")
    edge_ids = [edge.edge_id for edge in blueprint.edges]
    duplicate_edges = sorted({edge_id for edge_id in edge_ids if edge_ids.count(edge_id) > 1})
    if duplicate_edges:
        raise ACGValidationError(f"ACG has duplicate edge ids: {duplicate_edges}")

    _validate_edge_endpoints(blueprint)
    cycle = detect_cycle(blueprint)
    if cycle:
        raise ACGValidationError(f"ACG contains a cycle: {' -> '.join(cycle)}")

    for node in blueprint.nodes:
        if isinstance(node, ControlNode) and node.control_type == ControlType.LOOP:
            raise ACGValidationError(f"unsupported control node: {node.node_id} (loop)")
        if isinstance(node, ControlNode) and node.control_type == ControlType.IF:
            _validate_conditional_control(blueprint, node)
        if not isinstance(node, StepNode):
            continue
        if not node.agent_name:
            raise ACGValidationError(f"Step node {node.node_id} has no executable agentName")
        try:
            check_contract_schema(node.output_spec, label=f"{node.node_id}.outputSpec")
        except ValueError as exc:
            raise ACGValidationError(str(exc)) from exc
        input_schema = node.input_spec.get("schema") if isinstance(node.input_spec, dict) else None
        if isinstance(input_schema, dict):
            try:
                check_contract_schema(input_schema, label=f"{node.node_id}.inputSpec.schema")
            except ValueError as exc:
                raise ACGValidationError(str(exc)) from exc
        from_map = node.input_spec.get("from") if isinstance(node.input_spec, dict) else None
        if isinstance(from_map, dict):
            for source_id in from_map:
                source = str(source_id)
                if not blueprint.has_node(source):
                    raise ACGValidationError(f"Step {node.node_id} input.from references missing Step {source}")
                source_node = blueprint.get_node(source)
                if source_node.node_type != NodeType.STEP:
                    raise ACGValidationError(f"Step {node.node_id} input.from source is not a Step: {source}")
                if not _has_dependency_path(blueprint, source, node.node_id):
                    raise ACGValidationError(
                        f"Step {node.node_id} consumes {source} without an execution dependency path"
                    )

    for edge in blueprint.edges_of_type(EdgeType.COMMUNICATION):
        if not _has_dependency_path(blueprint, edge.source_id, edge.target_id):
            raise ACGValidationError(
                f"Communication edge {edge.edge_id} has no execution dependency path: "
                f"{edge.source_id} -> {edge.target_id}"
            )


def ready_steps(blueprint: ACGBlueprint, completed: Set[str]) -> List[str]:
    """计算就绪集：所有 DEPENDENCY 前驱都已完成、且自身未完成的 STEP 节点。

    这是执行器并行调度的核心：返回的全部 step 之间彼此无依赖，可并发执行。
    """
    ready: List[str] = []
    for step in blueprint.step_nodes():
        if step.node_id in completed:
            continue
        deps = blueprint.dependency_sources(step.node_id)
        if all(dep in completed for dep in deps):
            ready.append(step.node_id)
    return ready


__all__ = [
    "ACGValidationError",
    "detect_cycle",
    "topological_order",
    "find_dangling_dependencies",
    "validate_blueprint",
    "ready_steps",
]

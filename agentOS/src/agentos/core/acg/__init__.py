"""ACG（Agentic Computation Graph）核心包。

提供设计书定义的统一计算模型：节点（Step/Agent/Skill/Memory/Evidence/Control）、
边（Dependency/Communication/ControlFlow…）、蓝图（ACGBlueprint）、图算法
（环检测/拓扑排序/就绪集），以及线性工作流自动升格。

这是规划器的产物、执行器的输入，是整个动态异构群体智能架构的脊椎。
"""

from __future__ import annotations

from agentos.core.acg.blueprint import ACGBlueprint
from agentos.core.acg.edges import ACGEdge, EdgeActivation
from agentos.core.acg.enums import (
    ComplexityLevel,
    ControlType,
    EdgeType,
    NodeType,
)
from agentos.core.acg.graph_ops import (
    ACGValidationError,
    detect_cycle,
    find_dangling_dependencies,
    ready_steps,
    topological_order,
    validate_blueprint,
)
from agentos.core.acg.nodes import (
    ACGNode,
    ACGNodeBase,
    AgentNode,
    ControlNode,
    EvidenceNode,
    MemoryNode,
    SkillNode,
    StepNode,
    parse_node,
)
from agentos.core.acg.promote import promote_workflow_to_acg
from agentos.core.conditions import ConditionOperator, ConditionSpec

__all__ = [
    # enums
    "NodeType",
    "EdgeType",
    "ControlType",
    "ComplexityLevel",
    "ConditionOperator",
    "ConditionSpec",
    # nodes
    "ACGNodeBase",
    "StepNode",
    "AgentNode",
    "SkillNode",
    "MemoryNode",
    "EvidenceNode",
    "ControlNode",
    "ACGNode",
    "parse_node",
    # edges
    "ACGEdge",
    "EdgeActivation",
    # blueprint
    "ACGBlueprint",
    # graph ops
    "ACGValidationError",
    "detect_cycle",
    "topological_order",
    "find_dangling_dependencies",
    "validate_blueprint",
    "ready_steps",
    # promotion
    "promote_workflow_to_acg",
]

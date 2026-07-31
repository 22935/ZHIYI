"""ACGBlueprint：智能体计算图蓝图。

对应设计书表2.2《ACG 字段结构》。它是规划器的最终产物，也是执行器、
通信器、记忆器、审计器共同消费的唯一权威总规划图。

蓝图同时承载图级算法：环检测、就绪集计算、悬空依赖检查、拓扑分析。
这些算法是执行器“就绪集调度”和规划器“图验证”的基础。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentos.core.acg.edges import ACGEdge
from agentos.core.acg.enums import ComplexityLevel, EdgeType, NodeType
from agentos.core.acg.nodes import ACGNode, StepNode, parse_node


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ACGBlueprint(BaseModel):
    """智能体计算图蓝图（设计时静态图）。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    graph_id: str = Field(default_factory=lambda: f"acg_{uuid4().hex[:12]}", alias="graphId")
    task_id: Optional[str] = Field(default=None, alias="taskId")
    version: int = 1
    objective: str = ""
    complexity_level: ComplexityLevel = Field(default=ComplexityLevel.SIMPLE, alias="complexityLevel")
    priority: int = 0
    nodes: List[ACGNode] = Field(default_factory=list)
    edges: List[ACGEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=_utc_now, alias="updatedAt")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("nodes", mode="before")
    @classmethod
    def _coerce_nodes(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [parse_node(item) for item in value]
        return value

    # ------------------------------------------------------------------
    # 基础访问
    # ------------------------------------------------------------------
    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def get_node(self, node_id: str) -> ACGNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(f"ACG node not found: {node_id}")

    def has_node(self, node_id: str) -> bool:
        return any(node.node_id == node_id for node in self.nodes)

    def step_nodes(self) -> List[StepNode]:
        return [n for n in self.nodes if n.node_type == NodeType.STEP]  # type: ignore[misc]

    def nodes_of_type(self, node_type: NodeType) -> List[ACGNode]:
        return [n for n in self.nodes if n.node_type == node_type]

    def edges_of_type(self, edge_type: EdgeType) -> List[ACGEdge]:
        return [e for e in self.edges if e.edge_type == edge_type]

    def incoming(self, node_id: str, edge_type: Optional[EdgeType] = None) -> List[ACGEdge]:
        return [
            e for e in self.edges
            if e.target_id == node_id and (edge_type is None or e.edge_type == edge_type)
        ]

    def outgoing(self, node_id: str, edge_type: Optional[EdgeType] = None) -> List[ACGEdge]:
        return [
            e for e in self.edges
            if e.source_id == node_id and (edge_type is None or e.edge_type == edge_type)
        ]

    def dependency_sources(self, node_id: str) -> List[str]:
        """返回某节点在 DEPENDENCY 边上的所有前驱节点 id。"""
        return [e.source_id for e in self.incoming(node_id, EdgeType.DEPENDENCY)]

    def touch(self) -> None:
        self.updated_at = _utc_now()
        self.metadata["nodeCount"] = self.node_count
        self.metadata["edgeCount"] = self.edge_count


__all__ = ["ACGBlueprint"]

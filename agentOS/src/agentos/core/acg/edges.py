"""ACG 边定义（附件一表8/表9）。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.acg.enums import EdgeType


class EdgeActivation(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    TERMINATED = "terminated"


def _edge_id() -> str:
    return f"edge_{uuid4().hex[:10]}"


class ACGEdge(BaseModel):
    """ACG 边。统一描述依赖、通信、控制流等多种关系。

    - DEPENDENCY 边：执行器据此计算就绪集（source 完成后 target 才可执行）。
    - COMMUNICATION 边：通信器据此装配下游输入上下文。
    - CONTROL_FLOW 边：由 Control 节点驱动，可携带激活 condition。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    edge_id: str = Field(default_factory=_edge_id, alias="edgeId")
    source_id: str = Field(alias="sourceId")
    target_id: str = Field(alias="targetId")
    edge_type: EdgeType = Field(default=EdgeType.DEPENDENCY, alias="edgeType")
    condition: str = ""
    activation: EdgeActivation = EdgeActivation.ACTIVE
    # 通信边可声明下游需要从上游 output 提取哪些字段（低熵“按需投递”清单）
    data_fields: list[str] = Field(default_factory=list, alias="dataFields")
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["ACGEdge", "EdgeActivation", "_edge_id"]

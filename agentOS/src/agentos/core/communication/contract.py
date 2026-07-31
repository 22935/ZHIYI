"""低熵通信契约与 Token 估算。

对应设计书 §2.3/§3《低熵通信协议》。定义结构化消息载体 ContextPack
与轻量 Token 估算，用于量化“按需投递 vs 全量倾倒”的节省率。

低熵核心：Step 间不传自然语言对话，只沿依赖边传结构化 data；下游按
input_spec 这份“数据采购清单”精准取用，引擎不做全盘倾倒。
"""

from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


def estimate_tokens(payload: Any) -> int:
    """轻量 Token 估算（无需依赖具体分词器）。

    经验近似：中文约 1 token/字，英文约 1 token/4 字符。这里用
    “字符数 / 3.2”的折中系数，足以稳定度量相对节省率（演示与对比用途，
    不追求与某模型分词器精确一致）。
    """
    if payload is None:
        return 0
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(payload)
    return max(0, round(len(text) / 3.2))


class ContextPack(BaseModel):
    """下游 Step 的执行输入包。

    由上下文装配器按 input_spec 精准组装，包含：任务/步骤目标、按需提取的
    上游数据、聚合的证据链引用，以及低熵度量（节省率）。
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    run_id: str = Field(alias="runId")
    step_id: str = Field(alias="stepId")
    objective: str = ""
    step_goal: str = Field(default="", alias="stepGoal")
    data: Dict[str, Any] = Field(default_factory=dict)
    source_data: Dict[str, Dict[str, Any]] = Field(default_factory=dict, alias="sourceData")
    evidence_refs: List[str] = Field(default_factory=list, alias="evidenceRefs")
    missing_fields: List[str] = Field(default_factory=list, alias="missingFields")
    contract_status: str = Field(default="valid", alias="contractStatus")
    # 低熵度量
    tokens_delivered: int = Field(default=0, alias="tokensDelivered")
    tokens_available: int = Field(default=0, alias="tokensAvailable")
    saving_ratio: float = Field(default=0.0, alias="savingRatio")
    source_step_ids: List[str] = Field(default_factory=list, alias="sourceStepIds")
    graph_version: int = Field(default=0, alias="graphVersion")
    attempt_id: str = Field(default="", alias="attemptId")
    binding_id: str = Field(default="", alias="bindingId")
    input_revision: str = Field(default="", alias="inputRevision")


def input_revision(payload: Any) -> str:
    """Return a stable revision for one attempt's resolved context."""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["estimate_tokens", "input_revision", "ContextPack"]

"""记忆部件的共享数据合同与运行期工作记忆。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from contracts.memory import MemoryPolicy, MemoryQuery, MemoryRecord, MemoryType, MemoryWriteBatch


def _read(source: object, name: str, default: Any = None) -> Any:
    """同时接收合同对象与字典，避免工作记忆反向依赖运行时实现。"""
    if isinstance(source, Mapping):
        return source.get(name, source.get(name[:1].lower() + name[1:], default))
    return getattr(source, name, default)


@dataclass
class WorkingMemory:
    """一次运行内对 Agent 可见的最小工作上下文。

    此对象只保存任务输入和已经获准投递的步骤观察；持久化、召回和图状态
    仍分别属于 memory、retrieval 与 executor 部件，避免把旧工作流对象带回。
    """

    run_id: str
    task_input: dict[str, Any] = field(default_factory=dict)
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_run(cls, run: object) -> "WorkingMemory":
        """从兼容的运行对象或映射提取已完成步骤的工作记忆。

        读取 ``steps`` 或 ``nodes`` 中 completed/waiting_review 的映射输出，返回
        新 ``WorkingMemory``；未知字段被忽略，不反向依赖旧运行时模型。步骤数
        为 n 时复杂度 O(n)，输入对象与嵌套输出不被修改。
        """
        raw_steps = _read(run, "steps", []) or _read(run, "nodes", []) or []
        observations: dict[str, dict[str, Any]] = {}
        for step in raw_steps:
            status = str(_read(step, "status", "")).lower()
            output = _read(step, "output", {}) or {}
            step_id = _read(step, "step_id", None) or _read(step, "stepId", None) or _read(step, "node_id", None)
            if step_id and isinstance(output, Mapping) and status in {"completed", "waiting_review", "waiting review"}:
                observations[str(step_id)] = dict(output)
        return cls(
            run_id=str(_read(run, "run_id", None) or _read(run, "runId", "")),
            task_input=dict(_read(run, "input", {}) or _read(run, "task_input", {}) or {}),
            observations=observations,
        )

    def record(self, step_id: str, output: Mapping[str, Any]) -> None:
        """以 ``step_id`` 写入一份浅复制的步骤输出观察。

        同标识会覆盖先前观察，调用者随后增删顶层键不会影响已存值；嵌套可变值
        仍按引用共享。写入是唯一副作用，复杂度 O(k)，k 为输出顶层字段数。
        """
        self.observations[str(step_id)] = dict(output)

    @classmethod
    def from_context_pack(cls, run: object, pack: object) -> "WorkingMemory":
        """从通信器已过滤的 ``source_data`` 构建一份工作记忆。

        仅采纳映射类型的来源数据，禁止从上游全量输出旁路读取；返回新对象且不
        修改 ``run`` 或 ``pack``。来源数为 n、字段数为 m 时复杂度 O(n + m)。
        """
        source_data = _read(pack, "source_data", None) or _read(pack, "sourceData", {}) or {}
        observations = {
            str(source_id): dict(data)
            for source_id, data in source_data.items()
            if isinstance(data, Mapping)
        }
        return cls(
            run_id=str(_read(run, "run_id", None) or _read(run, "runId", _read(pack, "run_id", ""))),
            task_input=dict(_read(run, "input", {}) or _read(run, "task_input", {}) or {}),
            observations=observations,
        )


class HybridMemoryHit(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    memory_id: str = Field(alias="memoryId")
    lexical_score: float = Field(alias="lexicalScore", ge=0.0)
    vector_score: float = Field(alias="vectorScore", ge=0.0)
    fused_score: float = Field(alias="fusedScore", ge=0.0)


class MemoryRetrievalEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    scope: str
    mode: str
    hit_refs: list[str] = Field(alias="hitRefs")
    budget: int | None = None
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")


class StructuredMemoryEvent(BaseModel):
    """A compact committed-step projection safe for Trace and long-term memory."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    event_id: str = Field(alias="eventId")
    run_id: str = Field(alias="runId")
    step_id: str = Field(alias="stepId")
    commit_id: str = Field(alias="commitId")
    summary: str
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    metrics: dict[str, int] = Field(default_factory=dict)
    decision: str
    relations: list[dict[str, str]] = Field(default_factory=list)


class PhaseCapsule(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    capsule_id: str = Field(alias="capsuleId")
    run_id: str = Field(alias="runId")
    phase_id: str = Field(alias="phaseId")
    source_memory_refs: list[str] = Field(alias="sourceMemoryRefs")
    goal: str = ""
    confirmed_summary: str = Field(default="", alias="confirmedSummary")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list, alias="openQuestions")
    key_facts: list[str] = Field(default_factory=list, alias="keyFacts")
    open_risks: list[str] = Field(default_factory=list, alias="openRisks")
    decisions: list[str] = Field(default_factory=list)
    token_count: int = Field(alias="tokenCount", ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="createdAt")


__all__ = ["HybridMemoryHit", "MemoryPolicy", "MemoryQuery", "MemoryRecord", "MemoryRetrievalEvent", "MemoryType", "MemoryWriteBatch", "PhaseCapsule", "StructuredMemoryEvent", "WorkingMemory"]

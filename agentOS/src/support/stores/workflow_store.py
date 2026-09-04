"""运行时配套任务/运行存储合同，不包含跨部件业务编排实现。"""


from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from contracts.workflow import MissionRecordState, RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus


T = TypeVar("T")


@dataclass(frozen=True)
class WorkflowStorePage(Generic[T]):
    """WorkflowStore 的分页查询结果。"""

    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)


@dataclass(frozen=True)
class RuntimeRunRecordDeleteResult:
    """删除一次运行及其孤立父任务后的结果；``mission_deleted`` 明确是否发生级联删除。"""

    run_id: str
    mission_id: str
    mission_deleted: bool


class RuntimeRunRecordNotTerminalError(ValueError):
    """在运行未到终态时请求物理删除所抛出的错误，携带运行标识与当前状态。"""

    def __init__(self, run_id: str, status: WorkflowStatus):
        super().__init__(f"workflow run is not terminal: {run_id} ({status.value})")
        self.run_id = run_id
        self.status = status


def paginate_items(items: Sequence[T], *, page: int = 1, page_size: int = 20) -> WorkflowStorePage[T]:
    """按安全页码切分序列。

    页码和页大小下限为 1；保持输入顺序并返回总数，切片复杂度与当前页大小相关。
    """
    safe_page = max(1, page)
    safe_page_size = max(1, page_size)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return WorkflowStorePage(
        items=tuple(items[start:end]),
        total=len(items),
        page=safe_page,
        page_size=safe_page_size,
    )


def status_value(status: WorkflowStatus | str | None) -> str | None:
    """把状态枚举或字符串归一为存储筛选值；``None`` 保持为不筛选。"""
    if status is None:
        return None
    return status.value if isinstance(status, WorkflowStatus) else str(status)


def status_values(statuses: Sequence[WorkflowStatus | str] | None) -> set[str] | None:
    """把状态序列归一为集合；空序列返回 ``None`` 表示不施加多状态筛选。"""
    if not statuses:
        return None
    return {item.value if isinstance(item, WorkflowStatus) else str(item) for item in statuses}


_SAFE_EXECUTION_STATE_KEYS = {
    "activeStepIds",
    "blackboardSnapshots",
    "checkpointId",
    "communicationUsage",
    "compiledPackageChecksum",
    "compiledPackageBlueprintHash",
    "compiledPackageId",
    "compiledPackageVersion",
    "consensusResults",
    "contextRefs",
    "controlFrames",
    "debateSessions",
    "graphId",
    "graphPatchRefs",
    "graphVersion",
    "loopIterations",
    "loopPaths",
    "memoryRefs",
    "outputRefs",
    "parentRunId",
    "provenanceRefs",
    "resourceFailoverHistory",
    "recoveryOutcome",
    "schedulingDecisions",
    "sourceBlueprintVersion",
    "sourceRunId",
    "sourcePatchId",
    "supersedesRunId",
    "supersededByRunId",
    "rerunReason",
    "traceRefs",
}


def lifecycle_run_payload(run: RuntimeRunRecord) -> dict[str, Any]:
    """Build the reference-only Run fact admitted to the lifecycle Outbox.

    Blueprint and Planner snapshots are control-plane definitions needed to
    reconstruct Identity after a crash. Runtime input/output bodies, step
    payloads, checkpoints and trace bodies deliberately stay in Execution Runtime.
    """
    execution_state = dict(run.execution_state or {})
    safe_state = {
        key: execution_state[key]
        for key in _SAFE_EXECUTION_STATE_KEYS
        if execution_state.get(key) is not None
    }
    for key in ("taskPlan", "taskBindings"):
        if execution_state.get(key) is not None:
            safe_state[key] = execution_state[key]
    return {
        "runId": run.run_id,
        "missionId": run.mission_id,
        "workflowId": run.workflow_id,
        "status": run.status.value,
        "lifecyclePhase": (
            run.lifecycle_phase.value if run.lifecycle_phase is not None else None
        ),
        "currentStepId": run.current_step_id,
        "acgBlueprint": run.acg_blueprint,
        "executionState": safe_state,
        "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
        "runtimeRevision": run.runtime_revision,
    }


def lifecycle_run_event_type(run: RuntimeRunRecord) -> str | None:
    """Classify a Run snapshot only after its identity contract exists.

    A deferred ACG Run is durably accepted before L1 planning has produced a
    TaskPlan, Blueprint and bindings.  Publishing it as ``run.prepared`` would
    violate the V2 identity contract, so the snapshot stays inside the
    Execution Runtime until materialization removes ``planningDeferred``.
    """
    execution_state = run.execution_state or {}
    if execution_state.get("planningDeferred"):
        return None
    if run.status is WorkflowStatus.SUPERSEDED:
        return "run.superseded"
    if run.status in {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }:
        return "run.finished"
    if run.status is WorkflowStatus.PENDING:
        return "run.prepared"
    return "run.snapshot"


class WorkflowStore(ABC):
    """RuntimeMissionRecord 和 RuntimeRunRecord 状态的持久化边界。"""

    @abstractmethod
    def save_mission(self, task: RuntimeMissionRecord) -> None:
        """持久化任务；实现应定义覆盖和并发语义。"""
        raise NotImplementedError

    @abstractmethod
    def get_mission(self, mission_id: str) -> RuntimeMissionRecord:
        """按标识读取任务；不存在时应抛出 ``KeyError``。"""
        raise NotImplementedError

    @abstractmethod
    def set_mission_record_state(
        self, mission_id: str, state: MissionRecordState
    ) -> tuple[RuntimeMissionRecord, int]:
        """原子校验全部 Run 已终止并更新 Mission 的用户管理状态。"""
        raise NotImplementedError

    @abstractmethod
    def save_run(self, run: RuntimeRunRecord) -> None:
        """持久化运行；实现必须维护终态不可被旧快照覆盖的不变量。"""
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> RuntimeRunRecord:
        """按标识读取运行；不存在时应抛出 ``KeyError``。"""
        raise NotImplementedError

    @abstractmethod
    def delete_run(self, run_id: str, *, delete_orphan_mission: bool = True) -> RuntimeRunRecordDeleteResult:
        """删除终态运行，可选清除无其他运行引用的任务；未终态时抛出专用错误。"""
        raise NotImplementedError

    @abstractmethod
    def list_missions(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeMissionRecord]:
        """按条件分页列出任务；返回排序、复制与并发快照策略由实现定义。"""
        raise NotImplementedError

    @abstractmethod
    def list_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses: Sequence[WorkflowStatus | str] | None = None,
        domain: str | None = None,
        workflow_id: str | None = None,
        mission_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources: Sequence[str] | None = None,
        mission_record_state: MissionRecordState | str | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeRunRecord]:
        """按状态、归属和来源条件分页列出运行；筛选条件共同取交集。"""
        raise NotImplementedError

    @abstractmethod
    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        """返回数量受限、最新优先的未完成运行快照；实现不得返回终态运行。"""
        raise NotImplementedError

    @abstractmethod
    def list_all_runs(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        """Return an unscoped page for reconciliation, including terminal runs."""
        raise NotImplementedError

    @abstractmethod
    def save_run_with_events(self, run: RuntimeRunRecord, events: Sequence[dict]) -> None:
        """Atomically save the execution Run snapshot and append lifecycle Outbox events."""
        raise NotImplementedError

    @abstractmethod
    def save_graph_patch_transition(
        self,
        old_run: RuntimeRunRecord,
        new_run: RuntimeRunRecord,
        event: dict,
    ) -> None:
        """Atomically supersede one execution Run, persist its replacement, and append the patch event."""
        raise NotImplementedError

    @abstractmethod
    def find_run_by_idempotency_key(self, idempotency_key: str) -> RuntimeRunRecord | None:
        """按幂等键查找最近运行；无匹配时返回 ``None``。"""
        raise NotImplementedError

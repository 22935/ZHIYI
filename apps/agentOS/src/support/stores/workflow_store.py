"""运行时配套任务/运行存储合同，不包含跨部件业务编排实现。"""


from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Sequence, TypeVar

from contracts.workflow import MissionRecordState, RunRecordState, RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus


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
class RuntimeRunListSummary:
    """Small Run projection used by Mission lists without loading execution bodies."""

    run_id: str
    mission_id: str
    status: WorkflowStatus
    updated_at: datetime


@dataclass(frozen=True)
class RuntimeRunOverview:
    """Payload-free Run row projection for list endpoints.

    Backed by summary columns joined with the mission title; loading a page
    must not deserialize run payloads.
    """

    run_id: str
    mission_id: str
    workflow_id: str
    domain: str
    status: WorkflowStatus
    lifecycle_phase: str | None
    lifecycle_message: str | None
    source: str | None
    current_step_id: str | None
    started_at: datetime | None
    created_at: datetime
    updated_at: datetime
    runtime_revision: int
    title: str | None


@dataclass(frozen=True)
class RuntimeMissionRunSummary:
    """Batch summary of the runtime runs belonging to visible missions."""

    mission_id: str
    latest_run: RuntimeRunRecord | RuntimeRunListSummary | None
    run_count: int


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
    "singleStepRetry",
    "retryTargetStepId",
    "reusedStepIds",
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
    if (
        str(run.runtime_engine).strip().lower() == "acg"
        and (
            not isinstance(run.acg_blueprint, dict)
            or not isinstance(execution_state.get("taskPlan"), dict)
            or not isinstance(execution_state.get("taskBindings"), list)
        )
    ):
        # Planner progress is persisted in the Execution Runtime and Trace,
        # but cannot be consumed as an identity Run snapshot until the full
        # Blueprint/TaskPlan/binding contract is materialized.
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
    def get_task_copilot_permission(self, mission_id: str) -> str:
        """Return the task-wide operator policy, independently of Run snapshots."""

    @abstractmethod
    def set_task_copilot_permission(self, mission_id: str, permission: str) -> None:
        """Persist an explicit user permission selection for this Mission."""

    @abstractmethod
    def list_task_copilot_exchanges(self, mission_id: str, *, limit: int = 30) -> list[dict]:
        """Return bounded conversation with exact source Run attribution."""

    def list_planning_inputs(self, run_id: str) -> list[dict]:
        """Durable operator input inbox; separate from bounded chat history."""
        raise NotImplementedError

    def save_planning_input(self, run_id: str, operation_id: str, payload: dict) -> None:
        raise NotImplementedError

    def list_copilot_exchanges(self, run_id: str, *, limit: int = 30) -> list[dict]:
        """Bounded read of conversation bodies, separate from Run snapshots."""
        raise NotImplementedError

    def get_copilot_exchange(self, run_id: str, operation_id: str) -> dict | None:
        raise NotImplementedError

    def save_copilot_exchange(self, run_id: str, operation_id: str, payload: dict) -> None:
        """Append an immutable, idempotency-keyed successful conversation exchange."""
        raise NotImplementedError

    @abstractmethod
    def save_mission(self, task: RuntimeMissionRecord) -> None:
        """持久化任务；实现应定义覆盖和并发语义。"""
        raise NotImplementedError

    def create_mission_once(self, task: RuntimeMissionRecord) -> RuntimeMissionRecord:
        """Atomically insert/replay by creation key and fingerprint; never overwrite a Mission."""
        raise NotImplementedError

    def find_mission_by_creation_key(self, creation_key: str) -> RuntimeMissionRecord | None:
        """Read the existing creation anchor without creating or modifying a Mission."""
        raise NotImplementedError

    def save_prepared_run_once(self, run: RuntimeRunRecord) -> RuntimeRunRecord:
        """Atomically deduplicate initial Run persistence by idempotency key."""
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
    def save_run(self, run: RuntimeRunRecord, *, expected_snapshot: RuntimeRunRecord | None = None) -> None:
        """Save Run and Mission summary atomically; optional full snapshot CAS.

        A CAS conflict raises ValueError without modifying Run, Mission or outbox.
        """
        raise NotImplementedError

    @abstractmethod
    def project_mission_status(self, mission_id: str) -> RuntimeMissionRecord | None:
        """Atomically refresh from all persisted Runs; None for a runless Mission."""
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
    def set_run_record_state(self, run_id: str, state: RunRecordState) -> RuntimeRunRecord:
        """原子校验 Run 已终止并更新其用户管理状态（软删除）；未终态时抛出专用错误。"""
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
    def list_mission_ids(
        self,
        *,
        mission_record_state: MissionRecordState | str | None = None,
    ) -> set[str]:
        """Return mission IDs matching the runtime record-state filter."""
        raise NotImplementedError

    @abstractmethod
    def list_mission_run_summaries(
        self,
        mission_ids: Sequence[str],
        *,
        mission_record_state: MissionRecordState | str | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
    ) -> dict[str, RuntimeMissionRunSummary]:
        """Return latest-run and count data for many missions in one read."""
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
    def list_run_overviews(
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
    ) -> WorkflowStorePage[RuntimeRunOverview]:
        """与 ``list_runs`` 同筛选/排序/分页，但返回不载入 payload 的轻量行投影。"""
        raise NotImplementedError

    @abstractmethod
    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        """返回数量受限、最新优先的未完成运行快照；实现不得返回终态运行。"""
        raise NotImplementedError

    @abstractmethod
    def list_all_run_summaries(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunListSummary, ...]:
        """Internal recovery metadata; includes all owners without loading Run bodies."""
        raise NotImplementedError

    @abstractmethod
    def list_all_runs(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        """Return an unscoped page for reconciliation, including terminal runs."""
        raise NotImplementedError

    @abstractmethod
    def save_run_with_events(self, run: RuntimeRunRecord, events: Sequence[dict], *, expected_snapshot: RuntimeRunRecord | None = None) -> None:
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

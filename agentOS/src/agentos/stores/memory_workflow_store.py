"""AgentOS Core 的存储 memory_workflow_store 模块，管理任务和运行记录的持久化边界。"""


from __future__ import annotations

from typing import Dict

from agentos.core.models.types import AgentTask, WorkflowRun, WorkflowStatus
from agentos.stores.workflow_store import (
    WorkflowRunDeleteResult,
    WorkflowRunNotTerminalError,
    WorkflowStore,
    WorkflowStorePage,
    paginate_items,
    status_value,
    status_values,
)


class MemoryWorkflowStore(WorkflowStore):
    """面向本地开发和测试的内存 WorkflowStore 适配器。"""

    def __init__(self):
        self._tasks: Dict[str, AgentTask] = {}
        self._runs: Dict[str, WorkflowRun] = {}
        self._terminal_run_statuses: Dict[str, WorkflowStatus] = {}

    def save_task(self, task: AgentTask) -> None:
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> AgentTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task not found: {task_id}") from exc

    def save_run(self, run: WorkflowRun) -> None:
        existing = self._runs.get(run.run_id)
        terminal_status = self._terminal_run_statuses.get(run.run_id)
        if terminal_status is not None and _reject_terminal_status_overwrite(terminal_status, run.status):
            return
        if existing is not None and _reject_terminal_overwrite(existing, run):
            return
        if run.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }:
            self._terminal_run_statuses[run.run_id] = run.status
        elif terminal_status == WorkflowStatus.FAILED and run.status == WorkflowStatus.RETRYING:
            self._terminal_run_statuses.pop(run.run_id, None)
        self._runs[run.run_id] = run.model_copy(deep=True)

    def get_run(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"workflow run not found: {run_id}") from exc

    def delete_run(self, run_id: str, *, delete_orphan_task: bool = True) -> WorkflowRunDeleteResult:
        try:
            run = self._runs[run_id]
        except KeyError as exc:
            raise KeyError(f"workflow run not found: {run_id}") from exc
        if run.status not in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }:
            raise WorkflowRunNotTerminalError(run_id, run.status)
        self._runs.pop(run_id)
        self._terminal_run_statuses.pop(run_id, None)
        task_deleted = False
        if delete_orphan_task and not any(item.task_id == run.task_id for item in self._runs.values()):
            task_deleted = self._tasks.pop(run.task_id, None) is not None
        return WorkflowRunDeleteResult(
            run_id=run_id,
            task_id=run.task_id,
            task_deleted=task_deleted,
        )

    def list_tasks(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[AgentTask]:
        expected_status = status_value(status)
        tasks = [
            task.model_copy(deep=True)
            for task in self._tasks.values()
            if _matches_task(task, status=expected_status, domain=domain, source=source)
        ]
        tasks.sort(key=lambda task: (task.created_at, task.task_id), reverse=True)
        return paginate_items(tasks, page=page, page_size=page_size)

    def list_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses=None,
        domain: str | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources=None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[WorkflowRun]:
        expected_status = status_value(status)
        expected_statuses = status_values(statuses)
        runs = [
            run.model_copy(deep=True)
            for run in self._runs.values()
            if _matches_run(
                run,
                status=expected_status,
                statuses=expected_statuses,
                domain=domain,
                workflow_id=workflow_id,
                task_id=task_id,
                lifecycle_phase=lifecycle_phase,
                source=source,
                sources=set(sources) if sources else None,
                owner_user_id=owner_user_id,
                owner_tenant_id=owner_tenant_id,
            )
        ]
        runs.sort(
            key=lambda run: (_run_priority(run) if expected_statuses else 0, run.updated_at, run.run_id),
            reverse=True,
        )
        return paginate_items(runs, page=page, page_size=page_size)

    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[WorkflowRun, ...]:
        terminal = {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
        runs = [run.model_copy(deep=True) for run in self._runs.values() if run.status not in terminal]
        runs.sort(key=lambda run: (run.updated_at, run.run_id), reverse=True)
        return tuple(runs[: max(1, limit)])

    def find_run_by_idempotency_key(self, idempotency_key: str) -> WorkflowRun | None:
        matches = [
            run.model_copy(deep=True)
            for run in self._runs.values()
            if run.idempotency_key == idempotency_key
        ]
        if not matches:
            return None
        return max(matches, key=lambda run: (run.created_at, run.run_id))


def _matches_task(task: AgentTask, *, status: str | None, domain: str | None, source: str | None) -> bool:
    if status is not None and task.status.value != status:
        return False
    if domain is not None and task.domain != domain:
        return False
    if source is not None and task.input.get("source") != source:
        return False
    return True


def _matches_run(
    run: WorkflowRun,
    *,
    status: str | None,
    statuses: set[str] | None,
    domain: str | None,
    workflow_id: str | None,
    task_id: str | None,
    lifecycle_phase: str | None,
    source: str | None,
    sources: set[str] | None,
    owner_user_id: str | None,
    owner_tenant_id: str | None,
) -> bool:
    if status is not None and run.status.value != status:
        return False
    if statuses is not None and run.status.value not in statuses:
        return False
    if domain is not None and run.domain != domain:
        return False
    if workflow_id is not None and run.workflow_id != workflow_id:
        return False
    if task_id is not None and run.task_id != task_id:
        return False
    phase = run.lifecycle_phase.value if run.lifecycle_phase is not None else None
    if lifecycle_phase is not None and phase != lifecycle_phase:
        return False
    if source is not None and run.input.get("source") != source:
        return False
    if sources is not None and run.input.get("source") not in sources:
        return False
    run_owner = str(run.input.get("authenticatedUserId") or "").strip()
    run_tenant = str(run.input.get("authenticatedTenantId") or "").strip()
    if owner_user_id is not None and run_owner and run_owner != owner_user_id:
        return False
    if owner_tenant_id is not None and run_tenant and run_tenant != owner_tenant_id:
        return False
    return True


def _run_priority(run: WorkflowRun) -> int:
    if run.status == WorkflowStatus.WAITING_REVIEW:
        return 2
    if run.status not in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}:
        return 1
    return 0


def _reject_terminal_overwrite(existing: WorkflowRun, incoming: WorkflowRun) -> bool:
    terminal = {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }
    if existing.status == WorkflowStatus.FAILED and incoming.status == WorkflowStatus.RETRYING:
        return False
    if existing.status in terminal and incoming.status != existing.status:
        return True
    return existing.status in terminal and incoming.updated_at < existing.updated_at


def _reject_terminal_status_overwrite(
    existing: WorkflowStatus,
    incoming: WorkflowStatus,
) -> bool:
    if existing == WorkflowStatus.FAILED and incoming == WorkflowStatus.RETRYING:
        return False
    return incoming != existing

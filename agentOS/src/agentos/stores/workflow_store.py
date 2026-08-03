"""AgentOS Core 的存储 workflow_store 模块，管理任务和运行记录的持久化边界。"""


from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from agentos.core.models.types import AgentTask, WorkflowRun, WorkflowStatus


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
class WorkflowRunDeleteResult:
    """Result of deleting one run and, when orphaned, its parent task."""

    run_id: str
    task_id: str
    task_deleted: bool


class WorkflowRunNotTerminalError(ValueError):
    """Raised when physical deletion is attempted before a run is terminal."""

    def __init__(self, run_id: str, status: WorkflowStatus):
        super().__init__(f"workflow run is not terminal: {run_id} ({status.value})")
        self.run_id = run_id
        self.status = status


def paginate_items(items: Sequence[T], *, page: int = 1, page_size: int = 20) -> WorkflowStorePage[T]:
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
    if status is None:
        return None
    return status.value if isinstance(status, WorkflowStatus) else str(status)


def status_values(statuses: Sequence[WorkflowStatus | str] | None) -> set[str] | None:
    if not statuses:
        return None
    return {item.value if isinstance(item, WorkflowStatus) else str(item) for item in statuses}


def workflow_run_summary(run: WorkflowRun, *, title: str | None = None) -> dict[str, Any]:
    """Build the bounded list projection without exposing the full Run payload."""
    from agentos.core.workflow.progress import ProgressAssembler

    summary = ProgressAssembler().assemble(run).model_dump(by_alias=True, mode="json")
    summary.update(
        {
            "source": run.input.get("source"),
            "title": title,
            "createdAt": run.created_at.isoformat(),
        }
    )
    return summary


class WorkflowStore(ABC):
    """AgentTask 和 WorkflowRun 状态的持久化边界。"""

    @abstractmethod
    def save_task(self, task: AgentTask) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: str) -> AgentTask:
        raise NotImplementedError

    @abstractmethod
    def save_run(self, run: WorkflowRun) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> WorkflowRun:
        raise NotImplementedError

    @abstractmethod
    def delete_run(self, run_id: str, *, delete_orphan_task: bool = True) -> WorkflowRunDeleteResult:
        raise NotImplementedError

    @abstractmethod
    def list_tasks(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[AgentTask]:
        raise NotImplementedError

    @abstractmethod
    def list_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses: Sequence[WorkflowStatus | str] | None = None,
        domain: str | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources: Sequence[str] | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[WorkflowRun]:
        raise NotImplementedError

    def list_run_summaries(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses: Sequence[WorkflowStatus | str] | None = None,
        domain: str | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources: Sequence[str] | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[dict[str, Any]]:
        """Return a compact list projection; persistent stores should override this."""
        result = self.list_runs(
            status=status,
            statuses=statuses,
            domain=domain,
            workflow_id=workflow_id,
            task_id=task_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            sources=sources,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            page=page,
            page_size=page_size,
        )
        summaries = []
        for run in result.items:
            try:
                title = self.get_task(run.task_id).title
            except KeyError:
                title = None
            summaries.append(workflow_run_summary(run, title=title))
        return WorkflowStorePage(
            items=tuple(summaries),
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    @abstractmethod
    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[WorkflowRun, ...]:
        """Return a bounded newest-first snapshot of unfinished runs."""
        raise NotImplementedError

    @abstractmethod
    def find_run_by_idempotency_key(self, idempotency_key: str) -> WorkflowRun | None:
        raise NotImplementedError

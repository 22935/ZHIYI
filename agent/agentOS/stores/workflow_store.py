from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from agentos.core.types import AgentTask, WorkflowRun, WorkflowStatus


T = TypeVar("T")


@dataclass(frozen=True)
class WorkflowStorePage(Generic[T]):
    """Paginated WorkflowStore query result."""

    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)


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


class WorkflowStore(ABC):
    """Persistence seam for AgentTask and WorkflowRun state."""

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
        domain: str | None = None,
        workflow_id: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[WorkflowRun]:
        raise NotImplementedError

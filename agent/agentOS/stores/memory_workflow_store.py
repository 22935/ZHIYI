from __future__ import annotations

from typing import Dict

from agentos.core.types import AgentTask, WorkflowRun, WorkflowStatus
from agentos.stores.workflow_store import WorkflowStore, WorkflowStorePage, paginate_items, status_value


class MemoryWorkflowStore(WorkflowStore):
    """In-memory WorkflowStore adapter for local development and tests."""

    def __init__(self):
        self._tasks: Dict[str, AgentTask] = {}
        self._runs: Dict[str, WorkflowRun] = {}

    def save_task(self, task: AgentTask) -> None:
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> AgentTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task not found: {task_id}") from exc

    def save_run(self, run: WorkflowRun) -> None:
        self._runs[run.run_id] = run

    def get_run(self, run_id: str) -> WorkflowRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError(f"workflow run not found: {run_id}") from exc

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
            task
            for task in self._tasks.values()
            if _matches_task(task, status=expected_status, domain=domain, source=source)
        ]
        tasks.sort(key=lambda task: (task.created_at, task.task_id), reverse=True)
        return paginate_items(tasks, page=page, page_size=page_size)

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
        expected_status = status_value(status)
        runs = [
            run
            for run in self._runs.values()
            if _matches_run(
                run,
                status=expected_status,
                domain=domain,
                workflow_id=workflow_id,
                source=source,
            )
        ]
        runs.sort(key=lambda run: (run.created_at, run.run_id), reverse=True)
        return paginate_items(runs, page=page, page_size=page_size)


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
    domain: str | None,
    workflow_id: str | None,
    source: str | None,
) -> bool:
    if status is not None and run.status.value != status:
        return False
    if domain is not None and run.domain != domain:
        return False
    if workflow_id is not None and run.workflow_id != workflow_id:
        return False
    if source is not None and run.input.get("source") != source:
        return False
    return True

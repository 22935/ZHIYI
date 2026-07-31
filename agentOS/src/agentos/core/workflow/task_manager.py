"""任务管理器，负责任务创建、工作流绑定和生命周期状态流转。"""


from __future__ import annotations

from typing import Any, Optional

from agentos.core.governance.trace import TraceStore
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.workflow.progress import ProgressCalculator, WorkflowProgress
from agentos.core.workflow.state_machine import StateMachine
from agentos.core.models.types import (
    AgentTask,
    TraceEventType,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    utc_now,
)
from agentos.stores.workflow_store import WorkflowStore, WorkflowStorePage


class TaskManager:
    """任务控制面服务，负责任务创建、工作流绑定和生命周期状态。"""

    def __init__(
        self,
        *,
        workflow_store: WorkflowStore,
        workflow_registry: WorkflowRegistry,
        state_machine: Optional[StateMachine] = None,
        trace_store: Optional[TraceStore] = None,
        progress_calculator: Optional[ProgressCalculator] = None,
    ):
        self.workflow_store = workflow_store
        self.workflow_registry = workflow_registry
        self.state_machine = state_machine or StateMachine()
        self.trace_store = trace_store
        self.progress_calculator = progress_calculator or ProgressCalculator()

    def create_task(
        self,
        title: str,
        domain: str = "general",
        intent: str = "general",
        input: Optional[dict[str, Any]] = None,
        security_level: str = "internal",
        priority: str = "normal",
        *,
        role_type: Optional[str] = None,
        task_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
        enabled_plugin_ids: Optional[list[str]] = None,
        allowed_workflow_ids: Optional[tuple[str, ...]] = None,
    ) -> AgentTask:
        task_domain = self._first_nonblank(role_type, domain, default="general")
        task_intent = self._first_nonblank(task_type, intent, default="general")
        workflow = self._select_workflow(
            task_domain,
            task_intent,
            workflow_id,
            allowed_workflow_ids=allowed_workflow_ids,
        )

        task = AgentTask(
            title=title,
            domain=task_domain,
            intent=task_intent,
            input=input or {},
            securityLevel=security_level,
            priority=priority,
            recommendedWorkflow=workflow.workflow_id if workflow else None,
            enabledPluginIds=(
                list(enabled_plugin_ids) if enabled_plugin_ids is not None else None
            ),
        )
        self.workflow_store.save_task(task)
        self._record_task_event(
            task,
            TraceEventType.TASK_CREATED,
            observation=f"Task created: {task.title}",
            payload=task.model_dump(by_alias=True, mode="json"),
        )
        return task

    def get_task(self, task_id: str) -> AgentTask:
        return self.workflow_store.get_task(task_id)

    def list_tasks(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[AgentTask]:
        return self.workflow_store.list_tasks(
            status=status,
            domain=domain,
            source=source,
            page=page,
            page_size=page_size,
        )

    def bind_workflow(
        self,
        task: AgentTask | str,
        workflow_id: Optional[str] = None,
        *,
        allowed_workflow_ids: Optional[tuple[str, ...]] = None,
    ) -> WorkflowDefinition:
        resolved_task = self._task(task)
        workflow = self._select_workflow(
            resolved_task.domain,
            resolved_task.intent,
            workflow_id or resolved_task.recommended_workflow,
            allowed_workflow_ids=allowed_workflow_ids,
        )
        if workflow is None:
            raise KeyError(
                f"workflow not found for domain={resolved_task.domain}, intent={resolved_task.intent}"
            )
        if resolved_task.recommended_workflow != workflow.workflow_id:
            resolved_task.recommended_workflow = workflow.workflow_id
            resolved_task.updated_at = utc_now()
            self.workflow_store.save_task(resolved_task)
        return workflow

    def mark_running(self, task: AgentTask | str) -> AgentTask:
        return self.transition(task, WorkflowStatus.RUNNING)

    def mark_waiting_review(self, task: AgentTask | str) -> AgentTask:
        return self.transition(task, WorkflowStatus.WAITING_REVIEW)

    def mark_retrying(self, task: AgentTask | str) -> AgentTask:
        return self.transition(task, WorkflowStatus.RETRYING)

    def mark_failed(self, task: AgentTask | str) -> AgentTask:
        return self.transition(task, WorkflowStatus.FAILED)

    def mark_completed(self, task: AgentTask | str) -> AgentTask:
        return self.transition(task, WorkflowStatus.COMPLETED)

    def mark_cancelled(self, task: AgentTask | str) -> AgentTask:
        return self.transition(task, WorkflowStatus.CANCELLED)

    def transition(self, task: AgentTask | str, status: WorkflowStatus | str) -> AgentTask:
        resolved_task = self._task(task)
        old_status = resolved_task.status
        target_value = status.value if isinstance(status, WorkflowStatus) else str(status)
        try:
            target = status if isinstance(status, WorkflowStatus) else WorkflowStatus(status)
            resolved_task.status = self.state_machine.transition(old_status, target)
        except Exception as exc:
            self._record_task_error(
                resolved_task,
                from_status=old_status.value,
                to_status=target_value,
                error=str(exc),
            )
            raise
        resolved_task.updated_at = utc_now()
        self.workflow_store.save_task(resolved_task)
        if old_status != resolved_task.status:
            self._record_task_event(
                resolved_task,
                TraceEventType.TASK_STATUS_CHANGED,
                observation=f"Task status changed: {old_status.value} -> {resolved_task.status.value}",
                payload={
                    "fromStatus": old_status.value,
                    "toStatus": resolved_task.status.value,
                },
            )
        return resolved_task

    def calculate_progress(
        self,
        task: AgentTask | str,
        *,
        run: WorkflowRun | None = None,
        workflow: Optional[WorkflowDefinition] = None,
    ) -> WorkflowProgress:
        resolved_task = self._task(task)
        resolved_workflow = workflow or self._resolve_progress_workflow(resolved_task, run=run)
        return self.progress_calculator.calculate(
            task=resolved_task,
            run=run,
            workflow=resolved_workflow,
        )

    def _task(self, task: AgentTask | str) -> AgentTask:
        if isinstance(task, AgentTask):
            return task
        return self.workflow_store.get_task(task)

    def _select_workflow(
        self,
        domain: str,
        intent: str,
        workflow_id: Optional[str],
        *,
        allowed_workflow_ids: Optional[tuple[str, ...]] = None,
    ) -> Optional[WorkflowDefinition]:
        if workflow_id:
            return self.workflow_registry.get(
                workflow_id, allowed_workflow_ids=allowed_workflow_ids
            )
        return self.workflow_registry.recommend(
            domain=domain,
            intent=intent,
            allowed_workflow_ids=allowed_workflow_ids,
        )

    @staticmethod
    def _first_nonblank(preferred: Optional[str], fallback: Optional[str], *, default: str) -> str:
        for value in (preferred, fallback):
            normalized = (value or "").strip()
            if normalized:
                return normalized
        return default

    def _resolve_progress_workflow(
        self,
        task: AgentTask,
        *,
        run: WorkflowRun | None = None,
    ) -> Optional[WorkflowDefinition]:
        workflow_id = getattr(run, "workflow_id", None) or task.recommended_workflow
        if not workflow_id:
            return None
        try:
            return self.workflow_registry.get(workflow_id)
        except KeyError:
            return None

    def _record_task_event(
        self,
        task: AgentTask,
        event_type: TraceEventType,
        *,
        observation: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        if self.trace_store is None:
            return
        self.trace_store.append_task(
            task=task,
            event_type=event_type,
            observation=observation,
            payload=payload,
        )

    def _record_task_error(
        self,
        task: AgentTask,
        *,
        from_status: str,
        to_status: str,
        error: str,
    ) -> None:
        self._record_task_event(
            task,
            TraceEventType.TASK_ERROR,
            observation=error,
            payload={
                "fromStatus": from_status,
                "toStatus": to_status,
                "error": error,
            },
        )


__all__ = ["TaskManager"]

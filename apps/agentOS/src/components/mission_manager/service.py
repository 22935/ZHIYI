"""任务管理器，负责任务创建、工作流绑定和生命周期状态流转。"""


from __future__ import annotations

from typing import Any, Optional

from components.auditor.governance.trace import TraceStore
from .store import WorkflowRegistry
from .scheduler import ProgressCalculator, WorkflowProgress
from .state_machine import StateMachine
from contracts.workflow import (
    RuntimeMissionRecord,
    TraceEventType,
    WorkflowDefinition,
    RuntimeRunRecord,
    WorkflowStatus,
    utc_now,
)
from support.stores.workflow_store import WorkflowStore, WorkflowStorePage


class MissionManager:
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

    def create_mission(
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
        mission_id: str | None = None,
        creation_fingerprint: str | None = None,
        creation_key: str | None = None,
    ) -> RuntimeMissionRecord:
        """创建并持久化任务，同时记录创建轨迹。

        ``role_type``/``task_type`` 优先覆盖领域/意图；可选工作流在给定作用域内解析为推荐值。
        该方法写入任务存储与（若配置）轨迹存储，找不到显式工作流时会抛出 ``KeyError``。
        """
        task_domain = self._first_nonblank(role_type, domain, default="general")
        task_intent = self._first_nonblank(task_type, intent, default="general")
        workflow = self._select_workflow(
            task_domain,
            task_intent,
            workflow_id,
            allowed_workflow_ids=allowed_workflow_ids,
        )

        task = RuntimeMissionRecord(
            **({"missionId": mission_id} if mission_id is not None else {}),
            title=title,
            creationFingerprint=creation_fingerprint,
            creationKey=creation_key,
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
        if creation_fingerprint:
            task = self.workflow_store.create_mission_once(task)
        else:
            self.workflow_store.save_mission(task)
        self._record_task_event(
            task,
            TraceEventType.TASK_CREATED,
            observation=f"Task created: {task.title}",
            payload=task.model_dump(by_alias=True, mode="json"),
        )
        return task

    def get_mission(self, mission_id: str) -> RuntimeMissionRecord:
        """按任务标识从存储读取任务；缺失异常由底层存储保持原样抛出。"""
        return self.workflow_store.get_mission(mission_id)

    def list_missions(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeMissionRecord]:
        """分页读取任务，可按状态、领域和来源筛选；排序与页码语义由存储实现定义。"""
        return self.workflow_store.list_missions(
            status=status,
            domain=domain,
            source=source,
            page=page,
            page_size=page_size,
        )

    def bind_workflow(
        self,
        task: RuntimeMissionRecord | str,
        workflow_id: Optional[str] = None,
        *,
        allowed_workflow_ids: Optional[tuple[str, ...]] = None,
    ) -> WorkflowDefinition:
        """为任务解析并必要时持久化推荐工作流。

        显式标识优先于已有推荐，且受 ``allowed_workflow_ids`` 限制；仅在推荐改变时写任务，
        无可用工作流时抛出 ``KeyError``。
        """
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
            self.workflow_store.save_mission(resolved_task)
        return workflow

    def mark_running(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        """将任务推进到运行中；副作用与合法性校验委托 ``transition``。"""
        return self.transition(task, WorkflowStatus.RUNNING)

    def mark_running_for_new_run(self, task: RuntimeMissionRecord | str, *, run_id: str) -> RuntimeMissionRecord:
        """Refresh all branches after validating the callback's Run ownership."""
        self._require_run(task, run_id)
        return self.transition(task, WorkflowStatus.RUNNING)

    def mark_waiting_review(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        """将任务推进到等待审核；副作用与合法性校验委托 ``transition``。"""
        return self.transition(task, WorkflowStatus.WAITING_REVIEW)

    def mark_retrying(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        """将任务推进到重试中；副作用与合法性校验委托 ``transition``。"""
        return self.transition(task, WorkflowStatus.RETRYING)

    def mark_failed(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        """将任务推进到失败；副作用与合法性校验委托 ``transition``。"""
        return self.transition(task, WorkflowStatus.FAILED)

    def mark_failed_for_run(self, task: RuntimeMissionRecord | str, *, run_id: str) -> RuntimeMissionRecord:
        """A failed branch is not a latest/current execution authority."""
        self._require_run(task, run_id)
        return self.transition(task, WorkflowStatus.FAILED)

    def _require_run(self, task, run_id):
        if self.workflow_store.get_run(run_id).mission_id != self._task(task).mission_id:
            raise ValueError("Run does not belong to the mission")

    def mark_completed(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        """将任务推进到完成；副作用与合法性校验委托 ``transition``。"""
        return self.transition(task, WorkflowStatus.COMPLETED)

    def mark_cancelled(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        """将任务推进到取消；副作用与合法性校验委托 ``transition``。"""
        return self.transition(task, WorkflowStatus.CANCELLED)

    def transition(self, task: RuntimeMissionRecord | str, status: WorkflowStatus | str) -> RuntimeMissionRecord:
        """有 Run 时刷新兼容汇总；无 Run 时保留原状态机及错误轨迹。

        Run 状态只由 Runtime 及 WorkflowStore 写入，回调次序不决定 Mission 状态。
        """
        resolved_task = self._task(task)
        # Once Runs exist, their persisted set defines the compatibility summary.
        # Callback order and stale Mission snapshots cannot authorize execution.
        projected = self.workflow_store.project_mission_status(resolved_task.mission_id)
        if projected is not None:
            return projected
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
        self.workflow_store.save_mission(resolved_task)
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
        task: RuntimeMissionRecord | str,
        *,
        run: RuntimeRunRecord | None = None,
        workflow: Optional[WorkflowDefinition] = None,
    ) -> WorkflowProgress:
        """计算任务当前进度；优先使用给定运行快照，否则从任务推荐工作流推断初始进度。"""
        resolved_task = self._task(task)
        resolved_workflow = workflow or self._resolve_progress_workflow(resolved_task, run=run)
        return self.progress_calculator.calculate(
            task=resolved_task,
            run=run,
            workflow=resolved_workflow,
        )

    def _task(self, task: RuntimeMissionRecord | str) -> RuntimeMissionRecord:
        mission_id = task.mission_id if isinstance(task, RuntimeMissionRecord) else task
        return self.workflow_store.get_mission(mission_id).model_copy(deep=True)

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
        task: RuntimeMissionRecord,
        *,
        run: RuntimeRunRecord | None = None,
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
        task: RuntimeMissionRecord,
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
        task: RuntimeMissionRecord,
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


# Facade 与领域服务共用同一实现，避免迁移期出现两套任务状态真相源。
__all__ = ["MissionManager"]

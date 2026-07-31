"""Workflow progress calculation for tasks and runs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from pydantic import Field

from agentos.core.models.enums import WorkflowProgressPhase
from agentos.core.models.types import (
    AgentTask,
    CoreModel,
    StepStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)


class WorkflowProgress(CoreModel):
    """Snapshot of progress across a task, workflow run, and workflow definition."""

    task_id: str = Field(alias="taskId")
    run_id: Optional[str] = Field(default=None, alias="runId")
    workflow_id: Optional[str] = Field(default=None, alias="workflowId")
    status: WorkflowStatus = WorkflowStatus.PENDING
    phase: WorkflowProgressPhase = WorkflowProgressPhase.UNDERSTANDING
    message: str = ""
    percent: Optional[float] = None
    total_steps: int = Field(default=0, alias="totalSteps")
    pending_steps: int = Field(default=0, alias="pendingSteps")
    running_steps: int = Field(default=0, alias="runningSteps")
    waiting_review_steps: int = Field(default=0, alias="waitingReviewSteps")
    retrying_steps: int = Field(default=0, alias="retryingSteps")
    failed_steps: int = Field(default=0, alias="failedSteps")
    completed_steps: int = Field(default=0, alias="completedSteps")
    cancelled_steps: int = Field(default=0, alias="cancelledSteps")
    current_step_id: Optional[str] = Field(default=None, alias="currentStepId")
    active_step_ids: list[str] = Field(default_factory=list, alias="activeStepIds")
    recovery_count: int = Field(default=0, alias="recoveryCount")
    graph_version: Optional[int] = Field(default=None, alias="graphVersion")
    dynamic_step_count: int = Field(default=0, alias="dynamicStepCount")
    binding_switch_count: int = Field(default=0, alias="bindingSwitchCount")
    skipped_by_condition_count: int = Field(default=0, alias="skippedByConditionCount")
    conditional_decision_count: int = Field(default=0, alias="conditionalDecisionCount")
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")
    # Deprecated compatibility fields. `progress` is the 0..1 ratio and
    # `percentage` is the 0..100 value used by existing callers.
    progress: float = 0.0
    percentage: float = 0.0


class ProgressAssembler:
    """Pure projection from a WorkflowRun to a user-facing progress snapshot.

    ``WorkflowRun.lifecycle_message`` is an optional base lifecycle description.
    The projected ``message`` is authoritative for display: an explicit
    ``phase_message`` wins, active execution/review/recovery phases name the
    current step, and otherwise the matching base lifecycle message is kept.
    """

    _ACTIVE_STEP_STATUSES = {
        StepStatus.RUNNING,
        StepStatus.RETRYING,
        StepStatus.WAITING_REVIEW,
    }

    _DEFAULT_MESSAGES = {
        WorkflowProgressPhase.UNDERSTANDING: "正在解析任务目标",
        WorkflowProgressPhase.PLANNING: "正在规划 ACG 执行路径",
        WorkflowProgressPhase.GRAPH_BUILDING: "正在构建 ACG 拓扑",
        WorkflowProgressPhase.EXECUTING: "正在执行 ACG 步骤",
        WorkflowProgressPhase.RECOVERY: "正在恢复 ACG 步骤",
        WorkflowProgressPhase.REVIEW: "正在等待步骤审核",
        WorkflowProgressPhase.COMPLETED: "ACG 工作流执行完成",
        WorkflowProgressPhase.FAILED: "ACG 工作流执行失败",
        WorkflowProgressPhase.CANCELLED: "ACG 工作流已取消",
    }

    def assemble(
        self,
        run: WorkflowRun,
        explicit_phase: WorkflowProgressPhase | str | None = None,
        phase_message: str | None = None,
    ) -> WorkflowProgress:
        """Build a deterministic snapshot without mutating or querying the run."""

        steps = list(run.steps)
        counts: Counter[StepStatus] = Counter()
        step_by_id: dict[str, WorkflowStep] = {}
        definition_active_ids: list[str] = []
        for step in steps:
            counts[step.status] += 1
            step_by_id[step.step_id] = step
            if step.status in self._ACTIVE_STEP_STATUSES:
                definition_active_ids.append(step.step_id)

        active_step_ids = self._active_step_ids(run, step_by_id, definition_active_ids)
        phase = self._resolve_phase(run, counts, active_step_ids, explicit_phase)
        current_step_id = run.current_step_id or (active_step_ids[0] if active_step_ids else None)
        step_name = self._step_name(step_by_id, current_step_id)
        if phase_message is not None:
            message = phase_message
        elif step_name and phase in {
            WorkflowProgressPhase.EXECUTING,
            WorkflowProgressPhase.RECOVERY,
            WorkflowProgressPhase.REVIEW,
        }:
            # Active work is more useful to the UI than the run's base phase text.
            message = self._message(phase, step_name)
        elif run.lifecycle_phase == phase and run.lifecycle_message:
            message = run.lifecycle_message
        else:
            message = self._message(phase, step_name)
        skipped_by_condition_count = counts[StepStatus.SKIPPED_BY_CONDITION]
        percent = self._percent(
            phase,
            counts[StepStatus.COMPLETED] + skipped_by_condition_count,
            len(steps),
        )
        runtime_graph = run.runtime_graph
        graph_version = runtime_graph.graph_version if runtime_graph is not None else None
        dynamic_step_count = (
            sum(
                1
                for node in runtime_graph.nodes
                if node.node_type.value == "step" and node.created_graph_version > 1
            )
            if runtime_graph is not None
            else 0
        )
        binding_switch_count = (
            sum(node.binding_switch_count for node in runtime_graph.nodes)
            if runtime_graph is not None
            else 0
        )

        return WorkflowProgress(
            taskId=run.task_id,
            runId=run.run_id,
            workflowId=run.workflow_id,
            status=run.status,
            phase=phase,
            message=message,
            percent=percent,
            totalSteps=len(steps),
            pendingSteps=counts[StepStatus.PENDING],
            runningSteps=counts[StepStatus.RUNNING],
            waitingReviewSteps=counts[StepStatus.WAITING_REVIEW],
            retryingSteps=counts[StepStatus.RETRYING],
            failedSteps=counts[StepStatus.FAILED],
            completedSteps=counts[StepStatus.COMPLETED],
            cancelledSteps=counts[StepStatus.CANCELLED],
            currentStepId=current_step_id,
            activeStepIds=active_step_ids,
            recoveryCount=run.recovery_count,
            graphVersion=graph_version,
            dynamicStepCount=dynamic_step_count,
            bindingSwitchCount=binding_switch_count,
            skippedByConditionCount=skipped_by_condition_count,
            conditionalDecisionCount=(
                len(runtime_graph.branch_decisions) if runtime_graph is not None else 0
            ),
            startedAt=run.started_at,
            updatedAt=run.updated_at,
            **self._compatibility_values(percent),
        )

    @staticmethod
    def _coerce_phase(value: WorkflowProgressPhase | str) -> WorkflowProgressPhase:
        if isinstance(value, WorkflowProgressPhase):
            return value
        return WorkflowProgressPhase(str(value))

    def _infer_phase(
        self,
        run: WorkflowRun,
        counts: Counter[StepStatus],
        active_step_ids: list[str],
    ) -> WorkflowProgressPhase:
        if run.status == WorkflowStatus.COMPLETED:
            return WorkflowProgressPhase.COMPLETED
        if run.status == WorkflowStatus.FAILED:
            return WorkflowProgressPhase.FAILED
        if run.status == WorkflowStatus.CANCELLED:
            return WorkflowProgressPhase.CANCELLED
        if run.status == WorkflowStatus.WAITING_REVIEW or counts[StepStatus.WAITING_REVIEW]:
            return WorkflowProgressPhase.REVIEW
        if run.status == WorkflowStatus.RETRYING or counts[StepStatus.RETRYING]:
            return WorkflowProgressPhase.RECOVERY
        if run.status == WorkflowStatus.PLANNING:
            return WorkflowProgressPhase.PLANNING
        if run.status == WorkflowStatus.RUNNING:
            if active_step_ids or counts[StepStatus.COMPLETED]:
                return WorkflowProgressPhase.EXECUTING
            if run.acg_blueprint is not None or run.steps:
                return WorkflowProgressPhase.GRAPH_BUILDING
        if run.acg_blueprint is not None or run.steps:
            return WorkflowProgressPhase.GRAPH_BUILDING
        return WorkflowProgressPhase.UNDERSTANDING

    def _resolve_phase(
        self,
        run: WorkflowRun,
        counts: Counter[StepStatus],
        active_step_ids: list[str],
        explicit_phase: WorkflowProgressPhase | str | None,
    ) -> WorkflowProgressPhase:
        # Canonical terminal and step state always wins over a stale lifecycle marker.
        if run.status == WorkflowStatus.COMPLETED:
            return WorkflowProgressPhase.COMPLETED
        if run.status == WorkflowStatus.FAILED:
            return WorkflowProgressPhase.FAILED
        if run.status == WorkflowStatus.CANCELLED:
            return WorkflowProgressPhase.CANCELLED
        if run.status == WorkflowStatus.WAITING_REVIEW or counts[StepStatus.WAITING_REVIEW]:
            return WorkflowProgressPhase.REVIEW
        if run.status == WorkflowStatus.RETRYING or counts[StepStatus.RETRYING]:
            return WorkflowProgressPhase.RECOVERY
        if explicit_phase is not None:
            return self._coerce_phase(explicit_phase)
        if run.lifecycle_phase is not None:
            return self._coerce_phase(run.lifecycle_phase)
        return self._infer_phase(run, counts, active_step_ids)

    def _active_step_ids(
        self,
        run: WorkflowRun,
        step_by_id: dict[str, WorkflowStep],
        definition_active_ids: list[str],
    ) -> list[str]:
        active_ids: list[str] = []
        for step_id in run.active_step_ids:
            step = step_by_id.get(step_id)
            if step is not None and step.status in self._ACTIVE_STEP_STATUSES and step_id not in active_ids:
                active_ids.append(step_id)
        for step_id in definition_active_ids:
            if step_id not in active_ids:
                active_ids.append(step_id)
        return active_ids

    @staticmethod
    def _step_name(step_by_id: dict[str, WorkflowStep], step_id: str | None) -> str | None:
        if not step_id:
            return None
        step = step_by_id.get(step_id)
        if step is None:
            return step_id
        return step.name or step.step_id

    @staticmethod
    def _message(phase: WorkflowProgressPhase, step_name: str | None) -> str:
        message = ProgressAssembler._DEFAULT_MESSAGES[phase]
        if step_name and phase in {
            WorkflowProgressPhase.EXECUTING,
            WorkflowProgressPhase.RECOVERY,
            WorkflowProgressPhase.REVIEW,
        }:
            return f"{message}：{step_name}"
        return message

    @staticmethod
    def _percent(
        phase: WorkflowProgressPhase,
        completed_steps: int,
        total_steps: int,
    ) -> float | None:
        if phase in {
            WorkflowProgressPhase.UNDERSTANDING,
            WorkflowProgressPhase.PLANNING,
            WorkflowProgressPhase.GRAPH_BUILDING,
        }:
            return None
        if phase == WorkflowProgressPhase.COMPLETED:
            return 100.0
        if total_steps <= 0:
            return None
        return round(max(0.0, min(100.0, completed_steps / total_steps * 100)), 2)

    @staticmethod
    def _compatibility_values(percent: float | None) -> dict[str, float]:
        if percent is None:
            return {"progress": 0.0, "percentage": 0.0}
        return {"progress": round(percent / 100, 4), "percentage": percent}


class ProgressCalculator(ProgressAssembler):
    """Backward-compatible task/run calculator backed by ProgressAssembler."""

    def calculate(
        self,
        *,
        task: AgentTask,
        run: WorkflowRun | None = None,
        workflow: WorkflowDefinition | None = None,
    ) -> WorkflowProgress:
        if run is not None:
            return self.assemble(run)

        step_statuses = [StepStatus.PENDING for _ in workflow.steps] if workflow is not None else []
        counts = Counter(step_statuses)
        total_steps = len(step_statuses)
        return WorkflowProgress(
            taskId=task.task_id,
            workflowId=workflow.workflow_id if workflow is not None else task.recommended_workflow,
            status=task.status,
            phase=WorkflowProgressPhase.UNDERSTANDING,
            message=self._DEFAULT_MESSAGES[WorkflowProgressPhase.UNDERSTANDING],
            percent=None,
            totalSteps=total_steps,
            pendingSteps=counts[StepStatus.PENDING],
            runningSteps=counts[StepStatus.RUNNING],
            waitingReviewSteps=counts[StepStatus.WAITING_REVIEW],
            retryingSteps=counts[StepStatus.RETRYING],
            failedSteps=counts[StepStatus.FAILED],
            completedSteps=counts[StepStatus.COMPLETED],
            cancelledSteps=counts[StepStatus.CANCELLED],
            **self._compatibility_values(None),
        )


__all__ = [
    "ProgressAssembler",
    "ProgressCalculator",
    "WorkflowProgress",
    "WorkflowProgressPhase",
]

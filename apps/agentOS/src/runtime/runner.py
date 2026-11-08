"""只编排新身份链和持久化的 ACG 身份生命周期服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts.identity import AttemptId, BlueprintId, RunId, StepExecutionId, TaskId, MissionId
from domain.models import (
    AcgBlueprint,
    Attempt,
    AttemptStatus,
    RunStatus,
    StepExecution,
    StepExecutionStatus,
    SemanticTask,
    Mission,
    MissionStatus,
    WorkflowRun,
)
from domain.repository import EntityNotFoundError, IdentityConflictError, RepositorySet
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage

from .context import ExecutionContext
from .state import require_transition

class AcgIdentityLifecycleService:
    """AgentOS V2 身份与生命周期控制面；实际执行始终由 Execution Runtime ACG 内核完成。"""

    def __init__(self, repositories: RepositorySet) -> None:
        self.repositories = repositories

    @classmethod
    def from_sqlite(
        cls,
        db_path: str | Path = "data/agentos_v2.sqlite3",
    ) -> "AcgIdentityLifecycleService":
        return cls(SQLiteV2Repositories(SQLiteV2Storage(db_path)))

    def close(self) -> None:
        self.repositories.close()

    def create_mission(
        self,
        *,
        user_id: str,
        goal: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        mission_id: MissionId | None = None,
    ) -> Mission:
        task = Mission(
            **({"missionId": mission_id} if mission_id is not None else {}),
            userId=user_id,
            goal=goal,
            description=description,
            metadata=metadata or {},
        )
        self.repositories.missions.add(task)
        return task

    def create_task(
        self,
        *,
        mission_id: MissionId,
        title: str,
        objective: str,
        parent_task_id: TaskId | None = None,
        constraints: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticTask:
        task = self._mission(mission_id)
        if task.status is MissionStatus.CREATED:
            require_transition(task.status, MissionStatus.PLANNING)
            self.repositories.missions.update_status(mission_id, MissionStatus.PLANNING)
        node = SemanticTask(
            missionId=mission_id,
            parentTaskId=parent_task_id,
            title=title,
            objective=objective,
            constraints=constraints or [],
            metadata=metadata or {},
        )
        self.repositories.semantic_tasks.add(node)
        return node

    def create_blueprint(
        self,
        *,
        mission_id: MissionId,
        version: int,
        graph_id: str,
        graph: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> AcgBlueprint:
        task = self._mission(mission_id)
        if not self.repositories.semantic_tasks.list_for_mission(mission_id):
            raise ValueError("AcgBlueprint requires at least one SemanticTask")
        blueprint = AcgBlueprint(
            missionId=mission_id,
            version=version,
            graphId=graph_id,
            graph=graph,
            metadata=metadata or {},
        )
        self.repositories.blueprints.add(blueprint)
        if task.status is MissionStatus.PLANNING:
            require_transition(task.status, MissionStatus.READY)
            self.repositories.missions.update_status(mission_id, MissionStatus.READY)
        return blueprint

    def create_run(
        self,
        *,
        mission_id: MissionId,
        blueprint_id: BlueprintId,
        metadata: dict[str, Any] | None = None,
        run_id: RunId | None = None,
    ) -> WorkflowRun:
        self._mission(mission_id)
        blueprint = self._blueprint(blueprint_id)
        if blueprint.mission_id != mission_id:
            raise IdentityConflictError("WorkflowRun cannot use another Mission's Blueprint")
        if run_id is not None:
            existing = self.repositories.runs.get(run_id)
            if existing is not None:
                if existing.mission_id != mission_id:
                    raise IdentityConflictError(
                        "runId already belongs to another Mission"
                    )
                if (
                    existing.blueprint_id != blueprint_id
                    or existing.graph_version != blueprint.version
                ):
                    raise IdentityConflictError(
                        "runId already identifies another execution definition"
                    )
                return existing
        run = WorkflowRun(
            **({"runId": run_id} if run_id is not None else {}),
            missionId=mission_id,
            blueprintId=blueprint_id,
            graphVersion=blueprint.version,
            metadata=metadata or {},
        )
        self.repositories.runs.add(run)
        return run

    def create_context(self, run_id: RunId) -> ExecutionContext:
        run = self._run(run_id)
        attempts = self.repositories.attempts.list_for_run(run_id)
        current = attempts[-1].attempt_id if attempts else None
        active = [
            execution.step_execution_id
            for attempt in attempts
            for execution in self.repositories.step_executions.list_for_attempt(
                attempt.attempt_id
            )
            if execution.status is StepExecutionStatus.RUNNING
        ]
        return ExecutionContext(
            runId=run.run_id,
            missionId=run.mission_id,
            blueprintId=run.blueprint_id,
            currentAttempt=current,
            activeExecutions=active,
        )

    def create_attempt(
        self,
        *,
        run_id: RunId,
        task_id: TaskId,
        resource_binding: dict[str, Any] | None = None,
        attempt_number: int | None = None,
        attempt_id: AttemptId | None = None,
    ) -> Attempt:
        run = self._run(run_id)
        node = self._task(task_id)
        if node.mission_id != run.mission_id:
            raise IdentityConflictError("Attempt cannot use another Mission's SemanticTask")
        return self.repositories.ensure_attempt(
            run_id,
            task_id,
            attempt_number=attempt_number,
            attempt_id=attempt_id,
            resource_binding=resource_binding,
        )

    def start_step_execution(
        self,
        context: ExecutionContext,
        *,
        input: dict[str, Any],
        attempt_id: AttemptId | None = None,
        step_execution_id: StepExecutionId | None = None,
    ) -> StepExecution:
        selected_attempt_id = attempt_id or context.current_attempt
        if selected_attempt_id is None:
            raise ValueError("ExecutionContext has no current Attempt")
        run = self._run(context.run_id)
        attempt = self._attempt(selected_attempt_id)
        if (
            run.mission_id != context.mission_id
            or run.blueprint_id != context.blueprint_id
            or attempt.run_id != context.run_id
        ):
            raise IdentityConflictError("ExecutionContext identity chain is inconsistent")
        execution = self.repositories.ensure_step_execution(
            run.run_id,
            attempt.task_id,
            attempt.attempt_id,
            input=input,
            step_execution_id=step_execution_id,
        )
        if execution.status is StepExecutionStatus.RUNNING:
            context.active_executions = list(dict.fromkeys([
                *context.active_executions,
                execution.step_execution_id,
            ]))
        return execution

    def complete_step_execution(
        self,
        context: ExecutionContext,
        step_execution_id: str,
        *,
        output: dict[str, Any],
    ) -> StepExecution:
        execution = self._active_execution(context, step_execution_id)
        execution, _ = self.repositories.finish_execution(
            execution.step_execution_id,
            execution.attempt_id,
            step_status=StepExecutionStatus.SUCCEEDED,
            attempt_status=AttemptStatus.SUCCEEDED,
            output=output,
        )
        context.active_executions.remove(execution.step_execution_id)
        return execution

    def fail_step_execution(
        self,
        context: ExecutionContext,
        step_execution_id: str,
        *,
        failure_reason: str,
        output: dict[str, Any] | None = None,
    ) -> StepExecution:
        execution = self._active_execution(context, step_execution_id)
        execution, _ = self.repositories.finish_execution(
            execution.step_execution_id,
            execution.attempt_id,
            step_status=StepExecutionStatus.FAILED,
            attempt_status=AttemptStatus.FAILED,
            output=output or {},
            failure_reason=failure_reason,
        )
        context.active_executions.remove(execution.step_execution_id)
        return execution

    def cancel_step_execution(
        self,
        context: ExecutionContext,
        step_execution_id: str,
        *,
        reason: str,
    ) -> StepExecution:
        execution = self._active_execution(context, step_execution_id)
        execution, _ = self.repositories.finish_execution(
            execution.step_execution_id,
            execution.attempt_id,
            step_status=StepExecutionStatus.CANCELLED,
            attempt_status=AttemptStatus.CANCELLED,
            output={},
            failure_reason=reason,
        )
        context.active_executions.remove(execution.step_execution_id)
        return execution

    def finish_run(self, run_id: RunId, status: RunStatus) -> WorkflowRun:
        if status not in {
            RunStatus.FAILED,
            RunStatus.SUCCEEDED,
            RunStatus.CANCELLED,
            RunStatus.SUPERSEDED,
        }:
            raise ValueError("finish_run requires a terminal RunStatus")
        run = self._run(run_id)
        require_transition(run.status, status)
        finished = self.repositories.runs.update_status(run_id, status)
        task = self._mission(run.mission_id)
        if status is RunStatus.SUCCEEDED and task.status is MissionStatus.RUNNING:
            require_transition(task.status, MissionStatus.COMPLETED)
            self.repositories.missions.update_status(task.mission_id, MissionStatus.COMPLETED)
        elif (
            status in {RunStatus.FAILED, RunStatus.CANCELLED}
            and task.status is MissionStatus.RUNNING
        ):
            other_active_runs = any(
                item.run_id != run_id and item.status is RunStatus.RUNNING
                for item in self.repositories.runs.list_for_mission(task.mission_id)
            )
            if not other_active_runs:
                require_transition(task.status, MissionStatus.READY)
                self.repositories.missions.update_status(task.mission_id, MissionStatus.READY)
        return finished

    def retry_failed_run(self, run_id: RunId) -> WorkflowRun:
        """Move a failed identity Run back to pending for an operator retry."""
        run = self._run(run_id)
        require_transition(run.status, RunStatus.PENDING)
        return self.repositories.runs.reopen_failed(run_id)

    def _mission(self, mission_id: MissionId) -> Mission:
        task = self.repositories.missions.get(mission_id)
        if task is None:
            raise EntityNotFoundError(f"Mission not found: {mission_id}")
        return task

    def _task(self, task_id: TaskId) -> SemanticTask:
        node = self.repositories.semantic_tasks.get(task_id)
        if node is None:
            raise EntityNotFoundError(f"SemanticTask not found: {task_id}")
        return node

    def _blueprint(self, blueprint_id: BlueprintId) -> AcgBlueprint:
        blueprint = self.repositories.blueprints.get(blueprint_id)
        if blueprint is None:
            raise EntityNotFoundError(f"AcgBlueprint not found: {blueprint_id}")
        return blueprint

    def _run(self, run_id: RunId) -> WorkflowRun:
        run = self.repositories.runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"WorkflowRunV2 not found: {run_id}")
        return run

    def _attempt(self, attempt_id: AttemptId) -> Attempt:
        attempt = self.repositories.attempts.get(attempt_id)
        if attempt is None:
            raise EntityNotFoundError(f"Attempt not found: {attempt_id}")
        return attempt

    def _active_execution(
        self,
        context: ExecutionContext,
        step_execution_id: str,
    ) -> StepExecution:
        if step_execution_id not in context.active_executions:
            raise IdentityConflictError("StepExecution is not active in this ExecutionContext")
        execution = self.repositories.step_executions.get(step_execution_id)
        if execution is None:
            raise EntityNotFoundError(f"StepExecution not found: {step_execution_id}")
        if execution.run_id != context.run_id:
            raise IdentityConflictError("StepExecution identity chain is inconsistent")
        return execution


# 兼容既有内部调用；新代码必须使用职责名称，避免被误认为第二套执行内核。
__all__ = ["AcgIdentityLifecycleService"]

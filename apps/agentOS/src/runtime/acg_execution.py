"""已物化 canonical ACG Run 的执行边界：图推进、READY 调度、事件投影与执行态收敛。

本服务从 ``WorkflowRuntime`` 机械迁移而来（PR-8C.2）。它只负责"怎么继续跑"：
执行或恢复一个已经 materialized 的 V4 Compiled ACG Run；"是否应该开始"、"是否
允许并发启动另一个 Run"、"Mission lifecycle 是否允许执行"仍由 facade 裁决。
依赖全部显式注入，禁止引用 WorkflowRuntime、ExecutionRuntime 或 Planner 语义。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
import json
import logging
import threading
import sys
from time import monotonic
from typing import Any

from contracts import stable_checksum
from contracts.identity import new_attempt_id, new_step_execution_id
from contracts.artifacts import is_final_synthesis_role
from support.acg.schema import RuntimeBlueprintSpec

logger = logging.getLogger(__name__)
from components.communicator import (
    CommunicationBroker,
    CommunicatorService,
)
from components.communicator.provenance import ProvenanceLedger
from components.executor import (
    ACGExecutionState,
    ACGGraphCompiler,
    ACGNodeRunner,
)
from components.executor.graph import ACGSuperstepError
from components.memory import MemoryService, StructuredMemoryEvent
from components.mission_manager.state_machine import StateMachine
from contracts.resource import ExecutionBinding, ExecutionRequirement
from contracts.execution import WorkflowProgressPhase
from contracts.workflow import (
    RuntimeMissionRecord,
    RuntimeRunRecord,
    StepStatus,
    TraceEvent,
    TraceEventType,
    WorkflowDefinition,
    WorkflowStatus,
    utc_now,
)
from components.resource.scheduler.models import (
    FATAL_SCHEDULING_REASONS,
    SchedulerAllocationTimeout,
    SchedulerNoEligibleResource,
)
from components.resource.scheduler.leases import LeaseRenewalFailedError
from components.recovery.checkpoint import ExecutionInterrupt, ExecutionResumeCommand
from adapters.agent_invocation import AgentInvocationAdapter
from adapters.resource_execution import (
    ResourceAgentProxy,
    ResourceExecutionAdapter,
    ResourceExecutionError,
    build_resource_execution_adapter,
)
from components.resource.runtime.embedded_runtime import (
    EMBEDDED_AGENTS_RUNTIME_ID,
    register_embedded_agents_runtime,
)
from service.agents.base import AgentProfile
from adapters.audited_tool_runtime import AuditedToolRuntime
from adapters.guarded_model import GuardedModelRuntime
from adapters.guarded_tool import GuardedToolRuntime
from adapters.model_runtime import RegisteredModelRuntime
from adapters.resource_model_execution import build_resource_model_runtime
from adapters.tool_adapter import configured_tool_runtime
from support.stores._policy import acg_review_subject
from runtime.execution_migration import ExecutionEngineMigratingError
from runtime.ports import CollaboratorAccess, RuntimeCollaborators
from runtime.binding import execution_requirements_for, requirements_match_manifest
from runtime.state_persistence import ACGStatePersistenceService
from support.async_tasks import await_settled, cancel_and_wait
from contracts.runtime_events import TRANSIENT_RUNTIME_EVENT_TYPES


class ExecutionRunCancelled(RuntimeError):
    """操作者请求取消后，用于在调度边界协作式终止图推进的控制流异常。

    它不是 ``asyncio.CancelledError``：不撕毁事件循环中正在执行的任务树，
    只让当前 run 停止认领新的节点执行，让已真实完成的步骤保留其提交。
    """


class ExecutionStateChanged(RuntimeError):
    """A concurrent authority changed the state observed by runtime planning."""


class ACGExecutionService(CollaboratorAccess):
    """执行一个已物化的 canonical ACG Run，或从检查点恢复继续推进。

    facade（``WorkflowRuntime``）保留 run 锁、执行槽与全部 public 入口；本服务
    通过显式注入的端口回写 Run 生命周期、Mission 投影与身份 outbox，不反向
    依赖 facade 实现。Scheduler 仍是 concrete resource 的唯一 authority，本
    服务只调用并持久化其决定。
    """

    def __init__(
        self,
        *,
        load_mission: Callable[[str], RuntimeMissionRecord],
        load_workflow: Callable[[RuntimeRunRecord], WorkflowDefinition],
        state_machine: StateMachine,
        state_persistence: ACGStatePersistenceService,
        collaborators: RuntimeCollaborators,
        model_max_concurrency: int,
        model_min_interval_seconds: float,
        record_execution_failure: Callable[[RuntimeRunRecord, ACGExecutionState, BaseException], None],
        terminal_run_statuses: frozenset[WorkflowStatus],
        lifecycle_messages: Mapping[WorkflowProgressPhase, str],
        cancellation_event: Callable[[str], threading.Event],
        cancellation_requested: Callable[[str], bool],
        flush_identity_outbox: Callable[..., None],
        set_run_lifecycle: Callable[..., RuntimeRunRecord],
        publish_run_terminal_event: Callable[[RuntimeRunRecord, str, Mapping[str, Any] | None], None],
        fail_run_safely: Callable[..., Awaitable[RuntimeRunRecord]],
        safe_error_message: Callable[[BaseException], str],
        mark_running: Callable[[RuntimeMissionRecord], None],
        mark_running_for_new_run: Callable[[RuntimeMissionRecord, str], None],
        mark_completed: Callable[[RuntimeMissionRecord], None],
        mark_waiting_review: Callable[[RuntimeMissionRecord], None],
        observe_boundary: Callable[..., Awaitable[str]] | None = None,
    ) -> None:
        # 端口：与 facade 共享的窄回调，命名保持原调用点语义。
        self._load_mission = load_mission
        self._load_workflow = load_workflow
        self._cancellation_event = cancellation_event
        self._cancellation_requested = cancellation_requested
        self._flush_identity_outbox = flush_identity_outbox
        self._set_run_lifecycle = set_run_lifecycle
        self._publish_run_terminal_event = publish_run_terminal_event
        self._fail_run_safely = fail_run_safely
        self._safe_error_message = safe_error_message
        self._mark_running = mark_running
        self._mark_running_for_new_run = mark_running_for_new_run
        self._mark_completed = mark_completed
        self._mark_waiting_review = mark_waiting_review
        self._record_execution_failure = record_execution_failure
        self._observe_boundary = observe_boundary
        # 协作者经共享上下文按引用读取：facade 属性写入即时可见，无派发前重对齐。
        self.state_machine = state_machine
        self.state_persistence = state_persistence
        self.ports = collaborators
        self.model_max_concurrency = model_max_concurrency
        self.model_min_interval_seconds = model_min_interval_seconds
        self._terminal_run_statuses = terminal_run_statuses
        self._lifecycle_messages = lifecycle_messages

    async def execute(
        self,
        run: RuntimeRunRecord,
        *,
        state: ACGExecutionState | None = None,
        command: ExecutionResumeCommand | None = None,
        _resume_planning: bool = True,
    ) -> RuntimeRunRecord:
        """执行或续跑融合 ACG，并把图状态投影为既有运行合同。

        图、值仓库和检查点均只传递引用型状态。此方法是执行服务唯一的 ACG 接线点：
        通信、记忆、审计、Agent 适配由 ``ACGNodeRunner`` 组合，RuntimeRunRecord
        只保存生命周期、步骤状态、摘要和引用，绝不写入 Agent 的完整输出正文。
        """
        if run.status in self._terminal_run_statuses:
            return run
        is_resuming = state is not None and (
            run.status in {WorkflowStatus.RUNNING, WorkflowStatus.RETRYING, WorkflowStatus.WAITING_REVIEW}
            or bool(state.completed_step_ids or state.checkpoint_id)
            or bool(run.execution_state.get("checkpointResume"))
        )
        task = self._load_mission(run.mission_id)
        workflow = self._load_workflow(run)
        blueprint_data = run.acg_blueprint
        if not isinstance(blueprint_data, dict):
            raise ExecutionEngineMigratingError(run.run_id)
        blueprint = RuntimeBlueprintSpec.model_validate(blueprint_data)
        raw_package = run.execution_state.get("compiledACGPackage")
        if not isinstance(raw_package, dict):
            raise ExecutionEngineMigratingError(run.run_id)
        from contracts.compiled_acg import load_compiled_acg_package

        compiled_package = load_compiled_acg_package(raw_package)
        graph = ACGGraphCompiler().compile(
            blueprint,
            run_id=run.run_id,
            package=compiled_package,
        )
        execution_state = state or ACGExecutionState(
            runId=run.run_id,
            graphId=blueprint.graph_id,
            graphVersion=blueprint.version,
        )
        if execution_state.run_id != run.run_id:
            raise ValueError("execution state runId does not match workflow run")
        self._validate_acg_resume_identity(
            run=run,
            workflow=workflow,
            blueprint=blueprint,
            state=execution_state,
        )
        ledger = self.provenance_store.load_ledger(run_id=run.run_id, mission_id=task.mission_id)
        self.validate_state_references(run=run, state=execution_state, ledger=ledger)
        runner = self._build_runner(
            task=task,
            run=run,
            workflow=workflow,
            graph=graph,
            state=execution_state,
            ledger=ledger,
        )
        scheduled_runner = self._ready_node_runner(run=run, runner=runner)
        run.execution_state["engineMigration"] = "langgraph_fused_v1"
        run.execution_state["graphId"] = blueprint.graph_id
        run.execution_state["compiledPackageId"] = compiled_package.package_id
        run = self._set_run_lifecycle(
            run,
            status=WorkflowStatus.RUNNING,
            phase=WorkflowProgressPhase.EXECUTING,
            message=self._lifecycle_messages[WorkflowProgressPhase.EXECUTING],
            set_started_at=True,
        )
        if self.identity_lifecycle is not None or run.execution_state.get("sourceRunId"):
            self._mark_running_for_new_run(task, run_id=run.run_id)
        else:
            self._mark_running(task)
        cancel_requested = self._cancellation_event(run.run_id)
        stream = None
        try:
            if self._observe_boundary is not None and _resume_planning and (is_resuming or command is not None):
                # Human/control review is resolved by the graph's resume command,
                # before Planner may observe it. Planner never approves a review.
                if command is not None:
                    graph._prepare_resume(execution_state, command)
                    command = None
                wake_reason = "restart" if (run.execution_state.get("planningLoop") or {}).get("restartPending") else "resume"
                boundary_action = await self._observe_boundary(run, execution_state, wake_reason)
                if boundary_action == "stop":
                    return run
                if boundary_action == "complete":
                    self.state_persistence.persist(run, execution_state)
                    return self._complete_run(run, execution_state, blueprint, task)
            stream = (
                graph.astream(execution_state, scheduled_runner)
                if command is None
                else graph.astream_after_resume(execution_state, command, scheduled_runner)
            )
            async for event in stream:
                # ``nodes_scheduled`` 是图的安全取消点：此刻新 superstep 尚未派生
                # 任何节点任务，在此停止推进即可避免一切新增 Agent/模型调用。
                if (
                    cancel_requested.is_set()
                    and isinstance(event, dict)
                    and event.get("type") == "nodes_scheduled"
                ):
                    break
                self._project_event(run, execution_state, event)
                if self._observe_boundary is not None and event.get("type") == "superstep_completed":
                    if await self._observe_boundary(run, execution_state, "progress") == "stop":
                        await stream.aclose()
                        return run
            if cancel_requested.is_set():
                return await self._finalize_cancelled_run(run, execution_state)
            self.state_persistence.persist(run, execution_state)
            if self._observe_boundary is not None:
                if await self._observe_boundary(run, execution_state, "exhausted") != "complete":
                    return run
            return self._complete_run(run, execution_state, blueprint, task)
        except ExecutionRunCancelled:
            # 节点执行体在调度边界感知到取消；与主循环 break 走同一条收敛路径。
            return await self._finalize_cancelled_run(run, execution_state)
        except ExecutionStateChanged:
            latest = self.workflow_store.get_run(run.run_id)
            if latest.status in self._terminal_run_statuses or latest.status == WorkflowStatus.WAITING_REVIEW:
                return latest
            latest = self._set_run_lifecycle(latest, status=WorkflowStatus.RETRYING, phase=WorkflowProgressPhase.RECOVERY)
            self.workflow_store.save_run(latest)
            return latest
        except ExecutionInterrupt as interrupt:
            self.state_persistence.persist(run, execution_state)
            checkpoint_id = self.state_persistence.save_checkpoint(
                run, execution_state
            )
            self.state_persistence.persist(run, execution_state)
            subject_type, subject_id = acg_review_subject(interrupt.payload)
            blueprint = RuntimeBlueprintSpec.model_validate(run.acg_blueprint)
            subject_node = blueprint.get_node(subject_id)
            expected_node_type = "step" if subject_type == "step" else "control"
            if subject_node.node_type.value != expected_node_type:
                raise ValueError(
                    f"ACG review subject type does not match blueprint node: {subject_id}"
                )
            if subject_type == "step":
                step = run.get_step(subject_id)
                step.status = StepStatus.WAITING_REVIEW
            run.current_step_id = subject_id
            self.trace_store.append_execution_event(run, {"type": "interrupted", **interrupt.payload})
            self.trace_store.append_execution_event(run, {"type": "checkpoint_created", "checkpointId": checkpoint_id})
            run = self._set_run_lifecycle(
                run,
                status=WorkflowStatus.WAITING_REVIEW,
                phase=WorkflowProgressPhase.REVIEW,
                message=self._lifecycle_messages[WorkflowProgressPhase.REVIEW],
            )
            self._mark_waiting_review(task)
            self.workflow_store.save_run(run)
            return run
        except Exception as exc:
            if stream is not None:
                await await_settled(asyncio.create_task(stream.aclose(), name=f"acg-stream-error-close:{run.run_id}"))
            if isinstance(exc, ACGSuperstepError):
                recovered = self._recover_remote_acg_failure(
                    run=run,
                    state=execution_state,
                    error=exc,
                )
                if recovered:
                    return await self.execute(
                        run,
                        state=execution_state,
                        # Keep bounded failover within the authorized fragment;
                        # a real process restart retains the normal boundary.
                        _resume_planning=False,
                    )
            # 失败投影与 recoveryOutcome 持久化归 RuntimeRecoveryCoordinator；
            # 本服务只负责检测失败并收敛安全终态（端口由 facade 接线）。
            self._record_execution_failure(run, execution_state, exc)
            if getattr(exc, "outcome_unknown", False):
                run.execution_state["recoveryOutcome"].update({
                    "action": "review", "status": "required",
                    "reasonCode": "REMOTE_EXECUTION_OUTCOME_UNKNOWN",
                })
                self.workflow_store.save_run(run)
            if self._observe_boundary is not None and isinstance(run.execution_state.get("planningLoop"), dict) and not getattr(exc, "outcome_unknown", False):
                execution_state.active_step_ids = []
                self.state_persistence.persist(run, execution_state)
                try:
                    await self._observe_boundary(run, execution_state, "failure")
                except ExecutionRunCancelled:
                    return await self._finalize_cancelled_run(run, execution_state)
                except ExecutionStateChanged:
                    latest = self.workflow_store.get_run(run.run_id)
                    if latest.status not in self._terminal_run_statuses and latest.status != WorkflowStatus.WAITING_REVIEW:
                        latest = self._set_run_lifecycle(latest, status=WorkflowStatus.RETRYING, phase=WorkflowProgressPhase.RECOVERY)
                        self.workflow_store.save_run(latest)
                    return latest
                except Exception:
                    # Invalid commit/audit/manifest references cannot be laundered
                    # into a new planning observation via the failure path.
                    await self._fail_run_safely(run.run_id,
                        error_code="runtime_observation_invalid",
                        error_message="Cannot form a trustworthy runtime planning observation")
                    raise
                if run.status == WorkflowStatus.FAILED:
                    raise
                return run
            await self._fail_run_safely(
                run.run_id,
                error_code="acg_execution_failed",
                error_message=self._safe_error_message(exc),
            )
            if self.identity_lifecycle is not None:
                self._flush_identity_outbox()
            raise
        finally:
            if stream is not None:
                await await_settled(asyncio.create_task(stream.aclose(), name=f"acg-stream-close:{run.run_id}"))

    @staticmethod
    def _unwrap_resource_execution_error(error: BaseException) -> ResourceExecutionError | None:
        """Find a remote execution error hidden behind an ACG superstep wrapper."""
        pending = [error]
        visited: set[int] = set()
        first = None
        while pending:
            current = pending.pop()
            if id(current) in visited:
                continue
            visited.add(id(current))
            if isinstance(current, ResourceExecutionError):
                first = first or current
                if current.outcome_unknown:
                    return current
            pending.extend(item for item in (getattr(current, "cause", None), current.__cause__, current.__context__)
                           if isinstance(item, BaseException))
            pending.extend(item for item in getattr(current, "causes", ()) if isinstance(item, BaseException))
        return first

    def _remote_runtime_adapter(self, runtime_id: str) -> ResourceExecutionAdapter | None:
        """Lazily construct the signed adapter for a bound remote Runtime."""
        existing = self.resource_execution_adapters.get(runtime_id)
        if existing is not None:
            return existing
        try:
            profile = self.resource_plane.runtime(runtime_id)
        except KeyError:
            return None
        if profile.endpoint is None or profile.endpoint.protocol == "local":
            return None
        try:
            adapter = build_resource_execution_adapter(
                profile,
                credential_provider=self.resource_plane,
            )
        except KeyError as exc:
            raise ResourceExecutionError(
                f"REMOTE_EXECUTION_CONFIG_INVALID: credential missing for {runtime_id}"
            ) from exc
        self.resource_execution_adapters[runtime_id] = adapter
        return adapter

    def _resolve_embedded_agent(self, *, run, step, role_hint: object):
        """在嵌入式后端内解析逻辑 Agent 角色；这不是资源选择。

        Planner 的角色提示只是解析顺序的一部分：显式角色名 → 步骤声明的
        agent_name → 历史绑定 → 能力匹配。任何提示失败都退回下一层，
        绝不扩大冻结的运行范围。
        """
        allowed = run.execution_scope.agent_ids if run.execution_scope else None
        attempts: list[tuple[str, str]] = []
        hint = role_hint if isinstance(role_hint, str) and role_hint.strip() else None
        if hint:
            attempts.append(("name", hint.strip()))
        if step.agent_name:
            attempts.append(("name", str(step.agent_name)))
        previous = (run.execution_state.get("resourceBindings") or {}).get(step.step_id)
        if previous:
            attempts.append(("id", str(previous)))
        for kind, value in attempts:
            try:
                if kind == "name":
                    return self.agent_registry.resolve(
                        run.domain, agent_name=value, allowed_agent_ids=allowed
                    )
                return self.agent_registry.resolve_by_id(value, allowed_agent_ids=allowed)
            except KeyError:
                continue
        if step.capability:
            return self.agent_registry.resolve(
                run.domain, capability=step.capability, allowed_agent_ids=allowed
            )
        raise KeyError(
            f"EMBEDDED_AGENT_UNRESOLVED: step {step.step_id} has no eligible logical agent"
        )

    def _recover_remote_acg_failure(
        self,
        *,
        run: RuntimeRunRecord,
        state: ACGExecutionState,
        error: ACGSuperstepError,
    ) -> bool:
        """Mark failed remote resources unhealthy and prepare one safe rebind.

        The graph has already projected ``superstep_failed`` when this method is
        called.  We therefore repair only nodes without a committed graph result;
        committed nodes remain completed and are replayed from the value store.
        Each step/resource pair gets at most one automatic failover attempt.
        """
        resource_error = self._unwrap_resource_execution_error(error)
        if resource_error is None or error.outcome_unknown or resource_error.outcome_unknown:
            return False

        execution_bindings = run.execution_state.get("executionBindings")
        if not isinstance(execution_bindings, dict):
            return False
        history = list(run.execution_state.get("resourceFailoverHistory") or [])
        failed_resources: list[dict[str, str]] = []
        failed_step_ids = list(dict.fromkeys(error.failed_step_ids))
        reset_step_ids = list(dict.fromkeys(
            [*error.failed_step_ids, *error.cancelled_step_ids]
        ))
        # ACG exposes the first failed task's exception as ``cause``. Other
        # failed tasks may have independent causes, and cancelled siblings did
        # not necessarily contact their bound remote resource at all.
        for step_id in failed_step_ids[:1]:
            binding = execution_bindings.get(step_id)
            if not isinstance(binding, dict):
                continue
            resource_id = str(binding.get("resourceId") or "")
            if resource_id not in self.resource_execution_adapters:
                try:
                    if self.resource_plane.runtime(resource_id).endpoint is None:
                        continue
                except KeyError:
                    continue
            already_attempted = any(
                isinstance(item, dict)
                and item.get("stepId") == step_id
                and item.get("resourceId") == resource_id
                for item in history
            )
            if already_attempted:
                continue
            self.resource_plane.set_runtime_health(resource_id, healthy=False)
            failed_resources.append({"stepId": step_id, "resourceId": resource_id})

        if not failed_resources:
            return False

        for item in failed_resources:
            item["error"] = str(resource_error)[:500]
        history.extend(failed_resources)
        run.execution_state["resourceFailoverHistory"] = history
        run.execution_state["recoveryOutcome"] = {
            "action": "resource_failover",
            "status": "applied",
            "resources": list(failed_resources),
        }
        run.recovery_count += 1
        run.error = None
        run.active_step_ids = []
        run.current_step_id = None

        committed_step_ids = set(state.completed_step_ids)
        for step_id in reset_step_ids:
            if step_id in committed_step_ids:
                continue
            step = run.get_step(step_id)
            if step_id in execution_bindings:
                # A remote failure can precede NodeRunner's attempt counter.
                # Its binding/start events already exist, so the new binding
                # must use a new Attempt instead of conflicting with that key.
                step.attempt = max(step.attempt, step.retry_count) + 1
                step.retry_count += 1
            if step.status in {
                StepStatus.FAILED,
                StepStatus.CANCELLED,
                StepStatus.RETRYING,
                StepStatus.RUNNING,
            }:
                # This is an explicit recovery projection, not a normal
                # lifecycle transition from FAILED back to PENDING.
                step.status = StepStatus.PENDING
                step.error = None
                step.completed_at = None

        self.trace_store.append(
            run,
            TraceEventType.RUN_RECOVERED,
            step_id=(failed_resources[0]["stepId"]),
            observation="远程资源执行失败，已切换到备用资源重新调度",
            payload={
                "failedResources": list(failed_resources),
                "retryStepIds": [
                    step_id for step_id in reset_step_ids
                    if step_id not in committed_step_ids
                ],
            },
        )
        self.workflow_store.save_run(run)
        return True

    def _ready_node_runner(self, *, run: RuntimeRunRecord, runner: ACGNodeRunner):
        """Decorate NodeRunner after Executor readiness with binding and lease coordination."""
        raw_requirements = run.execution_state.get("bindingRequirements")
        if "graphActivation" in run.execution_state:
            def invocation_guard(step_id, state):
                authority = self.execution_permit_authority
                if authority is None:
                    raise ExecutionRunCancelled("execution permit authority unavailable before invocation")
                try:
                    authority.assert_invocation(run, state, step_id, runner.attempt_ids.get(step_id))
                except (ValueError, KeyError, TypeError) as exc:
                    raise ExecutionRunCancelled("execution permit changed before Adapter invocation") from exc
            runner.invocation_guard = invocation_guard
            # The activated package, not a mutable Run dictionary, is the
            # source of execution eligibility. Require the persisted projection
            # to match it exactly so ordinary Run writes cannot lower policy.
            from contracts.compiled_acg import load_compiled_acg_package
            raw_package = run.execution_state.get("compiledACGPackage")
            if not isinstance(raw_package, dict):
                raise ValueError("activated Run has no compiled binding package")
            package = load_compiled_acg_package(raw_package)
            workflow = self._load_workflow(run)
            expected = execution_requirements_for(
                package.binding_manifest, (step.step_id for step in run.steps),
                domain=run.domain or workflow.domain,
            )
            if not requirements_match_manifest(raw_requirements, expected):
                raise ValueError("activated Run binding requirements differ from its compiled package")
        if not isinstance(raw_requirements, dict):
            return runner
        # A recreated Runtime resumes an already-prepared run without repeating
        # prepare_run. Re-project the embedded agent runtime so every resource
        # starts UNKNOWN and becomes usable only after this live registration.
        register_embedded_agents_runtime(self.resource_plane, self.agent_registry.all())

        async def execute(step_id: str, state: ACGExecutionState):
            scheduling_started = monotonic()
            execution_started: float | None = None
            execution_outcome = "failed"
            if self._cancellation_requested(run.run_id):
                raise ExecutionRunCancelled(
                    f"run {run.run_id} cancelled before scheduling step {step_id}"
                )
            permit_authority = self.execution_permit_authority
            if "graphActivation" in run.execution_state:
                if permit_authority is None:
                    raise ExecutionRunCancelled("execution permit authority unavailable")
                try:
                    permit_authority.assert_dispatchable(run)
                except (ValueError, KeyError, TypeError) as exc:
                    raise ExecutionRunCancelled("execution permit or authorization is stale") from exc
            payload = raw_requirements.get(step_id)
            if not isinstance(payload, dict):
                raise ValueError(f"READY step has no binding requirement: {step_id}")
            requirement = ExecutionRequirement.model_validate(payload)
            step = run.get_step(step_id)
            attempt_number = max(step.attempt, step.retry_count) + 1
            loop_path = tuple(state.loop_paths.get(step_id, ()))
            loop_key = ".".join(str(item) for item in loop_path) or "root"
            attempts = run.execution_state.setdefault("attemptIds", {})
            attempt_key = f"{step_id}:{attempt_number}:{loop_key}"
            if state.execution_generation:
                expected_attempt_id = "attempt_" + stable_checksum({
                    "generation": state.execution_generation, "run": run.run_id,
                    "step": step_id, "attempt": attempt_number, "loop": loop_key,
                })[:12]
                previous_attempt_id = attempts.get(attempt_key)
                if previous_attempt_id is not None and previous_attempt_id != expected_attempt_id:
                    raise ValueError("stored Attempt identity belongs to another execution generation")
                attempts[attempt_key] = expected_attempt_id
                attempt_id = expected_attempt_id
            else:
                attempt_id = str(attempts.setdefault(
                    attempt_key,
                    new_attempt_id() if self.identity_lifecycle is not None
                    else f"{run.run_id}:{step_id}:{step.attempt}:{loop_key}",
                ))
            allocation_deadline = monotonic() + self.scheduler_wait_timeout
            retry_delay = 0.05
            while True:
                # The embedded agent runtime executes in this process. Its
                # continued presence is the authoritative liveness signal;
                # without this heartbeat a valid long Run becomes permanently
                # ineligible once the registration heartbeat reaches its TTL.
                try:
                    self.resource_plane.heartbeat_runtime(
                        EMBEDDED_AGENTS_RUNTIME_ID, source="local"
                    )
                    embedded_node = self.resource_plane.runtime(
                        EMBEDDED_AGENTS_RUNTIME_ID
                    ).node_id
                    self.resource_plane.heartbeat_node(embedded_node)
                except KeyError:
                    pass
                decision = self.resource_binder.bind_ready(
                    run_id=run.run_id,
                    step_id=step_id,
                    attempt_id=attempt_id,
                    requirement=requirement,
                )
                if decision.status == "allocated":
                    break
                if decision.status == "rejected" or (decision.reason or "") in FATAL_SCHEDULING_REASONS:
                    rejected = ", ".join(
                        f"{item.resource_id}:[{','.join(reason.value for reason in item.reasons)}]"
                        for item in decision.candidates
                        if item.reasons
                    )
                    raise SchedulerNoEligibleResource(
                        f"{decision.reason}:{step_id}: "
                        f"{rejected or 'no registered candidates'}",
                        reason=decision.reason, step_id=step_id, candidates=decision.candidates,
                    )
                if monotonic() >= allocation_deadline:
                    raise SchedulerAllocationTimeout(
                        f"SCHEDULER_CAPACITY_TIMEOUT:{step_id}: "
                        f"no lease after {self.scheduler_wait_timeout:g}s",
                        step_id=step_id, candidates=decision.candidates,
                    )
                if self._cancellation_requested(run.run_id):
                    raise ExecutionRunCancelled(
                        f"run {run.run_id} cancelled while waiting for step {step_id} lease"
                    )
                await asyncio.sleep(retry_delay)
                retry_delay = min(1.0, retry_delay * 2)
            assert decision.binding is not None and decision.lease is not None
            if permit_authority is not None and "graphActivation" in run.execution_state:
                try:
                    permit_authority.assert_dispatchable(run)
                except (ValueError, KeyError, TypeError) as exc:
                    self.resource_binder.release(decision.lease.lease_id)
                    raise ExecutionRunCancelled("execution permit changed after resource allocation") from exc
            from components.resource.scheduler.binder import LeaseKeepAlive

            keep_alive = LeaseKeepAlive(
                self.resource_binder.coordinator, decision.lease
            )
            keep_alive.start()
            remote_adapter = None
            selected_resource_id = decision.binding.resource_id
            outcome_unknown = False
            step_execution_id = None
            cancellation_reason = "attempt_settled"
            try:
                binding = decision.binding
                selected_resource_id = binding.resource_id
                remote_adapter = self._remote_runtime_adapter(selected_resource_id)
                if remote_adapter is not None:
                    runtime_profile = self.resource_plane.runtime(selected_resource_id)
                    runner.resource_execution_adapters[step_id] = remote_adapter
                    remote_agent_id = binding.metadata.get("agentId") or selected_resource_id
                    runner.agents[step_id] = ResourceAgentProxy(
                        profile=AgentProfile(
                            agentId=str(remote_agent_id),
                            agentName=step.agent_name or str(remote_agent_id),
                            domain=run.domain,
                            capabilities=list(runtime_profile.capabilities),
                            enabled=runtime_profile.enabled,
                        ),
                        adapter=remote_adapter,
                    )
                    selected_profile = runner.agents[step_id].profile
                    agent_id = str(selected_profile.agent_id or selected_resource_id)
                else:
                    runner.resource_execution_adapters.pop(step_id, None)
                    selected_agent = self._resolve_embedded_agent(
                        run=run,
                        step=step,
                        role_hint=requirement.preferences.get("agentRole"),
                    )
                    agent_id = str(self.agent_registry.agent_id(selected_agent))
                    runner.agents[step_id] = selected_agent
                    selected_profile = selected_agent.profile
                run.execution_state.setdefault("logicalAgents", {})[step_id] = agent_id
                model_binding = self._resolve_model_binding(
                    step_id=step_id,
                    binding=binding,
                    profile=selected_profile,
                )
                run.execution_state.setdefault("modelBindings", {})[step_id] = model_binding
                if model_binding is not None:
                    model_runtime = self._model_runtime_from_binding(model_binding)
                    if model_runtime is not None:
                        runner.model_runtimes[step_id] = model_runtime
                runner.attempt_ids[step_id] = attempt_id
                step_execution_id = (
                    run.execution_state.setdefault("stepExecutionIds", {}).setdefault(
                        attempt_key,
                        new_step_execution_id()
                        if self.identity_lifecycle is not None
                        else f"execution:{attempt_id}",
                    )
                )
                profile = selected_profile
                base_events = [
                    self._lifecycle_event(
                        f"attempt.ensured:{attempt_id}", "attempt.ensured", run.run_id,
                        {"runId": run.run_id, "missionId": run.mission_id, "stepId": step_id,
                         "attemptId": attempt_id, "attemptNumber": attempt_number},
                    ),
                    self._lifecycle_event(
                        f"resource.bound:{attempt_id}", "resource.bound", attempt_id,
                        {"attemptId": attempt_id,
                         "binding": decision.binding.model_dump(by_alias=True, mode="json"),
                         "agentId": str(profile.agent_id or decision.binding.resource_id),
                         "modelId": str(profile.model_name or "runtime-default")},
                    ),
                    self._lifecycle_event(
                        f"step.started:{step_execution_id}", "step.started", step_execution_id,
                        {"runId": run.run_id, "attemptId": attempt_id, "stepId": step_id,
                         "stepExecutionId": step_execution_id},
                    ),
                ]
                run.execution_state.setdefault("executionBindings", {})[step_id] = (
                    decision.binding.model_dump(by_alias=True, mode="json")
                )
                run.execution_state.setdefault("schedulingDecisions", []).append(
                    {
                        "stepId": step_id,
                        "attemptId": attempt_id,
                        "candidates": [
                            item.model_dump(by_alias=True, mode="json") for item in decision.candidates
                        ],
                        "binding": decision.binding.model_dump(by_alias=True, mode="json"),
                        "lease": decision.lease.model_dump(by_alias=True, mode="json"),
                    }
                )
                run.execution_state.setdefault("resourceBindings", {})[step_id] = (
                    decision.binding.resource_id
                )
                base_events = self._reuse_persisted_lifecycle_events(base_events)
                self.workflow_store.save_run_with_events(run, base_events)
                self._flush_identity_outbox()
                if permit_authority is not None and "graphActivation" in run.execution_state:
                    try:
                        permit_authority.assert_dispatchable(run)
                    except (ValueError, KeyError, TypeError) as exc:
                        raise ExecutionRunCancelled("execution permit changed before node dispatch") from exc
                execution_started = monotonic()
                runner_task = asyncio.create_task(runner(step_id, state), name=f"acg-runner:{run.run_id}:{step_id}")
                renewal_failure_task = asyncio.create_task(keep_alive.wait_failed(), name=f"acg-renewal:{run.run_id}:{step_id}")
                try:
                    done, _ = await asyncio.wait(
                        {runner_task, renewal_failure_task}, return_when=asyncio.FIRST_COMPLETED,
                    )
                    if renewal_failure_task in done:
                        cancellation_reason = "lease_renewal_failure"
                        raise renewal_failure_task.result()
                    result = runner_task.result()
                except asyncio.CancelledError as exc:
                    cancellation_reason = ("operator_cancel" if self._cancellation_requested(run.run_id)
                                           else str(exc) or "execution_cancelled")
                    raise
                finally:
                    results = await cancel_and_wait((runner_task, renewal_failure_task), reason=cancellation_reason)
                    if cancellation_reason != "attempt_settled" and isinstance(results[0], Exception):
                        raise results[0]
                execution_outcome = "completed"
                self._observe_resource_execution(
                    selected_resource_id,
                    success=True,
                    latency_ms=(monotonic() - (execution_started or monotonic())) * 1000,
                )
                self._save_attempt_events(run, [self._lifecycle_event(
                    f"step.succeeded:{step_execution_id}", "step.succeeded", step_execution_id,
                    {"runId": run.run_id, "attemptId": attempt_id,
                     "stepExecutionId": step_execution_id,
                     "result": self._safe_lifecycle_result(result)},
                )])
                self._flush_identity_outbox()
                return result
            except ExecutionRunCancelled:
                execution_outcome = "cancelled"
                reason = "operator_cancel" if self._cancellation_requested(run.run_id) else "execution_authority_changed"
                self._save_attempt_events(run, [self._lifecycle_event(
                    f"step.cancelled:{step_execution_id}", "step.cancelled", step_execution_id,
                    {"runId": run.run_id, "attemptId": attempt_id,
                     "stepExecutionId": step_execution_id, "reason": reason},
                )])
                self._flush_identity_outbox()
                raise
            except asyncio.CancelledError as exc:
                execution_outcome = "cancelled"
                reason = ("operator_cancel" if self._cancellation_requested(run.run_id)
                          else str(exc) or "execution_cancelled")
                self._save_attempt_events(run, [self._lifecycle_event(
                    f"step.cancelled:{step_execution_id}", "step.cancelled", step_execution_id,
                    {"runId": run.run_id, "attemptId": attempt_id,
                     "stepExecutionId": step_execution_id, "reason": reason},
                )])
                self._flush_identity_outbox()
                raise
            except Exception as exc:
                from contracts.runtime_events import RuntimeEvent
                from runtime.live_events import runtime_event_broker

                error_code = str(
                    getattr(exc, "code", None)
                    or getattr(exc, "cause_code", None)
                    or type(exc).__name__
                )
                resource_error = self._unwrap_resource_execution_error(exc)
                outcome_unknown = bool(getattr(exc, "outcome_unknown", False)
                                       or (resource_error is not None and resource_error.outcome_unknown))
                if outcome_unknown:
                    execution_outcome = "unknown"
                if self._cancellation_requested(run.run_id) and step_execution_id is not None:
                    self._save_attempt_events(run, [self._lifecycle_event(
                        f"step.cancelled:{step_execution_id}", "step.cancelled", step_execution_id,
                        {"runId": run.run_id, "attemptId": attempt_id,
                         "stepExecutionId": step_execution_id, "reason": "operator_cancel",
                         "settlement": "unknown" if outcome_unknown else "ended_with_error",
                         "errorCode": error_code},
                    )])
                await runtime_event_broker.publish(
                    run.run_id,
                    RuntimeEvent(
                        eventType="node.failed",
                        runId=run.run_id,
                        nodeId=step_id,
                        attemptId=attempt_id,
                        sequence=0,
                        payload={
                            "errorCode": error_code,
                            "retryable": bool(getattr(exc, "retryable", False)),
                            "attempt": attempt_number,
                        },
                    ),
                )
                if remote_adapter is not None and isinstance(exc, ResourceExecutionError):
                    self.resource_plane.set_runtime_health(selected_resource_id, healthy=False)
                self._observe_resource_execution(
                    selected_resource_id,
                    success=False,
                    latency_ms=(monotonic() - (execution_started or monotonic())) * 1000,
                )
                if outcome_unknown:
                    # Performance observation updates heartbeat/health. Quarantine
                    # last, so that observation cannot undo UNKNOWN isolation.
                    self.resource_plane.set_runtime_health(selected_resource_id, healthy=False)
                    self.resource_plane.set_runtime_enabled(selected_resource_id, enabled=False)
                if step_execution_id is not None:
                    self._save_attempt_events(run, [self._lifecycle_event(
                        f"step.failed:{step_execution_id}", "step.failed", step_execution_id,
                        {"runId": run.run_id, "attemptId": attempt_id,
                         "stepExecutionId": step_execution_id, "reason": self._safe_error_message(exc),
                         "reasonCode": "lease_renewal_failure" if isinstance(exc, LeaseRenewalFailedError) else error_code},
                    )])
                self._flush_identity_outbox()
                raise
            finally:
                failure = sys.exception()
                async def cleanup():
                    stop_error = None
                    try:
                        await keep_alive.stop()
                    except BaseException as exc:
                        stop_error = exc
                        raise
                    finally:
                        finished = monotonic()
                        started = execution_started or finished
                        run.execution_state.setdefault("stepPerformance", {})[step_id] = {
                            "schedulingWaitMs": round((started - scheduling_started) * 1000),
                            "executionMs": round((finished - started) * 1000),
                            "totalMs": round((finished - scheduling_started) * 1000),
                            "outcome": execution_outcome,
                            "resourceId": selected_resource_id,
                        }
                        lease_state = "retained_unknown" if outcome_unknown else "release_failed"
                        try:
                            if not outcome_unknown:
                                released = self.resource_binder.release(decision.lease.lease_id)
                                lease_state = "released" if released else "not_owned"
                        finally:
                            cleanup_error = sys.exception()
                            settlement = {"taskState": "ended", "outcome": execution_outcome,
                                          "leaseState": lease_state, "leaseId": decision.lease.lease_id,
                                          "trigger": cancellation_reason}
                            if failure is not None and not isinstance(failure, asyncio.CancelledError):
                                settlement["errorType"] = type(failure).__name__
                            if cleanup_error is not None or stop_error is not None:
                                settlement["cleanupErrorType"] = type(cleanup_error or stop_error).__name__
                            run.execution_state.setdefault("taskSettlement", {})[attempt_id] = settlement
                            latest = self.workflow_store.get_run(run.run_id)
                            candidate = latest.model_copy(deep=True)
                            candidate.execution_state.setdefault("taskSettlement", {})[attempt_id] = settlement
                            candidate.execution_state.setdefault("stepPerformance", {})[step_id] = run.execution_state["stepPerformance"][step_id]
                            for snapshot in (run, candidate):
                                for item in snapshot.execution_state.get("schedulingDecisions", []):
                                    lease = item.get("lease") or {}
                                    if lease.get("leaseId") == decision.lease.lease_id and lease_state == "released":
                                        lease["status"] = "released"
                            candidate.updated_at = max(utc_now(), latest.updated_at)
                            # Cleanup metadata is not another Run transition.
                            # Commit it with CAS without emitting run.finished again.
                            self.workflow_store.save_run_with_events(candidate, [], expected_snapshot=latest)

                await await_settled(asyncio.create_task(cleanup(), name=f"acg-cleanup:{run.run_id}:{step_id}"))

        execute.prepare_superstep = runner.prepare_superstep
        return execute

    def _save_attempt_events(self, run: RuntimeRunRecord, events: list[dict]) -> None:
        latest = self.workflow_store.get_run(run.run_id)
        if latest.status in self._terminal_run_statuses:
            # Only cancellation/cleanup facts may arrive after durable cancellation.
            events = [event for event in events if event["eventType"] == "step.cancelled"]
            if not events or latest.status != WorkflowStatus.CANCELLED:
                return
            self.workflow_store.save_run_with_events(latest, events, expected_snapshot=latest)
        else:
            self.workflow_store.save_run_with_events(run, events, expected_snapshot=latest)

    def _observe_resource_execution(self, runtime_id: str, *, success: bool, latency_ms: float) -> None:
        """把一次 attempt 的真实执行结果回写资源观测（延迟/可靠性/健康事件）。

        观测属于旁路信号：任何失败只降级为日志，绝不影响执行主流程。
        """
        try:
            self.resource_plane.observe_execution(
                runtime_id, success=success, latency_ms=max(0.0, latency_ms)
            )
        except Exception as exc:  # 观测永远不阻断执行
            logger.warning("resource observation failed for %s: %s", runtime_id, exc)

    @staticmethod
    def _lifecycle_event(event_id: str, event_type: str, aggregate_id: str, payload: dict) -> dict:
        return {"eventId": event_id, "eventType": event_type, "aggregateId": aggregate_id, "payload": payload}

    @staticmethod
    def _safe_lifecycle_result(result: dict) -> dict:
        allowed = {
            "commitId", "outputRef", "outputSummary", "contextRef", "memoryRef",
            "traceRef", "auditDecisionRef", "auditOutcome", "nodeExecution",
            "communicationRefs", "evidenceRefs", "provenanceEvents",
        }
        safe = {key: result[key] for key in allowed if result.get(key) is not None}
        raw = result.get("artifacts")
        if raw is None and isinstance(result.get("artifact"), dict):
            raw = [result["artifact"]]
        elif isinstance(raw, dict):
            raw = [raw]
        if isinstance(raw, list):
            descriptor_keys = {
                "artifactKey", "semanticTaskKey", "name", "title", "artifactType",
                "type", "mediaType", "manifestId", "checksum", "metadata",
            }
            descriptors = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                descriptor = {
                    key: item[key]
                    for key in descriptor_keys
                    if item.get(key) is not None
                }
                descriptor.setdefault("artifactKey", "primary")
                descriptors.append(descriptor)
            if descriptors:
                safe["artifacts"] = descriptors
        return safe

    def _reuse_persisted_lifecycle_events(self, events: list[dict]) -> list[dict]:
        """Reuse the first committed event body during an idempotent attempt resume.

        Scheduler leases carry timestamps and scores, so rebuilding the same attempt
        can otherwise produce a different payload for an already persisted event ID.
        The store remains authoritative: a different payload is still rejected by
        ``save_run_with_events`` when no prior event exists in the outbox.
        """
        existing = {
            str(item.get("event_id")): item
            for item in self.workflow_store.list_outbox(limit=100000)
            if isinstance(item, dict) and item.get("event_id")
        }
        normalized: list[dict] = []
        for event in events:
            prior = existing.get(str(event.get("eventId")))
            if prior is None:
                normalized.append(event)
                continue
            payload = prior.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = None
            normalized.append({
                "eventId": prior["event_id"],
                "eventType": prior["event_type"],
                "aggregateId": prior["aggregate_id"],
                "payload": payload if isinstance(payload, dict) else event.get("payload", {}),
            })
        return normalized

    @staticmethod
    def _validate_acg_resume_identity(
        *,
        run: RuntimeRunRecord,
        workflow: WorkflowDefinition,
        blueprint: RuntimeBlueprintSpec,
        state: ACGExecutionState,
    ) -> None:
        """恢复前校验运行、蓝图、工作流和 checkpoint 的版本身份。"""
        expected_graph_id = str(run.execution_state.get("graphId") or blueprint.graph_id)
        if state.graph_id != expected_graph_id:
            raise ValueError(
                f"checkpoint graphId {state.graph_id!r} does not match run graphId {expected_graph_id!r}"
            )
        if int(state.graph_version) != int(blueprint.version):
            raise ValueError(
                f"checkpoint graphVersion {state.graph_version} does not match blueprint version {blueprint.version}"
            )
        permit_projection = (run.execution_state.get("graphActivation") or {}).get("executionPermit")
        if isinstance(permit_projection, dict):
            if (state.execution_permit_id != run.execution_state.get("executionPermitId")
                    or state.execution_generation != run.execution_state.get("executionGeneration")
                    or state.checkpoint_id != run.execution_state.get("checkpointId")):
                raise ValueError("checkpoint permit, generation or recovery identity does not match Run")
        elif state.execution_permit_id is not None or state.execution_generation is not None:
            raise ValueError("checkpoint has an execution generation without a durable permit")
        source_blueprint_version = run.execution_state.get("sourceBlueprintVersion")
        if source_blueprint_version is not None and int(blueprint.version) != int(source_blueprint_version):
            raise ValueError(
                "checkpoint sourceBlueprintVersion does not match persisted blueprint version"
            )
        workflow_version = run.execution_state.get("workflowVersion")
        if workflow_version is not None and str(workflow.version) != str(workflow_version):
            raise ValueError("checkpoint workflowVersion does not match persisted workflow version")

    def validate_state_references(
        self,
        *,
        run: RuntimeRunRecord,
        state: ACGExecutionState,
        ledger: ProvenanceLedger | None = None,
    ) -> None:
        """在恢复前重验检查点的引用归属，且不读取任何输出或上下文正文。

        State 字典的键就是产生引用的步骤标识。若键、runId 或引用类别被篡改，必须在
        改变运行生命周期、创建 Agent 或追加血缘事件之前停止，避免恢复路径成为越权入口。
        """
        valid_step_ids = {step.step_id for step in run.steps}
        reference_maps = {
            "output summaries": state.output_summaries,
            "output": state.output_refs,
            "context": state.context_refs,
            "memory": state.memory_refs,
            "trace": state.trace_refs,
            "provenance": state.provenance_refs,
        }
        for reference_name, references in reference_maps.items():
            for step_id in references:
                if step_id not in valid_step_ids:
                    raise ValueError(f"unknown ACG step {step_id} in {reference_name} references")
        for step_id, output_ref in state.output_refs.items():
            self.execution_value_store.assert_reference(
                kind="output", run_id=run.run_id, step_id=step_id, reference=output_ref
            )
        for step_id, context_ref in state.context_refs.items():
            self.execution_value_store.assert_reference(
                kind="context", run_id=run.run_id, step_id=step_id, reference=context_ref
            )
        for patch_ref in state.graph_patch_refs:
            self.execution_value_store.assert_reference(
                kind="graph-patch",
                run_id=run.run_id,
                step_id="__graph__",
                reference=patch_ref,
            )
        for step_id, memory_ref in state.memory_refs.items():
            if memory_ref != "memory:none":
                MemoryService(store=self.memory_store).assert_step_ref(
                    run_id=run.run_id,
                    step_id=step_id,
                    memory_ref=memory_ref,
                )
        for step_id, trace_ref in state.trace_refs.items():
            if trace_ref != f"trace:{step_id}":
                raise ValueError(f"trace reference {trace_ref} does not belong to step {step_id}")
            if not any(
                event.event_type == TraceEventType.STEP_SUCCEEDED and event.step_id == step_id
                for event in run.trace
            ):
                raise ValueError(f"trace reference {trace_ref} has no completed trace for step {step_id}")
        active_ledger = ledger or self.provenance_store.load_ledger(
            run_id=run.run_id,
            mission_id=run.mission_id,
        )
        for step_id, event_ids in state.provenance_refs.items():
            for event_id in event_ids:
                active_ledger.assert_event_owner(event_id=event_id, step_id=step_id)
        review_payload = state.review_payload
        if isinstance(review_payload, dict):
            decision_ref = review_payload.get("auditDecisionRef")
            outcome = review_payload.get("auditOutcome")
            review_step_id = review_payload.get("stepId")
            if isinstance(decision_ref, str) and isinstance(outcome, str) and isinstance(review_step_id, str):
                self.decision_store.assert_decision(
                    run_id=run.run_id,
                    step_id=review_step_id,
                    decision_ref=decision_ref,
                    outcomes={outcome},
                )

    def _complete_run(self, run, state, blueprint, task):
        """Finalize through the same lifecycle after an authorized completion."""
        run.output = self._acg_output(state, blueprint)
        run = self._set_run_lifecycle(run, status=WorkflowStatus.COMPLETED,
            phase=WorkflowProgressPhase.COMPLETED,
            message=self._lifecycle_messages[WorkflowProgressPhase.COMPLETED])
        self._mark_completed(task)
        self.trace_store.append(run, TraceEventType.RUN_COMPLETED, observation="ACG workflow completed")
        self.workflow_store.save_run(run)
        self._publish_run_terminal_event(run, "run.completed")
        if self.identity_lifecycle is not None:
            self._flush_identity_outbox()
        return run

    def _build_runner(
        self,
        *,
        task: RuntimeMissionRecord,
        run: RuntimeRunRecord,
        workflow: WorkflowDefinition,
        graph,
        state: ACGExecutionState,
        ledger: ProvenanceLedger,
    ) -> ACGNodeRunner:
        """按冻结插件范围解析 Agent，并组装本 run 的通信、记忆与适配依赖。"""
        steps = {step.step_id: step for step in run.steps}
        bindings = run.execution_state.get("resourceBindings")
        if not isinstance(bindings, dict):
            bindings = {}
        agents = {}
        resource_adapters = {}
        for step_id, step in steps.items():
            resource_id = str(bindings.get(step_id) or "")
            if not resource_id:
                # The READY wrapper will populate this step after the binder
                # allocation. Preparation must not force a concrete resource.
                continue
            persisted = (run.execution_state.get("executionBindings") or {}).get(step_id)
            binding = (
                ExecutionBinding.model_validate(persisted)
                if isinstance(persisted, dict) and persisted.get("resourceId") == resource_id
                else None
            )
            runtime_id = binding.resource_id if binding is not None else resource_id
            adapter = self._remote_runtime_adapter(runtime_id)
            if adapter is None:
                # 嵌入式后端：恢复期按历史绑定或能力解析逻辑 Agent。
                agents[step_id] = self._resolve_embedded_agent(
                    run=run, step=step, role_hint=None
                )
                continue
            runtime_profile = self.resource_plane.runtime(runtime_id)
            agents[step_id] = ResourceAgentProxy(
                profile=AgentProfile(
                    agentId=(binding.metadata.get("agentId") if binding is not None else None) or runtime_id,
                    agentName=step.agent_name or runtime_id,
                    domain=workflow.domain,
                    capabilities=list(runtime_profile.capabilities),
                    enabled=runtime_profile.enabled,
                ),
                adapter=adapter,
            )
            resource_adapters[step_id] = adapter
        communication_rules = tuple(
            getattr(graph.communication_manifest, "rules", ())
            if graph.communication_manifest is not None
            else ()
        )
        upstream_step_ids = {
            node_id: tuple(
                dict.fromkeys(
                    [source for source, target in graph.edges if target == node_id]
                    + [
                        rule.producer_step_id
                        for rule in communication_rules
                        if rule.consumer_step_id == node_id
                    ]
                )
            )
            for node_id in steps
        }
        allowed_agent_ids = run.execution_scope.agent_ids if run.execution_scope is not None else None
        allowed_agent_set = set(allowed_agent_ids) if allowed_agent_ids is not None else None
        allowed_tools = {
            tool_name
            for agent in self.agent_registry.all()
            if allowed_agent_set is None or self.agent_registry.agent_id(agent) in allowed_agent_set
            for tool_name in agent.profile.allowed_tools
        }
        delegate = self.tool_runtime or configured_tool_runtime()
        # 工具必须先经过 AgentOS 的授权检查，再进入统一的超时、重试、限流与安全
        # 错误映射边界。对已受保护的运行时不重复包装，避免双重重试放大副作用。
        protected_tools = (
            delegate
            if isinstance(delegate, GuardedToolRuntime)
            else GuardedToolRuntime(delegate=delegate, retries=1)
        ) if delegate is not None else None
        scoped_tools = (
            AuditedToolRuntime(delegate=protected_tools, allowed_tools=allowed_tools)
            if protected_tools is not None
            else None
        )
        # Broker 由单次图执行共享，读取后的预算计数写入引用型 State；从检查点恢复
        # 时，已消费额度会作为构造参数重新载入，不能因重启而回到零。
        communication_broker = (
            CommunicationBroker(
                manifest=graph.communication_manifest,
                value_store=self.execution_value_store,
                usage=state.communication_usage,
            )
            if graph.communication_manifest is not None
            else None
        )
        if communication_broker is not None:
            # 空图或仅根节点的运行同样必须采用统一的零值表示。否则首次执行会在
            # Broker 调用后才写入零计数，而提交重放会保留空对象，造成等价状态生成
            # 不同 checkpoint 摘要并破坏恢复幂等性。
            state.communication_usage = communication_broker.usage_snapshot()
        model_bindings = run.execution_state.get("modelBindings")
        if not isinstance(model_bindings, dict):
            model_bindings = {}
        # Steps frozen to the same provider/model must share one guard. Creating
        # one guard per step makes every semaphore independent and allows a
        # parallel superstep to burst past the provider quota.
        shared_model_runtimes: dict[str, object | None] = {}
        step_model_runtimes: dict[str, object | None] = {}
        for step_id in steps:
            binding = model_bindings.get(step_id)
            cache_key = json.dumps(binding, sort_keys=True) if isinstance(binding, dict) else "null"
            if cache_key not in shared_model_runtimes:
                shared_model_runtimes[cache_key] = self._model_runtime_from_binding(binding)
            step_model_runtimes[step_id] = shared_model_runtimes[cache_key]
        resolved_task = task.model_copy(deep=True)
        resolved_task.input = (
            self.attachment_context_builder.enrich(dict(run.input))
            if self.attachment_context_builder is not None
            else dict(run.input)
        )
        return ACGNodeRunner(
            task=resolved_task,
            run=run,
            workflow=workflow,
            steps=steps,
            agents=agents,
            communicator=CommunicatorService(
                run_id=run.run_id,
                mission_id=task.mission_id,
                ledger=ledger,
            ),
            memory=MemoryService(store=self.memory_store),
            entropy_budget=(int(run.input["entropyBudget"]) if run.input.get("entropyBudget") is not None else None),
            value_store=self.execution_value_store,
            content_manifest_store=self.content_manifest_store,
            communication_modes={node_id: spec.communication_mode for node_id, spec in graph.node_specs.items() if spec.kind == "step"},
            upstream_step_ids=upstream_step_ids,
            model_runtime=self.model_runtime,
            model_runtimes={
                step_id: runtime
                for step_id, runtime in step_model_runtimes.items()
                if runtime is not None
            },
            capability_descriptors={
                step.capability: self.capability_catalog.resolve(step.capability)
                for step in steps.values()
                if step.capability
            },
            tool_runtime=scoped_tools,
            communication_broker=communication_broker,
            reliable_communication_store=self.reliable_communication_store,
            compiled_package=graph.compiled_package,
            skill_manifest=graph.compiled_package.skill_manifest,
            memory_manifest=graph.compiled_package.memory_manifest,
            evidence_manifest=graph.compiled_package.evidence_manifest,
            agent_invoker=AgentInvocationAdapter(
                registry=(self.agent_registry.scoped(allowed_agent_ids) if allowed_agent_ids is not None else self.agent_registry)
            ),
            resource_execution_adapters=resource_adapters,
            decision_store=self.decision_store,
            fault_hook=self._fault_hook,
        )

    def _project_event(self, run: RuntimeRunRecord, state: ACGExecutionState, event: dict) -> None:
        """投影单个图事件与步骤状态；事件正文只含步骤标识、摘要或引用。"""
        projection_before = self._acg_projection_snapshot(run, state)
        event_type = event.get("type")
        commit_id = event.get("commitId")
        node_trace_batch: list[TraceEvent] = []
        if event_type == "node_completed" and isinstance(commit_id, str) and self._is_projected_commit(run, commit_id):
            # Trace 已经确认过该提交，说明上次在状态保存前中断。重放时不能再次追加
            # 步骤成功、记忆访问或通信血缘事件；但可变 WorkflowStep 投影仍必须与
            # 提交事实对齐，否则 Run 会在完成时残留 RUNNING 步骤。
            step_id = str(event.get("stepId"))
            step = run.get_step(step_id)
            step.status = StepStatus.COMPLETED
            step.completed_at = step.completed_at or utc_now()
            run.current_step_id = step_id
            run.completed_step_ids = list(state.completed_step_ids)
            run.active_step_ids = list(state.active_step_ids)
            self.state_persistence.persist(
                run,
                state,
                projection_changed=(self._acg_projection_snapshot(run, state) != projection_before),
            )
            return
        if event_type == "nodes_scheduled":
            for step_id in event.get("stepIds", []):
                step = run.get_step(str(step_id))
                step.status = StepStatus.RUNNING
                step.started_at = step.started_at or utc_now()
            run.active_step_ids = list(event.get("stepIds", []))
            run.current_step_id = state.current_step_id
        elif event_type == "node_completed":
            step_id = str(event.get("stepId"))
            step = run.get_step(step_id)
            step.status = StepStatus.COMPLETED
            step.completed_at = utc_now()
            run.current_step_id = step_id
            run.completed_step_ids = list(state.completed_step_ids)
            # Graph 的并行 superstep 会逐个 yield 完成事件，State.activeStepIds
            # 在整批提交前仍包含兄弟节点；已完成节点不能继续显示为活动。
            run.active_step_ids = [
                item for item in state.active_step_ids
                if item not in state.completed_step_ids
            ]
            for runtime_event in event.get("runtimeEvents") or []:
                if not isinstance(runtime_event, dict):
                    continue
                if runtime_event.get("eventType") in TRANSIENT_RUNTIME_EVENT_TYPES:
                    continue
                target = runtime_event.get("nodeId") or step_id
                payload = {key: value for key, value in runtime_event.items() if key not in {"eventId", "eventType", "runId", "nodeId"}}
                node_trace_batch.append(self.trace_store.build_event(
                    run, event_type=TraceEventType.RUNTIME_EVENT_CLASSIFIED,
                    step_id=str(target), observation=str(runtime_event.get("eventType") or "runtime event"),
                    payload={"runtimeEvent": str(runtime_event.get("eventType") or ""), **payload},
                ))
        elif event_type == "superstep_completed":
            self._project_completed_phase_capsules(run=run, state=state)
            checkpoint_id = self.state_persistence.save_checkpoint(run, state)
            state.checkpoint_id = checkpoint_id
            run.execution_state["checkpointId"] = checkpoint_id
            self.trace_store.append_execution_event(
                run,
                {"type": "checkpoint_created", "checkpointId": checkpoint_id},
            )
        elif event_type == "superstep_failed":
            for step_id in event.get("failedStepIds", []):
                step = run.get_step(str(step_id))
                if step.status in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.RETRYING}:
                    self._transition_step(step, StepStatus.FAILED)
                    step.error = "ACG superstep node failed"
            for step_id in event.get("cancelledStepIds", []):
                step = run.get_step(str(step_id))
                if step.status in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.RETRYING}:
                    self._transition_step(step, StepStatus.CANCELLED)
                    step.error = "ACG superstep cancelled after sibling failure"
            run.active_step_ids = []
        # 条件控制节点由图在超步边界内部推进，不会产生独立的节点事件。这里根据
        # 已持久化的 skippedStepIds 补齐 RuntimeRunRecord 的可见步骤状态，供查询、
        # 审计和取消逻辑一致地区分“未执行”与“条件明确跳过”。
        for step_id in state.skipped_step_ids:
            step = run.get_step(step_id)
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.SKIPPED_BY_CONDITION
                step.completed_at = utc_now()
        if event_type not in {"superstep_completed", "superstep_failed"}:
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_execution_event(run, event))
            else:
                self.trace_store.append_execution_event(run, event)
        if event_type == "superstep_failed":
            self.trace_store.append(
                run,
                TraceEventType.STEP_FAILED,
                step_id=(event.get("failedStepIds") or [None])[0],
                observation="ACG parallel superstep failed",
                payload={
                    "failedStepIds": list(event.get("failedStepIds") or []),
                    "cancelledStepIds": list(event.get("cancelledStepIds") or []),
                },
            )
        for model_call in event.get("modelInvocations", []):
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_event(
                    run,
                    event_type=TraceEventType.MODEL_CALLED,
                    step_id=event.get("stepId"),
                    observation="Model invocation metadata projected",
                    payload=dict(model_call),
                ))
            else:
                self.trace_store.append(
                    run,
                    TraceEventType.MODEL_CALLED,
                    step_id=event.get("stepId"),
                    observation="Model invocation metadata projected",
                    payload=dict(model_call),
                )
        for tool_call in event.get("toolCalls", []):
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_event(
                    run,
                    event_type=TraceEventType.TOOL_CALLED,
                    step_id=event.get("stepId"),
                    observation="Tool invocation metadata projected",
                    payload=dict(tool_call),
                ))
            else:
                self.trace_store.append(
                    run,
                    TraceEventType.TOOL_CALLED,
                    step_id=event.get("stepId"),
                    observation="Tool invocation metadata projected",
                    payload=dict(tool_call),
                )
        memory_access = event.get("memoryAccess")
        if isinstance(memory_access, dict):
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_event(
                    run,
                    event_type=TraceEventType.DATA_CONSUMED,
                    step_id=event.get("stepId"),
                    observation="Step memory policy applied",
                    payload=dict(memory_access),
                ))
            else:
                self.trace_store.append(
                    run,
                    TraceEventType.DATA_CONSUMED,
                    step_id=event.get("stepId"),
                    observation="Step memory policy applied",
                    payload=dict(memory_access),
                )
        memory_event = event.get("memoryEvent")
        if isinstance(memory_event, dict) and memory_event:
            projected = StructuredMemoryEvent.model_validate(memory_event).model_dump(
                by_alias=True, mode="json"
            )
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_event(
                    run,
                    event_type=TraceEventType.DATA_PRODUCED,
                    step_id=event.get("stepId"),
                    observation="Structured memory event projected",
                    payload=projected,
                ))
            else:
                self.trace_store.append(
                    run,
                    TraceEventType.DATA_PRODUCED,
                    step_id=event.get("stepId"),
                    observation="Structured memory event projected",
                    payload=projected,
                )
        # 通信读取事件来自 Broker，仅允许引用、字段名、计数与逻辑通道进入审计。
        # 即便节点事件被外部调用方伪造，也不能借此把 reason 或任何正文塞进 Trace。
        for communication_read in event.get("communicationReads", []):
            if not isinstance(communication_read, dict):
                continue
            allowed = {
                "runId",
                "consumerStepId",
                "producerStepId",
                "outputRef",
                "fields",
                "tokens",
                "channel",
            }
            payload = {
                key: value
                for key, value in communication_read.items()
                if key in allowed
            }
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_event(
                    run,
                    event_type=TraceEventType.DATA_CONSUMED,
                    step_id=event.get("stepId"),
                    observation="Broker communication read projected",
                    payload=payload,
                ))
            else:
                self.trace_store.append(
                    run,
                    TraceEventType.DATA_CONSUMED,
                    step_id=event.get("stepId"),
                    observation="Broker communication read projected",
                    payload=payload,
                )
        for provenance_event in event.get("provenanceEvents", []):
            if not isinstance(provenance_event, dict):
                continue
            event_name = provenance_event.get("eventType")
            trace_type = {
                "data_produced": TraceEventType.DATA_PRODUCED,
                "data_consumed": TraceEventType.DATA_CONSUMED,
            }.get(event_name)
            payload = provenance_event.get("payload")
            if trace_type is None or not isinstance(payload, dict):
                continue
            if event_type == "node_completed":
                node_trace_batch.append(self.trace_store.build_event(
                    run,
                    event_type=trace_type,
                    step_id=event.get("stepId"),
                    observation="Communication provenance projected",
                    payload=dict(payload),
                ))
            else:
                self.trace_store.append(
                    run,
                    trace_type,
                    step_id=event.get("stepId"),
                    observation="Communication provenance projected",
                    payload=dict(payload),
                )
        if node_trace_batch:
            self.trace_store.append_batch(run, node_trace_batch)
            self._inject_fault("after_trace")
        # 状态持久化属于图事件投影，不依赖模型或工具调用是否存在。若放在工具循环中，
        # 没有工具调用的普通节点会一直停留在存储层的旧快照，直到后续事件偶然覆盖。
        self.state_persistence.persist(
            run,
            state,
            projection_changed=(self._acg_projection_snapshot(run, state) != projection_before),
        )

    def _project_completed_phase_capsules(
        self,
        *,
        run: RuntimeRunRecord,
        state: ACGExecutionState,
    ) -> None:
        """Persist one deterministic capsule when every step in a planning stage completed."""
        if not isinstance(run.acg_blueprint, dict):
            return
        blueprint = RuntimeBlueprintSpec.model_validate(run.acg_blueprint)
        stages: dict[str, list[str]] = {}
        for node in blueprint.step_nodes():
            stage = str(node.metadata.get("planningStage") or "execution")
            stages.setdefault(stage, []).append(node.node_id)
        completed = set(state.completed_step_ids)
        capsule_refs = run.execution_state.setdefault("phaseCapsuleRefs", {})
        if not isinstance(capsule_refs, dict):
            raise ValueError("phaseCapsuleRefs must be an object")
        task = self._load_mission(run.mission_id)
        raw_constraints = task.input.get("constraints")
        constraints = raw_constraints if isinstance(raw_constraints, list) else []
        from contracts.mission_semantic import run_intent_basis
        basis = run_intent_basis(run)
        if basis is not None:
            constraints = [c.text for c in basis.constraints]
        raw_questions = task.input.get("openQuestions")
        open_questions = raw_questions if isinstance(raw_questions, list) else []
        service = MemoryService(store=self.memory_store)
        for stage, step_ids in stages.items():
            if not set(step_ids) <= completed:
                continue
            source_refs = [
                state.memory_refs[step_id]
                for step_id in step_ids
                if state.memory_refs.get(step_id) not in {None, "memory:none"}
            ]
            if not source_refs:
                continue
            capsule = service.create_phase_capsule(
                run_id=run.run_id,
                phase_id=stage,
                source_memory_refs=source_refs,
                goal=basis.objective if basis is not None else task.title,
                constraints=constraints,
                open_questions=open_questions,
            )
            previous = capsule_refs.get(stage)
            if previous is not None and previous != capsule.capsule_id:
                raise ValueError(f"phase {stage} already points to a different capsule")
            if previous == capsule.capsule_id:
                continue
            capsule_refs[stage] = capsule.capsule_id
            self.trace_store.append(
                run,
                TraceEventType.DATA_PRODUCED,
                observation="Phase capsule persisted",
                payload={
                    "kind": "phase_capsule",
                    "phaseId": stage,
                    "capsuleRef": capsule.capsule_id,
                    "sourceMemoryRefs": list(capsule.source_memory_refs),
                    "evidenceRefs": list(capsule.evidence_refs),
                    "tokenCount": capsule.token_count,
                },
            )

    @staticmethod
    def _is_projected_commit(run: RuntimeRunRecord, commit_id: str) -> bool:
        """通过既有步骤完成 Trace 判断提交是否已被投影，不额外保存正文状态。"""
        return any(
            event.event_type == TraceEventType.STEP_SUCCEEDED
            and event.payload.get("commitId") == commit_id
            for event in run.trace
        )

    @staticmethod
    def _acg_projection_snapshot(run: RuntimeRunRecord, state: ACGExecutionState) -> str:
        """返回用于判断 Run 是否真的发生可观察变化的稳定快照。

        该快照只存在于当前投影调用，不写入执行状态或 checkpoint。Trace 事件 ID、
        步骤状态和引用型 State 的变化都会触发版本推进；同一 commit 的重放如果没有
        修复任何缺失投影，则不会无意义地改变 ``updatedAt``。
        """
        steps = [
            {
                "stepId": step.step_id,
                "status": step.status.value,
                "startedAt": step.started_at.isoformat() if step.started_at else None,
                "completedAt": step.completed_at.isoformat() if step.completed_at else None,
                "error": step.error,
            }
            for step in run.steps
        ]
        return json.dumps(
            {
                "state": state.model_dump(by_alias=True, mode="json"),
                "completedStepIds": list(run.completed_step_ids),
                "activeStepIds": list(run.active_step_ids),
                "currentStepId": run.current_step_id,
                "steps": steps,
                "traceEventIds": [event.event_id for event in run.trace],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _inject_fault(self, stage: str) -> None:
        """调用测试专用中断钩子；正常执行没有附加分支或持久化副作用。"""
        if self._fault_hook is not None:
            self._fault_hook(stage)

    @staticmethod
    def _acg_output(
        state: ACGExecutionState,
        blueprint: RuntimeBlueprintSpec | None = None,
    ) -> dict[str, str]:
        """Select the final-synthesis output ref without copying its body."""
        if not state.completed_step_ids:
            return {}
        if blueprint is not None:
            final_step_ids = {
                node.node_id
                for node in blueprint.step_nodes()
                if is_final_synthesis_role(node.logical_role)
            }
            for step_id in reversed(state.completed_step_ids):
                if step_id in final_step_ids and state.output_refs.get(step_id):
                    return {"outputRef": state.output_refs[step_id]}
            if final_step_ids:
                # A completed Run with a declared final step but no committed
                # final output has no authoritative deliverable.
                return {}
            # Historical blueprints predate the final role. Keep their legacy
            # reference for compatibility; Workspace/API still refuse to
            # promote it without the canonical Artifact identity.
        # Compatibility fallback for callers that only provide the legacy state.
        for final_step_id in reversed(state.completed_step_ids):
            output_ref = state.output_refs.get(final_step_id)
            if output_ref:
                return {"outputRef": output_ref}
        return {}

    def _resolve_model_binding(self, *, step_id: str, binding: ExecutionBinding, profile) -> dict[str, Any] | None:
        """优先采用绑定冻结的模型端点；无端点绑定时回退角色画像/全局默认。

        模型端点绑定由 ResourceBinder 依据任务的 ModelDemand 决定；角色画像
        里的 modelProvider/modelName 只是兼容性偏好，不构成资源事实。
        """
        endpoint = binding.model_binding
        if endpoint is not None:
            resource_runtime = self._resource_model_runtime(endpoint.endpoint_id)
            if resource_runtime is not None:
                frozen: dict[str, Any] = {
                    "provider": endpoint.provider,
                    "model": endpoint.model,
                    "streamingCapability": False,
                    "endpointId": endpoint.endpoint_id,
                    "resourceModel": True,
                }
                if endpoint.version is not None:
                    frozen["version"] = endpoint.version
                return frozen
            try:
                adapter = self.model_registry.resolve(
                    endpoint.provider, endpoint.model, version=endpoint.version
                )
            except LookupError as exc:
                raise ValueError(
                    f"MODEL_PROFILE_UNAVAILABLE: step {step_id} cannot resolve "
                    f"{endpoint.provider}/{endpoint.model}"
                ) from exc
            frozen: dict[str, Any] = {
                "provider": endpoint.provider,
                "model": endpoint.model,
                # This is an explicit capability fact, not permission to fall back
                # to the synchronous gateway. NativeGeneralAgent enforces it.
                "streamingCapability": callable(getattr(adapter, "astream", None)),
            }
            if endpoint.version is not None:
                frozen["version"] = endpoint.version
            if endpoint.endpoint_id is not None:
                frozen["endpointId"] = endpoint.endpoint_id
            return frozen
        return self._freeze_model_binding(step_id=step_id, profile=profile)

    def _resource_model_runtime(self, endpoint_id: str | None):
        """构造已冻结资源端点的实际模型 transport；未实现协议返回 ``None``。

        这里不改变全局模型注册表。资源端点的 HMAC 凭据和地址只属于本次
        绑定，避免同名 provider/model 覆盖应用级默认路由。
        """
        if not endpoint_id:
            return None
        try:
            endpoint = self.resource_plane.model_endpoint(endpoint_id)
        except KeyError as exc:
            raise ValueError(f"MODEL_ENDPOINT_UNAVAILABLE: {endpoint_id}") from exc
        if endpoint.adapter != "agentos_model_http" or endpoint.runtime_id is None:
            return None
        try:
            runtime = self.resource_plane.runtime(endpoint.runtime_id)
        except KeyError as exc:
            raise ValueError(f"MODEL_RUNTIME_UNAVAILABLE: {endpoint.runtime_id}") from exc
        return build_resource_model_runtime(
            endpoint,
            runtime,
            credential_provider=self.resource_plane,
            execution_observer=self.resource_plane,
            audit_reporter=self.resource_plane,
        )

    def _freeze_model_binding(self, *, step_id: str, profile) -> dict[str, Any] | None:
        """验证并冻结步骤的 Profile 模型路由，禁止恢复时读取可变 Profile。"""
        provider = (getattr(profile, "model_provider", None) or "").strip()
        model = (getattr(profile, "model_name", None) or "").strip()
        version = (getattr(profile, "model_version", None) or "").strip() or None
        if not provider and not model:
            default = self.default_model_binding
            if not isinstance(default, dict):
                return None
            provider = str(default.get("provider") or "").strip()
            model = str(default.get("model") or "").strip()
            version = str(default.get("version") or "").strip() or None
            if not provider or not model:
                return None
        if not provider or not model:
            raise ValueError(
                f"MODEL_PROFILE_INCOMPLETE: step {step_id} must set both modelProvider and modelName"
            )
        try:
            self.model_registry.resolve(provider, model, version=version)
        except LookupError as exc:
            raise ValueError(
                f"MODEL_PROFILE_UNAVAILABLE: step {step_id} cannot resolve {provider}/{model}"
            ) from exc
        adapter = self.model_registry.resolve(provider, model, version=version)
        binding: dict[str, Any] = {
            "provider": provider,
            "model": model,
            # This is an explicit capability fact, not permission to fall back
            # to the synchronous gateway. NativeGeneralAgent enforces it.
            "streamingCapability": callable(getattr(adapter, "astream", None)),
        }
        if version is not None:
            binding["version"] = version
        return binding

    def _model_runtime_from_binding(self, binding: object) -> object | None:
        """依据冻结路由构造受保护运行时；未配置 Profile 时回退既有全局默认值。"""
        if binding is None:
            return None
        if not isinstance(binding, dict):
            raise ValueError("ACG model binding must be an object or null")
        provider = binding.get("provider")
        model = binding.get("model")
        version = binding.get("version")
        endpoint_id = binding.get("endpointId")
        if not isinstance(provider, str) or not isinstance(model, str):
            raise ValueError("ACG model binding is incomplete")
        if version is not None and not isinstance(version, str):
            raise ValueError("ACG model binding version is invalid")
        if isinstance(endpoint_id, str):
            resource_runtime = self._resource_model_runtime(endpoint_id)
            if resource_runtime is not None:
                return GuardedModelRuntime(
                    delegate=resource_runtime,
                    retries=1,
                    max_concurrency=self.model_max_concurrency,
                    min_interval_seconds=self.model_min_interval_seconds,
                )
        return GuardedModelRuntime(
            delegate=RegisteredModelRuntime(
                registry=self.model_registry,
                provider=provider,
                model=model,
                version=version,
            ),
            retries=2,
            max_concurrency=self.model_max_concurrency,
            min_interval_seconds=self.model_min_interval_seconds,
            retry_delay_seconds=1.0,
        )

    def _transition_step(self, step, status: StepStatus) -> None:
        step.status = self.state_machine.transition(step.status, status)
        if status == StepStatus.RUNNING:
            step.started_at = step.started_at or utc_now()
        if status == StepStatus.COMPLETED:
            step.completed_at = step.completed_at or utc_now()

    async def _finalize_cancelled_run(
        self,
        run: RuntimeRunRecord,
        execution_state: ACGExecutionState | None,
    ) -> RuntimeRunRecord:
        """把仍处于活动状态的投影收敛为 CANCELLED，并保留真实完成的最新进度。

        ``cancel()`` 先行写入了 CANCELLED 终态投影；本方法用携带更新后步骤状态
        的内存投影覆盖它，让审计能看到取消前实际完成的步骤，而不改变终态，
        也绝不把已取消的任务推进为 COMPLETED。
        """
        latest = self.workflow_store.get_run(run.run_id)
        if latest.status in self._terminal_run_statuses:
            return latest
        if execution_state is not None:
            self.state_persistence.persist(run, execution_state)
        if run.status in self._terminal_run_statuses:
            return run
        run.status = self.state_machine.transition(run.status, WorkflowStatus.CANCELLED)
        run.lifecycle_phase = WorkflowProgressPhase.CANCELLED
        run.lifecycle_message = self._lifecycle_messages[WorkflowProgressPhase.CANCELLED]
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)
        return run


__all__ = ["ACGExecutionService", "ExecutionRunCancelled"]

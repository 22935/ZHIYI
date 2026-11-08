"""Runtime 恢复应用边界：把已决定的恢复动作映射到现有 Runtime 操作。

三层所有权（PR-8C.3）：
- 失败检测 = ``ACGExecutionService``（执行循环内的 except 收敛入口）；
- 恢复策略 = 既有 ``components.recovery.RecoveryService``（domain，未改动）；
- 恢复应用 = 本协调器。

本协调器承载：single-step retry 的继任 Run 准备、review barrier 处的 concrete
rebind、checkpoint resume 的应用校验，以及执行失败的 FailureEvent 投影与
proposed recoveryOutcome 持久化。Run 锁与执行槽由 facade 持有；retry/rebind/
resume 一律只改 concrete runtime 投影，不触碰 TaskPlan、graphVersion 或任何
语义修订路径（语义变更只能走 SemanticRevisionService）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
import logging
from typing import Any

from contracts.identity import new_attempt_id, new_step_execution_id
from components.executor import ACGExecutionState, ACGGraphCompiler
from components.mission_manager.state_machine import StateMachine


class ResourceNotFoundError(KeyError):
    """冻结范围内没有可用的替代执行资源。"""

from contracts.execution import WorkflowProgressPhase
from contracts.resource import ExecutionRequirement
from contracts.workflow import (
    RuntimeMissionRecord,
    RuntimeRunRecord,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowStatus,
    utc_now,
)
from runtime.ports import CollaboratorAccess, RuntimeCollaborators
from runtime.state_persistence import acg_execution_state_from_run
from support.acg.schema import RuntimeBlueprintSpec
from support.stores._policy import acg_review_subject


logger = logging.getLogger(__name__)


def _normalize_runtime_engine(runtime_engine: str) -> str:
    return (runtime_engine or "").strip().lower()


class RuntimeRecoveryCoordinator(CollaboratorAccess):
    """应用层恢复协调器：决定已定时，把动作落到 Runtime 可执行的操作上。"""

    @staticmethod
    def node_rerun_cut(graph, package, step_id):
        """Invalidate causal consumers, treating each declared loop as one region.

        The compiled control manifest owns loop boundaries. Re-entering any
        part restarts both body endpoints and its condition producer; the
        original graph remains responsible for routing and iteration limits.
        """
        causal_edges = list(graph.edges)
        causal_edges.extend((r.producer_step_id, r.consumer_step_id) for r in package.communication_manifest.rules)
        for rule in package.control_manifest.rules:
            if rule.loop is None:
                raise ValueError("node rerun currently supports dependency graphs and bounded loops")
            members = {rule.loop.body_entry_id, rule.loop.body_exit_id, rule.loop.condition.source_step_id}
            causal_edges.extend((member, rule.control_id) for member in members)
            causal_edges.extend((rule.control_id, member) for member in members)
        cut = {step_id}
        while True:
            expanded = cut | {target for origin, target in causal_edges if origin in cut}
            if cut == expanded:
                return cut
            cut = expanded

    def __init__(
        self,
        *,
        collaborators: RuntimeCollaborators,
        state_machine: StateMachine,
        lifecycle_messages: Mapping[WorkflowProgressPhase, str],
        load_workflow: Callable[[RuntimeRunRecord], WorkflowDefinition],
        prepare_successor_run: Callable[..., tuple[RuntimeMissionRecord, RuntimeRunRecord]],
        mark_retrying: Callable[[str], None],
        mark_failed: Callable[[str, str], None],
        set_run_lifecycle: Callable[..., RuntimeRunRecord],
        publish_run_terminal_event: Callable[[RuntimeRunRecord, str, dict], None],
        flush_identity_outbox: Callable[..., None],
    ) -> None:
        self.ports = collaborators
        self.state_machine = state_machine
        self._lifecycle_messages = lifecycle_messages
        self._load_workflow = load_workflow
        self._prepare_successor_run = prepare_successor_run
        self._mark_retrying = mark_retrying
        self._mark_failed = mark_failed
        self._set_run_lifecycle = set_run_lifecycle
        self._publish_run_terminal_event = publish_run_terminal_event
        self._flush_identity_outbox = flush_identity_outbox

    def record_execution_failure(
        self,
        run: RuntimeRunRecord,
        state: ACGExecutionState,
        error: BaseException,
    ) -> None:
        """把执行失败投影为 FailureEvent 并持久化 proposed recoveryOutcome。

        策略决定仍归 domain ``RecoveryService``；这里只做投影与落库，动作本身
        不在本方法内执行（与迁移前的执行异常路径逐行一致）。
        """
        from components.recovery import RecoveryService, failure_event_from_exception

        self._terminalize_active_execution(run, "ACG execution interrupted before commit")

        failure = failure_event_from_exception(
            error,
            subject_ref=(
                f"run:{run.run_id}:step:{state.current_step_id}"
                if state.current_step_id
                else f"run:{run.run_id}"
            ),
        )
        recovery_plan = RecoveryService().propose(failure)
        run.execution_state.setdefault("failureEvents", []).append(
            failure.model_dump(by_alias=True, mode="json")
        )
        run.execution_state["recoveryOutcome"] = {
            "failureId": failure.failure_id,
            "source": failure.source.value,
            "reasonCode": failure.reason_code,
            "action": recovery_plan.strategy.value,
            "status": "proposed",
        }
        self.workflow_store.save_run(run)

    def fail_run_safely(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
        error_metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeRunRecord:
        """Converge one managed Run to FAILED with the existing event order."""

        run = self.workflow_store.get_run(run_id)
        if run.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.SUPERSEDED,
        }:
            return run
        error = {"code": error_code, "message": error_message[:500]}
        safe_metadata = {
            key: value
            for key, value in dict(error_metadata or {}).items()
            if key
            in {
                "provider",
                "model",
                "stage",
                "attemptCount",
                "retryCount",
                "streamUsed",
                "timeoutSeconds",
                "elapsedMs",
                "transportErrorClass",
            }
            and isinstance(value, (str, int, float, bool))
        }
        error.update(safe_metadata)
        self._terminalize_active_execution(run, error["message"])
        run = self._set_run_lifecycle(
            run,
            status=WorkflowStatus.FAILED,
            phase=WorkflowProgressPhase.FAILED,
            message=self._lifecycle_messages[WorkflowProgressPhase.FAILED],
            error=error,
        )
        try:
            self._mark_failed(run.mission_id, run.run_id)
        except Exception:
            logger.exception(
                "Failed to align task status after run failure",
                extra={"missionId": run.mission_id, "runId": run.run_id},
            )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_FAILED,
            observation=error["message"],
            payload={"errorCode": error_code, **error},
        )
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)
        self._publish_run_terminal_event(
            run, "run.failed", {"errorCode": error_code}
        )
        if self.identity_lifecycle is not None and _normalize_runtime_engine(
            run.runtime_engine
        ) == "acg":
            self._flush_identity_outbox()
        return run

    def close_orphaned_runs(self, *, limit: int = 200) -> list[str]:
        """Close nonterminal Runs whose in-process executor disappeared."""

        closed: list[str] = []
        for run in self.workflow_store.list_non_terminal_runs(limit=limit):
            if "graphActivation" in run.execution_state:
                # A durable pause is an intentional handoff boundary, not an
                # orphan executor or a v1 planning round to restart. Validate
                # its evidence even when this Runtime has no activation authority.
                import sqlite3
                from support.stores.graph_activation_store import validate_activation_run
                with self.workflow_store._connect() as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("BEGIN")
                    if validate_activation_run(conn, run) is None:
                        raise ValueError("activation recovery evidence unavailable")
                continue
            if run.status == WorkflowStatus.WAITING_REVIEW:
                if self._normalize_waiting_review_after_restart(run):
                    run.updated_at = utc_now()
                    self.workflow_store.save_run(run)
                continue
            if isinstance(run.execution_state.get("planningLoop"), dict) and isinstance(run.acg_blueprint, dict):
                # The same Runtime resumes via its normal prepared-run entry. No
                # execution occurs during startup scanning; queued work is visible.
                from contracts.runtime_planning import RuntimePlanningState
                loop = RuntimePlanningState.model_validate(run.execution_state["planningLoop"])
                run.execution_state["planningLoop"] = loop.model_copy(update={"restart_pending": True}).model_dump(by_alias=True, mode="json")
                run.status = WorkflowStatus.RETRYING
                run.lifecycle_phase = WorkflowProgressPhase.RECOVERY
                run.lifecycle_message = "从持久化任务状态恢复 Planner 控制环"
                run.updated_at = utc_now()
                self.workflow_store.save_run(run)
                continue
            if run.status not in {
                WorkflowStatus.PENDING,
                WorkflowStatus.PLANNING,
                WorkflowStatus.RUNNING,
                WorkflowStatus.RETRYING,
            }:
                continue
            self._fail_interrupted_run_after_restart(run)
            closed.append(run.run_id)
            logger.warning(
                "interrupted_run_closed_after_restart",
                extra={
                    "missionId": run.mission_id,
                    "runId": run.run_id,
                    "workflowId": run.workflow_id,
                    "phase": (
                        run.lifecycle_phase.value if run.lifecycle_phase else None
                    ),
                },
            )
        return closed

    def _normalize_waiting_review_after_restart(
        self, run: RuntimeRunRecord
    ) -> bool:
        changed = False
        if _normalize_runtime_engine(run.runtime_engine) == "acg":
            subject_type, subject_id = acg_review_subject(
                run.execution_state.get("reviewPayload")
            )
            if run.current_step_id != subject_id:
                run.current_step_id = subject_id
                changed = True
            if subject_type == "step":
                step = run.get_step(subject_id)
                if step.status != StepStatus.WAITING_REVIEW:
                    step.status = StepStatus.WAITING_REVIEW
                    changed = True
        else:
            waiting_ids = {
                step.step_id
                for step in run.steps
                if step.status == StepStatus.WAITING_REVIEW
            }
            if not waiting_ids and run.current_step_id:
                waiting_ids.add(run.current_step_id)
            for step in run.steps:
                if (
                    step.step_id in waiting_ids
                    and step.status != StepStatus.WAITING_REVIEW
                ):
                    step.status = StepStatus.WAITING_REVIEW
                    changed = True
        if run.lifecycle_phase != WorkflowProgressPhase.REVIEW:
            run.lifecycle_phase = WorkflowProgressPhase.REVIEW
            changed = True
        review_message = self._lifecycle_messages[WorkflowProgressPhase.REVIEW]
        if run.lifecycle_message != review_message:
            run.lifecycle_message = review_message
            changed = True
        return changed

    def _fail_interrupted_run_after_restart(self, run: RuntimeRunRecord) -> None:
        interruption_message = "任务因服务重启而中断。"
        self._terminalize_active_execution(
            run,
            interruption_message,
            include_current_pending=True,
        )
        run.status = WorkflowStatus.FAILED
        run.lifecycle_phase = WorkflowProgressPhase.FAILED
        run.lifecycle_message = interruption_message
        run.error = {
            "code": "interrupted_after_restart",
            "message": interruption_message,
        }
        try:
            self._mark_failed(run.mission_id, run.run_id)
        except Exception:
            logger.exception(
                "Failed to align task status after interrupted run",
                extra={"missionId": run.mission_id, "runId": run.run_id},
            )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_FAILED,
            observation=interruption_message,
            payload=dict(run.error),
        )
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)

    @staticmethod
    def _terminalize_active_execution(
        run: RuntimeRunRecord,
        error_message: str,
        *,
        include_current_pending: bool = False,
    ) -> None:
        active_statuses = {StepStatus.RUNNING, StepStatus.RETRYING}
        current_step_id = run.current_step_id if include_current_pending else None
        ended_at = utc_now()
        for step in run.steps:
            if step.status in active_statuses or (
                current_step_id
                and step.step_id == current_step_id
                and step.status == StepStatus.PENDING
            ):
                step.status = StepStatus.FAILED
                step.error = error_message
                step.completed_at = ended_at
        run.active_step_ids = []

    def prepare_single_step_retry(
        self,
        source_run_id: str,
        step_id: str,
        *,
        reason: str = "operator_requested",
        expected_runtime_revision: int | None = None,
        idempotency_key: str | None = None,
        idempotency_fingerprint: str | None = None,
        reuse_source_run: bool = False,
        validate_only: bool = False,
        restart_from_step: bool = False,
    ) -> RuntimeRunRecord:
        """Prepare a successor Run that resumes from a failed ACG step.

        The source Run remains immutable.  The child Run reuses only committed
        upstream output references copied through ``ExecutionValueStore`` and
        seeds the ACG state so the graph scheduler executes the failed step and
        every still-unsettled downstream step without replaying completed work.

        调用方（facade）已持有 source Run 锁；无锁的幂等快路径由锁内的同条件
        复查覆盖，语义不变。
        """
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("single-step retry reason must not be empty")

        source = self.workflow_store.get_run(source_run_id)
        permit_mode = bool(source.execution_state.get("executionPermitId"))
        if permit_mode:
            if not reuse_source_run:
                raise ValueError("Permit retry must retain its formally activated Run")
            from runtime.permit_recovery import assert_settled_operations
            assert_settled_operations(self, source)
        from contracts.task_acceptance import frozen_task_acceptance

        acceptance = frozen_task_acceptance(source)
        in_place_requests = source.execution_state.get("inPlaceRetryRequests")
        if reuse_source_run and idempotency_key and isinstance(in_place_requests, dict):
            previous_fingerprint = in_place_requests.get(idempotency_key)
            if previous_fingerprint is not None:
                if previous_fingerprint != idempotency_fingerprint:
                    raise ValueError("idempotency key conflicts with the in-place retry request")
                return source
        if idempotency_key and not reuse_source_run:
            existing = self.workflow_store.find_run_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.idempotency_fingerprint != idempotency_fingerprint:
                    raise ValueError("idempotency key conflicts with the single-step retry request")
                return existing
        if restart_from_step and reuse_source_run:
            raise ValueError("node rerun requires a successor Run")
        if restart_from_step and source.status not in {
            WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED,
        }:
            raise ValueError("node rerun requires a terminal, nonsuperseded source Run")
        if not restart_from_step and source.status is not WorkflowStatus.FAILED and not (
            validate_only and source.status in {WorkflowStatus.RUNNING, WorkflowStatus.WAITING_REVIEW}
        ):
            raise ValueError("single-step retry requires a failed source Run")
        if expected_runtime_revision is not None and source.runtime_revision != expected_runtime_revision:
            raise ValueError("source Run changed after the retry request was prepared")
        if _normalize_runtime_engine(source.runtime_engine) != "acg":
            raise ValueError("single-step retry is only available for ACG Runs")
        # A partial replay inherits committed results; never rebase its environment.
        self._load_workflow(source)
        blueprint_data = source.acg_blueprint
        if not isinstance(blueprint_data, dict):
            raise ValueError("single-step retry requires a persisted ACG Blueprint")
        blueprint = RuntimeBlueprintSpec.model_validate(blueprint_data)
        raw_package = source.execution_state.get("compiledACGPackage")
        if not isinstance(raw_package, dict):
            raise ValueError("single-step retry requires a persisted compiled ACG package")
        from contracts.compiled_acg import load_compiled_acg_package

        package = load_compiled_acg_package(raw_package)
        graph = ACGGraphCompiler().compile(
            blueprint,
            run_id=source.run_id,
            package=package,
        )
        target_spec = graph.node_specs.get(step_id)
        target_node = next(
            (node for node in blueprint.step_nodes() if node.node_id == step_id),
            None,
        )
        source_step = source.get_step(step_id)
        if target_spec is None or target_spec.kind != "step" or target_node is None:
            raise ValueError("single-step retry target must be an executable ACG step")
        if target_spec.communication_mode != "STRICT_CONTRACT":
            raise ValueError("single-step retry target must use STRICT_CONTRACT communication")
        if not restart_from_step and source_step.status is not StepStatus.FAILED:
            raise ValueError("single-step retry target must be failed")
        source_state = acg_execution_state_from_run(source)
        if (permit_mode and source.status == WorkflowStatus.FAILED
                and (source_state.review_payload or {}).get("subjectType") == "planner"
                and any(event.event_type == TraceEventType.REVIEW_DECIDED
                        and event.step_id == source.current_step_id
                        and event.payload.get("subjectType") == "planner"
                        and event.payload.get("decision") == "rejected" for event in source.trace)):
            # The operator has resolved this strategic barrier by rejection.
            # A separate explicit retry may clear its marker, never node audit.
            source_state.review_payload = None
        if validate_only and (source_state.review_payload or {}).get("subjectType") == "planner":
            source_state.review_payload = None
        if not restart_from_step and source_state.output_refs.get(step_id):
            raise ValueError("single-step retry target already has a committed output")

        stale_active_step_ids = set(source_state.active_step_ids)
        if stale_active_step_ids and (
            stale_active_step_ids != {step_id}
            or source_step.status is not StepStatus.FAILED
            or source_state.output_refs.get(step_id)
        ):
            raise ValueError("single-step retry requires no active source steps")
        # A restart can persist the failed target in the ACG state while
        # the authoritative Run projection has already cleared its active
        # steps.  Only that exact failed, output-less target is safe to
        # reconcile here; any other active marker remains a hard reject.
        if (
            source_state.control_frames
            or source_state.loop_iterations
            or source_state.loop_paths
            or source_state.blackboard_snapshots
            or source_state.debate_sessions
            or source_state.review_payload
            or source_state.control_review_decisions
        ):
            raise ValueError("single-step retry does not support control or review state")
        invalidated = set()
        if restart_from_step:
            # Only strict communication and settled bounded loops are safe for
            # this cut. Other control semantics retain their own authority.
            if (any(spec.communication_mode != "STRICT_CONTRACT"
                    or (spec.kind == "control" and spec.control_type != "loop")
                    for spec in graph.node_specs.values()) or source_state.consensus_results
                    or any(r.mode.value != "STRICT_CONTRACT" for r in package.communication_manifest.rules)):
                raise ValueError("node rerun requires strict dependencies and settled bounded loops")
            invalidated = self.node_rerun_cut(graph, package, step_id)
            checkpoint = self.checkpoint_store.load(run_id=source.run_id, checkpoint_id=source_state.checkpoint_id) if source_state.checkpoint_id else None
            if checkpoint is None:
                raise ValueError("node rerun requires a persisted checkpoint")
            persisted = ACGExecutionState.model_validate(checkpoint)
            if (persisted.run_id != source.run_id or persisted.graph_id != source_state.graph_id
                    or persisted.graph_version != source_state.graph_version
                    or persisted.output_refs != source_state.output_refs
                    or persisted.completed_step_ids != source_state.completed_step_ids
                    or persisted.skipped_step_ids != source_state.skipped_step_ids):
                raise ValueError("node rerun checkpoint does not match committed state")
            from runtime.planning_observation import RuntimePlanningObservationBuilder
            inspector = RuntimePlanningObservationBuilder(collaborators=self.ports,
                load_goal=lambda _: "", validate_references=lambda **_: None)
            for reusable_id in set(source_state.completed_step_ids) - invalidated:
                if graph.node_specs[reusable_id].kind != "step":
                    continue
                _, audit, owner_id = inspector._committed(source.run_id, reusable_id, source_state.output_refs[reusable_id])
                if audit.outcome == "review" or source.get_step(reusable_id).requires_review:
                    owner = self.workflow_store.get_run(owner_id)
                    if not any(e.event_type == TraceEventType.REVIEW_DECIDED and e.step_id == reusable_id
                               and e.payload.get("decision") == "approved" for e in owner.trace):
                        raise ValueError("node rerun cannot reuse unresolved human review")
            source_state = source_state.model_copy(deep=True)
            source_state.completed_step_ids = [s for s in source_state.completed_step_ids if s not in invalidated]
            source_state.skipped_step_ids = [s for s in source_state.skipped_step_ids if s not in invalidated]
        settled = set(source_state.completed_step_ids) | set(source_state.skipped_step_ids)
        resumable_step_ids = {
            node_id
            for node_id in graph.nodes
            if node_id not in settled
            and (unsettled_spec := graph.node_specs.get(node_id)) is not None
            and unsettled_spec.kind == "step"
        }
        if step_id in settled or step_id not in resumable_step_ids:
            raise ValueError("single-step retry target is not resumable from persisted state")

        reusable_outputs: list[tuple[str, str, dict[str, Any], str]] = []
        for reusable_step_id in source_state.completed_step_ids:
            reusable_spec = graph.node_specs.get(reusable_step_id)
            if reusable_spec is None:
                raise ValueError(
                    f"single-step retry found an unknown completed graph node: {reusable_step_id}"
                )
            if reusable_spec.kind != "step":
                continue
            source_ref = source_state.output_refs.get(reusable_step_id)
            if not source_ref:
                raise ValueError(
                    f"single-step retry requires a committed upstream output: {reusable_step_id}"
                )
            payload = self.execution_value_store.get_output(
                run_id=source.run_id,
                output_ref=source_ref,
            )
            reusable_outputs.append((
                reusable_step_id,
                source_ref,
                payload,
                source_state.output_summaries.get(reusable_step_id, ""),
            ))

        if validate_only:
            return source

        copied_refs: dict[str, str] = {}
        copied_summaries: dict[str, str] = {}
        if reuse_source_run:
            retry = source
            copied_refs = {
                reusable_step_id: source_ref
                for reusable_step_id, source_ref, _payload, _summary in reusable_outputs
            }
            copied_summaries = {
                reusable_step_id: summary
                for reusable_step_id, _source_ref, _payload, summary in reusable_outputs
            }
        else:
            task_plan = source.execution_state.get("taskPlan")
            task_bindings = source.execution_state.get("taskBindings")
            if not isinstance(task_plan, dict) or not isinstance(task_bindings, list):
                raise ValueError("single-step retry requires persisted TaskPlan and bindings")
            _, retry = self._prepare_successor_run(
                source.mission_id,
                workflow_id=source.workflow_id,
                review_mode=source.review_mode,
                idempotency_key=idempotency_key,
                idempotency_fingerprint=idempotency_fingerprint,
                enabled_plugin_ids=list(source.enabled_plugin_ids),
                defer_acg_planning=False,
                input_override={
                    **deepcopy(source.input),
                    "taskAcceptance": acceptance.model_dump(by_alias=True, mode="json") if acceptance else None,
                    "acgBlueprint": deepcopy(source.acg_blueprint),
                    "taskPlan": deepcopy(task_plan),
                    "taskBindings": deepcopy(task_bindings),
                },
                parent_run_id=source.run_id,
                inherit_parent_basis=True,
                rerun_reason="node_rerun" if restart_from_step else "resume_failed",
                **({"persist_run": False, "execution_scope_override": source.execution_scope} if restart_from_step else {}),
            )
            if retry.run_id == source.run_id:
                raise ValueError("single-step retry cannot reuse the source Run")
            for reusable_step_id, source_ref, payload, summary in reusable_outputs:
                commit_id = f"single-step-retry:{retry.run_id}:{reusable_step_id}"
                self.execution_value_store.prepare_node_commit(run_id=retry.run_id, commit_id=commit_id)
                child_ref = self.execution_value_store.put_output(
                    run_id=retry.run_id,
                    step_id=reusable_step_id,
                    payload=payload,
                    operation_id=commit_id,
                )
                self.execution_value_store.complete_node_commit(
                    run_id=retry.run_id,
                    commit_id=commit_id,
                    payload={
                        "outputRef": child_ref,
                        "outputSummary": summary,
                        "reusedFromRunId": source.run_id,
                        "reusedFromOutputRef": source_ref,
                    },
                )
                copied_refs[reusable_step_id] = child_ref
                copied_summaries[reusable_step_id] = summary

        state = acg_execution_state_from_run(retry)
        state.completed_step_ids = list(source_state.completed_step_ids)
        state.skipped_step_ids = list(source_state.skipped_step_ids)
        state.active_step_ids = []
        state.current_step_id = step_id
        state.output_refs = copied_refs
        state.output_summaries = copied_summaries
        if not permit_mode:
            state.context_refs = {}
            state.memory_refs = {}
            state.trace_refs = {}
            state.provenance_refs = {}
        if not permit_mode:
            state.graph_patch_refs = []
            state.communication_usage = {}
        state.checkpoint_id = None
        state.review_payload = None
        state.control_review_decisions = {}
        retry.execution_state.update(state.model_dump(by_alias=True, mode="json"))
        retry.execution_state.update({
            "singleStepRetry": {
                "sourceRunId": source.run_id,
                "targetStepId": step_id,
                "reason": normalized_reason[:500],
                "reusedStepIds": sorted(copied_refs),
            },
            "checkpointResume": {
                "sourceRunId": source.run_id,
                "failedStepId": step_id,
                "reason": normalized_reason[:500],
                "reusedStepIds": sorted(copied_refs),
                "resumeStepIds": sorted(resumable_step_ids),
                "mode": "current_run" if reuse_source_run else "successor_run",
            },
            "retryTargetStepId": step_id,
            "reusedStepIds": sorted(copied_refs),
        })
        if restart_from_step:
            retry.execution_state["nodeRerun"] = {
                "sourceRunId": source.run_id, "targetStepId": step_id,
                "invalidatedStepIds": sorted(invalidated),
                "reusedStepIds": sorted(copied_refs),
            }
        # A resumed node is a new Attempt even when the operator chooses
        # to keep the same Run identity.  Retaining the failed attempt's
        # generated IDs would replay its projection keys with different
        # scheduling content.
        for identity_key in ("attemptIds", "stepExecutionIds"):
            persisted_ids = retry.execution_state.get(identity_key)
            if isinstance(persisted_ids, dict):
                retry.execution_state[identity_key] = {
                    key: value
                    for key, value in persisted_ids.items()
                    if str(key).split(":", 1)[0] not in resumable_step_ids
                }
        reused_projection_events: list[dict] = []
        if not reuse_source_run and self.identity_lifecycle is not None:
            # 惰性导入与 flush_identity_outbox 同理由：不把 runtime 的
            # 重组件图拖进本模块的包初始化。
            from runtime.resume_projection import (
                build_reused_step_projection_events,
            )

            source_step_counters = {}
            for reused_step_id in copied_refs:
                source_step = source.get_step(reused_step_id)
                source_step_counters[reused_step_id] = (
                    int(source_step.attempt or 0),
                    int(source_step.retry_count or 0),
                )
            reused_projection_events, reused_state_updates = (
                build_reused_step_projection_events(
                    run_id=retry.run_id,
                    mission_id=retry.mission_id,
                    reused_step_ids=sorted(copied_refs),
                    copied_refs=copied_refs,
                    copied_summaries=copied_summaries,
                    source_run_id=source.run_id,
                    source_execution_state=source.execution_state or {},
                    source_step_counters=source_step_counters,
                    attempt_id_for=lambda _step_id: new_attempt_id(),
                    step_execution_id_for=lambda _step_id: new_step_execution_id(),
                )
            )
            # attemptIds/stepExecutionIds/executionBindings 写回继任 Run，
            # 后续若再从本 Run 发起链式恢复，复用账目可被继续追溯。
            for state_key, entries in reused_state_updates.items():
                retry.execution_state.setdefault(state_key, {}).update(entries)
        retry.completed_step_ids = list(source_state.completed_step_ids)
        retry.active_step_ids = []
        retry.current_step_id = step_id
        retry.output = {}
        retry.error = None
        retry.recovery_count = source.recovery_count + 1
        if reuse_source_run:
            retry.status = self.state_machine.transition(retry.status, WorkflowStatus.RETRYING)
            retry.lifecycle_phase = WorkflowProgressPhase.RECOVERY
            retry.lifecycle_message = self._lifecycle_messages[WorkflowProgressPhase.RECOVERY]
            requests = retry.execution_state.setdefault("inPlaceRetryRequests", {})
            if idempotency_key and isinstance(requests, dict):
                requests[idempotency_key] = idempotency_fingerprint
            retry.execution_state["inPlaceRetry"] = {
                "failedStepId": step_id,
                "reason": normalized_reason[:500],
            }
        persisted_attempt_counts: dict[str, int] = {}
        if reuse_source_run and self.identity_lifecycle is not None:
            next_attempt_number = getattr(
                self.identity_lifecycle,
                "next_attempt_number",
                None,
            )
            if callable(next_attempt_number):
                persisted_attempt_counts = {
                    resumable_step_id: max(
                        0,
                        int(next_attempt_number(retry.run_id, resumable_step_id)) - 1,
                    )
                    for resumable_step_id in resumable_step_ids
                }
        for child_step in retry.steps:
            if child_step.step_id in source_state.completed_step_ids:
                source_completed = source.get_step(child_step.step_id)
                child_step.status = StepStatus.COMPLETED
                child_step.started_at = source_completed.started_at
                child_step.completed_at = source_completed.completed_at
                child_step.attempt = source_completed.attempt
                child_step.retry_count = source_completed.retry_count
            elif child_step.step_id in source_state.skipped_step_ids:
                child_step.status = StepStatus.SKIPPED_BY_CONDITION
                child_step.completed_at = source.get_step(child_step.step_id).completed_at
            else:
                source_unsettled = source.get_step(child_step.step_id)
                child_step.status = StepStatus.PENDING
                child_step.error = None
                child_step.started_at = None
                child_step.completed_at = None
                if child_step.step_id in persisted_attempt_counts:
                    child_step.attempt = persisted_attempt_counts[child_step.step_id]
                    child_step.retry_count = persisted_attempt_counts[child_step.step_id]
                else:
                    child_step.attempt = max(
                        source_unsettled.attempt,
                        source_unsettled.retry_count,
                    ) + (1 if reuse_source_run and child_step.step_id == step_id else 0)
                    child_step.retry_count = (
                        source_unsettled.retry_count + 1
                        if reuse_source_run and child_step.step_id == step_id
                        else source_unsettled.retry_count
                    )
        self.trace_store.append(
            retry,
            TraceEventType.RUN_RECOVERED,
            step_id=step_id,
            observation="Failed Run checkpoint resume prepared",
            payload={
                "sourceRunId": source.run_id,
                "failedStepId": step_id,
                "reusedStepIds": sorted(copied_refs),
                "resumeStepIds": sorted(resumable_step_ids),
                "reason": normalized_reason[:500],
                "mode": "current_run" if reuse_source_run else "successor_run",
            },
        )
        retry.updated_at = utc_now()
        if permit_mode:
            # Same graph/Permit/generation; retry has a fresh Attempt and a
            # normal native checkpoint, never the old failed recovery state.
            from runtime.state_persistence import ACGStatePersistenceService
            ACGStatePersistenceService(collaborators=self.ports).save_checkpoint(retry, state)
            retry.execution_state.update(state.model_dump(by_alias=True, mode="json"))
        if reuse_source_run and self.identity_lifecycle is not None:
            # Persist the retry lifecycle transition itself. Snapshots are read
            # against current runtime truth during reconciliation, so snapshots
            # alone can lose FAILED -> RETRYING once execution has advanced.
            reused_projection_events.append({
                "eventId": f"run.retry_prepared:{retry.run_id}:{retry.recovery_count}",
                "eventType": "run.retry_prepared", "aggregateId": retry.run_id,
                "payload": {"runId": retry.run_id, "recoveryCount": retry.recovery_count},
            })
        if not reuse_source_run and isinstance(source.execution_state.get("planningLoop"), dict):
            from contracts.runtime_planning import successor_planning_state
            retry.execution_state["planningLoop"] = successor_planning_state(source.execution_state["planningLoop"],
                self.workflow_store.list_planning_inputs(source.run_id))
        if reused_projection_events:
            if restart_from_step:
                from support.stores.workflow_store import lifecycle_run_payload
                reused_projection_events.insert(0, {"eventId": f"node-rerun-prepared:{retry.run_id}",
                    "eventType": "run.prepared", "aggregateId": retry.run_id, "payload": lifecycle_run_payload(retry)})
            self.workflow_store.save_run_with_events(retry, reused_projection_events)
        else:
            self.workflow_store.save_run(retry)
        if reuse_source_run:
            self._mark_retrying(source.mission_id)
        if self.identity_lifecycle is not None:
            self._flush_identity_outbox()
        return retry

    def rebind_step(self, *, run: RuntimeRunRecord, step_id: str, reason: str) -> str:
        """Select a healthy alternate Agent inside the run's frozen scope.

        Rebinding is intentionally limited to a persisted review barrier and a
        not-yet-executed step. It changes only the frozen resource projection;
        no executor, workflow state machine, or graph is duplicated.

        调用方（facade）已持有 Run 锁。角色候选按冻结 scope 内的逻辑 Agent
        注册表排序；执行后端与资源选择权威仍在 ResourceBinder。
        """
        if _normalize_runtime_engine(run.runtime_engine) != "acg":
            raise ValueError("resource rebinding is only available for ACG runs")
        if run.status is not WorkflowStatus.WAITING_REVIEW:
            raise ValueError("resource rebinding requires a persisted WAITING_REVIEW barrier")
        step = run.get_step(step_id)
        if step.status not in {StepStatus.PENDING, StepStatus.RETRYING}:
            raise ValueError("only a pending or retrying step can be rebound")
        scope = run.execution_scope
        if scope is None:
            raise ValueError("resource rebinding requires a frozen execution scope")
        bindings = dict(run.execution_state.get("resourceBindings") or {})
        current_agent_id = str(bindings.get(step_id) or "")
        if not current_agent_id:
            raise ValueError(f"ACG step has no frozen resource binding: {step_id}")
        history = list(run.execution_state.get("bindingHistory") or [])
        if any(item.get("stepId") == step_id for item in history if isinstance(item, dict)):
            raise ValueError(f"alternate binding budget exhausted for step: {step_id}")
        # 角色重绑定在嵌入式后端内完成：候选来自冻结 scope 内的逻辑 Agent
        # 注册表，选择权威是角色解析顺序（能力优先级），不是资源调度。
        candidates = self._alternate_logical_agents(
            run=run, step=step, scope=scope, excluded_agent_id=current_agent_id,
        )
        if not candidates:
            raise ResourceNotFoundError(f"no healthy alternate resource for step: {step_id}")
        selected_agent_id = candidates[0]
        # Resolve the instance now so a stale registry entry cannot enter
        # persisted state.
        self.agent_registry.resolve_by_id(selected_agent_id, allowed_agent_ids=scope.agent_ids)
        bindings[step_id] = selected_agent_id
        run.execution_state["resourceBindings"] = bindings
        requirements = dict(run.execution_state.get("bindingRequirements") or {})
        requirement_payload = requirements.get(step_id)
        if isinstance(requirement_payload, dict):
            requirement = ExecutionRequirement.model_validate(requirement_payload)
            requirements[step_id] = requirement.model_copy(
                update={
                    "preferences": {
                        **requirement.preferences,
                        "agentRole": selected_agent_id,
                    }
                }
            ).model_dump(by_alias=True, mode="json")
            run.execution_state["bindingRequirements"] = requirements
        history.append(
            {
                "stepId": step_id,
                "previousAgentId": current_agent_id,
                "agentId": selected_agent_id,
                "reason": reason,
            }
        )
        run.execution_state["bindingHistory"] = history
        self.trace_store.append(
            run,
            TraceEventType.RUNTIME_PATCH_APPLIED,
            observation="ACG resource binding changed at review barrier",
            step_id=step_id,
            agent_name=selected_agent_id,
            payload={
                "patchType": "alternate_binding",
                "previousAgentId": current_agent_id,
                "agentId": selected_agent_id,
                "reason": reason,
            },
        )
        self.workflow_store.save_run(run)
        return selected_agent_id

    def _alternate_logical_agents(
        self, *, run, step, scope, excluded_agent_id: str
    ) -> list[str]:
        """列出冻结 scope 内具备步骤能力的候选逻辑 Agent 标识。

        排序与 AgentRegistry.resolve 一致：领域精确匹配优先，其余按稳定
        标识序；排除当前绑定与冻结范围之外的候选。
        """
        domain = (self._load_workflow(run).domain or "").strip().lower()
        required = (step.capability or "").strip().lower()
        allowed = set(scope.agent_ids) if scope.agent_ids else None
        candidates: list[tuple[int, str]] = []
        for agent in self.agent_registry.all():
            agent_id = str(self.agent_registry.agent_id(agent))
            if agent_id == excluded_agent_id:
                continue
            if allowed is not None and agent_id not in allowed:
                continue
            profile = agent.profile
            if not profile.enabled:
                continue
            agent_domain = (profile.domain or "").strip().lower()
            if agent_domain not in {domain, "general"}:
                continue
            if required and required not in {
                str(item).strip().lower() for item in profile.capabilities
            }:
                continue
            candidates.append((0 if agent_domain == domain else 1, agent_id))
        candidates.sort()
        return [agent_id for _, agent_id in candidates]

    def load_resume_input(
        self,
        *,
        run_id: str,
        checkpoint_id: str,
    ) -> tuple[RuntimeRunRecord, ACGExecutionState]:
        """加载并校验同版本检查点，产出 resume 输入；执行仍走 ACGExecutionService。"""
        initial_run = self.workflow_store.get_run(run_id)
        if _normalize_runtime_engine(initial_run.runtime_engine) != "acg":
            raise ValueError("Checkpoint resume is only available for the ACG execution engine")
        checkpoint_data = self.checkpoint_store.load(run_id=run_id, checkpoint_id=checkpoint_id)
        if checkpoint_data is None:
            raise ValueError("checkpoint does not exist for this run")
        state = ACGExecutionState.model_validate(checkpoint_data)
        return initial_run, state


__all__ = ["RuntimeRecoveryCoordinator"]

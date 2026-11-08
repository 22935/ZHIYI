"""Execution Runtime 快照与 AgentOS 身份投影的启动对账。"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any

from contracts.planning import TaskImplementationBinding, TaskPlan
from contracts.workflow import RuntimeMissionRecord
from domain.lifecycle_projection import LifecycleProjectionEvent, ProjectionEventStatus
from domain.models import AttemptStatus, RunStatus, StepExecutionStatus
from support.acg.schema import RuntimeBlueprintSpec
from types import SimpleNamespace

from .identity_projection import DEAD_LETTER_MAX_ATTEMPTS, IdentityProjectionBridge

logger = logging.getLogger(__name__)


@dataclass
class IdentityReconciliationReport:
    examined_tasks: int = 0
    examined_runs: int = 0
    repaired_tasks: int = 0
    repaired_runs: int = 0
    replayed_events: int = 0
    inbox_backlog: int = 0
    outbox_backlog: int = 0
    outbox_failed_count: int = 0
    failed_event_count: int = 0
    dead_letter_count: int = 0
    oldest_event_at: str | None = None
    failures: list[str] = field(default_factory=list)
    failed_aggregate_ids: set[str] = field(default_factory=set, repr=False)


class IdentityProjectionReconciler:
    """只恢复身份投影，不改变 Execution Runtime WorkflowRun 的执行状态。"""

    def __init__(self, adapter: IdentityProjectionBridge) -> None:
        self.adapter = adapter

    def project_pending_events(
        self,
        workflow_store: Any,
        *,
        limit: int = 200,
    ) -> IdentityReconciliationReport:
        """Deliver pending lifecycle facts without scanning historical Missions or Runs."""
        report = IdentityReconciliationReport()
        projection_stats = self.adapter.repositories.projection_events.stats()
        replay = self.adapter.replay_unapplied(
            limit=max(limit, projection_stats["backlog"])
        )
        report.replayed_events = replay["applied"]
        if replay["failed"]:
            report.failures.append(
                f"{replay['failed']} lifecycle projection events could not be replayed"
            )
        self._consume_execution_outbox(workflow_store, report, limit=limit)
        self._update_backlog_report(workflow_store, report)
        return report

    def reconcile_workflow_store(
        self,
        workflow_store: Any,
        *,
        limit: int = 200,
        audit_existing: bool = True,
    ) -> IdentityReconciliationReport:
        """Repair historical projections at startup or during explicit recovery."""
        report = self.project_pending_events(workflow_store, limit=limit)
        page = 1
        while True:
            task_page = workflow_store.list_missions(page=page, page_size=max(1, limit))
            for task in task_page.items:
                if task.mission_id in report.failed_aggregate_ids:
                    continue
                report.examined_tasks += 1
                try:
                    if self.adapter.repositories.missions.get(task.mission_id) is None:
                        self.adapter.on_mission_created(task)
                        report.repaired_tasks += 1
                except Exception as exc:
                    report.failures.append(f"{task.mission_id}: {exc}")
            if page * task_page.page_size >= task_page.total:
                break
            page += 1
        for run in self._reconciliation_runs(workflow_store, limit, audit_existing):
            if run.run_id in report.failed_aggregate_ids:
                continue
            # Deferred planning is an accepted Execution Runtime placeholder,
            # not yet a V2 Run identity.  Until L1 produces TaskPlan, Blueprint
            # and bindings there is nothing valid to repair or audit.  This also
            # covers terminal planning failures, which deliberately retain the
            # marker so reconciliation never fabricates an empty graph identity.
            if (run.execution_state or {}).get("planningDeferred"):
                continue
            report.examined_runs += 1
            try:
                task = workflow_store.get_mission(run.mission_id)
                if self.adapter.repositories.runs.get(run.run_id) is None:
                    if "graphActivation" in run.execution_state:
                        raise ValueError("activation requires its existing source Identity Run")
                    raw_plan = run.execution_state.get("taskPlan")
                    raw_bindings = run.execution_state.get("taskBindings")
                    if (
                        not isinstance(run.acg_blueprint, dict)
                        or not isinstance(raw_plan, dict)
                        or not isinstance(raw_bindings, list)
                    ):
                        raise ValueError(
                            "execution run lacks persisted TaskPlan identity projection data"
                        )
                    self.adapter.on_run_prepared(
                        task,
                        run,
                        RuntimeBlueprintSpec.model_validate(run.acg_blueprint),
                        TaskPlan.model_validate(raw_plan),
                        tuple(
                            TaskImplementationBinding.model_validate(item)
                            for item in raw_bindings
                        ),
                    )
                    status = str(getattr(run.status, "value", run.status))
                    if status in {"completed", "failed", "cancelled"}:
                        self.adapter.on_run_finished(run.run_id, {
                            "completed": "succeeded",
                            "failed": "failed",
                            "cancelled": "cancelled",
                        }[status])
                    elif status == "superseded":
                        replacement = str(run.execution_state.get("supersededByRunId") or "")
                        if replacement:
                            self.adapter.on_run_superseded(run.run_id, replacement, str(run.execution_state.get("sourcePatchId") or "reconciliation"))
                    report.repaired_runs += 1
                self._audit_run(run)
            except Exception as exc:
                report.failures.append(f"{run.run_id}: {exc}")
        self._update_backlog_report(workflow_store, report)
        return report

    def _reconciliation_runs(self, workflow_store: Any, limit: int, audit_existing: bool):
        if audit_existing:
            offset = 0
            while True:
                runs = workflow_store.list_all_runs(offset=offset, limit=max(1, limit))
                yield from runs
                if len(runs) < max(1, limit):
                    return
                offset += len(runs)
        offset = 0
        terminal_statuses = {"completed": "succeeded", "failed": "failed", "cancelled": "cancelled", "superseded": "superseded"}
        while True:
            summaries = workflow_store.list_all_run_summaries(offset=offset, limit=max(1, limit))
            for summary in summaries:
                identity = self.adapter.repositories.runs.get(summary.run_id)
                expected = terminal_statuses.get(summary.status.value)
                if identity is None or expected is None or identity.status.value != expected:
                    yield workflow_store.get_run(summary.run_id)
            if len(summaries) < max(1, limit):
                return
            offset += len(summaries)

    def _update_backlog_report(
        self, workflow_store: Any, report: IdentityReconciliationReport,
    ) -> None:
        inbox_stats = self.adapter.repositories.inbox_events.stats()
        projection_stats = self.adapter.repositories.projection_events.stats()
        outbox_stats = (
            workflow_store.outbox_stats()
            if hasattr(workflow_store, "outbox_stats")
            else {"backlog": 0, "failed": 0, "oldestEventAt": None}
        )
        report.inbox_backlog = inbox_stats["backlog"]
        report.outbox_backlog = outbox_stats["backlog"]
        report.outbox_failed_count = outbox_stats["failed"]
        report.failed_event_count = (
            inbox_stats["failed"]
            + projection_stats["failed"]
            + outbox_stats["failed"]
        )
        timestamps = [
            value for value in (
                inbox_stats["oldestEventAt"],
                projection_stats["oldestEventAt"],
                outbox_stats["oldestEventAt"],
            )
            if value is not None
        ]
        report.oldest_event_at = min(timestamps) if timestamps else None

    def _consume_execution_outbox(
        self,
        workflow_store: Any,
        report: IdentityReconciliationReport,
        *,
        limit: int,
    ) -> None:
        if not hasattr(workflow_store, "list_outbox"):
            return
        requested = limit
        if hasattr(workflow_store, "outbox_stats"):
            requested = max(limit, workflow_store.outbox_stats()["backlog"])
        events = workflow_store.list_outbox(limit=requested)
        for event in events:
            delivery_attempts = int(event.get("attempts") or 0)
            if delivery_attempts >= DEAD_LETTER_MAX_ATTEMPTS:
                report.dead_letter_count += 1
                logger.warning(
                    "identity_outbox_dead_letter_bypassed",
                    extra={
                        "eventId": event["event_id"],
                        "eventType": event["event_type"],
                        "aggregateId": event["aggregate_id"],
                        "attempts": delivery_attempts,
                    },
                )
                continue
            inbox_event: LifecycleProjectionEvent | None = None
            try:
                payload = json.loads(event["payload"])
                encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                payload_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                inbox_event = self.adapter.repositories.inbox_events.begin(
                    LifecycleProjectionEvent(
                        eventId=event["event_id"],
                        eventType=event["event_type"],
                        aggregateId=event["aggregate_id"],
                        payload=payload,
                        payloadHash=payload_hash,
                    )
                )
                if inbox_event.status is ProjectionEventStatus.APPLIED:
                    workflow_store.mark_outbox(event["event_id"], applied=True)
                    continue
                if event["event_type"] in {"mission.snapshot", "mission.created"}:
                    missing_before = self.adapter.repositories.missions.get(
                        event["aggregate_id"]
                    ) is None
                    self.adapter.on_mission_created(RuntimeMissionRecord.model_validate(payload))
                    if missing_before:
                        report.repaired_tasks += 1
                elif event["event_type"] == "graph.patch.prepared":
                    payload = dict(payload)
                    task = SimpleNamespace(mission_id=payload["missionId"])
                    old_run = SimpleNamespace(run_id=payload["oldRunId"])
                    new_run = SimpleNamespace(
                        run_id=payload["newRunId"],
                        workflow_id=payload["workflowId"],
                        execution_state=payload.get("executionState") or {},
                    )
                    self.adapter.on_graph_patch_prepared(
                        task,
                        old_run,
                        new_run,
                        RuntimeBlueprintSpec.model_validate(payload["blueprint"]),
                        TaskPlan.model_validate(payload["taskPlan"]),
                        tuple(
                            TaskImplementationBinding.model_validate(item)
                            for item in payload["taskBindings"]
                        ),
                        payload["patchId"],
                    )
                elif event["event_type"] in {"run.snapshot", "run.prepared", "run.finished", "run.superseded"}:
                    runtime_run = workflow_store.get_run(event["aggregate_id"])
                    missing_before = self.adapter.repositories.runs.get(
                        runtime_run.run_id
                    ) is None
                    task = workflow_store.get_mission(runtime_run.mission_id)
                    raw_plan = runtime_run.execution_state.get("taskPlan")
                    raw_bindings = runtime_run.execution_state.get("taskBindings")
                    if not isinstance(runtime_run.acg_blueprint, dict) or not isinstance(raw_plan, dict) or not isinstance(raw_bindings, list):
                        raise ValueError("execution run snapshot lacks Planner identity data")
                    projection = dict(payload.get("executionState") or {})
                    if "graphActivation" in runtime_run.execution_state:
                        # A paused formal graph has not performed the Identity
                        # execution handoff. Reconcile lifecycle only; never
                        # replace the immutable v1 package identity implicitly.
                        from support.stores.graph_activation_store import validate_activation_run
                        with workflow_store._connect() as conn:
                            import sqlite3
                            conn.row_factory = sqlite3.Row
                            conn.execute("BEGIN")
                            if validate_activation_run(conn, runtime_run) is None:
                                raise ValueError("activation lifecycle evidence unavailable")
                        if missing_before:
                            raise ValueError("activation requires its existing source Identity Run")
                        for key in ("compiledPackageId", "compiledPackageChecksum",
                                    "compiledPackageVersion", "compiledPackageBlueprintHash"):
                            projection.pop(key, None)
                    if missing_before:
                        self.adapter.on_run_prepared(
                            task,
                            runtime_run,
                            RuntimeBlueprintSpec.model_validate(runtime_run.acg_blueprint),
                            TaskPlan.model_validate(raw_plan),
                            tuple(TaskImplementationBinding.model_validate(item) for item in raw_bindings),
                        )
                    self.adapter.on_run_snapshot(
                        runtime_run.run_id,
                        projection,
                    )
                    status = str(getattr(runtime_run.status, "value", runtime_run.status))
                    if event["event_type"] == "run.superseded":
                        replacement = str(runtime_run.execution_state.get("supersededByRunId") or "")
                        if replacement:
                            self.adapter.on_run_superseded(runtime_run.run_id, replacement, str(runtime_run.execution_state.get("sourcePatchId") or "outbox"))
                    elif status in {"completed", "failed", "cancelled"}:
                        self.adapter.on_run_finished(runtime_run.run_id, {
                            "completed": "succeeded",
                            "failed": "failed",
                            "cancelled": "cancelled",
                        }[status])
                    if missing_before:
                        report.repaired_runs += 1
                else:
                    self.adapter.apply_lifecycle_event(event["event_type"], payload)
                self.adapter.repositories.inbox_events.mark_applied(event["event_id"])
                workflow_store.mark_outbox(event["event_id"], applied=True)
            except Exception as exc:
                report.failed_aggregate_ids.add(str(event["aggregate_id"]))
                if event.get("event_type") == "graph.patch.prepared":
                    try:
                        failed_payload = json.loads(event["payload"])
                    except (TypeError, json.JSONDecodeError):
                        failed_payload = {}
                    for key in ("oldRunId", "newRunId"):
                        if failed_payload.get(key):
                            report.failed_aggregate_ids.add(str(failed_payload[key]))
                if inbox_event is not None:
                    self.adapter.repositories.inbox_events.mark_failed(
                        event["event_id"], str(exc)
                    )
                workflow_store.mark_outbox(event["event_id"], applied=False, error=str(exc))
                report.failures.append(f"outbox {event['event_id']}: {exc}")

    def _audit_run(self, runtime_run: Any) -> None:
        run = self.adapter.repositories.runs.get(runtime_run.run_id)
        if run is None:
            raise ValueError("identity WorkflowRun is missing after reconciliation")
        if run.mission_id != runtime_run.mission_id:
            raise ValueError("execution and identity Run belong to different Missions")
        blueprint = self.adapter.repositories.blueprints.get(run.blueprint_id)
        if blueprint is None:
            raise ValueError("identity Run Blueprint is missing")
        if int(blueprint.version) != int(run.graph_version):
            raise ValueError("identity Run graphVersion is inconsistent")
        runtime_status = str(getattr(runtime_run.status, "value", runtime_run.status))
        runtime_terminal = runtime_status in {
            "completed", "failed", "cancelled", "superseded"
        }
        if runtime_status in {"failed", "cancelled", "superseded"}:
            self._finish_open_nodes(
                runtime_run,
                cancelled=runtime_status in {"cancelled", "superseded"},
            )
        identity_terminal = run.status in {
            RunStatus.FAILED,
            RunStatus.SUCCEEDED,
            RunStatus.CANCELLED,
            RunStatus.SUPERSEDED,
        }
        if runtime_terminal and run.status in {RunStatus.PENDING, RunStatus.RUNNING}:
            if runtime_status == "superseded":
                replacement = str(
                    (getattr(runtime_run, "execution_state", None) or {}).get(
                        "supersededByRunId"
                    )
                    or ""
                )
                if not replacement:
                    raise ValueError("superseded execution Run has no replacement Run")
                self._finish_open_nodes(runtime_run, cancelled=True)
                self.adapter.on_run_superseded(
                    runtime_run.run_id,
                    replacement,
                    str(
                        (getattr(runtime_run, "execution_state", None) or {}).get(
                            "sourcePatchId"
                        )
                        or "reconciliation"
                    ),
                )
            else:
                self._finish_open_nodes(
                    runtime_run,
                    cancelled=runtime_status == "cancelled",
                )
                self.adapter.on_run_finished(
                    runtime_run.run_id,
                    {
                        "completed": "succeeded",
                        "failed": "failed",
                        "cancelled": "cancelled",
                    }[runtime_status],
                )
            return
        if (
            runtime_status == "retrying"
            and run.status is RunStatus.FAILED
        ):
            recovery_count = int(
                getattr(runtime_run, "recovery_count", 0)
                or (getattr(runtime_run, "execution_state", None) or {}).get("recoveryCount")
                or 0
            )
            self.adapter.on_run_retry_prepared(runtime_run.run_id, recovery_count)
            return
        if not runtime_terminal and identity_terminal:
            raise ValueError("non-terminal execution Run points to terminal identity Run")

    def _finish_open_nodes(self, runtime_run: Any, *, cancelled: bool) -> None:
        """Close identity Attempts/StepExecutions left open by a restart.

        A terminal Runtime Run is allowed to be ahead of its identity
        projection. Reconciliation must close the node records as well as the
        Run record, otherwise execution-tree keeps showing stale ``running``
        nodes even after the Run has failed.
        """
        reason = self._terminal_reason(runtime_run)
        for attempt in self.adapter.repositories.attempts.list_for_run(
            runtime_run.run_id
        ):
            executions = self.adapter.repositories.step_executions.list_for_attempt(
                attempt.attempt_id
            )
            for execution in executions:
                if execution.status is not StepExecutionStatus.RUNNING:
                    continue
                if cancelled:
                    self.adapter.on_step_cancelled(
                        run_id=runtime_run.run_id,
                        attempt_id=attempt.attempt_id,
                        step_execution_id=execution.step_execution_id,
                        reason=reason,
                    )
                else:
                    self.adapter.on_step_failed(
                        run_id=runtime_run.run_id,
                        attempt_id=attempt.attempt_id,
                        step_execution_id=execution.step_execution_id,
                        reason=reason,
                    )
            refreshed_attempt = self.adapter.repositories.attempts.get(
                attempt.attempt_id
            )
            if refreshed_attempt is not None and refreshed_attempt.status in {
                AttemptStatus.PENDING,
                AttemptStatus.RUNNING,
            }:
                self.adapter.repositories.attempts.update_status(
                    attempt.attempt_id,
                    AttemptStatus.CANCELLED if cancelled else AttemptStatus.FAILED,
                    failure_reason=reason,
                )

    @staticmethod
    def _terminal_reason(runtime_run: Any) -> str:
        error = getattr(runtime_run, "error", None)
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str) and error.strip():
            return error
        return "Execution Runtime terminated before the identity projection completed."


__all__ = ["IdentityProjectionReconciler", "IdentityReconciliationReport"]

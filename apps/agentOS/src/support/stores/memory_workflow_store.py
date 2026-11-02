"""运行时配套的内存任务/运行存储，面向开发和测试而非跨部件业务实现。"""


from __future__ import annotations

from typing import Dict, Sequence
from copy import deepcopy
import hashlib
import json
import threading
from functools import wraps
from contracts.mission_semantic import (
    EffectiveMissionSnapshot, MissionSemanticAggregate, MissionSemanticOperation,
    SemanticCommit, SemanticOperationReceipt, SemanticOperationResult,
)

from support.stores.mission_semantic_store import (
    MissionSemanticStore, prepare_commit, replay, request_fingerprint, semantic_outbox, snapshot,
)
from contracts.workflow import MissionRecordState, RunRecordState, RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus, utc_now
from support.stores._policy import (
    TERMINAL_RUN_STATUSES,
    matches_run,
    matches_mission,
    reject_terminal_overwrite,
    run_priority,
    validate_run_state,
    mission_status_from_runs,
)
from support.stores.workflow_store import (
    RuntimeRunRecordDeleteResult,
    RuntimeMissionRunSummary,
    RuntimeRunOverview,
    RuntimeRunListSummary,
    RuntimeRunRecordNotTerminalError,
    WorkflowStore,
    WorkflowStorePage,
    lifecycle_run_event_type,
    paginate_items,
    lifecycle_run_payload,
    status_value,
    status_values,
)


def _mission_locked(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._semantic_lock:
            return method(self, *args, **kwargs)
    return locked


class MemoryWorkflowStore(WorkflowStore, MissionSemanticStore):
    """面向本地开发和测试的内存 WorkflowStore 适配器。"""

    def __init__(self):
        self._semantic_lock = threading.RLock()
        self._semantic_states: dict[str, MissionSemanticAggregate] = {}
        self._semantic_commits: dict[str, list[SemanticCommit]] = {}
        self._semantic_receipts: dict[tuple[str, str], SemanticOperationReceipt] = {}
        self._semantic_outbox: dict[str, list[dict]] = {}
        self._revision_decisions: dict[tuple[str, str], object] = {}
        self._tasks: Dict[str, RuntimeMissionRecord] = {}
        self._runs: Dict[str, RuntimeRunRecord] = {}
        self._terminal_run_statuses: Dict[str, WorkflowStatus] = {}
        self._lifecycle_outbox: Dict[str, dict] = {}
        self._copilot_exchanges: dict[tuple[str, str], dict] = {}
        self._planning_inputs: dict[tuple[str, str], dict] = {}
        self._task_copilot_permissions: dict[str, str] = {}

    @_mission_locked
    def commit_semantics(self, operation: MissionSemanticOperation) -> SemanticOperationResult:
        operation = MissionSemanticOperation.model_validate(operation.model_dump())
        fingerprint = request_fingerprint(operation)
        key = (operation.mission_id, operation.operation_id)
        receipt = self._semantic_receipts.get(key)
        if receipt:
            return replay(operation, fingerprint, receipt)
        mission = self.get_mission(operation.mission_id)
        if mission.record_state == MissionRecordState.DELETED:
            raise ValueError("deleted mission cannot accept semantic changes")
        state, commit, receipt = prepare_commit(operation, fingerprint, self._semantic_states.get(operation.mission_id))
        # Prepare all data before publication: exceptions leave every map intact.
        states = dict(self._semantic_states)
        commits = dict(self._semantic_commits)
        receipts = dict(self._semantic_receipts)
        outbox = dict(self._semantic_outbox)
        if commit:
            states[operation.mission_id] = state
            commits[operation.mission_id] = [*commits.get(operation.mission_id, []), commit]
            outbox[operation.mission_id] = [*outbox.get(operation.mission_id, []),
                                           {**semantic_outbox(commit), "status": "pending"}]
        receipts[key] = receipt
        result = receipt.result.model_copy(deep=True)
        (self._semantic_states, self._semantic_commits,
         self._semantic_receipts, self._semantic_outbox) = states, commits, receipts, outbox
        return result

    @_mission_locked
    def get_semantic_snapshot(self, mission_id: str) -> EffectiveMissionSnapshot:
        return snapshot(mission_id, mission_id in self._tasks, deepcopy(self._semantic_states.get(mission_id)))

    @_mission_locked
    def decide_run_revision(self, principal, mission_id, run_id, request):
        from contracts.mission_revision import MissionRevisionConflict, prepare_revision_decision
        run = self.get_run(run_id)
        if run.mission_id != mission_id or self.get_mission(mission_id).record_state != MissionRecordState.ACTIVE:
            raise MissionRevisionConflict("MISSION_SCOPE_CONFLICT")
        key = (run_id, request.operation_id)
        receipt = prepare_revision_decision(run, self.get_semantic_snapshot(mission_id), request,
            principal, self._revision_decisions.get(key))
        self._revision_decisions[key] = deepcopy(receipt)
        return deepcopy(receipt)

    @_mission_locked
    def list_run_revision_decisions(self, mission_id, run_id):
        return deepcopy([r for r in self._revision_decisions.values()
                         if r.mission_id == mission_id and r.run_id == run_id])

    @_mission_locked
    def list_semantic_commits(self, mission_id: str) -> list[SemanticCommit]:
        return deepcopy(self._semantic_commits.get(mission_id, []))

    @_mission_locked
    def get_semantic_receipt(self, mission_id: str, operation_id: str) -> SemanticOperationReceipt | None:
        return deepcopy(self._semantic_receipts.get((mission_id, operation_id)))

    @_mission_locked
    def list_semantic_outbox(self, mission_id: str) -> list[dict]:
        return deepcopy(self._semantic_outbox.get(mission_id, []))

    def get_task_copilot_permission(self, mission_id: str) -> str:
        self.get_mission(mission_id)
        return self._task_copilot_permissions.get(mission_id, "task_collaboration")

    def set_task_copilot_permission(self, mission_id: str, permission: str) -> None:
        self.get_mission(mission_id)
        if permission not in {"read_only", "task_collaboration"}:
            raise ValueError("invalid task Copilot permission")
        self._task_copilot_permissions[mission_id] = permission

    def list_task_copilot_exchanges(self, mission_id: str, *, limit: int = 30) -> list[dict]:
        rows = [{**deepcopy(payload), "sourceRunId": owner}
            for (owner, _), payload in self._copilot_exchanges.items()
            if owner in self._runs and self._runs[owner].mission_id == mission_id]
        return rows[-min(max(limit, 1), 100):]

    def list_planning_inputs(self, run_id: str) -> list[dict]:
        return deepcopy([v for (owner, _), v in self._planning_inputs.items() if owner == run_id])

    def save_planning_input(self, run_id: str, operation_id: str, payload: dict) -> None:
        key = (run_id, operation_id)
        existing = self._planning_inputs.get(key)
        if existing is not None:
            if existing["content"] != payload["content"]:
                raise ValueError("planning input operation conflict")
            return
        if len(self.list_planning_inputs(run_id)) >= 32:
            raise ValueError("planning input budget exhausted")
        self._planning_inputs[key] = deepcopy(payload)

    def list_copilot_exchanges(self, run_id: str, *, limit: int = 30) -> list[dict]:
        return deepcopy([v for (owner, _), v in self._copilot_exchanges.items() if owner == run_id][-min(max(limit, 1), 100):])

    def get_copilot_exchange(self, run_id: str, operation_id: str) -> dict | None:
        return deepcopy(self._copilot_exchanges.get((run_id, operation_id)))

    def save_copilot_exchange(self, run_id: str, operation_id: str, payload: dict) -> None:
        key = (run_id, operation_id)
        if key in self._copilot_exchanges:
            raise ValueError("conversation exchange already exists")
        self._copilot_exchanges[key] = deepcopy(payload)

    @_mission_locked
    def save_mission(self, task: RuntimeMissionRecord) -> None:
        """按任务标识保存内存对象；调用方保留传入任务所有权。"""
        task = task.model_copy(deep=True)
        projected = mission_status_from_runs(run.status for run in self._runs.values() if run.mission_id == task.mission_id)
        if projected is not None:
            task.status = projected
        self._tasks[task.mission_id] = task
        payload = task.model_dump(by_alias=True, mode="json")
        self._append_lifecycle_event(
            event_id=self._snapshot_event_id("mission.created", task.mission_id, payload),
            event_type="mission.created",
            aggregate_id=task.mission_id,
            payload=payload,
        )

    @_mission_locked
    def create_mission_once(self, task: RuntimeMissionRecord) -> RuntimeMissionRecord:
        existing = next((m for m in self._tasks.values() if m.creation_key == task.creation_key), None) if task.creation_key else self._tasks.get(task.mission_id)
        if existing is not None:
            if not task.creation_fingerprint or existing.creation_fingerprint != task.creation_fingerprint:
                raise ValueError("mission creation request conflict")
            return existing.model_copy(deep=True)
        tasks, outbox = dict(self._tasks), deepcopy(self._lifecycle_outbox)
        try:
            self.save_mission(task.model_copy(deep=True))
        except Exception:
            self._tasks, self._lifecycle_outbox = tasks, outbox
            raise
        return task.model_copy(deep=True)

    @_mission_locked
    def find_mission_by_creation_key(self, creation_key: str) -> RuntimeMissionRecord | None:
        existing = next((m for m in self._tasks.values() if m.creation_key == creation_key), None)
        return existing.model_copy(deep=True) if existing is not None else None

    @_mission_locked
    def save_prepared_run_once(self, run: RuntimeRunRecord) -> RuntimeRunRecord:
        existing = self.find_run_by_idempotency_key(run.idempotency_key) if run.idempotency_key else None
        if existing is not None:
            if existing.mission_id != run.mission_id or existing.idempotency_fingerprint != run.idempotency_fingerprint:
                raise ValueError("run creation request conflict")
            return existing.model_copy(deep=True)
        runs, terminal, outbox = dict(self._runs), dict(self._terminal_run_statuses), deepcopy(self._lifecycle_outbox)
        from contracts.mission_revision import validate_revision_successor
        if run.execution_state.get("missionRevisionDecision"):
            from contracts.mission_revision import MissionRevisionConflict
            if self.get_mission(run.mission_id).record_state != MissionRecordState.ACTIVE:
                raise MissionRevisionConflict("MISSION_NOT_ACTIVE")
            validate_revision_successor(run, self._runs.get(run.execution_state.get("parentRunId")),
                self.get_semantic_snapshot(run.mission_id),
                self.list_run_revision_decisions(run.mission_id, run.execution_state.get("parentRunId")))
        try:
            self.save_run(run)
        except Exception:
            self._runs, self._terminal_run_statuses, self._lifecycle_outbox = runs, terminal, outbox
            raise
        return run.model_copy(deep=True)

    @_mission_locked
    def get_mission(self, mission_id: str) -> RuntimeMissionRecord:
        """读取任务副本，避免过期调用方绕过存储修改兼容投影。"""
        try:
            return self._tasks[mission_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"task not found: {mission_id}") from exc

    @_mission_locked
    def set_mission_record_state(
        self, mission_id: str, state: MissionRecordState
    ) -> tuple[RuntimeMissionRecord, int]:
        task = self.get_mission(mission_id)
        if task.record_state is MissionRecordState.DELETED:
            raise ValueError("deleted mission record state is immutable")
        runs = [run for run in self._runs.values() if run.mission_id == mission_id]
        for run in runs:
            if run.status not in TERMINAL_RUN_STATUSES:
                raise RuntimeRunRecordNotTerminalError(run.run_id, run.status)
        now = utc_now()
        task.record_state = state
        task.updated_at = now
        task.archived_at = now if state is MissionRecordState.ARCHIVED else None
        if state is MissionRecordState.DELETED:
            task.deleted_at = now
        self._tasks[mission_id] = task.model_copy(deep=True)
        return task.model_copy(deep=True), len(runs)

    @_mission_locked
    def save_run(self, run: RuntimeRunRecord, *, expected_snapshot: RuntimeRunRecord | None = None) -> None:
        """深复制保存运行，并拒绝终态被不同状态或更旧快照覆盖。

        失败到重试是唯一允许的终态回退兼容路径；与 Mission 清除共享锁。
        """
        if expected_snapshot is not None and self.get_run(run.run_id) != expected_snapshot:
            raise ValueError('Run changed before persistence')
        event_type = lifecycle_run_event_type(run)
        events = []
        if event_type is not None:
            payload = lifecycle_run_payload(run)
            events.append({'eventId': self._snapshot_event_id(event_type, run.run_id, payload),
                'eventType': event_type, 'aggregateId': run.run_id, 'payload': payload})
        self.save_run_with_events(run, events)

    def _save_run_snapshot(self, run: RuntimeRunRecord) -> bool:
        if run.mission_id not in self._tasks:
            raise ValueError(f"workflow run task does not exist: {run.mission_id}")
        validate_run_state(run)
        existing = self._runs.get(run.run_id)
        from support.stores._policy import validate_intent_basis
        validate_intent_basis(existing, run)
        terminal_status = self._terminal_run_statuses.get(run.run_id)
        if terminal_status is not None and _reject_terminal_status_overwrite(terminal_status, run.status):
            return False
        if existing is not None and reject_terminal_overwrite(existing, run):
            return False
        if run.status in TERMINAL_RUN_STATUSES:
            self._terminal_run_statuses[run.run_id] = run.status
        elif terminal_status == WorkflowStatus.FAILED and run.status == WorkflowStatus.RETRYING:
            self._terminal_run_statuses.pop(run.run_id, None)
        self._runs[run.run_id] = run.model_copy(deep=True)
        self.project_mission_status(run.mission_id)
        return True

    @_mission_locked
    def project_mission_status(self, mission_id: str) -> RuntimeMissionRecord | None:
        status = mission_status_from_runs(run.status for run in self._runs.values() if run.mission_id == mission_id)
        if status is None:
            return None
        task = self.get_mission(mission_id)
        if task.status != status:
            task.status = status
            task.updated_at = utc_now()
            self.save_mission(task)
        return task

    @_mission_locked
    def save_run_with_events(self, run: RuntimeRunRecord, events, *, expected_snapshot: RuntimeRunRecord | None = None) -> None:
        if expected_snapshot is not None and self.get_run(run.run_id) != expected_snapshot:
            raise ValueError('Run changed before persistence')
        tasks_snapshot = dict(self._tasks)
        outbox_snapshot = dict(self._lifecycle_outbox)
        run_snapshot = dict(self._runs)
        terminal_snapshot = dict(self._terminal_run_statuses)
        try:
            if not self._save_run_snapshot(run):
                return
            for event in events:
                event_id = str(event["eventId"])
                current = self._lifecycle_outbox.get(event_id)
                payload = {
                    "event_id": event_id,
                    "event_type": str(event["eventType"]),
                    "aggregate_id": str(event.get("aggregateId") or run.run_id),
                    "payload": json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True),
                    "attempts": 0,
                }
                if current is not None and current != payload:
                    raise ValueError(f"lifecycle event payload conflict: {event_id}")
                self._lifecycle_outbox[event_id] = payload
        except Exception:
            self._tasks = tasks_snapshot
            self._lifecycle_outbox = outbox_snapshot
            self._runs = run_snapshot
            self._terminal_run_statuses = terminal_snapshot
            raise

    @_mission_locked
    def save_graph_patch_transition(
        self, old_run: RuntimeRunRecord, new_run: RuntimeRunRecord, event: dict
    ) -> None:
        tasks_snapshot = dict(self._tasks)
        runs_snapshot = dict(self._runs)
        terminal_snapshot = dict(self._terminal_run_statuses)
        outbox_snapshot = dict(self._lifecycle_outbox)
        try:
            self._save_run_snapshot(new_run)
            self._save_run_snapshot(old_run)
            event_id = str(event["eventId"])
            payload = {
                "event_id": event_id,
                "event_type": str(event["eventType"]),
                "aggregate_id": str(event.get("aggregateId") or old_run.run_id),
                "payload": json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True),
                "attempts": 0,
            }
            current = self._lifecycle_outbox.get(event_id)
            if current is not None and current != payload:
                raise ValueError(f"lifecycle event payload conflict: {event_id}")
            self._lifecycle_outbox[event_id] = payload
        except Exception:
            self._tasks = tasks_snapshot
            self._runs = runs_snapshot
            self._terminal_run_statuses = terminal_snapshot
            self._lifecycle_outbox = outbox_snapshot
            raise

    def _append_lifecycle_event(
        self,
        *,
        event_id: str,
        event_type: str,
        aggregate_id: str,
        payload: dict,
    ) -> None:
        encoded = {
            "event_id": event_id,
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "attempts": 0,
        }
        current = self._lifecycle_outbox.get(event_id)
        if current is not None and current != encoded:
            raise ValueError(f"lifecycle event payload conflict: {event_id}")
        self._lifecycle_outbox[event_id] = encoded

    @staticmethod
    def _snapshot_event_id(event_type: str, aggregate_id: str, payload: dict) -> str:
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{event_type}:{aggregate_id}:{digest}"

    def list_outbox(self, *, limit: int = 200) -> list[dict]:
        return [dict(item) for item in list(self._lifecycle_outbox.values())[:max(1, limit)]]

    def mark_outbox(self, event_id: str, *, applied: bool, error: str | None = None) -> None:
        if applied:
            self._lifecycle_outbox.pop(event_id, None)

    @_mission_locked
    def get_run(self, run_id: str) -> RuntimeRunRecord:
        """返回运行的深复制快照，避免调用方绕过存储修改内部状态。"""
        try:
            return self._runs[run_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"workflow run not found: {run_id}") from exc

    @_mission_locked
    def delete_run(self, run_id: str, *, delete_orphan_mission: bool = True) -> RuntimeRunRecordDeleteResult:
        """删除终态运行，并可清理无剩余运行引用的任务；非终态时抛出专用错误。"""
        try:
            run = self._runs[run_id]
        except KeyError as exc:
            raise KeyError(f"workflow run not found: {run_id}") from exc
        if run.status not in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }:
            raise RuntimeRunRecordNotTerminalError(run_id, run.status)
        # Prepare the complete purge before publishing any mutation.
        runs = dict(self._runs)
        runs.pop(run_id)
        exchanges = {key: value for key, value in self._copilot_exchanges.items() if key[0] != run_id}
        inputs = {key: value for key, value in self._planning_inputs.items() if key[0] != run_id}
        revision_decisions = {key: value for key, value in self._revision_decisions.items() if key[0] != run_id}
        terminals = dict(self._terminal_run_statuses)
        terminals.pop(run_id, None)
        tasks = dict(self._tasks)
        permissions = dict(self._task_copilot_permissions)
        states = dict(self._semantic_states)
        commits = dict(self._semantic_commits)
        receipts = dict(self._semantic_receipts)
        outbox = dict(self._semantic_outbox)
        mission_deleted = False
        if delete_orphan_mission and not any(item.mission_id == run.mission_id for item in runs.values()):
            mission_deleted = tasks.pop(run.mission_id, None) is not None
            permissions.pop(run.mission_id, None)
            states.pop(run.mission_id, None)
            commits.pop(run.mission_id, None)
            outbox.pop(run.mission_id, None)
            receipts = {key: value for key, value in receipts.items() if key[0] != run.mission_id}
        result = RuntimeRunRecordDeleteResult(
            run_id=run_id,
            mission_id=run.mission_id,
            mission_deleted=mission_deleted,
        )
        (self._runs, self._copilot_exchanges, self._planning_inputs,
         self._terminal_run_statuses, self._tasks, self._task_copilot_permissions,
         self._semantic_states, self._semantic_commits, self._semantic_receipts,
         self._semantic_outbox) = (runs, exchanges, inputs, terminals, tasks, permissions,
                                  states, commits, receipts, outbox)
        self._revision_decisions = revision_decisions
        return result

    @_mission_locked
    def set_run_record_state(self, run_id: str, state: RunRecordState) -> RuntimeRunRecord:
        """更新终态运行的用户管理状态；非终态抛专用错误，已删除不可再变更。"""
        try:
            run = self._runs[run_id]
        except KeyError as exc:
            raise KeyError(f"workflow run not found: {run_id}") from exc
        if run.status not in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.SUPERSEDED,
        }:
            raise RuntimeRunRecordNotTerminalError(run_id, run.status)
        if run.record_state is RunRecordState.DELETED:
            raise ValueError("deleted run record state is immutable")
        now = utc_now()
        run.record_state = state
        run.updated_at = now
        run.deleted_at = now if state is RunRecordState.DELETED else None
        return run.model_copy(deep=True)

    def list_missions(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeMissionRecord]:
        """筛选并按 ``(created_at, mission_id)`` 降序分页返回任务深复制，复杂度 ``O(T)``。"""
        expected_status = status_value(status)
        tasks = [
            task.model_copy(deep=True)
            for task in self._tasks.values()
            if matches_mission(task, status=expected_status, domain=domain, source=source)
        ]
        tasks.sort(key=lambda task: (task.created_at, task.mission_id), reverse=True)
        return paginate_items(tasks, page=page, page_size=page_size)

    def list_mission_ids(
        self,
        *,
        mission_record_state: MissionRecordState | str | None = None,
    ) -> set[str]:
        expected_record_state = (
            mission_record_state.value
            if isinstance(mission_record_state, MissionRecordState)
            else mission_record_state
        )
        return {
            mission_id
            for mission_id, task in self._tasks.items()
            if expected_record_state is None
            or task.record_state.value == expected_record_state
        }

    def list_mission_run_summaries(
        self,
        mission_ids: Sequence[str],
        *,
        mission_record_state: MissionRecordState | str | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
    ) -> dict[str, RuntimeMissionRunSummary]:
        expected_record_state = (
            mission_record_state.value
            if isinstance(mission_record_state, MissionRecordState)
            else mission_record_state
        )
        requested_ids = tuple(dict.fromkeys(str(mission_id) for mission_id in mission_ids))
        summaries = {
            mission_id: RuntimeMissionRunSummary(
                mission_id=mission_id,
                latest_run=None,
                run_count=0,
            )
            for mission_id in requested_ids
            if mission_id in self._tasks
            and (
                expected_record_state is None
                or self._tasks[mission_id].record_state.value == expected_record_state
            )
        }
        for run in self._runs.values():
            if run.record_state is RunRecordState.DELETED:
                continue
            if run.mission_id not in summaries or not matches_run(
                run,
                status=None,
                statuses=None,
                domain=None,
                workflow_id=None,
                mission_id=None,
                lifecycle_phase=None,
                source=None,
                sources=None,
                owner_user_id=owner_user_id,
                owner_tenant_id=owner_tenant_id,
            ):
                continue
            current = summaries[run.mission_id]
            latest = current.latest_run
            if latest is None or (
                run.updated_at,
                run.run_id,
            ) > (latest.updated_at, latest.run_id):
                latest = run.model_copy(deep=True)
            summaries[run.mission_id] = RuntimeMissionRunSummary(
                mission_id=run.mission_id,
                latest_run=latest,
                run_count=current.run_count + 1,
            )
        return summaries

    def list_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses=None,
        domain: str | None = None,
        workflow_id: str | None = None,
        mission_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources=None,
        mission_record_state: MissionRecordState | str | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeRunRecord]:
        """筛选并分页返回运行深复制。

        有多状态筛选时等待审核、非终态、终态依次优先，再按更新时间和标识降序，复杂度
        ``O(R log R)``。
        """
        expected_status = status_value(status)
        expected_statuses = status_values(statuses)
        expected_sources = {str(item) for item in sources} if sources else None
        expected_record_state = (
            mission_record_state.value if isinstance(mission_record_state, MissionRecordState)
            else mission_record_state
        )
        runs = [
            run.model_copy(deep=True)
            for run in self._runs.values()
            if run.record_state is not RunRecordState.DELETED
            and (
                expected_record_state is None
                or self._tasks[run.mission_id].record_state.value == expected_record_state
            ) and matches_run(
                run,
                status=expected_status,
                statuses=expected_statuses,
                domain=domain,
                workflow_id=workflow_id,
                mission_id=mission_id,
                lifecycle_phase=lifecycle_phase,
                source=source,
                sources=expected_sources,
                owner_user_id=owner_user_id,
                owner_tenant_id=owner_tenant_id,
            )
        ]
        runs.sort(
            key=lambda run: (run_priority(run) if expected_statuses else 0, run.updated_at, run.run_id),
            reverse=True,
        )
        return paginate_items(runs, page=page, page_size=page_size)

    def list_run_overviews(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses=None,
        domain: str | None = None,
        workflow_id: str | None = None,
        mission_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources=None,
        mission_record_state: MissionRecordState | str | None = None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeRunOverview]:
        """复用 ``list_runs`` 的筛选排序分页，把当前页映射为轻量行投影。"""
        result = self.list_runs(
            status=status,
            statuses=statuses,
            domain=domain,
            workflow_id=workflow_id,
            mission_id=mission_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            sources=sources,
            mission_record_state=mission_record_state,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            page=page,
            page_size=page_size,
        )
        overviews = []
        for run in result.items:
            source_raw = run.input.get("source")
            overviews.append(
                RuntimeRunOverview(
                    run_id=run.run_id,
                    mission_id=run.mission_id,
                    workflow_id=run.workflow_id,
                    domain=run.domain,
                    status=run.status,
                    lifecycle_phase=(
                        run.lifecycle_phase.value if run.lifecycle_phase is not None else None
                    ),
                    lifecycle_message=run.lifecycle_message,
                    source=str(source_raw) if source_raw not in (None, "") else None,
                    current_step_id=run.current_step_id,
                    started_at=run.started_at,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                    runtime_revision=int(run.runtime_revision),
                    title=(
                        self._tasks[run.mission_id].title
                        if run.mission_id in self._tasks
                        else None
                    ),
                )
            )
        return WorkflowStorePage(
            items=tuple(overviews),
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        """返回最新优先的未终态运行深复制，数量下限为 1，复杂度 ``O(R log R)``。"""
        runs = [
            run.model_copy(deep=True)
            for run in self._runs.values()
            if run.status not in TERMINAL_RUN_STATUSES
        ]
        runs.sort(key=lambda run: (run.updated_at, run.run_id), reverse=True)
        return tuple(runs[: max(1, limit)])

    def list_all_run_summaries(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunListSummary, ...]:
        runs = sorted(self._runs.values(), key=lambda run: (run.updated_at, run.run_id))
        start = max(0, offset)
        return tuple(RuntimeRunListSummary(
            run_id=run.run_id, mission_id=run.mission_id,
            status=run.status, updated_at=run.updated_at,
        ) for run in runs[start:start + max(1, limit)])

    def list_all_runs(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        runs = sorted(
            (run.model_copy(deep=True) for run in self._runs.values()),
            key=lambda run: (run.created_at, run.run_id),
        )
        start = max(0, offset)
        return tuple(runs[start:start + max(1, limit)])

    def find_run_by_idempotency_key(self, idempotency_key: str) -> RuntimeRunRecord | None:
        """按幂等键返回创建时间最新的运行深复制；无匹配时返回 ``None``。"""
        matches = [
            run.model_copy(deep=True)
            for run in self._runs.values()
            if run.idempotency_key == idempotency_key
        ]
        if not matches:
            return None
        return max(matches, key=lambda run: (run.created_at, run.run_id))


def _reject_terminal_status_overwrite(
    existing: WorkflowStatus,
    incoming: WorkflowStatus,
) -> bool:
    if existing == WorkflowStatus.FAILED and incoming == WorkflowStatus.RETRYING:
        return False
    return incoming != existing

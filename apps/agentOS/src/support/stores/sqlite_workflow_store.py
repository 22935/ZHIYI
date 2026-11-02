"""运行时配套的 SQLite 任务/运行存储，不包含跨部件业务实现。"""


from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Sequence

from contracts.mission_semantic import (
    EffectiveMissionSnapshot, MissionSemanticAggregate, MissionSemanticOperation,
    SemanticCommit, SemanticOperationReceipt, SemanticOperationResult,
)
from support.stores.mission_semantic_store import (
    MissionSemanticStore, prepare_commit, replay, request_fingerprint, semantic_outbox, snapshot,
)

from contracts.workflow import MissionRecordState, RunRecordState, RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus, utc_now
from support.stores._policy import matches_mission, reject_terminal_overwrite, validate_run_state, mission_status_from_runs
from support.stores.workflow_store import (
    RuntimeMissionRunSummary,
    RuntimeRunListSummary,
    RuntimeRunOverview,
    RuntimeRunRecordDeleteResult,
    RuntimeRunRecordNotTerminalError,
    WorkflowStore,
    WorkflowStorePage,
    lifecycle_run_event_type,
    lifecycle_run_payload,
    paginate_items,
    status_value,
    status_values,
)


class SQLiteWorkflowStore(WorkflowStore, MissionSemanticStore):
    """基于 SQLite 的本地持久化 WorkflowStore。"""

    def __init__(self, db_path: str | Path, *, enable_mission_semantics: bool = False):
        self.db_path = Path(db_path)
        self.busy_timeout_ms = int(os.getenv("AGENTOS_SQLITE_BUSY_TIMEOUT_MS", "5000"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._hydrate_cache: OrderedDict[str, tuple[bytes, RuntimeRunRecord]] = OrderedDict()
        self._hydrate_cache_lock = threading.Lock()
        self._init_schema()
        self._mission_semantics_enabled = enable_mission_semantics
        if enable_mission_semantics:
            self._init_semantic_schema()

    def _require_semantic_schema(self) -> None:
        if not self._mission_semantics_enabled:
            raise RuntimeError("Mission semantics require explicit schema upgrade opt-in")

    def enable_existing_mission_semantics(self) -> None:
        """Attach to an explicitly upgraded database. Never run semantic DDL here."""
        with self._connect() as conn:
            try:
                versions = [row[0] for row in conn.execute("SELECT version FROM mission_semantic_schema")]
                for table in ("mission_semantic_state", "mission_semantic_commits",
                              "mission_semantic_receipts", "mission_semantic_outbox"):
                    conn.execute(f"SELECT 1 FROM {table} LIMIT 0")
            except sqlite3.OperationalError as exc:
                raise RuntimeError("Mission semantic schema must be upgraded explicitly before activation") from exc
            if versions != [1]:
                raise RuntimeError(f"unsupported Mission semantic schema: {versions}")
        self._mission_semantics_enabled = True

    def _init_semantic_schema(self) -> None:
        """Additive v1 migration; separate from IdentityV2's schema version.

        No legacy payload backfill. Existing tables are never dropped. Older
        binaries can read their original tables but must not perform hard purge
        on a database upgraded with semantic history.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS mission_semantic_schema (version INTEGER PRIMARY KEY)")
            versions = [row[0] for row in conn.execute("SELECT version FROM mission_semantic_schema")]
            if versions and versions != [1]:
                raise RuntimeError(f"unsupported Mission semantic schema: {versions}")
            if not versions:
                conn.execute("""CREATE TABLE mission_semantic_state (
                    mission_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision >= 1),
                    payload TEXT NOT NULL)""")
                conn.execute("""CREATE TABLE mission_semantic_commits (
                    commit_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    operation_id TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(mission_id, revision), UNIQUE(mission_id, operation_id))""")
                conn.execute("""CREATE TABLE mission_semantic_receipts (
                    mission_id TEXT NOT NULL, operation_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(mission_id, operation_id))""")
                conn.execute("""CREATE TABLE mission_semantic_outbox (
                    event_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    UNIQUE(mission_id, revision))""")
                conn.execute("INSERT INTO mission_semantic_schema(version) VALUES(1)")
            conn.execute("""CREATE TABLE IF NOT EXISTS mission_revision_decisions (
                mission_id TEXT NOT NULL, run_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(run_id, operation_id))""")
            conn.commit()

    def list_run_revision_decisions(self, mission_id, run_id):
        from contracts.mission_revision import MissionRevisionReceipt
        self._require_semantic_schema()
        with self._connect() as conn:
            return [MissionRevisionReceipt.model_validate_json(row[0]) for row in conn.execute(
                "SELECT payload FROM mission_revision_decisions WHERE mission_id=? AND run_id=? ORDER BY rowid",
                (mission_id, run_id))]

    def decide_run_revision(self, principal, mission_id, run_id, request):
        from contracts.mission_revision import MissionRevisionReceipt, MissionRevisionConflict, prepare_revision_decision
        self._require_semantic_schema()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            run = RuntimeRunRecord.model_validate_json(row[0])
            row = conn.execute("SELECT payload FROM tasks WHERE mission_id=?", (mission_id,)).fetchone()
            if (run.mission_id != mission_id or not row or
                    RuntimeMissionRecord.model_validate_json(row[0]).record_state != MissionRecordState.ACTIVE):
                raise MissionRevisionConflict("MISSION_SCOPE_CONFLICT")
            row = conn.execute("SELECT payload FROM mission_semantic_state WHERE mission_id=?", (mission_id,)).fetchone()
            state = MissionSemanticAggregate.model_validate_json(row[0]) if row else None
            row = conn.execute("SELECT payload FROM mission_revision_decisions WHERE run_id=? AND operation_id=?",
                               (run_id, request.operation_id)).fetchone()
            previous = MissionRevisionReceipt.model_validate_json(row[0]) if row else None
            receipt = prepare_revision_decision(run, snapshot(mission_id, True, state), request, principal, previous)
            if previous is None:
                conn.execute("INSERT INTO mission_revision_decisions VALUES(?,?,?,?)",
                    (mission_id, run_id, request.operation_id, receipt.model_dump_json(by_alias=True)))
            return receipt

    def commit_semantics(self, operation: MissionSemanticOperation) -> SemanticOperationResult:
        self._require_semantic_schema()
        operation = MissionSemanticOperation.model_validate(operation.model_dump())
        fingerprint = request_fingerprint(operation)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM mission_semantic_receipts WHERE mission_id=? AND operation_id=?",
                               (operation.mission_id, operation.operation_id)).fetchone()
            if row:
                return replay(operation, fingerprint, SemanticOperationReceipt.model_validate_json(row[0]))
            mission = conn.execute("SELECT payload FROM tasks WHERE mission_id=?", (operation.mission_id,)).fetchone()
            if not mission:
                raise KeyError(f"mission not found: {operation.mission_id}")
            if RuntimeMissionRecord.model_validate_json(mission[0]).record_state == MissionRecordState.DELETED:
                raise ValueError("deleted mission cannot accept semantic changes")
            row = conn.execute("SELECT payload FROM mission_semantic_state WHERE mission_id=?",
                               (operation.mission_id,)).fetchone()
            old = MissionSemanticAggregate.model_validate_json(row[0]) if row else None
            state, commit, receipt = prepare_commit(operation, fingerprint, old)
            if commit:
                if old is None:
                    conn.execute("INSERT INTO mission_semantic_state VALUES(?,?,?)",
                                 (operation.mission_id, state.mission_revision, state.model_dump_json(by_alias=True)))
                else:
                    updated = conn.execute("UPDATE mission_semantic_state SET revision=?, payload=? WHERE mission_id=? AND revision=?",
                                           (state.mission_revision, state.model_dump_json(by_alias=True),
                                            operation.mission_id, operation.expected_mission_revision))
                    if updated.rowcount != 1:
                        raise RuntimeError("semantic CAS lost its transaction boundary")
                conn.execute("INSERT INTO mission_semantic_commits VALUES(?,?,?,?,?)",
                             (commit.commit_id, operation.mission_id, commit.mission_revision,
                              operation.operation_id, commit.model_dump_json(by_alias=True)))
                self._append_semantic_outbox(conn, commit)
            conn.execute("INSERT INTO mission_semantic_receipts VALUES(?,?,?)",
                         (operation.mission_id, operation.operation_id, receipt.model_dump_json(by_alias=True)))
            conn.commit()
            return receipt.result

    def _append_semantic_outbox(self, conn: sqlite3.Connection, commit: SemanticCommit) -> None:
        conn.execute("INSERT INTO mission_semantic_outbox(event_id,mission_id,revision,payload) VALUES(?,?,?,?)",
                     (commit.commit_id, commit.mission_id, commit.mission_revision,
                      json.dumps(semantic_outbox(commit), ensure_ascii=False)))

    def get_semantic_snapshot(self, mission_id: str) -> EffectiveMissionSnapshot:
        self._require_semantic_schema()
        with self._connect() as conn:
            # One read statement gives a consistent Mission/state view.
            row = conn.execute("""SELECT t.mission_id, s.payload FROM tasks t
                LEFT JOIN mission_semantic_state s ON s.mission_id=t.mission_id
                WHERE t.mission_id=?""", (mission_id,)).fetchone()
            state = MissionSemanticAggregate.model_validate_json(row[1]) if row and row[1] else None
            return snapshot(mission_id, row is not None, state)

    def list_semantic_commits(self, mission_id: str) -> list[SemanticCommit]:
        self._require_semantic_schema()
        with self._connect() as conn:
            return [SemanticCommit.model_validate_json(row[0]) for row in conn.execute(
                "SELECT payload FROM mission_semantic_commits WHERE mission_id=? ORDER BY revision", (mission_id,))]

    def get_semantic_receipt(self, mission_id: str, operation_id: str) -> SemanticOperationReceipt | None:
        self._require_semantic_schema()
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM mission_semantic_receipts WHERE mission_id=? AND operation_id=?",
                               (mission_id, operation_id)).fetchone()
            return SemanticOperationReceipt.model_validate_json(row[0]) if row else None

    def list_semantic_outbox(self, mission_id: str) -> list[dict]:
        self._require_semantic_schema()
        with self._connect() as conn:
            return [{**json.loads(row[0]), "status": row[1]} for row in conn.execute(
                "SELECT payload,status FROM mission_semantic_outbox WHERE mission_id=? ORDER BY revision", (mission_id,))]

    def save_mission(self, task: RuntimeMissionRecord) -> None:
        """以任务标识 UPSERT JSON 快照并提交事务；SQLite 错误由驱动层原样抛出。"""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = task.model_copy(deep=True)
            projected = mission_status_from_runs(WorkflowStatus(row[0]) for row in conn.execute(
                "SELECT status FROM runs WHERE mission_id=?", (task.mission_id,)))
            if projected is not None:
                task.status = projected
            payload = json.dumps(task.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            conn.execute(
                """INSERT INTO tasks(mission_id, payload, updated_at)
                   VALUES(?, ?, ?)
                   ON CONFLICT(mission_id) DO UPDATE SET
                       payload=excluded.payload, updated_at=excluded.updated_at""",
                (task.mission_id, payload, task.updated_at.isoformat()),
            )
            self._append_outbox(
                conn,
                self._snapshot_event_id("mission.created", task.mission_id, payload),
                "mission.created",
                task.mission_id,
                payload,
            )
            conn.commit()

    def create_mission_once(self, task: RuntimeMissionRecord) -> RuntimeMissionRecord:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM tasks WHERE json_extract(payload, '$.creationKey')=?",
                               (task.creation_key,)).fetchone() if task.creation_key else conn.execute(
                                   "SELECT payload FROM tasks WHERE mission_id=?", (task.mission_id,)).fetchone()
            if row is not None:
                existing = RuntimeMissionRecord.model_validate_json(row[0])
                if not task.creation_fingerprint or existing.creation_fingerprint != task.creation_fingerprint:
                    raise ValueError("mission creation request conflict")
                return existing
            payload = task.model_dump_json(by_alias=True)
            conn.execute("INSERT INTO tasks(mission_id,payload,updated_at) VALUES(?,?,?)",
                         (task.mission_id, payload, task.updated_at.isoformat()))
            self._append_outbox(conn, self._snapshot_event_id("mission.created", task.mission_id, payload),
                                "mission.created", task.mission_id, payload)
            return task.model_copy(deep=True)

    def find_mission_by_creation_key(self, creation_key: str) -> RuntimeMissionRecord | None:
        row = self._fetch_one("SELECT payload FROM tasks WHERE json_extract(payload, '$.creationKey')=?", (creation_key,))
        return RuntimeMissionRecord.model_validate_json(row["payload"]) if row is not None else None

    def save_prepared_run_once(self, run: RuntimeRunRecord) -> RuntimeRunRecord:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM runs WHERE json_extract(payload, '$.idempotencyKey')=?",
                               (run.idempotency_key,)).fetchone() if run.idempotency_key else None
            if row is not None:
                existing = RuntimeRunRecord.model_validate_json(row[0])
                if existing.mission_id != run.mission_id or existing.idempotency_fingerprint != run.idempotency_fingerprint:
                    raise ValueError("run creation request conflict")
                return existing
            if run.execution_state.get("missionRevisionDecision"):
                from contracts.mission_revision import validate_revision_successor, MissionRevisionReceipt, MissionRevisionConflict
                mission = conn.execute("SELECT payload FROM tasks WHERE mission_id=?", (run.mission_id,)).fetchone()
                if not mission or RuntimeMissionRecord.model_validate_json(mission[0]).record_state != MissionRecordState.ACTIVE:
                    raise MissionRevisionConflict("MISSION_NOT_ACTIVE")
                source = conn.execute("SELECT payload FROM runs WHERE run_id=?",
                    (run.execution_state.get("parentRunId"),)).fetchone()
                state = conn.execute("SELECT payload FROM mission_semantic_state WHERE mission_id=?",
                    (run.mission_id,)).fetchone()
                validate_revision_successor(run, RuntimeRunRecord.model_validate_json(source[0]) if source else None,
                    snapshot(run.mission_id, True, MissionSemanticAggregate.model_validate_json(state[0]) if state else None),
                    [MissionRevisionReceipt.model_validate_json(r[0]) for r in conn.execute(
                        "SELECT payload FROM mission_revision_decisions WHERE mission_id=? AND run_id=? ORDER BY rowid",
                        (run.mission_id, run.execution_state.get("parentRunId")))])
            self._upsert_run(conn, run)
            event_type = lifecycle_run_event_type(run)
            if event_type:
                payload = json.dumps(lifecycle_run_payload(run), ensure_ascii=False, sort_keys=True)
                self._append_outbox(conn, self._snapshot_event_id(event_type, run.run_id, payload),
                                    event_type, run.run_id, payload)
            return run.model_copy(deep=True)

    def get_mission(self, mission_id: str) -> RuntimeMissionRecord:
        """读取并校验任务 JSON 快照；缺失时抛出 ``KeyError``。"""
        row = self._fetch_one("SELECT payload FROM tasks WHERE mission_id = ?", (mission_id,))
        if row is None:
            raise KeyError(f"task not found: {mission_id}")
        return RuntimeMissionRecord.model_validate(json.loads(row["payload"]))

    def set_mission_record_state(
        self, mission_id: str, state: MissionRecordState
    ) -> tuple[RuntimeMissionRecord, int]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT payload FROM tasks WHERE mission_id = ?", (mission_id,)).fetchone()
            if row is None:
                raise KeyError(f"task not found: {mission_id}")
            task = RuntimeMissionRecord.model_validate(json.loads(row["payload"]))
            if task.record_state is MissionRecordState.DELETED:
                raise ValueError("deleted mission record state is immutable")
            run_rows = conn.execute("SELECT payload FROM runs WHERE mission_id = ?", (mission_id,)).fetchall()
            runs = [RuntimeRunRecord.model_validate(json.loads(item["payload"])) for item in run_rows]
            for run in runs:
                if run.status not in {
                    WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
                    WorkflowStatus.CANCELLED, WorkflowStatus.SUPERSEDED,
                }:
                    raise RuntimeRunRecordNotTerminalError(run.run_id, run.status)
            now = utc_now()
            task.record_state = state
            task.updated_at = now
            task.archived_at = now if state is MissionRecordState.ARCHIVED else None
            if state is MissionRecordState.DELETED:
                task.deleted_at = now
            payload = json.dumps(task.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            conn.execute(
                "UPDATE tasks SET payload = ?, updated_at = ? WHERE mission_id = ?",
                (payload, now.isoformat(), mission_id),
            )
            conn.commit()
            return task, len(runs)

    def save_run(self, run: RuntimeRunRecord, *, expected_snapshot: RuntimeRunRecord | None = None) -> None:
        """在单连接事务中保存运行。

        要求父任务存在且 ``mission_id`` 不可变；拒绝终态被旧/不同状态覆盖，验证明显状态冲突后
        执行 UPSERT 与提交。
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if expected_snapshot is not None:
                current = conn.execute("SELECT payload FROM runs WHERE run_id=?", (run.run_id,)).fetchone()
                if current is None or RuntimeRunRecord.model_validate_json(current[0]) != expected_snapshot:
                    raise ValueError('Run changed before persistence')
            if not self._upsert_run(conn, run):
                return
            event_type = lifecycle_run_event_type(run)
            if event_type is None:
                conn.commit()
                return
            lifecycle_payload = json.dumps(
                lifecycle_run_payload(run), ensure_ascii=False, sort_keys=True
            )
            self._append_outbox(
                conn,
                self._snapshot_event_id(event_type, run.run_id, lifecycle_payload),
                event_type,
                run.run_id,
                lifecycle_payload,
            )
            conn.commit()

    def save_run_with_events(self, run: RuntimeRunRecord, events) -> None:
        """Commit the run snapshot and step lifecycle facts in one Execution Runtime transaction."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._upsert_run(conn, run):
                return
            for event in events:
                event_id = str(event["eventId"])
                event_type = str(event["eventType"])
                aggregate_id = str(event.get("aggregateId") or run.run_id)
                payload = json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True)
                existing = conn.execute(
                    "SELECT event_type, aggregate_id, payload FROM lifecycle_outbox WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if existing is not None and tuple(str(item) for item in existing) != (
                    event_type, aggregate_id, payload
                ):
                    raise ValueError(f"lifecycle event payload conflict: {event_id}")
                self._append_outbox(conn, event_id, event_type, aggregate_id, payload)
            conn.commit()

    def save_graph_patch_transition(
        self, old_run: RuntimeRunRecord, new_run: RuntimeRunRecord, event: dict
    ) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._upsert_run(conn, new_run):
                raise ValueError("replacement run already has an incompatible snapshot")
            if not self._upsert_run(conn, old_run):
                raise ValueError("superseded run snapshot conflicts with terminal state")
            event_id = str(event["eventId"])
            event_type = str(event["eventType"])
            aggregate_id = str(event.get("aggregateId") or old_run.run_id)
            payload = json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True)
            self._append_outbox(conn, event_id, event_type, aggregate_id, payload)
            conn.commit()

    @staticmethod
    def _upsert_run(conn: sqlite3.Connection, run: RuntimeRunRecord) -> bool:
        conn.row_factory = sqlite3.Row
        from support.stores.graph_activation_store import validate_activation_run
        validate_activation_run(conn, run)
        task_row = conn.execute(
            "SELECT 1 FROM tasks WHERE mission_id = ?", (run.mission_id,)
        ).fetchone()
        if task_row is None:
            raise ValueError(f"workflow run task does not exist: {run.mission_id}")
        row = conn.execute(
            "SELECT mission_id, payload FROM runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()
        existing = None
        if row is not None:
            if str(row["mission_id"]) != run.mission_id:
                raise ValueError(f"workflow run missionId cannot change: {run.run_id}")
            existing = RuntimeRunRecord.model_validate(json.loads(row["payload"]))
        from support.stores._policy import validate_intent_basis
        validate_intent_basis(existing, run)
        if (existing is not None and existing.execution_state.get("planningCommitRequired")
                and run.execution_state.get("planningCommitRequired") is not True):
            raise ValueError("persisted Planning Commit mode cannot be removed or disabled")
        if existing is not None:
            if reject_terminal_overwrite(existing, run):
                return False
        validate_run_state(run)
        owner_user_id = str(run.input.get("authenticatedUserId") or "").strip() or None
        owner_tenant_id = str(run.input.get("authenticatedTenantId") or "").strip() or None
        conn.execute(
            """INSERT INTO runs(
                   run_id, mission_id, payload, updated_at,
                   status, owner_user_id, owner_tenant_id,
                   domain, workflow_id, lifecycle_phase, lifecycle_message,
                   source, current_step_id, started_at, created_at, runtime_revision,
                   record_state
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET
                   mission_id=excluded.mission_id,
                   payload=excluded.payload,
                   updated_at=excluded.updated_at,
                   status=excluded.status,
                   owner_user_id=excluded.owner_user_id,
                   owner_tenant_id=excluded.owner_tenant_id,
                   domain=excluded.domain,
                   workflow_id=excluded.workflow_id,
                   lifecycle_phase=excluded.lifecycle_phase,
                   lifecycle_message=excluded.lifecycle_message,
                   source=excluded.source,
                   current_step_id=excluded.current_step_id,
                   started_at=excluded.started_at,
                   created_at=excluded.created_at,
                   runtime_revision=excluded.runtime_revision,
                   record_state=excluded.record_state""",
            (
                run.run_id,
                run.mission_id,
                json.dumps(run.model_dump(by_alias=True, mode="json"), ensure_ascii=False),
                run.updated_at.isoformat(),
                run.status.value,
                owner_user_id,
                owner_tenant_id,
                *SQLiteWorkflowStore._run_summary_values(run),
                run.record_state.value,
            ),
        )
        SQLiteWorkflowStore._project_mission_status(conn, run.mission_id)
        return True

    def project_mission_status(self, mission_id: str) -> RuntimeMissionRecord | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return self._project_mission_status(conn, mission_id)

    @staticmethod
    def _project_mission_status(conn, mission_id: str) -> RuntimeMissionRecord | None:
        status = mission_status_from_runs(WorkflowStatus(row[0]) for row in conn.execute(
            "SELECT status FROM runs WHERE mission_id=?", (mission_id,)))
        if status is None:
            return None
        row = conn.execute("SELECT payload FROM tasks WHERE mission_id=?", (mission_id,)).fetchone()
        task = RuntimeMissionRecord.model_validate_json(row[0])
        if task.status != status:
            task.status = status
            task.updated_at = utc_now()
            payload = json.dumps(task.model_dump(by_alias=True, mode='json'), ensure_ascii=False)
            conn.execute("UPDATE tasks SET payload=?,updated_at=? WHERE mission_id=?",
                (payload, task.updated_at.isoformat(), mission_id))
            SQLiteWorkflowStore._append_outbox(conn,
                SQLiteWorkflowStore._snapshot_event_id('mission.created', mission_id, payload),
                'mission.created', mission_id, payload)
        return task

    def list_outbox(self, *, limit: int = 200) -> list[dict]:
        rows = self._fetch_all(
            """SELECT event_id, event_type, aggregate_id, payload, attempts
               FROM lifecycle_outbox WHERE status != 'applied'
               ORDER BY created_at, rowid LIMIT ?""",
            (max(1, limit),),
        )
        return [dict(row) for row in rows]

    def outbox_stats(self) -> dict:
        row = self._fetch_one(
            """SELECT
                   SUM(CASE WHEN status != 'applied' THEN 1 ELSE 0 END) AS backlog,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                   MIN(CASE WHEN status != 'applied' THEN created_at END) AS oldest
               FROM lifecycle_outbox""",
            (),
        )
        return {
            "backlog": int(row["backlog"] or 0),
            "failed": int(row["failed"] or 0),
            "oldestEventAt": row["oldest"],
        }

    def mark_outbox(self, event_id: str, *, applied: bool, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE lifecycle_outbox
                   SET status = ?, attempts = attempts + 1, last_error = ?
                   WHERE event_id = ?""",
                ("applied" if applied else "failed", error, event_id),
            )
            conn.commit()

    def get_run(self, run_id: str) -> RuntimeRunRecord:
        """读取并校验运行 JSON 快照；缺失时抛出 ``KeyError``。"""
        row = self._fetch_one("SELECT payload FROM runs WHERE run_id = ?", (run_id,))
        if row is None:
            raise KeyError(f"workflow run not found: {run_id}")
        return RuntimeRunRecord.model_validate(json.loads(row["payload"]))

    def get_run_cached(self, run_id: str) -> RuntimeRunRecord:
        """``get_run`` 的只读快路径：payload 摘要未变化时复用上次水合结果。

        单个运行快照可达数十 MB，``json.loads`` + ``model_validate`` 一次上百毫秒，
        而 memory-events 等读接口被前端秒级轮询。以 payload 摘要为键，数据一变
        即失效，不会读到陈旧数据。返回的记录对象被多个调用方共享，调用方不得
        修改；需要变更的路径请继续使用 ``get_run``。
        """
        row = self._fetch_one("SELECT payload FROM runs WHERE run_id = ?", (run_id,))
        if row is None:
            raise KeyError(f"workflow run not found: {run_id}")
        payload = row["payload"]
        digest = hashlib.blake2b(
            payload.encode("utf-8") if isinstance(payload, str) else bytes(payload),
            digest_size=16,
        ).digest()
        with self._hydrate_cache_lock:
            entry = self._hydrate_cache.get(run_id)
            if entry is not None and entry[0] == digest:
                self._hydrate_cache.move_to_end(run_id)
                return entry[1]
        record = RuntimeRunRecord.model_validate(json.loads(payload))
        with self._hydrate_cache_lock:
            self._hydrate_cache[run_id] = (digest, record)
            self._hydrate_cache.move_to_end(run_id)
            while len(self._hydrate_cache) > 8:
                self._hydrate_cache.popitem(last=False)
        return record

    def list_missions(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[RuntimeMissionRecord]:
        """载入、筛选并按创建时间/标识降序分页任务，复杂度 ``O(T log T)``。"""
        expected_status = status_value(status)
        rows = self._fetch_all("SELECT payload FROM tasks")
        tasks = [
            task
            for task in (RuntimeMissionRecord.model_validate(json.loads(row["payload"])) for row in rows)
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
        rows = self._fetch_all("SELECT mission_id, payload FROM tasks")
        return {
            str(row["mission_id"])
            for row in rows
            if expected_record_state is None
            or RuntimeMissionRecord.model_validate(json.loads(row["payload"])).record_state.value
            == expected_record_state
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
        if not requested_ids:
            return {}
        placeholders = ", ".join("?" for _ in requested_ids)
        task_rows = self._fetch_all(
            f"SELECT mission_id, payload FROM tasks WHERE mission_id IN ({placeholders})",
            requested_ids,
        )
        active_ids = {
            str(row["mission_id"])
            for row in task_rows
            if expected_record_state is None
            or RuntimeMissionRecord.model_validate(json.loads(row["payload"])).record_state.value
            == expected_record_state
        }
        summaries = {
            mission_id: RuntimeMissionRunSummary(
                mission_id=mission_id,
                latest_run=None,
                run_count=0,
            )
            for mission_id in requested_ids
            if mission_id in active_ids
        }
        if not summaries:
            return summaries

        summary_ids = tuple(mission_id for mission_id in requested_ids if mission_id in summaries)
        run_placeholders = ", ".join("?" for _ in summary_ids)
        run_rows = self._fetch_all(
            f"""WITH visible_runs AS (
                    SELECT
                        run_id,
                        mission_id,
                        status,
                        updated_at,
                        COUNT(*) OVER (PARTITION BY mission_id) AS run_count,
                        ROW_NUMBER() OVER (
                            PARTITION BY mission_id
                            ORDER BY updated_at DESC, run_id DESC
                        ) AS position
                    FROM runs
                    WHERE mission_id IN ({run_placeholders})
                      AND COALESCE(record_state, 'active') != 'deleted'
                      AND (owner_user_id IS NULL OR owner_user_id = '' OR owner_user_id = ?)
                      AND (
                          owner_user_id IS NULL OR owner_user_id = ''
                          OR owner_tenant_id IS NULL OR owner_tenant_id = ''
                          OR owner_tenant_id = ?
                      )
                )
                SELECT run_id, mission_id, status, updated_at, run_count
                FROM visible_runs
                WHERE position = 1""",
            (*summary_ids, owner_user_id, owner_tenant_id),
        )
        for row in run_rows:
            mission_id = str(row["mission_id"])
            if mission_id not in summaries:
                continue
            summaries[mission_id] = RuntimeMissionRunSummary(
                mission_id=mission_id,
                latest_run=RuntimeRunListSummary(
                    run_id=str(row["run_id"]),
                    mission_id=mission_id,
                    status=WorkflowStatus(str(row["status"])),
                    updated_at=datetime.fromisoformat(str(row["updated_at"])),
                ),
                run_count=int(row["run_count"]),
            )
        return summaries

    _RUN_PRIORITY_SQL = (
        "CASE r.status WHEN 'waiting_review' THEN 2 "
        "WHEN 'completed' THEN 0 WHEN 'failed' THEN 0 "
        "WHEN 'cancelled' THEN 0 WHEN 'superseded' THEN 0 ELSE 1 END"
    )

    @staticmethod
    def _normalize_record_state(
        mission_record_state: MissionRecordState | str | None,
    ) -> str | None:
        return (
            mission_record_state.value
            if isinstance(mission_record_state, MissionRecordState)
            else mission_record_state
        )

    @staticmethod
    def _run_list_where(
        *,
        expected_status: str | None,
        expected_statuses: set[str] | None,
        domain: str | None,
        workflow_id: str | None,
        mission_id: str | None,
        lifecycle_phase: str | None,
        source: str | None,
        expected_sources: set[str] | None,
        expected_record_state: str | None,
        owner_user_id: str | None,
        owner_tenant_id: str | None,
    ) -> tuple[str, list]:
        """Translate the legacy ``matches_run`` predicate onto summary columns.

        Owner clauses mirror ``matches_run`` exactly: runs with no owner stay
        visible to every actor, while an owned run must match both the caller
        and (when the run declares one) the tenant. A NULL bind parameter
        degrades to the legacy "owned runs are hidden from anonymous callers".
        """
        clauses: list[str] = []
        params: list = []
        # 软删除的 Run 从所有用户列表退场；直达读取（get_run）不受此限制，
        # 由 API 层按 404 语义收敛。record_state 是摘要列，不碰 payload。
        clauses.append("COALESCE(r.record_state, 'active') != 'deleted'")
        if expected_status is not None:
            clauses.append("r.status = ?")
            params.append(expected_status)
        if expected_statuses is not None:
            values = sorted(expected_statuses)
            clauses.append(f"r.status IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        if domain is not None:
            clauses.append("r.domain = ?")
            params.append(domain)
        if workflow_id is not None:
            clauses.append("r.workflow_id = ?")
            params.append(workflow_id)
        if mission_id is not None:
            clauses.append("r.mission_id = ?")
            params.append(mission_id)
        if lifecycle_phase is not None:
            clauses.append("r.lifecycle_phase = ?")
            params.append(lifecycle_phase)
        if source is not None:
            clauses.append("r.source = ?")
            params.append(source)
        if expected_sources is not None:
            values = sorted(expected_sources)
            clauses.append(f"r.source IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        if expected_record_state is not None:
            # Legacy list_runs drops orphan runs (no parent mission) under a
            # record-state filter; the NOT NULL guard keeps that semantics.
            clauses.append(
                "(t.mission_id IS NOT NULL AND "
                "COALESCE(json_extract(t.payload, '$.recordState'), 'active') = ?)"
            )
            params.append(expected_record_state)
        owner_clause = "(r.owner_user_id IS NULL OR r.owner_user_id = ''"
        if owner_user_id is not None:
            owner_clause += " OR r.owner_user_id = ?"
            params.append(owner_user_id)
        clauses.append(owner_clause + ")")
        tenant_clause = (
            "(r.owner_user_id IS NULL OR r.owner_user_id = '' "
            "OR r.owner_tenant_id IS NULL OR r.owner_tenant_id = ''"
        )
        if owner_tenant_id is not None:
            tenant_clause += " OR r.owner_tenant_id = ?"
            params.append(owner_tenant_id)
        clauses.append(tenant_clause + ")")
        return " AND ".join(clauses), params

    @classmethod
    def _run_list_order(cls, expected_statuses: set[str] | None) -> str:
        if expected_statuses is not None:
            return f"{cls._RUN_PRIORITY_SQL} DESC, r.updated_at DESC, r.run_id DESC"
        return "r.updated_at DESC, r.run_id DESC"

    _RUN_LIST_FROM = "FROM runs r LEFT JOIN tasks t ON t.mission_id = r.mission_id"

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
        """在 SQL 侧按摘要列过滤、排序并分页，仅反序列化当前页 payload。

        多状态查询按等待审核、非终态、终态优先，再按更新时间和标识降序，与内存实现
        的 ``matches_run`` + ``run_priority`` 语义一致。
        """
        expected_status = status_value(status)
        expected_statuses = status_values(statuses)
        expected_sources = {str(item) for item in sources} if sources else None
        expected_record_state = self._normalize_record_state(mission_record_state)
        where_sql, params = self._run_list_where(
            expected_status=expected_status,
            expected_statuses=expected_statuses,
            domain=domain,
            workflow_id=workflow_id,
            mission_id=mission_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            expected_sources=expected_sources,
            expected_record_state=expected_record_state,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
        )
        safe_page = max(1, page)
        safe_size = max(1, page_size)
        total = int(
            self._fetch_one(
                f"SELECT COUNT(*) {self._RUN_LIST_FROM} WHERE {where_sql}",
                tuple(params),
            )[0]
        )
        rows = self._fetch_all(
            f"SELECT r.payload {self._RUN_LIST_FROM} WHERE {where_sql} "
            f"ORDER BY {self._run_list_order(expected_statuses)} LIMIT ? OFFSET ?",
            (*params, safe_size, (safe_page - 1) * safe_size),
        )
        runs = tuple(
            RuntimeRunRecord.model_validate(json.loads(row["payload"])) for row in rows
        )
        return WorkflowStorePage(
            items=runs, total=total, page=safe_page, page_size=safe_size
        )

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
        """与 ``list_runs`` 同筛选排序分页，但只读摘要列与任务标题，零 payload 反序列化。"""
        expected_status = status_value(status)
        expected_statuses = status_values(statuses)
        expected_sources = {str(item) for item in sources} if sources else None
        expected_record_state = self._normalize_record_state(mission_record_state)
        where_sql, params = self._run_list_where(
            expected_status=expected_status,
            expected_statuses=expected_statuses,
            domain=domain,
            workflow_id=workflow_id,
            mission_id=mission_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            expected_sources=expected_sources,
            expected_record_state=expected_record_state,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
        )
        safe_page = max(1, page)
        safe_size = max(1, page_size)
        total = int(
            self._fetch_one(
                f"SELECT COUNT(*) {self._RUN_LIST_FROM} WHERE {where_sql}",
                tuple(params),
            )[0]
        )
        rows = self._fetch_all(
            f"""SELECT r.run_id, r.mission_id, r.workflow_id, r.domain, r.status,
                       r.lifecycle_phase, r.lifecycle_message, r.source,
                       r.current_step_id, r.started_at, r.created_at,
                       r.updated_at, r.runtime_revision,
                       json_extract(t.payload, '$.title') AS title
                {self._RUN_LIST_FROM} WHERE {where_sql}
                ORDER BY {self._run_list_order(expected_statuses)}
                LIMIT ? OFFSET ?""",
            (*params, safe_size, (safe_page - 1) * safe_size),
        )
        overviews = tuple(
            RuntimeRunOverview(
                run_id=str(row["run_id"]),
                mission_id=str(row["mission_id"]),
                workflow_id=str(row["workflow_id"] or ""),
                domain=str(row["domain"] or ""),
                status=WorkflowStatus(str(row["status"])),
                lifecycle_phase=str(row["lifecycle_phase"]) if row["lifecycle_phase"] else None,
                lifecycle_message=str(row["lifecycle_message"]) if row["lifecycle_message"] else None,
                source=str(row["source"]) if row["source"] else None,
                current_step_id=str(row["current_step_id"]) if row["current_step_id"] else None,
                started_at=(
                    datetime.fromisoformat(str(row["started_at"])) if row["started_at"] else None
                ),
                created_at=datetime.fromisoformat(str(row["created_at"])),
                updated_at=datetime.fromisoformat(str(row["updated_at"])),
                runtime_revision=int(row["runtime_revision"] or 0),
                title=str(row["title"]) if row["title"] else None,
            )
            for row in rows
        )
        return WorkflowStorePage(
            items=overviews, total=total, page=safe_page, page_size=safe_size
        )

    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        """通过 SQLite JSON 条件返回最新优先的未终态运行；数量下限为 1。"""
        safe_limit = max(1, limit)
        rows = self._fetch_all(
            """
            SELECT payload FROM runs
            WHERE json_extract(payload, '$.status') NOT IN (?, ?, ?, ?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (
                WorkflowStatus.COMPLETED.value,
                WorkflowStatus.FAILED.value,
                WorkflowStatus.CANCELLED.value,
                WorkflowStatus.SUPERSEDED.value,
                safe_limit,
            ),
        )
        return tuple(
            RuntimeRunRecord.model_validate(json.loads(row["payload"])) for row in rows
        )

    def list_all_run_summaries(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunListSummary, ...]:
        rows = self._fetch_all(
            "SELECT run_id, mission_id, status, updated_at FROM runs ORDER BY updated_at, run_id LIMIT ? OFFSET ?",
            (max(1, limit), max(0, offset)),
        )
        return tuple(RuntimeRunListSummary(
            run_id=row["run_id"], mission_id=row["mission_id"],
            status=WorkflowStatus(row["status"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        ) for row in rows)

    def list_all_runs(self, *, offset: int = 0, limit: int = 200) -> tuple[RuntimeRunRecord, ...]:
        rows = self._fetch_all(
            "SELECT payload FROM runs ORDER BY updated_at, run_id LIMIT ? OFFSET ?",
            (max(1, limit), max(0, offset)),
        )
        return tuple(RuntimeRunRecord.model_validate(json.loads(row["payload"])) for row in rows)

    def find_run_by_idempotency_key(self, idempotency_key: str) -> RuntimeRunRecord | None:
        """按幂等键返回更新时间最新的运行；无匹配时返回 ``None``。"""
        row = self._fetch_one(
            """
            SELECT payload FROM runs
            WHERE json_extract(payload, '$.idempotencyKey') = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (idempotency_key,),
        )
        if row is None:
            return None
        return RuntimeRunRecord.model_validate(json.loads(row["payload"]))

    def delete_run(self, run_id: str, *, delete_orphan_mission: bool = True) -> RuntimeRunRecordDeleteResult:
        """事务删除终态运行并可清理孤立任务。

        非终态运行拒绝删除；提交前验证不会留下缺失父任务的运行，任何异常都会使连接上下文回滚。
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT mission_id, payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"workflow run not found: {run_id}")
            mission_id = str(row["mission_id"])
            run = RuntimeRunRecord.model_validate(json.loads(row["payload"]))
            if run.status not in {
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED,
            }:
                raise RuntimeRunRecordNotTerminalError(run_id, run.status)
            conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_copilot_exchanges WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_planning_inputs WHERE run_id = ?", (run_id,))
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mission_revision_decisions'").fetchone():
                conn.execute("DELETE FROM mission_revision_decisions WHERE run_id = ?", (run_id,))
            mission_deleted = False
            if delete_orphan_mission:
                referenced = conn.execute(
                    "SELECT 1 FROM runs WHERE mission_id = ? LIMIT 1",
                    (mission_id,),
                ).fetchone()
                if referenced is None:
                    # Explicit same-database purge, not FK cascade or retention.
                    installed = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mission_semantic_schema'").fetchone()
                    if installed:
                        versions = conn.execute("SELECT version FROM mission_semantic_schema").fetchall()
                        if [row[0] for row in versions] != [1]:
                            raise RuntimeError("unsupported Mission semantic schema during purge")
                        for table in ("mission_semantic_outbox", "mission_semantic_receipts",
                                      "mission_semantic_commits", "mission_semantic_state"):
                            conn.execute(f"DELETE FROM {table} WHERE mission_id = ?", (mission_id,))
                    conn.execute("DELETE FROM task_copilot_permissions WHERE mission_id = ?", (mission_id,))
                    cursor = conn.execute("DELETE FROM tasks WHERE mission_id = ?", (mission_id,))
                    mission_deleted = cursor.rowcount > 0
            orphan_runs = conn.execute(
                """
                SELECT COUNT(*)
                FROM runs r
                LEFT JOIN tasks t ON t.mission_id = r.mission_id
                WHERE t.mission_id IS NULL
                """
            ).fetchone()[0]
            if int(orphan_runs) != 0:
                raise RuntimeError("workflow run deletion would leave missing task references")
            conn.commit()
        return RuntimeRunRecordDeleteResult(
            run_id=run_id,
            mission_id=mission_id,
            mission_deleted=mission_deleted,
        )

    def set_run_record_state(self, run_id: str, state: RunRecordState) -> RuntimeRunRecord:
        """在单事务中更新终态运行的用户管理状态；记录状态仅落 payload，随列表过滤。"""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"workflow run not found: {run_id}")
            run = RuntimeRunRecord.model_validate(json.loads(row["payload"]))
            if run.status not in {
                WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED, WorkflowStatus.SUPERSEDED,
            }:
                raise RuntimeRunRecordNotTerminalError(run_id, run.status)
            if run.record_state is RunRecordState.DELETED:
                raise ValueError("deleted run record state is immutable")
            now = utc_now()
            run.record_state = state
            run.updated_at = now
            run.deleted_at = now if state is RunRecordState.DELETED else None
            payload = json.dumps(run.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            conn.execute(
                "UPDATE runs SET payload = ?, updated_at = ?, record_state = ? WHERE run_id = ?",
                (payload, now.isoformat(), run.record_state.value, run_id),
            )
            conn.commit()
        return run

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS task_copilot_permissions (
                mission_id TEXT PRIMARY KEY, permission TEXT NOT NULL
                CHECK(permission IN ('read_only', 'task_collaboration')))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS run_planning_inputs (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                operation_id TEXT NOT NULL, payload TEXT NOT NULL,
                UNIQUE(run_id, operation_id))""")
            # Conversation bodies stay outside mutable execution snapshots.
            conn.execute("""CREATE TABLE IF NOT EXISTS run_copilot_exchanges (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                operation_id TEXT NOT NULL, payload TEXT NOT NULL,
                UNIQUE(run_id, operation_id))""")
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise RuntimeError(f"SQLite WAL mode is required, got: {journal_mode}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    mission_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT,
                    owner_user_id TEXT,
                    owner_tenant_id TEXT
                )
                """
            )
            run_columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            for column, column_type in (
                ("status", "TEXT"), ("owner_user_id", "TEXT"), ("owner_tenant_id", "TEXT"),
                ("domain", "TEXT"), ("workflow_id", "TEXT"), ("lifecycle_phase", "TEXT"),
                ("lifecycle_message", "TEXT"), ("source", "TEXT"), ("current_step_id", "TEXT"),
                ("started_at", "TEXT"), ("created_at", "TEXT"),
                ("runtime_revision", "INTEGER"), ("record_state", "TEXT"),
            ):
                if column not in run_columns:
                    conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {column_type}")
            conn.execute(
                """UPDATE runs
                   SET status = COALESCE(status, json_extract(payload, '$.status')),
                       owner_user_id = COALESCE(
                           owner_user_id,
                           NULLIF(json_extract(payload, '$.input.authenticatedUserId'), '')
                       ),
                       owner_tenant_id = COALESCE(
                           owner_tenant_id,
                           NULLIF(json_extract(payload, '$.input.authenticatedTenantId'), '')
                       )
                   WHERE status IS NULL"""
            )
            conn.execute(
                """UPDATE runs
                   SET record_state = COALESCE(json_extract(payload, '$.recordState'), 'active')
                   WHERE record_state IS NULL"""
            )
            self._backfill_run_summary_columns(conn)
            # Run payloads sit between the key columns and the summary
            # columns, so reading any tail column from the table b-tree walks
            # the row's overflow chain (tens of MB per heavy run). This
            # covering index serves list/overview queries entirely from index
            # pages and never touches payloads. record_state participates in
            # every list filter, so both indexes carry it; a definition change
            # rebuilds instead of silently keeping the stale shape.
            for index_name, index_sql in (
                (
                    "idx_runs_mission_updated_at",
                    """CREATE INDEX IF NOT EXISTS idx_runs_mission_updated_at
                       ON runs(mission_id, record_state, updated_at DESC, run_id DESC)""",
                ),
                (
                    "idx_runs_owner_overview",
                    """CREATE INDEX IF NOT EXISTS idx_runs_owner_overview
                       ON runs(owner_user_id, owner_tenant_id, record_state, updated_at DESC,
                               run_id DESC, mission_id, workflow_id, domain, status,
                               lifecycle_phase, lifecycle_message, source,
                               current_step_id, started_at, created_at,
                               runtime_revision)""",
                ),
            ):
                indexed = {
                    str(row[2])
                    for row in conn.execute(f"PRAGMA index_info({index_name})").fetchall()
                }
                if "record_state" not in indexed:
                    conn.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.execute(index_sql)
            conn.execute(
                """CREATE TABLE IF NOT EXISTS lifecycle_outbox (
                       event_id TEXT PRIMARY KEY,
                       event_type TEXT NOT NULL,
                       aggregate_id TEXT NOT NULL,
                       payload TEXT NOT NULL,
                       status TEXT NOT NULL DEFAULT 'pending',
                       attempts INTEGER NOT NULL DEFAULT 0,
                       last_error TEXT,
                       created_at TEXT NOT NULL
                   )"""
            )
            conn.commit()

    @staticmethod
    def _run_summary_values(run: RuntimeRunRecord) -> tuple:
        source_raw = run.input.get("source")
        return (
            run.domain,
            run.workflow_id,
            run.lifecycle_phase.value if run.lifecycle_phase is not None else None,
            run.lifecycle_message,
            str(source_raw) if source_raw not in (None, "") else None,
            run.current_step_id,
            run.started_at.isoformat() if run.started_at is not None else None,
            run.created_at.isoformat(),
            int(run.runtime_revision),
        )

    @staticmethod
    def _backfill_run_summary_columns(conn: sqlite3.Connection) -> None:
        """One-shot summary-column migration for rows written before they existed.

        ``domain`` is required on every RuntimeRunRecord, so ``domain IS NULL``
        marks rows that were never backfilled; the pass runs once per row and
        skips clean databases on restart. Payload dicts are read raw instead of
        going through pydantic so startup cost stays near a plain JSON parse.
        """
        pending = conn.execute(
            "SELECT run_id, payload FROM runs WHERE domain IS NULL"
        ).fetchall()
        for row in pending:
            data = json.loads(row[1])
            source_raw = (data.get("input") or {}).get("source")
            conn.execute(
                """UPDATE runs
                   SET domain = ?, workflow_id = ?, lifecycle_phase = ?, lifecycle_message = ?,
                       source = ?, current_step_id = ?, started_at = ?, created_at = ?,
                       runtime_revision = ?
                   WHERE run_id = ?""",
                (
                    str(data.get("domain") or ""),
                    str(data.get("workflowId") or ""),
                    data.get("lifecyclePhase") or None,
                    data.get("lifecycleMessage") or None,
                    str(source_raw) if source_raw not in (None, "") else None,
                    data.get("currentStepId") or None,
                    data.get("startedAt") or None,
                    str(data.get("createdAt") or ""),
                    int(data.get("runtimeRevision") or 0),
                    row[0],
                ),
            )

    @staticmethod
    def _append_outbox(
        conn: sqlite3.Connection,
        event_id: str,
        event_type: str,
        aggregate_id: str,
        payload: str,
    ) -> None:
        existing = conn.execute(
            "SELECT event_type, aggregate_id, payload FROM lifecycle_outbox WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if existing is not None:
            if tuple(str(item) for item in existing) != (event_type, aggregate_id, payload):
                raise ValueError(f"lifecycle event payload conflict: {event_id}")
            return
        conn.execute(
            """INSERT INTO lifecycle_outbox(
                   event_id, event_type, aggregate_id, payload, status, attempts, created_at
               ) VALUES (?, ?, ?, ?, 'pending', 0, datetime('now'))
               """,
            (event_id, event_type, aggregate_id, payload),
        )

    @staticmethod
    def _snapshot_event_id(event_type: str, aggregate_id: str, payload: str) -> str:
        canonical = json.dumps(
            json.loads(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{event_type}:{aggregate_id}:{digest}"

    def _execute(self, sql: str, params: tuple) -> None:
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def _fetch_one(self, sql: str, params: tuple):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def _fetch_all(self, sql: str, params: tuple = ()):
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=max(self.busy_timeout_ms, 1) / 1000)
        conn.execute(f"PRAGMA busy_timeout={max(self.busy_timeout_ms, 1)}")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def list_copilot_exchanges(self, run_id: str, *, limit: int = 30) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM run_copilot_exchanges WHERE run_id = ? "
                "ORDER BY sequence DESC LIMIT ?", (run_id, min(max(limit, 1), 100))).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def get_task_copilot_permission(self, mission_id: str) -> str:
        self.get_mission(mission_id)
        with self._connect() as conn:
            row = conn.execute("SELECT permission FROM task_copilot_permissions WHERE mission_id=?", (mission_id,)).fetchone()
        return row[0] if row else "task_collaboration"

    def set_task_copilot_permission(self, mission_id: str, permission: str) -> None:
        self.get_mission(mission_id)
        if permission not in {"read_only", "task_collaboration"}:
            raise ValueError("invalid task Copilot permission")
        with self._connect() as conn:
            conn.execute("INSERT INTO task_copilot_permissions(mission_id,permission) VALUES(?,?) "
                "ON CONFLICT(mission_id) DO UPDATE SET permission=excluded.permission", (mission_id, permission))

    def list_task_copilot_exchanges(self, mission_id: str, *, limit: int = 30) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT e.run_id,e.payload FROM run_copilot_exchanges e JOIN runs r ON r.run_id=e.run_id "
                "WHERE r.mission_id=? ORDER BY e.sequence DESC LIMIT ?", (mission_id, min(max(limit, 1), 100))).fetchall()
        return [{**json.loads(row[1]), "sourceRunId": row[0]} for row in reversed(rows)]

    def list_planning_inputs(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM run_planning_inputs WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_planning_input(self, run_id: str, operation_id: str, payload: dict) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM run_planning_inputs WHERE run_id=? AND operation_id=?", (run_id, operation_id)).fetchone()
            if row:
                if json.loads(row[0])["content"] != payload["content"]:
                    raise ValueError("planning input operation conflict")
                return
            if conn.execute("SELECT COUNT(*) FROM run_planning_inputs WHERE run_id=?", (run_id,)).fetchone()[0] >= 32:
                raise ValueError("planning input budget exhausted")
            conn.execute("INSERT INTO run_planning_inputs(run_id,operation_id,payload) VALUES(?,?,?)",
                (run_id, operation_id, json.dumps(payload, ensure_ascii=False)))

    def get_copilot_exchange(self, run_id: str, operation_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM run_copilot_exchanges WHERE run_id=? AND operation_id=?",
                (run_id, operation_id)).fetchone()
        return json.loads(row[0]) if row else None

    def save_copilot_exchange(self, run_id: str, operation_id: str, payload: dict) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO run_copilot_exchanges(run_id, operation_id, payload) VALUES(?, ?, ?)",
                (run_id, operation_id, json.dumps(payload, ensure_ascii=False)))

    def checkpoint(self) -> tuple[int, int, int]:
        """在维护操作前刷写已提交 WAL 页，返回 SQLite checkpoint 三元计数。"""
        with self._connect() as conn:
            row = conn.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            return tuple(int(value) for value in row)

    def backup_to(self, destination: str | Path) -> dict[str, int | str]:
        """创建并验证事务一致的 SQLite 备份。

        目标不得与源库相同；使用 SQLite 备份 API 后执行完整性校验，失败抛出 ``ValueError`` 或
        ``RuntimeError``，成功返回路径、完整性和记录数。
        """
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == self.db_path.resolve():
            raise ValueError("backup destination must differ from source database")
        with self._connect() as source, sqlite3.connect(target) as dest:
            source.backup(dest)
            dest.commit()
        with sqlite3.connect(target) as verify:
            integrity = str(verify.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity.lower() != "ok":
                raise RuntimeError(f"SQLite backup integrity check failed: {integrity}")
            task_count = int(verify.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
            run_count = int(verify.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        return {
            "source": str(self.db_path),
            "destination": str(target),
            "integrity": integrity,
            "taskCount": task_count,
            "runCount": run_count,
        }



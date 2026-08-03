"""AgentOS Core 的存储 sqlite_workflow_store 模块，管理任务和运行记录的持久化边界。"""


from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from agentos.core.models.types import AgentTask, StepStatus, WorkflowRun, WorkflowStatus
from agentos.stores.workflow_store import (
    WorkflowRunDeleteResult,
    WorkflowRunNotTerminalError,
    WorkflowStore,
    WorkflowStorePage,
    paginate_items,
    status_value,
    status_values,
    workflow_run_summary,
)


class SQLiteWorkflowStore(WorkflowStore):
    """基于 SQLite 的本地持久化 WorkflowStore。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.busy_timeout_ms = int(os.getenv("AGENTOS_SQLITE_BUSY_TIMEOUT_MS", "5000"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def save_task(self, task: AgentTask) -> None:
        self._execute(
            """
            INSERT INTO tasks(task_id, payload, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                payload=excluded.payload,
                updated_at=excluded.updated_at
            """,
            (task.task_id, json.dumps(task.model_dump(by_alias=True, mode="json"), ensure_ascii=False), task.updated_at.isoformat()),
        )

    def get_task(self, task_id: str) -> AgentTask:
        row = self._fetch_one("SELECT payload FROM tasks WHERE task_id = ?", (task_id,))
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        return AgentTask.model_validate(json.loads(row["payload"]))

    def save_run(self, run: WorkflowRun) -> None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            task_row = conn.execute(
                "SELECT payload FROM tasks WHERE task_id = ?", (run.task_id,)
            ).fetchone()
            if task_row is None:
                raise ValueError(f"workflow run task does not exist: {run.task_id}")
            row = conn.execute(
                "SELECT task_id, payload FROM runs WHERE run_id = ?", (run.run_id,)
            ).fetchone()
            if row is not None:
                if str(row["task_id"]) != run.task_id:
                    raise ValueError(
                        f"workflow run taskId cannot change: {run.run_id}"
                    )
                existing = WorkflowRun.model_validate(json.loads(row["payload"]))
                if _reject_terminal_overwrite(existing, run):
                    return
            _validate_obvious_run_state_conflicts(run)
            task = AgentTask.model_validate(json.loads(task_row["payload"]))
            projection = _run_projection(run, title=task.title)
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, task_id, payload, updated_at, status, domain, workflow_id,
                    lifecycle_phase, source, owner_user_id, owner_tenant_id, summary_payload
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    task_id=excluded.task_id,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    domain=excluded.domain,
                    workflow_id=excluded.workflow_id,
                    lifecycle_phase=excluded.lifecycle_phase,
                    source=excluded.source,
                    owner_user_id=excluded.owner_user_id,
                    owner_tenant_id=excluded.owner_tenant_id,
                    summary_payload=excluded.summary_payload
                """,
                (
                    run.run_id,
                    run.task_id,
                    json.dumps(run.model_dump(by_alias=True, mode="json"), ensure_ascii=False),
                    run.updated_at.isoformat(),
                    *projection,
                ),
            )
            conn.execute(
                """
                INSERT INTO run_summaries(
                    run_id, task_id, updated_at, status, domain, workflow_id,
                    lifecycle_phase, source, owner_user_id, owner_tenant_id, payload
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    task_id=excluded.task_id,
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    domain=excluded.domain,
                    workflow_id=excluded.workflow_id,
                    lifecycle_phase=excluded.lifecycle_phase,
                    source=excluded.source,
                    owner_user_id=excluded.owner_user_id,
                    owner_tenant_id=excluded.owner_tenant_id,
                    payload=excluded.payload
                """,
                (run.run_id, run.task_id, run.updated_at.isoformat(), *projection),
            )
            conn.commit()

    def get_run(self, run_id: str) -> WorkflowRun:
        row = self._fetch_one("SELECT payload FROM runs WHERE run_id = ?", (run_id,))
        if row is None:
            raise KeyError(f"workflow run not found: {run_id}")
        return WorkflowRun.model_validate(json.loads(row["payload"]))

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
        rows = self._fetch_all("SELECT payload FROM tasks")
        tasks = [
            task
            for task in (AgentTask.model_validate(json.loads(row["payload"])) for row in rows)
            if _matches_task(task, status=expected_status, domain=domain, source=source)
        ]
        tasks.sort(key=lambda task: (task.created_at, task.task_id), reverse=True)
        return paginate_items(tasks, page=page, page_size=page_size)

    def list_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses=None,
        domain: str | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources=None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[WorkflowRun]:
        where_sql, params, priority_sql = _run_filter_query(
            status=status,
            statuses=statuses,
            domain=domain,
            workflow_id=workflow_id,
            task_id=task_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            sources=sources,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
        )
        total_row = self._fetch_one(f"SELECT COUNT(*) AS total FROM runs{where_sql}", tuple(params))
        safe_page = max(1, page)
        safe_page_size = max(1, page_size)
        offset = (safe_page - 1) * safe_page_size
        rows = self._fetch_all(
            f"SELECT payload FROM runs{where_sql} "
            f"ORDER BY {priority_sql}updated_at DESC, run_id DESC LIMIT ? OFFSET ?",
            tuple([*params, safe_page_size, offset]),
        )
        return WorkflowStorePage(
            items=tuple(WorkflowRun.model_validate(json.loads(row["payload"])) for row in rows),
            total=int(total_row["total"]) if total_row is not None else 0,
            page=safe_page,
            page_size=safe_page_size,
        )

    def list_run_summaries(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        statuses=None,
        domain: str | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        lifecycle_phase: str | None = None,
        source: str | None = None,
        sources=None,
        owner_user_id: str | None = None,
        owner_tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> WorkflowStorePage[dict[str, Any]]:
        where_sql, params, priority_sql = _run_filter_query(
            status=status,
            statuses=statuses,
            domain=domain,
            workflow_id=workflow_id,
            task_id=task_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            sources=sources,
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
        )
        total_row = self._fetch_one(f"SELECT COUNT(*) AS total FROM run_summaries{where_sql}", tuple(params))
        safe_page = max(1, page)
        safe_page_size = max(1, page_size)
        offset = (safe_page - 1) * safe_page_size
        rows = self._fetch_all(
            f"SELECT payload FROM run_summaries{where_sql} "
            f"ORDER BY {priority_sql}updated_at DESC, run_id DESC LIMIT ? OFFSET ?",
            tuple([*params, safe_page_size, offset]),
        )
        return WorkflowStorePage(
            items=tuple(json.loads(row["payload"]) for row in rows),
            total=int(total_row["total"]) if total_row is not None else 0,
            page=safe_page,
            page_size=safe_page_size,
        )

    def list_non_terminal_runs(self, *, limit: int = 200) -> tuple[WorkflowRun, ...]:
        safe_limit = max(1, limit)
        rows = self._fetch_all(
            """
            SELECT payload FROM runs
            WHERE status NOT IN (?, ?, ?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (
                WorkflowStatus.COMPLETED.value,
                WorkflowStatus.FAILED.value,
                WorkflowStatus.CANCELLED.value,
                safe_limit,
            ),
        )
        return tuple(
            WorkflowRun.model_validate(json.loads(row["payload"])) for row in rows
        )

    def find_run_by_idempotency_key(self, idempotency_key: str) -> WorkflowRun | None:
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
        return WorkflowRun.model_validate(json.loads(row["payload"]))

    def delete_run(self, run_id: str, *, delete_orphan_task: bool = True) -> WorkflowRunDeleteResult:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT task_id, payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"workflow run not found: {run_id}")
            task_id = str(row["task_id"])
            run = WorkflowRun.model_validate(json.loads(row["payload"]))
            if run.status not in {
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED,
            }:
                raise WorkflowRunNotTerminalError(run_id, run.status)
            conn.execute("DELETE FROM run_summaries WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            task_deleted = False
            if delete_orphan_task:
                referenced = conn.execute(
                    "SELECT 1 FROM runs WHERE task_id = ? LIMIT 1",
                    (task_id,),
                ).fetchone()
                if referenced is None:
                    cursor = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                    task_deleted = cursor.rowcount > 0
            orphan_runs = conn.execute(
                """
                SELECT COUNT(*)
                FROM runs r
                LEFT JOIN tasks t ON t.task_id = r.task_id
                WHERE t.task_id IS NULL
                """
            ).fetchone()[0]
            if int(orphan_runs) != 0:
                raise RuntimeError("workflow run deletion would leave missing task references")
            conn.commit()
        return WorkflowRunDeleteResult(
            run_id=run_id,
            task_id=task_id,
            task_deleted=task_deleted,
        )

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise RuntimeError(f"SQLite WAL mode is required, got: {journal_mode}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_run_projection_schema(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_summaries (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT,
                    domain TEXT,
                    workflow_id TEXT,
                    lifecycle_phase TEXT,
                    source TEXT,
                    owner_user_id TEXT,
                    owner_tenant_id TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO run_summaries(
                    run_id, task_id, updated_at, status, domain, workflow_id,
                    lifecycle_phase, source, owner_user_id, owner_tenant_id, payload
                )
                SELECT
                    run_id, task_id, updated_at, status, domain, workflow_id,
                    lifecycle_phase, source, owner_user_id, owner_tenant_id, summary_payload
                FROM runs
                WHERE summary_payload IS NOT NULL
                ON CONFLICT(run_id) DO UPDATE SET
                    task_id=excluded.task_id,
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    domain=excluded.domain,
                    workflow_id=excluded.workflow_id,
                    lifecycle_phase=excluded.lifecycle_phase,
                    source=excluded.source,
                    owner_user_id=excluded.owner_user_id,
                    owner_tenant_id=excluded.owner_tenant_id,
                    payload=excluded.payload
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC)")
            conn.execute("DROP INDEX IF EXISTS idx_runs_source_updated")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_source_updated "
                "ON runs(source, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_status_updated "
                "ON runs(status, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_summaries_source_updated "
                "ON run_summaries(source, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_summaries_status_updated "
                "ON run_summaries(status, updated_at DESC)"
            )
            conn.commit()

    def _ensure_run_projection_schema(self, conn: sqlite3.Connection) -> None:
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        projection_columns = {
            "status": "TEXT",
            "domain": "TEXT",
            "workflow_id": "TEXT",
            "lifecycle_phase": "TEXT",
            "source": "TEXT",
            "owner_user_id": "TEXT",
            "owner_tenant_id": "TEXT",
            "summary_payload": "TEXT",
        }
        for name, sql_type in projection_columns.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {sql_type}")

        stale_rows = conn.execute(
            "SELECT run_id, payload FROM runs WHERE summary_payload IS NULL"
        ).fetchall()
        if not stale_rows:
            return
        task_titles: dict[str, str | None] = {}
        for row in conn.execute("SELECT task_id, payload FROM tasks").fetchall():
            try:
                task_titles[str(row["task_id"])] = AgentTask.model_validate(
                    json.loads(row["payload"])
                ).title
            except (TypeError, ValueError):
                task_titles[str(row["task_id"])] = None
        for row in stale_rows:
            run = WorkflowRun.model_validate(json.loads(row["payload"]))
            projection = _run_projection(run, title=task_titles.get(run.task_id))
            conn.execute(
                """
                UPDATE runs SET
                    status = ?, domain = ?, workflow_id = ?, lifecycle_phase = ?,
                    source = ?, owner_user_id = ?, owner_tenant_id = ?, summary_payload = ?
                WHERE run_id = ?
                """,
                (*projection, run.run_id),
            )

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

    def checkpoint(self) -> tuple[int, int, int]:
        """Flush committed WAL pages before maintenance operations."""
        with self._connect() as conn:
            row = conn.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
            return tuple(int(value) for value in row)

    def backup_to(self, destination: str | Path) -> dict[str, int | str]:
        """Create and verify a transactionally consistent SQLite backup."""
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
    statuses: set[str] | None,
    domain: str | None,
    workflow_id: str | None,
    task_id: str | None,
    lifecycle_phase: str | None,
    source: str | None,
    sources: set[str] | None,
    owner_user_id: str | None,
    owner_tenant_id: str | None,
) -> bool:
    if status is not None and run.status.value != status:
        return False
    if statuses is not None and run.status.value not in statuses:
        return False
    if domain is not None and run.domain != domain:
        return False
    if workflow_id is not None and run.workflow_id != workflow_id:
        return False
    if task_id is not None and run.task_id != task_id:
        return False
    phase = run.lifecycle_phase.value if run.lifecycle_phase is not None else None
    if lifecycle_phase is not None and phase != lifecycle_phase:
        return False
    if source is not None and run.input.get("source") != source:
        return False
    if sources is not None and run.input.get("source") not in sources:
        return False
    run_owner = str(run.input.get("authenticatedUserId") or "").strip()
    run_tenant = str(run.input.get("authenticatedTenantId") or "").strip()
    if owner_user_id is not None and run_owner and run_owner != owner_user_id:
        return False
    if owner_tenant_id is not None and run_tenant and run_tenant != owner_tenant_id:
        return False
    return True


def _run_projection(run: WorkflowRun, *, title: str | None) -> tuple[object, ...]:
    phase = run.lifecycle_phase.value if run.lifecycle_phase is not None else None
    source = run.input.get("source")
    owner_user_id = str(run.input.get("authenticatedUserId") or "").strip() or None
    owner_tenant_id = str(run.input.get("authenticatedTenantId") or "").strip() or None
    summary_payload = json.dumps(
        workflow_run_summary(run, title=title),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        run.status.value,
        run.domain,
        run.workflow_id,
        phase,
        str(source) if source is not None else None,
        owner_user_id,
        owner_tenant_id,
        summary_payload,
    )


def _run_filter_query(
    *,
    status: WorkflowStatus | str | None,
    statuses,
    domain: str | None,
    workflow_id: str | None,
    task_id: str | None,
    lifecycle_phase: str | None,
    source: str | None,
    sources,
    owner_user_id: str | None,
    owner_tenant_id: str | None,
) -> tuple[str, list[object], str]:
    expected_status = status_value(status)
    expected_statuses = status_values(statuses)
    expected_sources = {str(item) for item in sources or [] if str(item)} or None
    clauses: list[str] = []
    params: list[object] = []

    def equals(column: str, value: str | None) -> None:
        if value is None:
            return
        clauses.append(f"{column} = ?")
        params.append(value)

    equals("status", expected_status)
    if expected_statuses:
        placeholders = ", ".join("?" for _ in expected_statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(sorted(expected_statuses))
    equals("domain", domain)
    equals("workflow_id", workflow_id)
    equals("task_id", task_id)
    equals("lifecycle_phase", lifecycle_phase)
    equals("source", source)
    if expected_sources:
        placeholders = ", ".join("?" for _ in expected_sources)
        clauses.append(f"source IN ({placeholders})")
        params.extend(sorted(expected_sources))
    if owner_user_id is not None:
        clauses.append("(owner_user_id IS NULL OR owner_user_id = '' OR owner_user_id = ?)")
        params.append(owner_user_id)
    if owner_tenant_id is not None:
        clauses.append("(owner_tenant_id IS NULL OR owner_tenant_id = '' OR owner_tenant_id = ?)")
        params.append(owner_tenant_id)

    priority_sql = ""
    if expected_statuses:
        priority_sql = (
            "CASE "
            "WHEN status = 'waiting_review' THEN 2 "
            "WHEN status NOT IN ('completed', 'failed', 'cancelled') THEN 1 "
            "ELSE 0 END DESC, "
        )
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params, priority_sql


def _validate_obvious_run_state_conflicts(run: WorkflowRun) -> None:
    statuses = {step.status for step in run.steps}
    if run.runtime_graph is not None:
        statuses.update(node.status for node in run.runtime_graph.nodes)

    if run.status == WorkflowStatus.COMPLETED:
        conflicts = {
            StepStatus.RUNNING,
            StepStatus.RETRYING,
            StepStatus.WAITING_REVIEW,
        }
        if statuses & conflicts:
            raise ValueError(
                f"completed workflow run has active or review steps: {run.run_id}"
            )
    elif run.status == WorkflowStatus.FAILED:
        if statuses & {StepStatus.RUNNING, StepStatus.RETRYING}:
            raise ValueError(f"failed workflow run has active steps: {run.run_id}")
    elif run.status == WorkflowStatus.WAITING_REVIEW:
        if StepStatus.WAITING_REVIEW not in statuses:
            raise ValueError(
                f"waiting_review workflow run has no waiting_review step: {run.run_id}"
            )


def _run_priority(run: WorkflowRun) -> int:
    if run.status == WorkflowStatus.WAITING_REVIEW:
        return 2
    if run.status not in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}:
        return 1
    return 0


def _reject_terminal_overwrite(existing: WorkflowRun, incoming: WorkflowRun) -> bool:
    terminal = {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }
    if existing.status == WorkflowStatus.FAILED and incoming.status == WorkflowStatus.RETRYING:
        return False
    if existing.status in terminal and incoming.status != existing.status:
        return True
    return existing.status in terminal and incoming.updated_at < existing.updated_at

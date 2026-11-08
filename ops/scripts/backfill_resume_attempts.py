"""一次性回填脚本：为断点恢复（successor_run）复用的步骤补建 Identity Attempt 投影。

背景（2026-09-19 排查结论）：继任 Run 断点恢复复用源 Run 已完成步骤的输出但不重新
调度它们，Identity 侧永远没有对应 Attempt，Workspace 把已产出结果的任务显示为
Pending · Attempt 0。根治代码在 apps/agentOS/src/runtime/workflow_runtime.py
（prepare_single_step_retry 经 runtime/v2/resume_projection.py 补投影，随恢复落地
同步发生）；本脚本与之共享同一事件构建函数，只处理根治代码部署前的终态历史 run
（受害范围盘点：177 个 run 中仅 run_8a53fc4c67e5）。

与运行时路径的差异：回填对象是终态历史 run，execution_state_updates 不写回；
绑定只查直接源 run（与运行时语义一致，不做恢复链上溯——根治代码部署后链式
恢复的中间 run 自带复用账目，本工具不应再有用武之地）。

幂等性：attempt/step_execution ID 由 sha256(run:step) 确定性派生，重复执行时
INSERT OR IGNORE 命中既有行直接跳过；已有 Attempt 的任务整步跳过。

用法（本地 N03，先停止对应环境）：
python ops/scripts/backfill_resume_attempts.py --data-dir <home>/data [--apply]
使用 workflows.sqlite3、identity.sqlite3、content.sqlite3，必须显式选择目录。
不带 --apply 只做盘点与校验，不写库。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/agentOS/src"))


def digest_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="停止后的 N03 home/data 目录")
    parser.add_argument("--apply", action="store_true", help="实际写入；缺省为预览")
    args = parser.parse_args()
    WORKFLOW_DB = args.data_dir / "workflows.sqlite3"
    IDENTITY_DB = args.data_dir / "identity.sqlite3"
    MANIFEST_DB = args.data_dir / "content.sqlite3"
    APPLY = args.apply
    for database in (WORKFLOW_DB, IDENTITY_DB, MANIFEST_DB):
        if not database.is_file():
            print(f"缺少数据库文件: {database}", file=sys.stderr)
            return 2

    from components.content import SQLiteContentManifestStore
    from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge
    from runtime.reconciliation import IdentityProjectionReconciler
    from runtime.resume_projection import build_reused_step_projection_events
    from support.stores.sqlite_workflow_store import SQLiteWorkflowStore

    store = SQLiteWorkflowStore(WORKFLOW_DB)
    service = AcgIdentityLifecycleService.from_sqlite(IDENTITY_DB)
    bridge = IdentityProjectionBridge(
        service, service.repositories, SQLiteContentManifestStore(MANIFEST_DB)
    )
    stats = store.outbox_stats()
    if stats["backlog"]:
        print(f"ABORT: outbox backlog is {stats['backlog']}, expect 0 before repair")
        return 2

    # 盘点：checkpointResume.mode == successor_run 的 run 即候选受害 run。
    with sqlite3.connect(f"file:{WORKFLOW_DB}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT run_id, payload FROM runs").fetchall()
    candidates = []
    for row in rows:
        payload = json.loads(row["payload"])
        resume = (payload.get("executionState") or {}).get("checkpointResume")
        if isinstance(resume, dict) and resume.get("mode") == "successor_run":
            candidates.append((row["run_id"], resume))

    repaired_steps = 0
    for run_id, resume in candidates:
        runtime_run = store.get_run(run_id)
        source_run = store.get_run(str(resume.get("sourceRunId")))
        reused = sorted(resume.get("reusedStepIds") or [])
        print(f"== {run_id} (source={source_run.run_id}) reused={len(reused)}")
        pending_steps = []
        for step_id in reused:
            domain_run = bridge.repositories.runs.get(run_id)
            task = bridge._resolve_semantic_task(domain_run.blueprint_id, step_id)
            existing = [
                attempt for attempt in bridge.repositories.attempts.list_for_run(run_id)
                if attempt.task_id == task.task_id
            ]
            if existing:
                print(f"   skip {step_id}: task {task.task_id} already has {len(existing)} attempt(s)")
                continue
            pending_steps.append(step_id)
        if not pending_steps:
            continue

        source_counters = {}
        for step_id in pending_steps:
            source_step = source_run.get_step(step_id)
            source_counters[step_id] = (
                int(source_step.attempt or 0),
                int(source_step.retry_count or 0),
            )
        output_refs = (runtime_run.execution_state or {}).get("outputRefs") or {}
        output_summaries = (runtime_run.execution_state or {}).get("outputSummaries") or {}
        try:
            events, _state_updates = build_reused_step_projection_events(
                run_id=run_id,
                mission_id=runtime_run.mission_id,
                reused_step_ids=pending_steps,
                copied_refs=output_refs,
                copied_summaries=output_summaries,
                source_run_id=source_run.run_id,
                source_execution_state=source_run.execution_state or {},
                source_step_counters=source_counters,
                attempt_id_for=lambda step_id: digest_id("attempt", "backfill", run_id, step_id),
                step_execution_id_for=lambda step_id: digest_id("step_execution", "backfill", run_id, step_id),
            )
        except ValueError as exc:
            print(f"   ABORT: {exc}")
            return 3
        for step_id in pending_steps:
            print(f"   backfill {step_id} -> {digest_id('attempt', 'backfill', run_id, step_id)}")
        repaired_steps += len(pending_steps)

        if not APPLY:
            print(f"   dry-run: {len(events)} events pending (use --apply)")
            continue
        conn = sqlite3.connect(WORKFLOW_DB, timeout=15)
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            for event in events:
                conn.execute(
                    """INSERT OR IGNORE INTO lifecycle_outbox(
                           event_id, event_type, aggregate_id, payload, status, attempts, created_at
                       ) VALUES (?, ?, ?, ?, 'pending', 0, datetime('now'))""",
                    (event["eventId"], event["eventType"], event["aggregateId"],
                     json.dumps(event["payload"], ensure_ascii=False, sort_keys=True)),
                )
            conn.commit()
        finally:
            conn.close()
        report = IdentityProjectionReconciler(bridge).reconcile_workflow_store(store, limit=200)
        print(f"   reconciled: applied={report.replayed_events} failures={report.failures}")
        if report.failures:
            print("ABORT: reconciliation reported failures")
            return 5

    # 终验：每个候选 run 的复用步骤都必须有且仅有补投影/既有的 succeeded Attempt。
    for run_id, resume in candidates:
        domain_run = bridge.repositories.runs.get(run_id)
        missing = []
        for step_id in sorted(resume.get("reusedStepIds") or []):
            task = bridge._resolve_semantic_task(domain_run.blueprint_id, step_id)
            attempts = [
                attempt for attempt in bridge.repositories.attempts.list_for_run(run_id)
                if attempt.task_id == task.task_id
            ]
            if not attempts:
                missing.append(step_id)
        print(f"verify {run_id}: {'OK' if not missing else 'MISSING ' + ','.join(missing)}")
    service.close()
    print(f"done: {repaired_steps} step(s) backfilled, apply={APPLY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

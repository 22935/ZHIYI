"""Contract tests shared by in-memory and SQLite workflow stores."""

from datetime import timedelta
from pathlib import Path
import sqlite3

import pytest

from contracts.workflow import (
    MissionRecordState,
    RunRecordState,
    RuntimeMissionRecord,
    RuntimeRunRecord,
    WorkflowProgressPhase,
    WorkflowStatus,
    utc_now,
)
from support.stores.workflow_store import RuntimeRunRecordNotTerminalError
from support.stores.memory_workflow_store import MemoryWorkflowStore
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore


@pytest.mark.parametrize("store_factory", [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "launch.db")])
def test_creation_key_lookup_reads_the_original_anchor_without_mutating_it(store_factory, tmp_path):
    store = store_factory(tmp_path)
    assert store.find_mission_by_creation_key("missing") is None
    mission = RuntimeMissionRecord(title="original", creationKey="launch-key", creationFingerprint="fingerprint")
    store.create_mission_once(mission)
    restored = store.find_mission_by_creation_key("launch-key")
    assert restored.mission_id == mission.mission_id
    restored.title = "caller changed a returned copy"
    assert store.get_mission(mission.mission_id).title == "original"


@pytest.mark.parametrize(
    "store_factory",
    [
        lambda _: MemoryWorkflowStore(),
        lambda path: SQLiteWorkflowStore(path / "workflow.db"),
    ],
)
def test_store_rejects_run_without_saved_parent_task(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    run = RuntimeRunRecord(
        missionId="mission_000000000003",
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
    )

    with pytest.raises(ValueError, match="workflow run task does not exist"):
        store.save_run(run)


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_deferred_planning_placeholder_is_persisted_without_prepared_identity_event(
    store_factory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_deferred", title="Deferred mission")
    store.save_mission(mission)
    run = RuntimeRunRecord(
        runId="run_deferred",
        missionId=mission.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
        executionState={"planningDeferred": True},
    )

    store.save_run(run)

    assert store.get_run(run.run_id).execution_state["planningDeferred"] is True
    assert not any(
        event["aggregate_id"] == run.run_id
        for event in store.list_outbox()
    )


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_mission_record_state_covers_all_runs_without_deleting_history(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_000000000004", title="Mission")
    store.save_mission(mission)
    for run_id in ("run_000000000004", "run_000000000005"):
        store.save_run(RuntimeRunRecord(
            runId=run_id, missionId=mission.mission_id, workflowId="workflow-1",
            domain="general", runtimeEngine="acg", status=WorkflowStatus.COMPLETED,
        ))

    archived, affected = store.set_mission_record_state(mission.mission_id, MissionRecordState.ARCHIVED)
    assert archived.record_state is MissionRecordState.ARCHIVED
    assert affected == 2
    assert store.list_runs(mission_record_state=MissionRecordState.ACTIVE).total == 0
    assert store.list_runs(mission_record_state=MissionRecordState.ARCHIVED).total == 2
    assert len(store.list_all_runs()) == 2

    restored, _ = store.set_mission_record_state(mission.mission_id, MissionRecordState.ACTIVE)
    assert restored.record_state is MissionRecordState.ACTIVE
    deleted, _ = store.set_mission_record_state(mission.mission_id, MissionRecordState.DELETED)
    assert deleted.record_state is MissionRecordState.DELETED
    assert store.list_runs(mission_record_state=MissionRecordState.ACTIVE).total == 0
    assert len(store.list_all_runs()) == 2
    with pytest.raises(ValueError, match="immutable"):
        store.set_mission_record_state(mission.mission_id, MissionRecordState.ACTIVE)


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_mission_record_state_rejects_active_runs(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_000000000006", title="Mission")
    store.save_mission(mission)
    store.save_run(RuntimeRunRecord(
        runId="run_000000000006", missionId=mission.mission_id, workflowId="workflow-1",
        domain="general", runtimeEngine="acg", status=WorkflowStatus.RUNNING,
    ))
    with pytest.raises(RuntimeRunRecordNotTerminalError):
        store.set_mission_record_state(mission.mission_id, MissionRecordState.ARCHIVED)
    assert store.get_mission(mission.mission_id).record_state is MissionRecordState.ACTIVE


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_run_record_state_soft_delete_hides_run_from_lists(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_run_delete", title="Mission")
    store.save_mission(mission)
    kept = RuntimeRunRecord(
        runId="run_delete_kept", missionId=mission.mission_id, workflowId="workflow-1",
        domain="general", runtimeEngine="acg", status=WorkflowStatus.COMPLETED,
    )
    removed = kept.model_copy(update={"run_id": "run_delete_removed"})
    running = kept.model_copy(update={"run_id": "run_delete_running", "status": WorkflowStatus.RUNNING})
    superseded = kept.model_copy(update={"run_id": "run_delete_superseded", "status": WorkflowStatus.SUPERSEDED})
    for run in (kept, removed, running, superseded):
        store.save_run(run)

    deleted = store.set_run_record_state(removed.run_id, RunRecordState.DELETED)
    assert deleted.record_state is RunRecordState.DELETED
    assert deleted.deleted_at is not None
    # 直达读取保留历史；列表与 Mission 汇总不再出现。
    assert store.get_run(removed.run_id).record_state is RunRecordState.DELETED
    assert [item.run_id for item in store.list_runs(page_size=10).items] == [
        "run_delete_superseded", "run_delete_running", "run_delete_kept",
    ]
    assert [item.run_id for item in store.list_run_overviews(page_size=10).items] == [
        "run_delete_superseded", "run_delete_running", "run_delete_kept",
    ]
    assert len(store.list_all_runs()) == 4
    summaries = store.list_mission_run_summaries([mission.mission_id])
    assert summaries[mission.mission_id].run_count == 3
    assert summaries[mission.mission_id].latest_run is not None
    assert summaries[mission.mission_id].latest_run.run_id == "run_delete_superseded"

    # 已删记录状态不可再变更；重复删除按同一不变量拒绝（API 层收敛为幂等）。
    with pytest.raises(ValueError, match="immutable"):
        store.set_run_record_state(removed.run_id, RunRecordState.DELETED)

    # 非终态 Run 拒绝删除；SUPERSEDED 属终态，允许软删。
    with pytest.raises(RuntimeRunRecordNotTerminalError):
        store.set_run_record_state(running.run_id, RunRecordState.DELETED)
    store.set_run_record_state(superseded.run_id, RunRecordState.DELETED)
    assert [item.run_id for item in store.list_run_overviews(page_size=10).items] == [
        "run_delete_running", "run_delete_kept",
    ]


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_batch_mission_summary_preserves_latest_count_and_visibility(
    store_factory,
    tmp_path: Path,
) -> None:
    store = store_factory(tmp_path)
    active = RuntimeMissionRecord(missionId="mission_batch_active", title="Active")
    archived = RuntimeMissionRecord(missionId="mission_batch_archived", title="Archived")
    store.save_mission(active)
    store.save_mission(archived)
    store.set_mission_record_state(archived.mission_id, MissionRecordState.ARCHIVED)

    now = utc_now()
    older = RuntimeRunRecord(
        runId="run_batch_older",
        missionId=active.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
        input={
            "authenticatedUserId": "user-a",
            "authenticatedTenantId": "tenant-a",
        },
        updatedAt=now,
    )
    newer = older.model_copy(
        update={
            "run_id": "run_batch_newer",
            "updated_at": now + timedelta(seconds=1),
        }
    )
    other_owner = older.model_copy(
        update={
            "run_id": "run_batch_other_owner",
            "input": {
                "authenticatedUserId": "user-b",
                "authenticatedTenantId": "tenant-a",
            },
        }
    )
    store.save_run(older)
    store.save_run(newer)
    store.save_run(other_owner)

    assert store.list_mission_ids(mission_record_state=MissionRecordState.ACTIVE) == {
        active.mission_id
    }
    summaries = store.list_mission_run_summaries(
        [active.mission_id, archived.mission_id],
        mission_record_state=MissionRecordState.ACTIVE,
        owner_user_id="user-a",
        owner_tenant_id="tenant-a",
    )

    assert summaries[active.mission_id].run_count == 2
    assert summaries[active.mission_id].latest_run is not None
    assert summaries[active.mission_id].latest_run.run_id == newer.run_id
    assert archived.mission_id not in summaries


def test_sqlite_mission_summary_does_not_deserialize_run_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "workflow.db"
    store = SQLiteWorkflowStore(db_path)
    mission = RuntimeMissionRecord(missionId="mission_summary_projection", title="Mission")
    store.save_mission(mission)
    run = RuntimeRunRecord(
        runId="run_summary_projection",
        missionId=mission.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
        status=WorkflowStatus.COMPLETED,
        input={"authenticatedUserId": "user-a"},
    )
    store.save_run(run)

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE runs SET payload = 'not-list-readable' WHERE run_id = ?", (run.run_id,))
        conn.commit()

    summaries = store.list_mission_run_summaries(
        [mission.mission_id],
        mission_record_state=MissionRecordState.ACTIVE,
        owner_user_id="user-a",
    )

    summary = summaries[mission.mission_id]
    assert summary.run_count == 1
    assert summary.latest_run is not None
    assert summary.latest_run.run_id == run.run_id
    assert summary.latest_run.status is WorkflowStatus.COMPLETED


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_list_runs_filter_matrix_matches_owner_scope_and_pagination(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    active = RuntimeMissionRecord(missionId="mission_matrix_active", title="Active mission")
    deleted = RuntimeMissionRecord(missionId="mission_matrix_deleted", title="Deleted mission")
    store.save_mission(active)
    store.save_mission(deleted)
    store.set_mission_record_state(deleted.mission_id, MissionRecordState.DELETED)

    base = utc_now()
    seed = dict(
        missionId=active.mission_id, workflowId="wf-1", domain="general", runtimeEngine="acg",
    )

    def run(run_id: str, **overrides) -> RuntimeRunRecord:
        defaults = dict(
            input={"authenticatedUserId": "user-a", "authenticatedTenantId": "tenant-a"}
        )
        return RuntimeRunRecord(runId=run_id, **{**seed, **defaults, **overrides})

    store.save_run(run("run_owner_completed", status=WorkflowStatus.COMPLETED, updatedAt=base))
    store.save_run(run(
        "run_owner_running", status=WorkflowStatus.RUNNING,
        updatedAt=base + timedelta(seconds=30),
    ))
    store.save_run(run(
        "run_owner_retrying", status=WorkflowStatus.RETRYING, updatedAt=base + timedelta(seconds=10),
    ))
    store.save_run(run(
        "run_other_owner", status=WorkflowStatus.FAILED,
        input={"authenticatedUserId": "user-b", "authenticatedTenantId": "tenant-a"},
        updatedAt=base + timedelta(seconds=20),
    ))
    store.save_run(run(
        "run_owner_other_tenant", status=WorkflowStatus.FAILED,
        input={"authenticatedUserId": "user-a", "authenticatedTenantId": "tenant-b"},
        updatedAt=base + timedelta(seconds=25),
    ))
    store.save_run(run(
        "run_deleted_mission", missionId=deleted.mission_id, status=WorkflowStatus.COMPLETED,
        input={"authenticatedUserId": "user-a"},
        updatedAt=base + timedelta(seconds=40),
    ))
    store.save_run(run(
        "run_chat_source", status=WorkflowStatus.COMPLETED,
        input={"source": "chat"}, updatedAt=base + timedelta(seconds=50),
    ))
    store.save_run(run(
        "run_legal_domain", status=WorkflowStatus.COMPLETED, domain="legal", input={},
        updatedAt=base + timedelta(seconds=60),
    ))

    owner_page = store.list_runs(
        mission_record_state=MissionRecordState.ACTIVE,
        owner_user_id="user-a",
        owner_tenant_id="tenant-a",
        page=1,
        page_size=10,
    )
    assert owner_page.total == 5
    assert [item.run_id for item in owner_page.items] == [
        # updated_at 降序；其他 owner / 异 tenant / deleted mission 均不可见。
        "run_legal_domain", "run_chat_source", "run_owner_running",
        "run_owner_retrying", "run_owner_completed",
    ]

    statuses_page = store.list_runs(
        statuses=["completed", "retrying"],
        mission_record_state=MissionRecordState.ACTIVE,
        owner_user_id="user-a",
        owner_tenant_id="tenant-a",
        page=1,
        page_size=10,
    )
    assert [item.run_id for item in statuses_page.items] == [
        # 多状态模式下非终态优先于终态，同级按更新时间降序。
        "run_owner_retrying", "run_legal_domain", "run_chat_source", "run_owner_completed",
    ]

    scoped = dict(owner_user_id="user-a", owner_tenant_id="tenant-a")
    assert [item.run_id for item in store.list_runs(
        source="chat", page_size=10, **scoped
    ).items] == ["run_chat_source"]
    assert [item.run_id for item in store.list_runs(
        domain="legal", page_size=10, **scoped
    ).items] == ["run_legal_domain"]
    assert store.list_runs(workflow_id="wf-2", **scoped).total == 0

    page_one = store.list_runs(
        mission_record_state=MissionRecordState.ACTIVE, page=1, page_size=2, **scoped
    )
    page_two = store.list_runs(
        mission_record_state=MissionRecordState.ACTIVE, page=2, page_size=2, **scoped
    )
    assert page_one.total == 5 and page_two.total == 5
    assert [item.run_id for item in page_one.items] == ["run_legal_domain", "run_chat_source"]
    assert [item.run_id for item in page_two.items][0] == "run_owner_running"

    anonymous = store.list_runs(owner_user_id=None, page_size=10)
    assert anonymous.total == 2
    assert {item.run_id for item in anonymous.items} == {"run_chat_source", "run_legal_domain"}


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_list_run_overviews_matches_list_runs_projection(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_overview", title="Overview mission")
    store.save_mission(mission)
    run_record = RuntimeRunRecord(
        runId="run_overview",
        missionId=mission.mission_id,
        workflowId="wf-overview",
        domain="legal",
        runtimeEngine="acg",
        status=WorkflowStatus.RUNNING,
        lifecyclePhase=WorkflowProgressPhase.EXECUTING,
        lifecycleMessage="executing step",
        currentStepId="step_2",
        startedAt=utc_now() - timedelta(minutes=5),
        input={"source": "acg", "authenticatedUserId": "user-a"},
        updatedAt=utc_now(),
    )
    store.save_run(run_record)

    overviews = store.list_run_overviews(
        owner_user_id="user-a", mission_record_state=MissionRecordState.ACTIVE
    )
    assert overviews.total == 1
    item = overviews.items[0]
    assert item.run_id == run_record.run_id
    assert item.mission_id == run_record.mission_id
    assert item.workflow_id == run_record.workflow_id
    assert item.domain == run_record.domain
    assert item.status is WorkflowStatus.RUNNING
    assert item.lifecycle_phase == "executing"
    assert item.lifecycle_message == "executing step"
    assert item.source == "acg"
    assert item.current_step_id == "step_2"
    assert item.started_at == run_record.started_at
    assert item.created_at == run_record.created_at
    assert item.updated_at == run_record.updated_at
    assert item.runtime_revision == run_record.runtime_revision
    assert item.title == "Overview mission"

    detail = store.list_runs(owner_user_id="user-a")
    assert [item.run_id for item in overviews.items] == [item.run_id for item in detail.items]
    assert overviews.total == detail.total


def test_sqlite_list_run_overviews_never_deserializes_run_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "workflow.db"
    store = SQLiteWorkflowStore(db_path)
    mission = RuntimeMissionRecord(missionId="mission_overview_payload", title="Mission")
    store.save_mission(mission)
    run = RuntimeRunRecord(
        runId="run_overview_payload",
        missionId=mission.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
        status=WorkflowStatus.COMPLETED,
        input={"authenticatedUserId": "user-a"},
    )
    store.save_run(run)

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE runs SET payload = 'not-list-readable' WHERE run_id = ?", (run.run_id,))
        conn.commit()

    overviews = SQLiteWorkflowStore(db_path).list_run_overviews(owner_user_id="user-a")
    assert overviews.total == 1
    assert overviews.items[0].run_id == run.run_id
    assert overviews.items[0].status is WorkflowStatus.COMPLETED
    assert overviews.items[0].title == "Mission"


def test_sqlite_summary_columns_backfill_survives_legacy_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "workflow.db"
    store = SQLiteWorkflowStore(db_path)
    mission = RuntimeMissionRecord(missionId="mission_backfill", title="Backfill mission")
    store.save_mission(mission)
    run = RuntimeRunRecord(
        runId="run_backfill",
        missionId=mission.mission_id,
        workflowId="wf-backfill",
        domain="legal",
        runtimeEngine="acg",
        status=WorkflowStatus.RUNNING,
        currentStepId="step_backfill",
        startedAt=utc_now() - timedelta(minutes=1),
        input={"source": "acg", "authenticatedUserId": "user-a"},
        updatedAt=utc_now(),
    )
    store.save_run(run)

    legacy_columns = (
        "domain", "workflow_id", "lifecycle_phase", "lifecycle_message", "source",
        "current_step_id", "started_at", "created_at", "runtime_revision",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE runs SET {', '.join(f'{column} = NULL' for column in legacy_columns)} "
            "WHERE run_id = ?",
            (run.run_id,),
        )
        conn.commit()

    reopened = SQLiteWorkflowStore(db_path)
    overviews = reopened.list_run_overviews(owner_user_id="user-a")
    assert overviews.total == 1
    item = overviews.items[0]
    assert item.domain == "legal"
    assert item.workflow_id == "wf-backfill"
    assert item.status is WorkflowStatus.RUNNING
    assert item.source == "acg"
    assert item.current_step_id == "step_backfill"
    assert item.started_at == run.started_at
    assert item.created_at == run.created_at
    assert item.updated_at == run.updated_at
    assert item.runtime_revision == run.runtime_revision
    assert item.title == "Backfill mission"

    # Reopening again must not touch backfilled rows or lose the filter.
    assert SQLiteWorkflowStore(db_path).list_runs(owner_user_id="user-a").total == 1


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_list_planning_recovery_candidates_returns_only_replayable_runs(
    store_factory, tmp_path: Path
) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_planning_recovery", title="Mission")
    store.save_mission(mission)
    base = dict(
        missionId=mission.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
        executionState={"planningLoop": {"kind": "legacy"}},
    )
    failed = RuntimeRunRecord(runId="run_recovery_failed", status=WorkflowStatus.FAILED, **base)
    # 合法的 Planner 评审屏障：checkpointId + reviewPayload(planner) + graphId 对齐。
    waiting = RuntimeRunRecord(
        runId="run_recovery_waiting",
        status=WorkflowStatus.WAITING_REVIEW,
        currentStepId="acg-graph-1",
        acgBlueprint={"graphId": "acg-graph-1", "nodes": []},
        executionState={
            "planningLoop": {"kind": "legacy"},
            "checkpointId": "cp-1",
            "reviewPayload": {"subjectType": "planner", "subjectId": "acg-graph-1"},
        },
        missionId=mission.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
    )
    completed = RuntimeRunRecord(runId="run_recovery_completed", status=WorkflowStatus.COMPLETED, **base)
    running = RuntimeRunRecord(runId="run_recovery_running", status=WorkflowStatus.RUNNING, **base)
    failed_without_loop = RuntimeRunRecord(
        runId="run_recovery_failed_bare", status=WorkflowStatus.FAILED,
        missionId=mission.mission_id, workflowId="workflow-1",
        domain="general", runtimeEngine="acg",
    )
    for run in (completed, failed, running, failed_without_loop, waiting):
        store.save_run(run)

    candidates = store.list_planning_recovery_candidates()
    assert [run.run_id for run in candidates] == ["run_recovery_failed", "run_recovery_waiting"]
    # 返回的是可变深复制：调用方改动不得污染存储内对象。
    candidates[0].execution_state["planningLoop"] = {"kind": "mutated"}
    assert store.get_run(failed.run_id).execution_state["planningLoop"] == {"kind": "legacy"}


def _corrupt_run_payload(db_path: Path, run_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE runs SET payload = 'not-json-readable' WHERE run_id = ?", (run_id,))
        conn.commit()


def test_sqlite_planning_recovery_never_reads_excluded_payloads(tmp_path: Path) -> None:
    db_path = tmp_path / "workflow.db"
    store = SQLiteWorkflowStore(db_path)
    mission = RuntimeMissionRecord(missionId="mission_recovery_scan", title="Mission")
    store.save_mission(mission)
    base = dict(
        missionId=mission.mission_id,
        workflowId="workflow-1",
        domain="general",
        runtimeEngine="acg",
        executionState={"planningLoop": {"kind": "legacy"}},
    )
    # completed/running 行即使携带 planningLoop 也不是恢复候选：status 摘要列
    # 必须先短路，json_extract 不得触碰这些行的大 payload（损坏 JSON 不炸即证明）。
    completed = RuntimeRunRecord(runId="run_scan_completed", status=WorkflowStatus.COMPLETED, **base)
    running = RuntimeRunRecord(runId="run_scan_running", status=WorkflowStatus.RUNNING, **base)
    failed = RuntimeRunRecord(runId="run_scan_failed", status=WorkflowStatus.FAILED, **base)
    for run in (completed, running, failed):
        store.save_run(run)
    _corrupt_run_payload(db_path, completed.run_id)
    _corrupt_run_payload(db_path, running.run_id)

    candidates = SQLiteWorkflowStore(db_path).list_planning_recovery_candidates()
    assert [run.run_id for run in candidates] == [failed.run_id]


def test_sqlite_non_terminal_scan_reads_status_column_not_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "workflow.db"
    store = SQLiteWorkflowStore(db_path)
    mission = RuntimeMissionRecord(missionId="mission_non_terminal_scan", title="Mission")
    store.save_mission(mission)
    completed = RuntimeRunRecord(
        runId="run_scan_terminal", missionId=mission.mission_id, workflowId="workflow-1",
        domain="general", runtimeEngine="acg", status=WorkflowStatus.COMPLETED,
    )
    running = RuntimeRunRecord(
        runId="run_scan_active", missionId=mission.mission_id, workflowId="workflow-1",
        domain="general", runtimeEngine="acg", status=WorkflowStatus.RUNNING,
    )
    store.save_run(completed)
    store.save_run(running)
    # 终态行的 payload 从不被解析（损坏 JSON 不炸），过滤只依赖摘要列。
    _corrupt_run_payload(db_path, completed.run_id)

    reopened = SQLiteWorkflowStore(db_path)
    assert [run.run_id for run in reopened.list_non_terminal_runs()] == [running.run_id]


@pytest.mark.parametrize(
    "store_factory",
    [lambda _: MemoryWorkflowStore(), lambda path: SQLiteWorkflowStore(path / "workflow.db")],
)
def test_store_accepts_only_recoverable_acg_control_review_barriers(store_factory, tmp_path: Path) -> None:
    store = store_factory(tmp_path)
    mission = RuntimeMissionRecord(missionId="mission_control_review", title="Mission")
    store.save_mission(mission)
    run = RuntimeRunRecord(
        runId="run_control_review",
        missionId=mission.mission_id,
        workflowId="workflow-control",
        domain="general",
        runtimeEngine="acg",
        status=WorkflowStatus.WAITING_REVIEW,
        currentStepId="ctrl_join",
        acgBlueprint={
            "graphId": "acg-control",
            "nodes": [
                {
                    "nodeId": "ctrl_join",
                    "nodeType": "control",
                    "name": "JOIN",
                    "controlType": "consensus",
                }
            ],
        },
        executionState={
            "checkpointId": "acgckpt_control",
            "reviewPayload": {
                "subjectType": "control",
                "subjectId": "ctrl_join",
                "controlId": "ctrl_join",
                "reasonCode": "CONSENSUS_UNRESOLVED",
            },
        },
    )

    store.save_run(run)
    assert store.get_run(run.run_id).status is WorkflowStatus.WAITING_REVIEW

    invalid = run.model_copy(deep=True)
    invalid.run_id = "run_control_review_invalid"
    invalid.execution_state.pop("checkpointId")
    with pytest.raises(ValueError, match="no checkpoint"):
        store.save_run(invalid)

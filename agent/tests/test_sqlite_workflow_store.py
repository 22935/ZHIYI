from datetime import datetime, timezone
import sqlite3

import pytest

from agentos.core.models.types import (
    AgentTask,
    PluginSnapshot,
    RunExecutionScope,
    StepStatus,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from agentos.core.acg import ACGBlueprint, ACGEdge, EdgeActivation, StepNode
from agentos.core.conditions import BranchDecision
from agentos.core.governance.checkpoint import CheckpointStore
from agentos.core.runtime_graph import (
    AppliedPatchRecord,
    RuntimeEvent,
    RuntimeEventStatus,
    RuntimeEventType,
    RuntimeGraph,
    RuntimeAttempt,
)
from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore


def test_sqlite_rejects_missing_or_changed_task_and_obvious_state_conflicts(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "validation.db")
    run = WorkflowRun(
        taskId="task_validation",
        workflowId="workflow",
        domain="test",
        runtimeEngine="acg",
    )
    with pytest.raises(ValueError, match="task does not exist"):
        store.save_run(run)

    store.save_task(AgentTask(taskId=run.task_id, title="Validation"))
    store.save_run(run)
    changed_task = run.model_copy(deep=True)
    changed_task.task_id = "task_changed"
    store.save_task(AgentTask(taskId="task_changed", title="Changed"))
    with pytest.raises(ValueError, match="taskId cannot change"):
        store.save_run(changed_task)

    completed = run.model_copy(deep=True)
    completed.status = WorkflowStatus.COMPLETED
    completed.steps = [
        WorkflowStep(
            stepId="active",
            name="Active",
            agentName="worker",
            status=StepStatus.RUNNING,
        )
    ]
    with pytest.raises(ValueError, match="completed workflow run"):
        store.save_run(completed)

    failed = run.model_copy(deep=True)
    failed.status = WorkflowStatus.FAILED
    failed.steps = [
        WorkflowStep(
            stepId="retrying",
            name="Retrying",
            agentName="worker",
            status=StepStatus.RETRYING,
        )
    ]
    with pytest.raises(ValueError, match="failed workflow run"):
        store.save_run(failed)

    waiting = run.model_copy(deep=True)
    waiting.status = WorkflowStatus.WAITING_REVIEW
    waiting.steps = [WorkflowStep(stepId="pending", name="Pending", agentName="worker")]
    with pytest.raises(ValueError, match="no waiting_review step"):
        store.save_run(waiting)


def test_sqlite_roundtrips_frozen_plugin_scope(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "plugin-scope.db")
    store.save_task(AgentTask(taskId="task_scope", title="Plugin scope"))
    snapshot = PluginSnapshot(
        pluginId="kinlin.legal",
        version="0.1.0",
        manifestHash="manifest-hash",
        contributionRevision="contribution-revision",
    )
    scope = RunExecutionScope(
        enabledPluginIds=("kinlin.legal",),
        capabilityIds=("文本解析",),
        agentIds=("contract_parse",),
        workflowIds=("native_acg_runtime_v1", "legal_contract_review_v1"),
        pluginSnapshots=(snapshot,),
        capabilityCatalogRevision="catalog-revision",
    )
    run = WorkflowRun(
        taskId="task_scope",
        workflowId="legal_contract_review_v1",
        domain="legal",
        runtimeEngine="acg",
        enabledPluginIds=["kinlin.legal"],
        resolvedEnabledPluginIds=["kinlin.legal"],
        pluginSnapshot=[snapshot],
        capabilityCatalogRevision="catalog-revision",
        planningDiversity="balanced",
        planningSeed=284731,
        plannerAlgorithmVersion="controlled-stochastic-v1",
        planningCandidateCount=4,
        selectedPlanningVariantId="variant_example",
        executionScope=scope,
    )

    store.save_run(run)
    loaded = SQLiteWorkflowStore(tmp_path / "plugin-scope.db").get_run(run.run_id)

    assert loaded.execution_scope == scope
    assert loaded.plugin_snapshot == [snapshot]
    assert loaded.resolved_enabled_plugin_ids == ["kinlin.legal"]
    assert loaded.legacy_plugin_scope is False
    assert loaded.planning_diversity == "balanced"
    assert loaded.planning_seed == 284731
    assert loaded.planner_algorithm_version == "controlled-stochastic-v1"
    assert loaded.planning_candidate_count == 4
    assert loaded.selected_planning_variant_id == "variant_example"


def test_sqlite_workflow_store_persists_tasks_and_runs(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "workflow.db")

    task = AgentTask(
        title="合同审查",
        domain="legal",
        intent="contract_review",
        input={"caseText": "合同逾期交付"},
    )
    task.updated_at = datetime(2026, 5, 15, tzinfo=timezone.utc)
    store.save_task(task)

    run = WorkflowRun(
        taskId=task.task_id,
        workflowId="legal_contract_review_v1",
        domain="legal",
        runtimeEngine="acg",
        currentStepId="case_intake",
        input={"caseText": "合同逾期交付"},
        steps=[
            WorkflowStep(
                stepId="case_intake",
                name="Case Intake",
                agentName="case_intake",
            )
        ],
    )
    run.status = WorkflowStatus.RUNNING
    run.updated_at = datetime(2026, 5, 15, tzinfo=timezone.utc)
    store.save_run(run)

    reopened = SQLiteWorkflowStore(tmp_path / "workflow.db")
    loaded_task = reopened.get_task(task.task_id)
    loaded_run = reopened.get_run(run.run_id)

    assert loaded_task.title == "合同审查"
    assert loaded_task.input["caseText"] == "合同逾期交付"
    assert loaded_run.workflow_id == "legal_contract_review_v1"
    assert loaded_run.current_step_id == "case_intake"
    assert loaded_run.status == WorkflowStatus.RUNNING
    assert [item.run_id for item in reopened.list_runs()] == [run.run_id]


def test_sqlite_workflow_store_roundtrips_runtime_graph_patch_history_and_checkpoint(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "runtime-graph.db")
    store.save_task(AgentTask(taskId="task_sqlite", title="Runtime graph"))
    blueprint = ACGBlueprint(
        graphId="graph_sqlite",
        version=8,
        nodes=[
            StepNode(nodeId="a", agentName="worker"),
            StepNode(nodeId="b", agentName="worker"),
        ],
        edges=[ACGEdge(edgeId="a_b", sourceId="a", targetId="b")],
    )
    graph = RuntimeGraph.from_blueprint(run_id="run_sqlite", blueprint=blueprint)
    graph.graph_version = 2
    graph.applied_patch_ids = ["patch_sqlite"]
    graph.applied_patch_idempotency_keys = ["idem_sqlite"]
    graph.processed_event_ids = ["event_sqlite"]
    graph.runtime_events = [
        RuntimeEvent(
            eventId="event_sqlite",
            idempotencyKey="event_key",
            runId="run_sqlite",
            graphId="graph_sqlite",
            graphVersion=1,
            eventType=RuntimeEventType.EVIDENCE_MISSING,
            runtimeNodeId="b",
            attemptId="attempt_sqlite",
            payload={"reasonCode": "EVIDENCE_MISSING", "targetNodeId": "b"},
            status=RuntimeEventStatus.PROCESSED,
        )
    ]
    graph.event_to_patch = {"event_sqlite": "patch_sqlite"}
    graph.applied_recipe_scopes = ["evidence_retrieval_and_validation.v1::b"]
    graph.applied_patches = [
        AppliedPatchRecord(
            patchId="patch_sqlite",
            idempotencyKey="idem_sqlite",
            contentHash="content_hash",
            semanticHash="semantic_hash",
            operationType="ADD_SUBGRAPH",
            baseGraphVersion=1,
            resultGraphVersion=2,
            sourceEventId="event_sqlite",
        )
    ]
    binding_node = graph.get_node("b")
    binding_node.current_binding = {
        "bindingId": "binding_alternate",
        "agentName": "alternate",
        "agentId": "alternate",
        "domain": "test",
        "capability": "work",
    }
    binding_node.binding_candidates = [dict(binding_node.current_binding)]
    binding_node.binding_history = [
        {
            "bindingId": "binding_alternate",
            "selectedAtGraphVersion": 2,
            "sourcePatchId": "patch_sqlite",
            "reasonCode": "BINDING_UNAVAILABLE",
        }
    ]
    binding_node.binding_switch_count = 1
    binding_node.attempts = [
        RuntimeAttempt(
            attemptNumber=1,
            graphVersion=1,
            bindingId="binding_primary",
            agentName="primary",
            status=StepStatus.FAILED,
            error="unavailable",
        )
    ]
    graph.edges[0].activation = EdgeActivation.TERMINATED
    binding_node.status = StepStatus.SKIPPED_BY_CONDITION
    graph.branch_decisions = [
        BranchDecision(
            decisionId="decision_sqlite",
            controlNodeId="route",
            sourceNodeId="a",
            sourceOutputVersion=1,
            inputHash="input_hash",
            selectedCaseKey="high",
            selectedEdgeIds=["selected_edge"],
            terminatedEdgeIds=["a_b"],
            skippedNodeIds=["b"],
            joinNodeId="join",
            sourceEventId="condition_sqlite",
            sourcePatchId="patch_sqlite",
            decidedAtGraphVersion=2,
        )
    ]
    run = WorkflowRun(
        runId="run_sqlite",
        taskId="task_sqlite",
        workflowId="workflow_sqlite",
        domain="test",
        runtimeEngine="acg",
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[
            WorkflowStep(stepId="a", name="A", agentName="worker"),
            WorkflowStep(stepId="b", name="B", agentName="worker"),
        ],
    )
    CheckpointStore().create(run, "b")

    store.save_run(run)
    reloaded = SQLiteWorkflowStore(tmp_path / "runtime-graph.db").get_run("run_sqlite")

    assert reloaded.runtime_graph.graph_version == 2
    assert reloaded.runtime_graph.source_blueprint_version == 8
    assert reloaded.runtime_graph.applied_patch_ids == ["patch_sqlite"]
    assert reloaded.runtime_graph.applied_patch_idempotency_keys == ["idem_sqlite"]
    assert reloaded.runtime_graph.processed_event_ids == ["event_sqlite"]
    assert reloaded.runtime_graph.runtime_events[0].status == RuntimeEventStatus.PROCESSED
    assert reloaded.runtime_graph.event_to_patch == {"event_sqlite": "patch_sqlite"}
    assert reloaded.runtime_graph.applied_recipe_scopes == [
        "evidence_retrieval_and_validation.v1::b"
    ]
    reloaded_binding = reloaded.runtime_graph.get_node("b")
    assert reloaded_binding.current_binding["bindingId"] == "binding_alternate"
    assert reloaded_binding.binding_switch_count == 1
    assert reloaded_binding.binding_history[0]["sourcePatchId"] == "patch_sqlite"
    assert reloaded_binding.attempts[0].binding_id == "binding_primary"
    assert reloaded_binding.status == StepStatus.SKIPPED_BY_CONDITION
    assert reloaded.runtime_graph.edges[0].activation == EdgeActivation.TERMINATED
    assert reloaded.runtime_graph.branch_decisions[0].decision_id == "decision_sqlite"
    assert reloaded.checkpoints[-1].state_snapshot["conditionalDecisionCount"] == 1
    assert reloaded.checkpoints[-1].state_snapshot["graphVersion"] == 2
    assert reloaded.checkpoints[-1].state_snapshot["appliedPatchIds"] == ["patch_sqlite"]
    assert reloaded.checkpoints[-1].state_snapshot["runtimeGraph"]["graphVersion"] == 2


def test_sqlite_workflow_store_queries_tasks_and_runs_with_filters_and_pagination(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "workflow.db")

    chat_task = AgentTask(
        title="Chat案件分析",
        domain="legal",
        intent="case_analysis",
        input={"source": "chat", "caseText": "聊天升级"},
    )
    chat_task.status = WorkflowStatus.COMPLETED
    chat_task.created_at = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    chat_task.updated_at = chat_task.created_at
    store.save_task(chat_task)

    workbench_task = AgentTask(
        title="Workbench合同审查",
        domain="legal",
        intent="contract_review",
        input={"source": "workbench", "caseText": "工作台发起"},
    )
    workbench_task.status = WorkflowStatus.RUNNING
    workbench_task.created_at = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    workbench_task.updated_at = workbench_task.created_at
    store.save_task(workbench_task)

    chat_run = WorkflowRun(
        taskId=chat_task.task_id,
        workflowId="legal_case_analysis_v1",
        domain="legal",
        runtimeEngine="acg",
        input={"source": "chat", "caseText": "聊天升级"},
    )
    chat_run.status = WorkflowStatus.COMPLETED
    chat_run.created_at = datetime(2026, 5, 15, 9, 1, tzinfo=timezone.utc)
    chat_run.updated_at = chat_run.created_at
    store.save_run(chat_run)

    workbench_run = WorkflowRun(
        taskId=workbench_task.task_id,
        workflowId="legal_contract_review_v1",
        domain="legal",
        runtimeEngine="acg",
        input={"source": "workbench", "caseText": "工作台发起"},
    )
    workbench_run.status = WorkflowStatus.RUNNING
    workbench_run.created_at = datetime(2026, 5, 15, 10, 1, tzinfo=timezone.utc)
    workbench_run.updated_at = workbench_run.created_at
    store.save_run(workbench_run)

    task_page = store.list_tasks(status=WorkflowStatus.RUNNING, domain="legal", source="workbench")
    assert task_page.total == 1
    assert [task.task_id for task in task_page.items] == [workbench_task.task_id]

    run_page = store.list_runs(status=WorkflowStatus.RUNNING, workflow_id="legal_contract_review_v1", source="workbench")
    assert run_page.total == 1
    assert [run.run_id for run in run_page.items] == [workbench_run.run_id]

    compatible_sources = store.list_runs(sources=["chat", "workbench"], page=1, page_size=1)
    assert compatible_sources.total == 2
    assert [run.run_id for run in compatible_sources.items] == [workbench_run.run_id]

    paged_runs = store.list_runs(page=2, page_size=1)
    assert paged_runs.total == 2
    assert paged_runs.page == 2
    assert paged_runs.page_size == 1
    assert [run.run_id for run in paged_runs.items] == [chat_run.run_id]

    summaries = store.list_run_summaries(sources=["chat", "workbench"], page_size=10)
    assert summaries.total == 2
    assert [item["runId"] for item in summaries.items] == [workbench_run.run_id, chat_run.run_id]
    assert summaries.items[0]["title"] == workbench_task.title

    # Summary reads must remain independent from the potentially very large full Run JSON.
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE runs SET payload = 'not-needed-for-summary' WHERE run_id = ?", (workbench_run.run_id,))
        conn.commit()
    lightweight = store.list_run_summaries(source="workbench")
    assert [item["runId"] for item in lightweight.items] == [workbench_run.run_id]


def test_sqlite_workflow_store_enables_wal_and_verified_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOS_SQLITE_BUSY_TIMEOUT_MS", "4321")
    source = tmp_path / "workflow.db"
    backup = tmp_path / "backup" / "workflow.db"
    store = SQLiteWorkflowStore(source)
    task = AgentTask(title="持久化测试", domain="legal", intent="contract_review")
    store.save_task(task)
    result = store.backup_to(backup)
    with sqlite3.connect(source) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert store.busy_timeout_ms == 4321
    assert result["integrity"] == "ok"
    assert result["taskCount"] == 1
    assert result["runCount"] == 0
    assert SQLiteWorkflowStore(backup).get_task(task.task_id).title == "持久化测试"


def test_delete_run_keeps_shared_task_then_removes_orphan_task(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "workflow.db")
    task = AgentTask(title="共享任务", domain="legal", intent="contract_review")
    store.save_task(task)
    first = WorkflowRun(
        taskId=task.task_id,
        workflowId="legal_contract_review_v1",
        domain="legal",
        runtimeEngine="acg",
    )
    second = first.model_copy(deep=True)
    second.run_id = "run_second"
    first.status = WorkflowStatus.COMPLETED
    second.status = WorkflowStatus.FAILED
    store.save_run(first)
    store.save_run(second)

    first_result = store.delete_run(first.run_id)
    assert first_result.task_deleted is False
    assert store.get_task(task.task_id).task_id == task.task_id
    assert store.get_run(second.run_id).run_id == second.run_id

    second_result = store.delete_run(second.run_id)
    assert second_result.task_deleted is True
    try:
        store.get_task(task.task_id)
    except KeyError:
        pass
    else:
        raise AssertionError("orphan task should be deleted")

    with pytest.raises(KeyError):
        store.delete_run(second.run_id)


def test_delete_run_rejects_nonterminal_statuses(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "nonterminal-delete.db")
    for status in (
        WorkflowStatus.PENDING,
        WorkflowStatus.PLANNING,
        WorkflowStatus.RUNNING,
        WorkflowStatus.RETRYING,
        WorkflowStatus.WAITING_REVIEW,
    ):
        task = AgentTask(title=status.value)
        store.save_task(task)
        step_status = (
            StepStatus.WAITING_REVIEW
            if status == WorkflowStatus.WAITING_REVIEW
            else StepStatus.PENDING
        )
        run = WorkflowRun(
            taskId=task.task_id,
            workflowId="workflow",
            domain="test",
            runtimeEngine="acg",
            status=status,
            steps=[
                WorkflowStep(
                    stepId="step",
                    name="Step",
                    agentName="worker",
                    status=step_status,
                )
            ],
        )
        store.save_run(run)
        with pytest.raises(ValueError, match="not terminal"):
            store.delete_run(run.run_id)

from __future__ import annotations

import pytest

from domain.identity_graph import ExecutionBinding, TaskBinding
from domain.models import AttemptStatus, RunStatus, StepExecutionStatus, MissionStatus
from domain.repository import IdentityConflictError
from runtime.v2 import AcgIdentityLifecycleService
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage


@pytest.fixture
def runtime_v2():
    storage = SQLiteV2Storage(":memory:")
    runtime = AcgIdentityLifecycleService(SQLiteV2Repositories(storage))
    try:
        yield runtime
    finally:
        runtime.close()


def _planned_task(runtime: AcgIdentityLifecycleService, *, goal: str = "审查合同"):
    task = runtime.create_mission(user_id="user-1", goal=goal)
    node = runtime.create_task(
        mission_id=task.mission_id,
        title="识别风险",
        objective="识别高风险合同条款",
    )
    acg_node_id = "risk-analysis"
    blueprint = runtime.create_blueprint(
        mission_id=task.mission_id,
        version=1,
        graph_id="acg_0123456789ab",
        graph={
            "nodes": [{
                "nodeId": acg_node_id,
                "nodeType": "step",
                "capability": "test.execute",
            }],
            "edges": [],
        },
    )
    runtime.repositories.task_bindings.add(TaskBinding(
        taskId=node.task_id,
        blueprintId=blueprint.blueprint_id,
        acgNodeId=acg_node_id,
    ))
    return task, node, blueprint


def _bind_attempt(runtime: AcgIdentityLifecycleService, attempt, blueprint) -> None:
    acg_node_id = runtime.repositories.task_bindings.find_for_task(
        attempt.task_id, blueprint.blueprint_id
    )[0].acg_node_id
    runtime.repositories.execution_bindings.add(ExecutionBinding(
        attemptId=attempt.attempt_id,
        acgNodeId=acg_node_id,
        resourceId="resource-test",
        agentId="agent-test",
        modelId="model-test",
    ))


def test_semantic_task_blueprint_lifecycle_is_persisted(runtime_v2: AcgIdentityLifecycleService) -> None:
    task, node, blueprint = _planned_task(runtime_v2)

    persisted_task = runtime_v2.repositories.missions.get(task.mission_id)
    persisted_nodes = runtime_v2.repositories.semantic_tasks.list_for_mission(task.mission_id)
    persisted_blueprints = runtime_v2.repositories.blueprints.list_for_mission(task.mission_id)

    assert persisted_task is not None
    assert persisted_task.status is MissionStatus.READY
    assert [item.task_id for item in persisted_nodes] == [node.task_id]
    assert [item.blueprint_id for item in persisted_blueprints] == [blueprint.blueprint_id]


def test_one_task_can_have_failed_then_successful_runs(runtime_v2: AcgIdentityLifecycleService) -> None:
    task, node, blueprint = _planned_task(runtime_v2)
    failed_run = runtime_v2.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint.blueprint_id,
    )
    runtime_v2.create_attempt(run_id=failed_run.run_id, task_id=node.task_id)
    runtime_v2.finish_run(failed_run.run_id, RunStatus.FAILED)

    successful_run = runtime_v2.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint.blueprint_id,
    )
    runtime_v2.create_attempt(run_id=successful_run.run_id, task_id=node.task_id)
    runtime_v2.finish_run(successful_run.run_id, RunStatus.SUCCEEDED)

    runs = runtime_v2.repositories.runs.list_for_mission(task.mission_id)
    assert [run.status for run in runs] == [RunStatus.FAILED, RunStatus.SUCCEEDED]
    assert runs[0].run_id != runs[1].run_id
    assert runtime_v2.repositories.missions.get(task.mission_id).status is MissionStatus.COMPLETED


def test_blueprint_versions_bind_runs_to_the_selected_version(runtime_v2: AcgIdentityLifecycleService) -> None:
    task, node, blueprint_v1 = _planned_task(runtime_v2)
    blueprint_v2 = runtime_v2.create_blueprint(
        mission_id=task.mission_id,
        version=2,
        graph_id="runtime_graph_v2",
        graph={"nodes": [{"nodeId": "risk-analysis-v2"}], "edges": [], "revision": 2},
    )
    run_v1 = runtime_v2.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint_v1.blueprint_id,
    )
    run_v2 = runtime_v2.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint_v2.blueprint_id,
    )

    assert run_v1.blueprint_id == blueprint_v1.blueprint_id
    assert run_v1.graph_version == 1
    assert run_v2.blueprint_id == blueprint_v2.blueprint_id
    assert run_v2.graph_version == 2


def test_attempt_retry_and_step_execution_are_persisted(runtime_v2: AcgIdentityLifecycleService) -> None:
    task, node, blueprint = _planned_task(runtime_v2)
    run = runtime_v2.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)
    attempt_one = runtime_v2.create_attempt(run_id=run.run_id, task_id=node.task_id)
    _bind_attempt(runtime_v2, attempt_one, blueprint)

    first_context = runtime_v2.create_context(run.run_id)
    first_execution = runtime_v2.start_step_execution(
        first_context, input={"contract": "v1"}
    )
    runtime_v2.fail_step_execution(
        first_context,
        first_execution.step_execution_id,
        failure_reason="temporary failure",
    )

    attempt_two = runtime_v2.create_attempt(run_id=run.run_id, task_id=node.task_id)
    _bind_attempt(runtime_v2, attempt_two, blueprint)
    second_context = runtime_v2.create_context(run.run_id)
    running = runtime_v2.start_step_execution(
        second_context, input={"contract": "v1"}
    )
    execution = runtime_v2.complete_step_execution(
        second_context,
        running.step_execution_id,
        output={"reviewed": "v1"},
    )

    attempts = runtime_v2.repositories.attempts.list_for_run(run.run_id)
    assert [item.attempt_number for item in attempts] == [1, 2]
    assert attempts[0].attempt_id == attempt_one.attempt_id
    assert attempts[0].status is AttemptStatus.FAILED
    assert attempts[0].failure_reason == "temporary failure"
    assert attempts[1].attempt_id == attempt_two.attempt_id
    assert attempts[1].status is AttemptStatus.SUCCEEDED
    assert execution.status is StepExecutionStatus.SUCCEEDED
    assert execution.attempt_id == attempt_two.attempt_id
    assert runtime_v2.repositories.step_executions.list_for_attempt(attempt_one.attempt_id)[0].status is StepExecutionStatus.FAILED


def test_execution_context_tracks_the_running_step(runtime_v2: AcgIdentityLifecycleService) -> None:
    task, node, blueprint = _planned_task(runtime_v2)
    run = runtime_v2.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)
    attempt = runtime_v2.create_attempt(run_id=run.run_id, task_id=node.task_id)
    _bind_attempt(runtime_v2, attempt, blueprint)
    context = runtime_v2.create_context(run.run_id)
    running = runtime_v2.start_step_execution(context, input={})
    assert context.active_executions == [running.step_execution_id]
    execution = runtime_v2.complete_step_execution(
        context, running.step_execution_id, output={"ok": True}
    )
    assert context.active_executions == []


def test_sqlite_runtime_survives_reopen(tmp_path) -> None:
    db_path = tmp_path / "new-acg.sqlite3"
    first = AcgIdentityLifecycleService.from_sqlite(db_path)
    task, node, blueprint = _planned_task(first)
    run = first.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)
    attempt = first.create_attempt(run_id=run.run_id, task_id=node.task_id)
    _bind_attempt(first, attempt, blueprint)
    context = first.create_context(run.run_id)
    running = first.start_step_execution(context, input={"source": "persisted"})
    execution = first.complete_step_execution(
        context,
        running.step_execution_id,
        output={"echo": "persisted"},
    )
    first.close()

    second = AcgIdentityLifecycleService.from_sqlite(db_path)
    try:
        assert second.repositories.missions.get(task.mission_id) is not None
        assert second.repositories.blueprints.get(blueprint.blueprint_id) is not None
        assert second.repositories.runs.get(run.run_id) is not None
        assert second.repositories.attempts.get(attempt.attempt_id).status is AttemptStatus.SUCCEEDED
        assert second.repositories.step_executions.get(execution.step_execution_id).output == {
            "echo": "persisted"
        }
    finally:
        second.close()


def test_run_cannot_use_another_tasks_blueprint(runtime_v2: AcgIdentityLifecycleService) -> None:
    task_a, _node_a, blueprint_a = _planned_task(runtime_v2, goal="目标 A")
    task_b = runtime_v2.create_mission(user_id="user-2", goal="目标 B")
    runtime_v2.create_task(
        mission_id=task_b.mission_id,
        title="节点 B",
        objective="执行目标 B",
    )

    with pytest.raises(IdentityConflictError, match="another Mission"):
        runtime_v2.create_run(
            mission_id=task_b.mission_id,
            blueprint_id=blueprint_a.blueprint_id,
        )

    assert runtime_v2.repositories.runs.list_for_mission(task_a.mission_id) == []
    assert runtime_v2.repositories.runs.list_for_mission(task_b.mission_id) == []

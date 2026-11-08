from __future__ import annotations


import pytest

from components.executor.graph import ACGExecutionGraph
from contracts.resource import ExecutionBinding as RuntimeExecutionBinding, RuntimeKind
from domain.identity_graph import IdentityRelation, IdentityResolver
from domain.models import RunStatus, MissionStatus
from domain.repository import IdentityConflictError
from runtime import (
    PlannerIdentityBridge,
    TaskPlan,
    PlannedTask,
    AcgIdentityLifecycleService,
    IdentityProjectionBridge,
)
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec
from support.acg.models import ACGBlueprint, ACGEdge, EdgeType, StepNode


@pytest.fixture
def foundation():
    runtime = AcgIdentityLifecycleService(SQLiteV2Repositories(SQLiteV2Storage(":memory:")))
    bridge = IdentityProjectionBridge(runtime, runtime.repositories)
    try:
        yield runtime, bridge
    finally:
        runtime.close()


def _registered_chain(
    runtime: AcgIdentityLifecycleService,
    bridge: IdentityProjectionBridge,
):
    task = runtime.create_mission(user_id="user-1", goal="审查软件开发合同")
    extract = runtime.create_task(
        mission_id=task.mission_id, title="提取条款", objective="提取付款相关条款"
    )
    risk = runtime.create_task(
        mission_id=task.mission_id,
        parent_task_id=extract.task_id,
        title="分析风险",
        objective="分析付款风险",
    )
    runtime_blueprint = ACGBlueprint(
        graphId="acg_0123456789ab",
        missionId=task.mission_id,
        nodes=[
            StepNode(
                nodeId="extract", name="提取条款",
                capability="contract.extract",
            ),
            StepNode(
                nodeId="risk", name="分析风险",
                capability="contract.risk",
            )],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="extract", plannedAgentId="合同智能体"), AgentBindingSpec(stepId="risk", plannedAgentId="合同智能体"),)),
        edges=[ACGEdge(
            edgeId="edge_extract_risk",
            sourceId="extract",
            targetId="risk",
            edgeType=EdgeType.DEPENDENCY,
        )],
    )
    blueprint = bridge.register_blueprint(
        mission_id=task.mission_id,
        version=1,
        runtime_blueprint=runtime_blueprint,
        task_bindings={extract.task_id: "extract", risk.task_id: "risk"},
    )
    return task, extract, risk, blueprint


def _runtime_binding(run_id: str, attempt_id: str, step_id: str) -> RuntimeExecutionBinding:
    return RuntimeExecutionBinding(
        bindingId=f"binding:{run_id}:{step_id}:{attempt_id}",
        runId=run_id,
        stepId=step_id,
        attemptId=attempt_id,
        resourceId="agent-contract-1",
        runtimeKind=RuntimeKind.EXECUTION_BACKEND,
        snapshotVersion=3,
        metadata={"score": 0.95},
    )


def test_planner_bridge_records_only_semantic_task_tree(foundation) -> None:
    runtime, _bridge = foundation
    task = runtime.create_mission(user_id="user-1", goal="审查合同")
    nodes = PlannerIdentityBridge(runtime).record_task_tree(task.mission_id, [
        PlannedTask(key="extract", title="提取条款", objective="识别付款条款"),
        PlannedTask(
            key="risk", parentKey="extract", title="分析风险", objective="判断付款风险"
        ),
    ])

    assert nodes[1].parent_task_id == nodes[0].task_id
    assert all(node.task_id.startswith("task_") for node in nodes)


def test_planner_bridge_rejects_nested_execution_identity(foundation) -> None:
    runtime, _bridge = foundation
    task = runtime.create_mission(user_id="user-1", goal="审查合同")

    with pytest.raises(ValueError, match="cannot contain execution identities"):
        PlannerIdentityBridge(runtime).record_task_tree(task.mission_id, [PlannedTask(
            key="risk",
            title="分析风险",
            objective="判断风险",
            metadata={"routing": {"agentId": "legal-agent"}},
        )])


def test_planner_semantic_keys_are_idempotent_and_reject_meaning_drift(foundation) -> None:
    runtime, _bridge = foundation
    task = runtime.create_mission(user_id="user-1", goal="审查合同")
    plan = TaskPlan(
        missionId=task.mission_id,
        planVersion=1,
        nodes=(
            PlannedTask(
                key="capability:contract.extract",
                title="提取条款",
                objective="识别付款条款",
            ),
        ),
    )
    planner = PlannerIdentityBridge(runtime)

    first = planner.record_task_plan(plan)
    replay = planner.record_task_plan(plan.model_copy(update={"plan_version": 2}))

    assert replay["capability:contract.extract"].task_id == first[
        "capability:contract.extract"
    ].task_id
    assert len(runtime.repositories.semantic_tasks.list_for_mission(task.mission_id)) == 1

    changed = plan.model_copy(deep=True, update={
        "nodes": (
            PlannedTask(
                key="capability:contract.extract",
                title="提取条款",
                objective="改变后的另一项任务",
            ),
        ),
    })
    with pytest.raises(IdentityConflictError, match="changed meaning"):
        planner.record_task_plan(changed)


def test_bridge_delegates_compilation_to_execution_kernel(foundation) -> None:
    runtime, bridge = foundation
    task, extract, _risk, blueprint = _registered_chain(runtime, bridge)
    run = runtime.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)

    graph = bridge.compile(blueprint.blueprint_id, run_id=run.run_id)

    assert isinstance(graph, ACGExecutionGraph)
    assert graph.nodes == ("extract", "risk")
    assert graph.edges == (("extract", "risk"),)
    assert extract.task_id != "extract"
    assert blueprint.graph_id == "acg_0123456789ab"


def test_run_creation_is_idempotent_but_rejects_identity_redefinition(foundation) -> None:
    runtime, bridge = foundation
    task, _extract, _risk, blueprint = _registered_chain(runtime, bridge)
    first = runtime.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint.blueprint_id,
    )

    replay = runtime.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint.blueprint_id,
        run_id=first.run_id,
    )

    assert replay == first
    other_task = runtime.create_mission(user_id="user-1", goal="另一个目标")
    other_node = runtime.create_task(
        mission_id=other_task.mission_id,
        title="执行",
        objective="执行另一个目标",
    )
    other_blueprint = bridge.register_blueprint(
        mission_id=other_task.mission_id,
        version=1,
        runtime_blueprint=ACGBlueprint(
            graphId="acg_other_identity",
            missionId=other_task.mission_id,
            nodes=[StepNode(nodeId="other", name="执行")],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="other", plannedAgentId="通用智能体"),)),
        edges=[]),
        task_bindings={other_node.task_id: "other"},
    )
    with pytest.raises(IdentityConflictError, match="another Mission"):
        runtime.create_run(
            mission_id=other_task.mission_id,
            blueprint_id=other_blueprint.blueprint_id,
            run_id=first.run_id,
        )


def test_same_task_parallel_runs_use_goal_level_completion_policy(foundation) -> None:
    runtime, bridge = foundation
    task, extract, _risk, blueprint = _registered_chain(runtime, bridge)
    failed_run = runtime.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint.blueprint_id,
    )
    successful_run = runtime.create_run(
        mission_id=task.mission_id,
        blueprint_id=blueprint.blueprint_id,
    )
    runtime.create_attempt(run_id=failed_run.run_id, task_id=extract.task_id)
    runtime.create_attempt(run_id=successful_run.run_id, task_id=extract.task_id)

    runtime.finish_run(failed_run.run_id, RunStatus.FAILED)
    assert runtime.repositories.missions.get(task.mission_id).status is MissionStatus.RUNNING

    runtime.finish_run(successful_run.run_id, RunStatus.SUCCEEDED)
    assert runtime.repositories.missions.get(task.mission_id).status is MissionStatus.COMPLETED


def test_runtime_binding_and_lifecycle_resolve_complete_origin(foundation) -> None:
    runtime, bridge = foundation
    task, _extract, risk, blueprint = _registered_chain(runtime, bridge)
    run = runtime.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)
    attempt = runtime.create_attempt(run_id=run.run_id, task_id=risk.task_id)
    binding = bridge.record_scheduling_binding(
        attempt_id=attempt.attempt_id,
        runtime_binding=_runtime_binding(run.run_id, attempt.attempt_id, "risk"),
        agent_id="agent-contract-1",
        model_id="legal-model-1",
    )
    context = runtime.create_context(run.run_id)
    running = bridge.start_execution(context, input={"clause": "30日内付款"})
    execution = bridge.finish_execution(
        context,
        running.step_execution_id,
        output={"risk": "付款期限风险"},
        evidence_ids=["evidence:contract:42"],
        memory_ids=["memory:run:42"],
    )

    resolver = IdentityResolver(runtime.repositories)
    origin = resolver.resolve_execution_origin(execution.step_execution_id)
    assert origin.mission.mission_id == task.mission_id
    assert origin.semantic_task.task_id == risk.task_id
    assert origin.task_binding.acg_node_id == "risk"
    assert origin.execution_binding.binding_id == binding.binding_id
    assert origin.execution_binding.metadata["runtimeBindingId"].startswith("binding:")
    assert {(link.target_id, link.relation_type) for link in resolver.resolve_provenance(
        execution.step_execution_id
    )} == {
        ("evidence:contract:42", IdentityRelation.PRODUCES),
        ("memory:run:42", IdentityRelation.WRITES),
    }


def test_bridge_rejects_runtime_binding_from_another_attempt(foundation) -> None:
    runtime, bridge = foundation
    task, extract, _risk, blueprint = _registered_chain(runtime, bridge)
    run = runtime.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)
    attempt = runtime.create_attempt(run_id=run.run_id, task_id=extract.task_id)

    with pytest.raises(IdentityConflictError, match="does not match Attempt"):
        bridge.record_scheduling_binding(
            attempt_id=attempt.attempt_id,
            runtime_binding=_runtime_binding(run.run_id, "attempt_000000000000", "extract"),
            agent_id="agent-contract-1",
            model_id="legal-model-1",
        )


def test_bridge_rejects_compiling_blueprint_for_another_run(foundation) -> None:
    runtime, bridge = foundation
    task, _extract, _risk, blueprint_v1 = _registered_chain(runtime, bridge)
    extra = runtime.create_task(
        mission_id=task.mission_id, title="输出报告", objective="输出审查报告"
    )
    blueprint_v2 = bridge.register_blueprint(
        mission_id=task.mission_id,
        version=2,
        runtime_blueprint=ACGBlueprint(
            graphId="acg_222222222222",
            missionId=task.mission_id,
            nodes=[StepNode(nodeId="report", name="输出报告")],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="report", plannedAgentId="合同智能体"),)),
        edges=[]),
        task_bindings={extra.task_id: "report"},
    )
    run = runtime.create_run(mission_id=task.mission_id, blueprint_id=blueprint_v1.blueprint_id)

    with pytest.raises(IdentityConflictError, match="do not belong to the Run"):
        bridge.compile(blueprint_v2.blueprint_id, run_id=run.run_id)


def test_bridge_rejects_semantic_task_substitution_for_execution_node(foundation) -> None:
    runtime, bridge = foundation
    task = runtime.create_mission(user_id="user-1", goal="目标")
    node = runtime.create_task(mission_id=task.mission_id, title="节点", objective="执行")
    runtime_blueprint = ACGBlueprint(
        graphId="acg_abcdefabcdef",
        missionId=task.mission_id,
        nodes=[StepNode(nodeId=node.task_id, name="错误复用")],
        resourcePlan=ACGResourcePlan(bindings=(
            AgentBindingSpec(stepId=node.task_id, plannedAgentId="合同智能体"),
        )),
        edges=[],
    )

    with pytest.raises(IdentityConflictError, match="remain distinct"):
        bridge.register_blueprint(
            mission_id=task.mission_id,
            version=1,
            runtime_blueprint=runtime_blueprint,
            task_bindings={node.task_id: node.task_id},
        )


def test_complete_identity_graph_survives_sqlite_reopen(tmp_path) -> None:
    db_path = tmp_path / "identity-graph.sqlite3"
    first = AcgIdentityLifecycleService.from_sqlite(db_path)
    first_bridge = IdentityProjectionBridge(first, first.repositories)
    task, extract, _risk, blueprint = _registered_chain(first, first_bridge)
    run = first.create_run(mission_id=task.mission_id, blueprint_id=blueprint.blueprint_id)
    attempt = first.create_attempt(run_id=run.run_id, task_id=extract.task_id)
    first_bridge.record_scheduling_binding(
        attempt_id=attempt.attempt_id,
        runtime_binding=_runtime_binding(run.run_id, attempt.attempt_id, "extract"),
        agent_id="agent-contract-1",
        model_id="legal-model-1",
    )
    context = first.create_context(run.run_id)
    running = first_bridge.start_execution(context, input={"contract": "persisted"})
    execution = first_bridge.finish_execution(
        context, running.step_execution_id, output={"ok": True}
    )
    first.close()

    second = AcgIdentityLifecycleService.from_sqlite(db_path)
    try:
        origin = IdentityResolver(second.repositories).resolve_execution_origin(
            execution.step_execution_id
        )
        assert origin.mission.mission_id == task.mission_id
        assert origin.semantic_task.task_id == extract.task_id
        assert origin.execution_binding.resource_id == "agent-contract-1"
    finally:
        second.close()

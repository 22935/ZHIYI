"""唯一执行运行时与 AgentOS V2 身份链的真实纵向接线。"""

from __future__ import annotations

from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec
from support.acg.models import ACGEdge, EdgeType


import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from components.mission_manager.store import WorkflowRegistry
from contracts.planning import (
    TaskBindingPatch,
    TaskImplementationBinding,
    TaskPlan,
    PlannedTask,
    TaskPlanPatch,
)
from contracts.resource import ExecutionBinding as RuntimeExecutionBinding, RuntimeKind
from contracts.workflow import WorkflowDefinition, RuntimeRunRecord, WorkflowStepDefinition, WorkflowStatus
from domain.identity_graph import IdentityResolver
from domain.models import AttemptStatus, RunStatus, StepExecutionStatus
from domain.lifecycle_projection import LifecycleProjectionEvent, ProjectionEventStatus
from runtime import (
    AcgIdentityLifecycleService,
    IdentityProjectionReconciler,
    IdentityQueryService,
    IdentityProjectionBridge,
)
from runtime.reconciliation import DEAD_LETTER_MAX_ATTEMPTS
from runtime.workflow_runtime import ExecutionRuntime
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.models import ACGBlueprint, CapabilityCatalog, StepNode, build_default_capability_catalog
from support.stores.memory_workflow_store import MemoryWorkflowStore


class _OutboxMemoryWorkflowStore(MemoryWorkflowStore):
    def __init__(self) -> None:
        super().__init__()
        self.outbox: list[dict] = []

    def list_outbox(self, *, limit: int = 200) -> list[dict]:
        return [
            event for event in self.outbox
            if event.get("status") != "applied"
        ][:limit]

    def mark_outbox(
        self,
        event_id: str,
        *,
        applied: bool,
        error: str | None = None,
    ) -> None:
        event = next(item for item in self.outbox if item["event_id"] == event_id)
        event["status"] = "applied" if applied else "failed"
        event["error"] = error


class _IdentityAgent(BaseAgent):
    async def run(self, context):
        if context.task.input.get("forceFailure"):
            raise RuntimeError("identity vertical slice failure")
        return AgentOutput(
            output={"result": context.step.step_id},
            summary=f"completed:{context.step.step_id}",
        )


def _runtime(
    *,
    force_failure: bool = False,
    blueprint: ACGBlueprint | None = None,
    workflow_store=None,
):
    repositories = SQLiteV2Repositories(SQLiteV2Storage(":memory:"))
    identity_runtime = AcgIdentityLifecycleService(repositories)
    catalog = CapabilityCatalog(
        descriptor.model_copy(update={"depends_on": []})
        if descriptor.capability_id == "analysis" else descriptor
        for descriptor in build_default_capability_catalog().available()
    )
    bridge = IdentityProjectionBridge(identity_runtime, repositories, capability_catalog=catalog)
    agents = AgentRegistry()
    agents.register(_IdentityAgent(AgentProfile(
        agentId="agent-identity",
        agentName="identity-agent",
        domain="general",
        capabilities=["analysis"],
    )))
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="identity-acg",
        name="identity acg",
        domain="general",
        runtimeEngine="acg",
        planningNodes=[PlannedTask(
            key="analysis",
            title="分析任务",
            objective="分析用户任务并产生结果",
            capabilityRequirements=("analysis",),
        )],
        steps=[WorkflowStepDefinition(
            stepId="analyse",
            name="分析任务",
            agentName="identity-agent",
            capability="analysis",
            outputSpec={"type": "object", "properties": {"result": {"type": "string"}}},
        )],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=workflow_store or MemoryWorkflowStore(),
        identity_lifecycle=bridge,
        capability_catalog=catalog,
    )
    task = runtime.create_mission(
        "身份纵向测试",
        workflow_id="identity-acg",
        input={
            "authenticatedUserId": "user-identity",
            "forceFailure": force_failure,
        }
        | (
            {"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")}
            if blueprint is not None
            else {}
        ),
    )
    if blueprint is not None:
        task_plan = TaskPlan(
            missionId=task.mission_id,
            planVersion=1,
            nodes=tuple(
                PlannedTask(
                    key=f"step:{step.node_id}",
                    title=step.name or step.node_id,
                    objective=step.goal or step.description or step.node_id,
                    capabilityRequirements=((step.capability,) if step.capability else ()),
                    metadata={"plannerStrategy": "test_explicit_blueprint"},
                )
                for step in blueprint.step_nodes()
            ),
        )
        task_bindings = tuple(
            TaskImplementationBinding(planNodeKey=f"step:{step.node_id}", acgNodeId=step.node_id)
            for step in blueprint.step_nodes()
        )
        task.input.update({
            "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": task_plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [
                item.model_dump(by_alias=True, mode="json")
                for item in task_bindings
            ],
        })
        runtime.workflow_store.save_mission(task)
    return runtime, identity_runtime, bridge, task


def test_execution_runtime_reuses_agentos_task_run_and_attempt_ids() -> None:
    runtime, identity_runtime, _bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        result = asyncio.run(runtime.execute_prepared_run(run.run_id))

        repositories = identity_runtime.repositories
        domain_task = repositories.missions.get(task.mission_id)
        domain_run = repositories.runs.get(run.run_id)
        attempts = repositories.attempts.list_for_run(run.run_id)
        executions = repositories.step_executions.list_for_attempt(attempts[0].attempt_id)
        binding = repositories.execution_bindings.get_for_attempt(attempts[0].attempt_id)
        origin = IdentityResolver(repositories).resolve_execution_origin(
            executions[0].step_execution_id
        )

        assert task.mission_id.startswith("mission_")
        assert run.run_id.startswith("run_")
        assert result.status is WorkflowStatus.COMPLETED
        assert domain_task is not None and domain_task.mission_id == task.mission_id
        assert domain_run is not None and domain_run.run_id == run.run_id
        assert domain_run.status is RunStatus.SUCCEEDED
        assert len(attempts) == 1
        assert attempts[0].attempt_id.startswith("attempt_")
        assert attempts[0].status is AttemptStatus.SUCCEEDED
        assert executions[0].status is StepExecutionStatus.SUCCEEDED
        assert executions[0].output["outputRef"].startswith("output:")
        assert binding is not None
        assert binding.metadata["runtimeBindingId"].startswith("binding:")
        assert result.execution_state["schedulingDecisions"][0]["attemptId"] == attempts[0].attempt_id
        assert origin.mission.mission_id == task.mission_id
        assert origin.run.run_id == run.run_id
        assert origin.task_binding.acg_node_id == "analyse"
        assert origin.execution_binding.agent_id == "agent-identity"
    finally:
        identity_runtime.close()


def test_runtime_failure_finishes_same_attempt_and_run_identity() -> None:
    runtime, identity_runtime, _bridge, task = _runtime(force_failure=True)
    try:
        _, run = runtime.prepare_run(task.mission_id)
        with pytest.raises(Exception):
            asyncio.run(runtime.execute_prepared_run(run.run_id))

        attempts = identity_runtime.repositories.attempts.list_for_run(run.run_id)
        execution = identity_runtime.repositories.step_executions.list_for_attempt(
            attempts[0].attempt_id
        )[0]
        assert identity_runtime.repositories.runs.get(run.run_id).status is RunStatus.FAILED
        assert attempts[0].status is AttemptStatus.FAILED
        assert attempts[0].failure_reason == "identity vertical slice failure"
        assert execution.status is StepExecutionStatus.FAILED
    finally:
        identity_runtime.close()


def test_identity_attempt_and_binding_hooks_are_idempotent() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        first = bridge.ensure_attempt(run, "analyse", 1)
        second = bridge.ensure_attempt(run, "analyse", 1)
        assert first == second
        assert len(identity_runtime.repositories.attempts.list_for_run(run.run_id)) == 1
    finally:
        identity_runtime.close()


def test_attempt_allocation_is_concurrency_safe_and_idempotent() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        with ThreadPoolExecutor(max_workers=8) as pool:
            attempt_ids = list(pool.map(
                lambda _: bridge.ensure_attempt(run, "analyse", 1),
                range(16),
            ))

        assert len(set(attempt_ids)) == 1
        assert len(identity_runtime.repositories.attempts.list_for_run(run.run_id)) == 1
    finally:
        identity_runtime.close()


def test_event_attempt_number_drift_is_healed_by_attempt_id_anchoring() -> None:
    """事件携带的 attemptNumber 漂移不得毒化投影（2026-09-10 事故回归）。

    断点恢复后 step 计数器与投影历史错位：要么编号不连续，要么同一编号换了
    attemptId。attemptId 是唯一幂等锚点：新 attemptId 一律由投影分配下一个
    连续编号，同 attemptId 重放返回既有行。
    """
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)

        def ensured(attempt_id: str, attempt_number: int) -> None:
            bridge.apply_lifecycle_event("attempt.ensured", {
                "runId": run.run_id,
                "missionId": task.mission_id,
                "stepId": "analyse",
                "attemptId": attempt_id,
                "attemptNumber": attempt_number,
            })

        ensured("attempt_000000000001", 1)
        # Incident shape 1: the resumed emitter's counter ran past the
        # projection history, so its attemptNumber was not contiguous.
        ensured("attempt_000000000002", 4)
        # Incident shape 2: the same (step, #1) re-emitted under the same
        # attemptId while rebuilding the execution state (idempotent replay).
        ensured("attempt_000000000002", 1)

        attempts = sorted(
            identity_runtime.repositories.attempts.list_for_run(run.run_id),
            key=lambda item: item.attempt_number,
        )
        assert [(item.attempt_id, item.attempt_number) for item in attempts] == [
            ("attempt_000000000001", 1),
            ("attempt_000000000002", 2),
        ]
    finally:
        identity_runtime.close()


def test_projection_journal_replays_an_interrupted_idempotent_event() -> None:
    _runtime_instance, identity_runtime, bridge, task = _runtime()
    try:
        event_id = f"mission.created:{task.mission_id}"
        identity_runtime.repositories.projection_events.mark_failed(
            event_id,
            "simulated crash after domain commit",
        )

        report = bridge.replay_unapplied()
        event = identity_runtime.repositories.projection_events.get(event_id)

        assert report == {"examined": 1, "applied": 1, "failed": 0, "dead_lettered": 0}
        assert event.status is ProjectionEventStatus.APPLIED
        assert event.attempts == 2
        assert identity_runtime.repositories.missions.get(task.mission_id) is not None
    finally:
        identity_runtime.close()


def test_projection_replay_bypasses_dead_letters_after_delivery_cap() -> None:
    """重放侧死信帽：反复失败的事件被旁路，不再拖垮每次 flush 的报告。"""
    runtime, identity_runtime, _bridge, task = _runtime()
    try:
        repositories = identity_runtime.repositories
        poison = LifecycleProjectionEvent(
            eventId="run.finished:run_ghost:failed",
            eventType="run.finished",
            aggregateId="run_ghost",
            payload={"runId": "run_ghost", "status": "failed"},
            payloadHash="0" * 64,
        )
        repositories.projection_events.begin(poison)
        for _ in range(DEAD_LETTER_MAX_ATTEMPTS):
            repositories.projection_events.record_replay_failure(
                poison.event_id, "simulated delivery failure"
            )

        report = _bridge.replay_unapplied()

        assert report["dead_lettered"] == 1
        assert report["failed"] == 0
        stored = repositories.projection_events.get(poison.event_id)
        assert stored.status is ProjectionEventStatus.FAILED
        assert stored.attempts >= DEAD_LETTER_MAX_ATTEMPTS
    finally:
        identity_runtime.close()


def test_projection_replay_repairs_partial_blueprint_registration(monkeypatch) -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    repository = identity_runtime.repositories.task_bindings
    original_add = repository.add
    failed = False

    def fail_once(binding):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("simulated relation persistence interruption")
        return original_add(binding)

    monkeypatch.setattr(repository, "add", fail_once)
    try:
        with pytest.raises(RuntimeError, match="simulated relation"):
            runtime.prepare_run(task.mission_id)
        pending = identity_runtime.repositories.projection_events.list_unapplied()
        run_event = next(item for item in pending if item.event_type == "run.prepared")
        monkeypatch.setattr(repository, "add", original_add)

        report = bridge.replay_unapplied()
        domain_run = identity_runtime.repositories.runs.get(
            run_event.payload["runId"]
        )

        assert report["failed"] == 0
        assert domain_run is not None
        assert len(identity_runtime.repositories.task_bindings.find_for_acg_node(
            "analyse",
            domain_run.blueprint_id,
        )) == 1
    finally:
        identity_runtime.close()


def test_planner_progress_does_not_publish_partial_run_identity_event(monkeypatch) -> None:
    runtime, identity_runtime, _bridge, task = _runtime()
    try:
        # Keep the Execution Runtime outbox observable so this test isolates
        # event admission from identity-side consumption.
        monkeypatch.setattr(runtime, "_flush_identity_outbox", lambda: None)

        _, run = runtime.prepare_run(task.mission_id)
        events = [
            item
            for item in runtime.workflow_store.list_outbox(limit=100)
            if item["aggregate_id"] == run.run_id
        ]

        assert len(events) == 1
        assert events[0]["event_type"] == "run.prepared"
        payload = json.loads(events[0]["payload"])
        assert isinstance(payload["acgBlueprint"], dict)
        assert isinstance(payload["executionState"].get("taskPlan"), dict)
        assert isinstance(payload["executionState"].get("taskBindings"), list)
    finally:
        identity_runtime.close()


def test_runtime_projects_lifecycle_events_without_scanning_history(monkeypatch) -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        def reject_history_scan(*args, **kwargs):
            raise AssertionError("node hot path scanned historical records")

        monkeypatch.setattr(runtime.workflow_store, "list_all_runs", reject_history_scan)
        monkeypatch.setattr(runtime.workflow_store, "list_missions", reject_history_scan)
        task.input["reasoningEffort"] = "low"
        runtime.workflow_store.save_mission(task)
        result = asyncio.run(runtime.start(task.mission_id, workflow_id="identity-acg"))
        assert result.status is WorkflowStatus.COMPLETED
        assert all(step.input["reasoningEffort"] == "low" for step in result.steps)
        assert all(step.input["reasoningPolicyReason"] == "run_explicit" for step in result.steps)
        assert identity_runtime.repositories.runs.get(result.run_id).status is RunStatus.SUCCEEDED
        report = IdentityProjectionReconciler(bridge).project_pending_events(runtime.workflow_store)
        assert report.failures == []
        assert report.examined_tasks == report.examined_runs == 0
        assert runtime.workflow_store.list_outbox() == []
    finally:
        identity_runtime.close()


def test_startup_reconciliation_skips_healthy_owned_run_bodies(monkeypatch, tmp_path) -> None:
    from support.stores.sqlite_workflow_store import SQLiteWorkflowStore

    store = SQLiteWorkflowStore(tmp_path / "workflows.sqlite3")
    runtime, identity_runtime, bridge, task = _runtime(workflow_store=store)
    try:
        task = runtime.create_mission(
            "Owned startup recovery", workflow_id="identity-acg",
            input={"authenticatedUserId": "owner-startup"},
        )
        asyncio.run(runtime.start(task.mission_id, workflow_id="identity-acg"))

        def reject_full_scan(*args, **kwargs):
            raise AssertionError("startup must not deserialize healthy historical Runs")

        monkeypatch.setattr(store, "list_all_runs", reject_full_scan)
        monkeypatch.setattr(store, "get_run", reject_full_scan)
        report = IdentityProjectionReconciler(bridge).reconcile_workflow_store(store, audit_existing=False)
        assert report.failures == []
        assert report.examined_runs == 0
    finally:
        identity_runtime.close()


def test_reconciler_restores_a_missing_run_projection_from_runtime_snapshot() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        runtime.identity_lifecycle = None
        task.input["usePlanner"] = True
        runtime.workflow_store.save_mission(task)
        _, run = runtime.prepare_run(task.mission_id)
        runtime.identity_lifecycle = bridge
        assert identity_runtime.repositories.runs.get(run.run_id) is None

        report = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            runtime.workflow_store, audit_existing=False,
        )

        assert report.failures == []
        assert report.repaired_runs == 1
        assert identity_runtime.repositories.runs.get(run.run_id) is not None
    finally:
        identity_runtime.close()


def test_reconciler_converges_terminal_runtime_and_closes_open_identity_nodes() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        identity_run = identity_runtime.repositories.runs.get(run.run_id)
        assert identity_run is not None
        identity_runtime.repositories.runs.update_status(run.run_id, RunStatus.RUNNING)

        identity_task = identity_runtime.repositories.semantic_tasks.list_for_mission(
            task.mission_id
        )[0]
        attempt = identity_runtime.create_attempt(
            run_id=run.run_id,
            task_id=identity_task.task_id,
        )
        bridge.record_scheduling_binding(
            attempt_id=attempt.attempt_id,
            runtime_binding=RuntimeExecutionBinding(
                bindingId="binding:reconciliation",
                runId=run.run_id,
                stepId="analyse",
                attemptId=attempt.attempt_id,
                resourceId="agent-identity",
                runtimeKind=RuntimeKind.EXECUTION_BACKEND,
                snapshotVersion=1,
            ),
            agent_id="agent-identity",
            model_id="test-model",
        )
        execution = bridge.start_execution(
            identity_runtime.create_context(run.run_id),
            input={"nodeId": "analyse"},
        )

        run.status = WorkflowStatus.FAILED
        run.error = {
            "code": "interrupted_after_restart",
            "message": "Task interrupted by service restart.",
        }
        runtime.workflow_store.save_run(run)

        report = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            runtime.workflow_store
        )

        assert report.failures == []
        assert identity_runtime.repositories.runs.get(run.run_id).status is RunStatus.FAILED
        assert identity_runtime.repositories.attempts.get(attempt.attempt_id).status is AttemptStatus.FAILED
        assert identity_runtime.repositories.step_executions.get(execution.step_execution_id).status is StepExecutionStatus.FAILED
    finally:
        identity_runtime.close()


def test_reconciler_skips_failed_run_that_never_materialized_planner_identity() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        run = RuntimeRunRecord(
            runId="run_planning_failed",
            missionId=task.mission_id,
            workflowId="identity-acg",
            domain="general",
            runtimeEngine="acg",
            status=WorkflowStatus.FAILED,
            executionState={"planningDeferred": True},
            error={
                "code": "task_decomposition_failed",
                "message": "TaskPlan dependency cycle: analyze -> understand -> analyze",
            },
        )
        runtime.workflow_store.save_run(run)

        report = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            runtime.workflow_store
        )

        assert report.failures == []
        assert report.examined_runs == 0
        assert identity_runtime.repositories.runs.get(run.run_id) is None
    finally:
        identity_runtime.close()


def test_inbox_retries_failed_consumption_and_recovers_missing_task(monkeypatch) -> None:
    workflow_store = _OutboxMemoryWorkflowStore()
    runtime, identity_runtime, bridge, _task = _runtime(workflow_store=workflow_store)
    runtime.identity_lifecycle = None
    missing = runtime.create_mission("outbox recovery", workflow_id="identity-acg")
    runtime.identity_lifecycle = bridge
    workflow_store.outbox.append({
        "event_id": f"task:{missing.mission_id}:created",
        "event_type": "mission.created",
        "aggregate_id": missing.mission_id,
        "payload": json.dumps(
            missing.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
        ),
        "attempts": 0,
        "status": "pending",
    })
    original = bridge.on_mission_created
    monkeypatch.setattr(
        bridge,
        "on_mission_created",
        lambda _task: (_ for _ in ()).throw(RuntimeError("simulated consumer crash")),
    )
    try:
        failed = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            workflow_store
        )
        inbox = identity_runtime.repositories.inbox_events.get(
            f"task:{missing.mission_id}:created"
        )

        assert any("simulated consumer crash" in item for item in failed.failures)
        assert inbox.status is ProjectionEventStatus.FAILED
        assert identity_runtime.repositories.missions.get(missing.mission_id) is None

        monkeypatch.setattr(bridge, "on_mission_created", original)
        recovered = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            workflow_store
        )
        inbox = identity_runtime.repositories.inbox_events.get(
            f"task:{missing.mission_id}:created"
        )

        assert recovered.failures == []
        assert inbox.status is ProjectionEventStatus.APPLIED
        assert inbox.attempts == 2
        assert identity_runtime.repositories.missions.get(missing.mission_id) is not None
    finally:
        identity_runtime.close()


def test_applied_inbox_skips_duplicate_projection_and_rejects_payload_drift(
    monkeypatch,
) -> None:
    workflow_store = _OutboxMemoryWorkflowStore()
    _runtime_instance, identity_runtime, bridge, task = _runtime(
        workflow_store=workflow_store
    )
    event_id = f"task:{task.mission_id}:created"
    event = {
        "event_id": event_id,
        "event_type": "mission.created",
        "aggregate_id": task.mission_id,
        "payload": json.dumps(task.model_dump(by_alias=True, mode="json"), ensure_ascii=False),
        "attempts": 0,
        "status": "pending",
    }
    workflow_store.outbox.append(event)
    try:
        first = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            workflow_store
        )
        assert first.failures == []

        event["status"] = "pending"
        monkeypatch.setattr(
            bridge,
            "on_mission_created",
            lambda _task: (_ for _ in ()).throw(AssertionError("duplicate projection")),
        )
        duplicate = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            workflow_store
        )
        assert duplicate.failures == []
        assert event["status"] == "applied"

        changed = task.model_dump(by_alias=True, mode="json")
        changed["title"] = "different content"
        event["payload"] = json.dumps(changed, ensure_ascii=False)
        event["status"] = "pending"
        conflict = IdentityProjectionReconciler(bridge).reconcile_workflow_store(
            workflow_store
        )

        assert any("different content" in item for item in conflict.failures)
        assert event["status"] == "failed"
    finally:
        identity_runtime.close()


def test_parallel_runtime_nodes_keep_attempt_and_execution_identity_isolated() -> None:
    blueprint = ACGBlueprint(
        graphId="identity-parallel-graph",
        nodes=[
            StepNode(nodeId="left",  capability="analysis"),
            StepNode(nodeId="right",  capability="analysis")],
    resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="left", plannedAgentId="identity-agent"), AgentBindingSpec(stepId="right", plannedAgentId="identity-agent"),)),
        edges=[ ])
    runtime, identity_runtime, _bridge, task = _runtime(blueprint=blueprint)
    try:
        _, run = runtime.prepare_run(task.mission_id)
        result = asyncio.run(runtime.execute_prepared_run(run.run_id))

        attempts = identity_runtime.repositories.attempts.list_for_run(run.run_id)
        executions = [
            execution
            for attempt in attempts
            for execution in identity_runtime.repositories.step_executions.list_for_attempt(
                attempt.attempt_id
            )
        ]
        assert result.status is WorkflowStatus.COMPLETED
        assert {attempt.task_id for attempt in attempts} == {
            execution.task_id for execution in executions
        }
        assert len({attempt.attempt_id for attempt in attempts}) == 2
        assert len({execution.step_execution_id for execution in executions}) == 2
        assert all(execution.run_id == run.run_id for execution in executions)
    finally:
        identity_runtime.close()


def test_explicit_blueprint_without_task_plan_is_rejected() -> None:
    blueprint = ACGBlueprint(
        graphId="identity-unplanned-graph",
        nodes=[StepNode(nodeId="analyse")],
    resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="analyse", plannedAgentId="identity-agent"),)),
        edges=[])
    runtime, identity_runtime, _bridge, task = _runtime(blueprint=blueprint)
    task.input.pop("taskPlan")
    task.input.pop("taskBindings")
    runtime.workflow_store.save_mission(task)
    try:
        with pytest.raises(ValueError, match="requires taskPlan and taskBindings"):
            runtime.prepare_run(task.mission_id)
    finally:
        identity_runtime.close()


def test_invalid_explicit_bindings_do_not_persist_partial_semantic_tasks() -> None:
    blueprint = ACGBlueprint(
        graphId="identity-invalid-bindings-graph",
        nodes=[StepNode(nodeId="analyse")],
    resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="analyse", plannedAgentId="identity-agent"),)),
        edges=[])
    runtime, identity_runtime, _bridge, task = _runtime(blueprint=blueprint)
    task.input["taskBindings"] = []
    runtime.workflow_store.save_mission(task)
    try:
        with pytest.raises(ValueError, match="complete TaskPlan"):
            runtime.prepare_run(task.mission_id)

        assert identity_runtime.repositories.semantic_tasks.list_for_mission(task.mission_id) == []
        assert identity_runtime.repositories.blueprints.list_for_mission(task.mission_id) == []
        assert identity_runtime.repositories.runs.list_for_mission(task.mission_id) == []
    finally:
        identity_runtime.close()


def test_run_creation_failure_rolls_back_plan_blueprint_and_bindings(monkeypatch) -> None:
    runtime, identity_runtime, _bridge, task = _runtime()
    monkeypatch.setattr(
        identity_runtime,
        "create_run",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated run failure")),
    )
    try:
        with pytest.raises(RuntimeError, match="simulated run failure"):
            runtime.prepare_run(task.mission_id)

        assert identity_runtime.repositories.task_plans.list_for_mission(task.mission_id) == []
        assert identity_runtime.repositories.semantic_tasks.list_for_mission(task.mission_id) == []
        assert identity_runtime.repositories.blueprints.list_for_mission(task.mission_id) == []
        assert identity_runtime.repositories.runs.list_for_mission(task.mission_id) == []
    finally:
        identity_runtime.close()


def test_cancelling_prepared_runtime_run_projects_cancelled_terminal_state() -> None:
    runtime, identity_runtime, _bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        cancelled = runtime.cancel(run.run_id)

        assert cancelled.status is WorkflowStatus.CANCELLED
        assert identity_runtime.repositories.runs.get(run.run_id).status is RunStatus.CANCELLED
    finally:
        identity_runtime.close()


def test_runtime_graph_revision_rejects_unplanned_executable_node() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        original = identity_runtime.repositories.runs.get(run.run_id)
        revised = ACGBlueprint.model_validate(run.acg_blueprint).model_copy(deep=True)
        revised.version += 1
        revised.nodes.append(
            StepNode(
                nodeId="verify",
                capability="analysis",
            )
        )
        revised.resource_plan.bindings += (
            AgentBindingSpec(stepId="verify", plannedAgentId="identity-agent"),
        )

        with pytest.raises(Exception, match="TaskPlanPatch"):
            bridge.on_blueprint_revised(run, revised)

        updated = identity_runtime.repositories.runs.get(run.run_id)
        assert updated.blueprint_id == original.blueprint_id
        assert len(identity_runtime.repositories.blueprints.list_for_mission(task.mission_id)) == 1
    finally:
        identity_runtime.close()


def test_runtime_graph_revision_accepts_explicit_task_plan_patch() -> None:
    runtime, identity_runtime, bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        original = identity_runtime.repositories.runs.get(run.run_id)
        revised = ACGBlueprint.model_validate(run.acg_blueprint).model_copy(deep=True)
        revised.version += 1
        revised.nodes.append(
            StepNode(
                nodeId="verify",
                name="复核结果",
                goal="复核分析结果",
                capability="analysis",
            )
        )
        revised.resource_plan.bindings += (
            AgentBindingSpec(stepId="verify", plannedAgentId="identity-agent"),
        )
        plan_patch = TaskPlanPatch(
            missionId=task.mission_id,
            basePlanVersion=1,
            planVersion=2,
            addNodes=(PlannedTask(
                key="step:verify",
                title="复核结果",
                objective="复核分析结果",
                constraints=[{"type": "required_capability", "value": "analysis"}],
            ),),
        )

        new_run_id = bridge.on_blueprint_revised(
            run,
            revised,
            plan_patch,
            TaskBindingPatch(bindings=(TaskImplementationBinding(
                planNodeKey="step:verify",
                acgNodeId="verify",
            ),)),
        )

        updated = identity_runtime.repositories.runs.get(new_run_id)
        superseded = identity_runtime.repositories.runs.get(run.run_id)
        assert updated.blueprint_id != original.blueprint_id
        assert updated.graph_version == original.graph_version + 1
        assert superseded.status is RunStatus.SUPERSEDED
        assert len(identity_runtime.repositories.blueprints.list_for_mission(task.mission_id)) == 2
        assert bridge.ensure_attempt(type(run).model_validate({**run.model_dump(by_alias=True), "runId": new_run_id}), "verify", 1).startswith("attempt_")
    finally:
        identity_runtime.close()


def test_same_mission_can_execute_another_run_after_success() -> None:
    runtime, identity_runtime, _bridge, task = _runtime()
    try:
        _, first = runtime.prepare_run(task.mission_id)
        asyncio.run(runtime.execute_prepared_run(first.run_id))
        first_nodes = identity_runtime.repositories.semantic_tasks.list_for_mission(task.mission_id)

        _, second = runtime.prepare_run(task.mission_id)
        result = asyncio.run(runtime.execute_prepared_run(second.run_id))

        runs = identity_runtime.repositories.runs.list_for_mission(task.mission_id)
        second_nodes = identity_runtime.repositories.semantic_tasks.list_for_mission(task.mission_id)
        assert first.run_id != second.run_id
        assert result.status is WorkflowStatus.COMPLETED
        assert [item.status for item in runs] == [RunStatus.SUCCEEDED, RunStatus.SUCCEEDED]
        assert [node.task_id for node in second_nodes] == [
            node.task_id for node in first_nodes
        ]
    finally:
        identity_runtime.close()


def test_identity_query_models_use_v2_repositories_as_their_only_source() -> None:
    runtime, identity_runtime, _bridge, task = _runtime()
    try:
        _, run = runtime.prepare_run(task.mission_id)
        asyncio.run(runtime.execute_prepared_run(run.run_id))
        query = IdentityQueryService(identity_runtime.repositories)

        task_detail = query.get_mission(task.mission_id)
        tree = query.run_execution_tree(run.run_id)
        attempt = tree.nodes[0].attempts[0]
        execution = attempt.executions[0]
        detail = query.step_execution_detail(execution.step_execution_id)

        assert task_detail.mission.mission_id == task.mission_id
        assert tree.run.run_id == run.run_id
        assert tree.blueprint.blueprint_id == tree.run.blueprint_id
        assert tree.nodes[0].acg_node_id == "analyse"
        assert attempt.execution_binding is not None
        assert detail.origin.mission.mission_id == task.mission_id
        assert detail.origin.step_execution.step_execution_id == execution.step_execution_id
        assert tree.operational.package is not None
        assert tree.operational.package.package_version == 4
        assert tree.operational.package.package_id
        assert tree.operational.node_executions[0].phase.value == "committed"
        assert tree.operational.node_executions[0].commit_id
        assert query.projection_health().inbox_failed == 0
    finally:
        identity_runtime.close()

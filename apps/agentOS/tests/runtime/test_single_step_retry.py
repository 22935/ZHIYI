from __future__ import annotations


import asyncio

import pytest

from components.content import SQLiteContentManifestStore
from components.executor import InMemoryExecutionValueStore
from components.mission_manager.store import WorkflowRegistry
from contracts.planning import PlannedTask, TaskImplementationBinding, TaskPlan, TaskPlanRelation
from contracts.workflow import StepStatus, WorkflowDefinition, WorkflowStatus, WorkflowStepDefinition
from domain.models import AttemptStatus, RunStatus, StepExecutionStatus
from runtime.workflow_runtime import ExecutionRuntime
from runtime import (
    AcgIdentityLifecycleService,
    IdentityProjectionBridge,
    MissionWorkspaceProjector,
    WorkspaceEntryKind,
)
from runtime.resume_projection import build_reused_step_projection_events
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec
from support.acg.models import ACGBlueprint, ACGEdge, EdgeType, StepNode
from support.stores.memory_workflow_store import MemoryWorkflowStore


class _RetryAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentProfile(
            agentName="retry-agent",
            domain="general",
            capabilities=["analysis", "artifact_generation"],
        ))
        self.final_calls = 0
        self.source_calls = 0

    async def run(self, context):
        if context.step.step_id == "final":
            self.final_calls += 1
            if self.final_calls == 1:
                raise RuntimeError("planned final-node failure")
            return AgentOutput(
                output={
                    "artifacts": [{
                        "title": "Recovered deliverable",
                        "content": "# Recovered deliverable\n",
                    }],
                },
                summary="recovered final deliverable",
            )
        self.source_calls += 1
        return AgentOutput(output={"source": "verified upstream"}, summary="upstream ready")


class _CheckpointResumeAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentProfile(
            agentName="checkpoint-agent",
            domain="general",
            capabilities=["analysis"],
        ))
        self.calls = {"source": 0, "design": 0, "final": 0}

    async def run(self, context):
        step_id = context.step.step_id
        self.calls[step_id] += 1
        if step_id == "design" and self.calls[step_id] == 1:
            raise RuntimeError("planned middle-node failure")
        return AgentOutput(output={step_id: f"{step_id}-output"}, summary=f"{step_id} ready")


def _retry_runtime(
    tmp_path,
    agent: _RetryAgent,
    *,
    with_identity: bool = False,
) -> tuple[ExecutionRuntime, ACGBlueprint]:
    agents = AgentRegistry()
    agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="single-step-retry",
        name="single-step retry",
        domain="general",
        runtimeEngine="acg",
        steps=[WorkflowStepDefinition(
            stepId="placeholder",
            name="placeholder",
            agentName="retry-agent",
        )],
    ))
    blueprint = ACGBlueprint(
        graphId="single-step-retry-graph",
        nodes=[
            StepNode(
                nodeId="source",
                name="source",

                capability="analysis",
                outputSpec={
                    "type": "object",
                    "required": ["source"],
                    "properties": {"source": {"type": "string"}},
                },
            ),
            StepNode(
                nodeId="final",
                name="final",

                capability="artifact_generation",
                logicalRole="finalization",
                inputSpec={"from": {"source": ["source"]}},
                outputSpec={
                    "type": "object",
                    "required": ["artifacts"],
                    "properties": {"artifacts": {"type": "array"}},
                },
            )],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="source", plannedAgentId="retry-agent"), AgentBindingSpec(stepId="final", plannedAgentId="retry-agent"),)),
        edges=[ACGEdge(sourceId="source", targetId="final", edgeType=EdgeType.DEPENDENCY)],
    )
    content_manifest_store = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    identity_lifecycle = None
    if with_identity:
        identity_service = AcgIdentityLifecycleService(
            SQLiteV2Repositories(SQLiteV2Storage(":memory:"))
        )
        identity_lifecycle = IdentityProjectionBridge(
            identity_service,
            identity_service.repositories,
            content_manifest_store,
        )
    return ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        execution_value_store=InMemoryExecutionValueStore(),
        content_manifest_store=content_manifest_store,
        identity_lifecycle=identity_lifecycle,
    ), blueprint


@pytest.mark.parametrize("with_identity", [False, True])
def test_single_step_retry_reuses_committed_upstream_and_runs_only_final(
    tmp_path,
    with_identity: bool,
) -> None:
    agent = _RetryAgent()
    runtime, blueprint = _retry_runtime(tmp_path, agent, with_identity=with_identity)
    try:
        mission = runtime.create_mission("single-step retry", workflow_id="single-step-retry")
        plan = TaskPlan(
            missionId=mission.mission_id,
            nodes=tuple(
                PlannedTask(
                    key=f"step:{node.node_id}",
                    title=node.name or node.node_id,
                    objective=node.goal or node.node_id,
                    capabilityRequirements=(node.capability,) if node.capability else (),
                    logicalRole=node.logical_role,
                )
                for node in blueprint.step_nodes()
            ),
            relations=(TaskPlanRelation(
                sourceKey="step:source", targetKey="step:final", relationType="depends_on",
            ),),
        )
        mission.input.update({
            "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [
                TaskImplementationBinding(
                    planNodeKey=f"step:{node.node_id}",
                    acgNodeId=node.node_id,
                ).model_dump(by_alias=True, mode="json")
                for node in blueprint.step_nodes()
            ],
        })
        runtime.workflow_store.save_mission(mission)
        _, source = runtime.prepare_run(mission.mission_id)

        with pytest.raises(RuntimeError, match="ACG superstep failed"):
            asyncio.run(runtime.execute_prepared_run(source.run_id))

        failed = runtime.get_status(source.run_id)
        assert failed.status is WorkflowStatus.FAILED
        assert failed.get_step("source").status is StepStatus.COMPLETED
        assert failed.get_step("final").status is StepStatus.FAILED
        source_ref = failed.execution_state["outputRefs"]["source"]
        assert failed.active_step_ids == []
        failed.execution_state["activeStepIds"] = ["final"]
        runtime.workflow_store.save_run(failed)

        retry = runtime.prepare_single_step_retry(
            failed.run_id,
            "final",
            reason="retry the failed final node",
            expected_runtime_revision=failed.runtime_revision,
            idempotency_key="single-step-retry-request",
            idempotency_fingerprint="single-step-retry-fingerprint",
        )

        assert retry.run_id != failed.run_id
        assert retry.status is WorkflowStatus.PENDING
        assert retry.execution_state["graphVersion"] == failed.execution_state["graphVersion"]
        assert retry.execution_state["taskPlan"] == failed.execution_state["taskPlan"]
        assert retry.acg_blueprint == failed.acg_blueprint
        assert retry.execution_state["compiledACGPackage"]["packageVersion"] == 4
        assert retry.current_step_id == "final"
        assert retry.completed_step_ids == ["source"]
        assert retry.get_step("source").status is StepStatus.COMPLETED
        assert retry.get_step("final").status is StepStatus.PENDING
        assert retry.execution_state["singleStepRetry"] == {
            "sourceRunId": failed.run_id,
            "targetStepId": "final",
            "reason": "retry the failed final node",
            "reusedStepIds": ["source"],
        }
        retry_ref = retry.execution_state["outputRefs"]["source"]
        assert retry_ref != source_ref
        assert runtime.execution_value_store.get_output(
            run_id=retry.run_id,
            output_ref=retry_ref,
        ) == runtime.execution_value_store.get_output(
            run_id=failed.run_id,
            output_ref=source_ref,
        )
        assert failed.execution_state["outputRefs"]["source"] == source_ref

        repeated = runtime.prepare_single_step_retry(
            failed.run_id,
            "final",
            idempotency_key="single-step-retry-request",
            idempotency_fingerprint="single-step-retry-fingerprint",
        )
        assert repeated.run_id == retry.run_id

        result = asyncio.run(runtime.execute_prepared_run(retry.run_id))
        assert result.status is WorkflowStatus.COMPLETED
        assert result.execution_state["compiledACGPackage"]["packageVersion"] == 4
        assert result.completed_step_ids == ["source", "final"]
        assert agent.source_calls == 1
        assert agent.final_calls == 2
        assert result.output["outputRef"] == result.execution_state["outputRefs"]["final"]
        assert result.execution_state["reusedStepIds"] == ["source"]
    finally:
        if runtime.identity_lifecycle is not None:
            runtime.identity_lifecycle.lifecycle_service.close()


@pytest.mark.parametrize("with_identity", [False, True])
def test_checkpoint_resume_can_retry_failed_step_in_the_same_run(
    tmp_path,
    with_identity: bool,
) -> None:
    agent = _CheckpointResumeAgent()
    agents = AgentRegistry()
    agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="checkpoint-resume",
        name="checkpoint resume",
        domain="general",
        runtimeEngine="acg",
        steps=[WorkflowStepDefinition(
            stepId="placeholder",
            name="placeholder",
            agentName="checkpoint-agent",
        )],
    ))
    step_ids = ("source", "design", "final")
    blueprint = ACGBlueprint(
        graphId="checkpoint-resume-graph",
        nodes=[
            StepNode(
                nodeId=step_id,
                name=step_id,
                capability="analysis",
                outputSpec={
                    "type": "object",
                    "required": [step_id],
                    "properties": {step_id: {"type": "string"}},
                },
            )
            for step_id in step_ids
        ],
        edges=[
            ACGEdge(sourceId="source", targetId="design", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="design", targetId="final", edgeType=EdgeType.DEPENDENCY),
        ],
        resourcePlan=ACGResourcePlan(bindings=tuple(
            AgentBindingSpec(stepId=step_id, plannedAgentId="checkpoint-agent")
            for step_id in step_ids
        )),
    )
    identity_service = (
        AcgIdentityLifecycleService(SQLiteV2Repositories(SQLiteV2Storage(":memory:")))
        if with_identity
        else None
    )
    content_manifest_store = SQLiteContentManifestStore(tmp_path / "checkpoint-content.sqlite3")
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        execution_value_store=InMemoryExecutionValueStore(),
        content_manifest_store=content_manifest_store,
        identity_lifecycle=(
            IdentityProjectionBridge(
                identity_service,
                identity_service.repositories,
                content_manifest_store,
            )
            if identity_service is not None
            else None
        ),
    )
    mission = runtime.create_mission("checkpoint resume", workflow_id="checkpoint-resume")
    plan = TaskPlan(
        missionId=mission.mission_id,
        nodes=tuple(
            PlannedTask(
                key=f"step:{node.node_id}",
                title=node.name or node.node_id,
                objective=node.goal or node.node_id,
                capabilityRequirements=(node.capability,) if node.capability else (),
                logicalRole=node.logical_role,
            )
            for node in blueprint.step_nodes()
        ),
        relations=(
            TaskPlanRelation(sourceKey="step:source", targetKey="step:design", relationType="depends_on"),
            TaskPlanRelation(sourceKey="step:design", targetKey="step:final", relationType="depends_on"),
        ),
    )
    mission.input.update({
        "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
        "taskPlan": plan.model_dump(by_alias=True, mode="json"),
        "taskBindings": [
            TaskImplementationBinding(
                planNodeKey=f"step:{node.node_id}",
                acgNodeId=node.node_id,
            ).model_dump(by_alias=True, mode="json")
            for node in blueprint.step_nodes()
        ],
    })
    runtime.workflow_store.save_mission(mission)
    _, source = runtime.prepare_run(mission.mission_id)

    with pytest.raises(RuntimeError, match="ACG superstep failed"):
        asyncio.run(runtime.execute_prepared_run(source.run_id))

    failed = runtime.get_status(source.run_id)
    assert failed.get_step("source").status is StepStatus.COMPLETED
    assert failed.get_step("design").status is StepStatus.FAILED
    assert failed.get_step("final").status is StepStatus.PENDING

    retry = runtime.prepare_single_step_retry(
        failed.run_id,
        "design",
        reason="resume from the failed design step",
        idempotency_key="same-run-retry",
        idempotency_fingerprint="same-run-retry-fingerprint",
        reuse_source_run=True,
    )

    assert retry.run_id == failed.run_id
    assert retry.status is WorkflowStatus.RETRYING
    assert retry.execution_state["checkpointResume"] == {
        "sourceRunId": failed.run_id,
        "failedStepId": "design",
        "reason": "resume from the failed design step",
        "reusedStepIds": ["source"],
        "resumeStepIds": ["design", "final"],
        "mode": "current_run",
    }
    assert retry.get_step("source").status is StepStatus.COMPLETED
    assert retry.get_step("design").status is StepStatus.PENDING
    assert retry.get_step("final").status is StepStatus.PENDING
    if identity_service is not None:
        identity_run = identity_service.repositories.runs.get(retry.run_id)
        assert identity_run is not None
        assert identity_run.status is RunStatus.PENDING
        assert identity_run.finished_at is None
        assert retry.get_step("design").attempt == 1
        assert retry.get_step("final").attempt == 0

    result = asyncio.run(runtime.execute_prepared_run(retry.run_id))

    assert result.status is WorkflowStatus.COMPLETED
    assert result.completed_step_ids == ["source", "design", "final"]
    assert agent.calls == {"source": 1, "design": 2, "final": 1}
    if identity_service is not None:
        assert identity_service.repositories.runs.get(result.run_id).status is RunStatus.SUCCEEDED
        identity_service.close()


class _TwiceFailingDesignAgent(BaseAgent):
    """design fails on its first two executions, then succeeds."""

    def __init__(self) -> None:
        super().__init__(AgentProfile(
            agentName="checkpoint-agent",
            domain="general",
            capabilities=["analysis"],
        ))
        self.calls = {"source": 0, "design": 0, "final": 0}

    async def run(self, context):
        step_id = context.step.step_id
        self.calls[step_id] += 1
        if step_id == "design" and self.calls[step_id] <= 2:
            raise RuntimeError(f"planned design failure #{self.calls[step_id]}")
        return AgentOutput(output={step_id: f"{step_id}-output"}, summary=f"{step_id} ready")


def _twice_failure_runtime(tmp_path):
    agent = _TwiceFailingDesignAgent()
    agents = AgentRegistry()
    agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="checkpoint-resume",
        name="checkpoint resume",
        domain="general",
        runtimeEngine="acg",
        steps=[WorkflowStepDefinition(
            stepId="placeholder",
            name="placeholder",
            agentName="checkpoint-agent",
        )],
    ))
    step_ids = ("source", "design", "final")
    blueprint = ACGBlueprint(
        graphId="checkpoint-resume-graph",
        nodes=[
            StepNode(
                nodeId=step_id,
                name=step_id,
                capability="analysis",
                outputSpec={
                    "type": "object",
                    "required": [step_id],
                    "properties": {step_id: {"type": "string"}},
                },
            )
            for step_id in step_ids
        ],
        edges=[
            ACGEdge(sourceId="source", targetId="design", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="design", targetId="final", edgeType=EdgeType.DEPENDENCY),
        ],
        resourcePlan=ACGResourcePlan(bindings=tuple(
            AgentBindingSpec(stepId=step_id, plannedAgentId="checkpoint-agent")
            for step_id in step_ids
        )),
    )
    identity_service = AcgIdentityLifecycleService(
        SQLiteV2Repositories(SQLiteV2Storage(":memory:"))
    )
    content_manifest_store = SQLiteContentManifestStore(tmp_path / "twice-failure-content.sqlite3")
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        execution_value_store=InMemoryExecutionValueStore(),
        content_manifest_store=content_manifest_store,
        identity_lifecycle=IdentityProjectionBridge(
            identity_service,
            identity_service.repositories,
            content_manifest_store,
        ),
    )
    mission = runtime.create_mission("second checkpoint resume", workflow_id="checkpoint-resume")
    plan = TaskPlan(
        missionId=mission.mission_id,
        nodes=tuple(
            PlannedTask(
                key=f"step:{node.node_id}",
                title=node.name or node.node_id,
                objective=node.goal or node.node_id,
                capabilityRequirements=(node.capability,) if node.capability else (),
                logicalRole=node.logical_role,
            )
            for node in blueprint.step_nodes()
        ),
        relations=(
            TaskPlanRelation(sourceKey="step:source", targetKey="step:design", relationType="depends_on"),
            TaskPlanRelation(sourceKey="step:design", targetKey="step:final", relationType="depends_on"),
        ),
    )
    mission.input.update({
        "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
        "taskPlan": plan.model_dump(by_alias=True, mode="json"),
        "taskBindings": [
            TaskImplementationBinding(
                planNodeKey=f"step:{node.node_id}",
                acgNodeId=node.node_id,
            ).model_dump(by_alias=True, mode="json")
            for node in blueprint.step_nodes()
        ],
    })
    runtime.workflow_store.save_mission(mission)
    return runtime, identity_service, mission, agent


def test_second_in_place_resume_keeps_attempt_numbering_contiguous(tmp_path) -> None:
    """同一 Run 的第二次原地断点恢复不得毒化身份编号（2026-09-10 16:26 事故回归）。

    对"投影里已有 attempt 历史"的 step 再次发起断点恢复时，发射侧编号与投影
    既有行数必然错位；投影必须以 attemptId 为幂等锚点自动衔接编号，恢复链路
    才能继续复用已完成的 source 节点。
    """
    runtime, identity_service, mission, agent = _twice_failure_runtime(tmp_path)
    try:
        _, source = runtime.prepare_run(mission.mission_id)
        with pytest.raises(RuntimeError, match="ACG superstep failed"):
            asyncio.run(runtime.execute_prepared_run(source.run_id))

        first_retry = runtime.prepare_single_step_retry(
            source.run_id,
            "design",
            reason="first in-place resume",
            idempotency_key="same-run-retry-1",
            idempotency_fingerprint="same-run-retry-1-fingerprint",
            reuse_source_run=True,
        )
        assert first_retry.run_id == source.run_id
        assert first_retry.get_step("design").attempt == 1
        with pytest.raises(RuntimeError, match="ACG superstep failed"):
            asyncio.run(runtime.execute_prepared_run(first_retry.run_id))

        second_retry = runtime.prepare_single_step_retry(
            source.run_id,
            "design",
            reason="second in-place resume",
            idempotency_key="same-run-retry-2",
            idempotency_fingerprint="same-run-retry-2-fingerprint",
            reuse_source_run=True,
        )

        assert second_retry.run_id == source.run_id
        assert second_retry.status is WorkflowStatus.RETRYING
        assert second_retry.get_step("source").status is StepStatus.COMPLETED
        assert second_retry.get_step("design").attempt == 2

        result = asyncio.run(runtime.execute_prepared_run(second_retry.run_id))

        assert result.status is WorkflowStatus.COMPLETED
        assert result.completed_step_ids == ["source", "design", "final"]
        assert agent.calls == {"source": 1, "design": 3, "final": 1}

        repositories = identity_service.repositories
        assert repositories.runs.get(result.run_id).status is RunStatus.SUCCEEDED
        domain_run = repositories.runs.get(result.run_id)
        design_task = runtime.identity_lifecycle._resolve_semantic_task(
            domain_run.blueprint_id, "design"
        )
        design_attempts = sorted(
            (
                attempt
                for attempt in repositories.attempts.list_for_run(result.run_id)
                if attempt.task_id == design_task.task_id
            ),
            key=lambda attempt: attempt.attempt_number,
        )
        assert [attempt.attempt_number for attempt in design_attempts] == [1, 2, 3]
        assert design_attempts[-1].status is AttemptStatus.SUCCEEDED
    finally:
        identity_service.close()


def test_successor_resume_backfills_identity_attempts_for_reused_steps(tmp_path) -> None:
    """继任 Run 断点恢复必须为复用步骤补建 Attempt 投影（2026-09-19 Pending 事故回归）。

    继任 Run 不重新调度源 Run 已完成的步骤，调度器的 attempt.ensured 事件链不会
    发生；若不为它们补投影，Identity 侧永远没有这些任务在本 Run 的执行账目，
    Workspace 把已产出结果的任务显示为 Pending · Attempt 0。
    """
    agent = _RetryAgent()
    runtime, blueprint = _retry_runtime(tmp_path, agent, with_identity=True)
    try:
        mission = runtime.create_mission("successor resume backfill", workflow_id="single-step-retry")
        plan = TaskPlan(
            missionId=mission.mission_id,
            nodes=tuple(
                PlannedTask(
                    key=f"step:{node.node_id}",
                    title=node.name or node.node_id,
                    objective=node.goal or node.node_id,
                    capabilityRequirements=(node.capability,) if node.capability else (),
                    logicalRole=node.logical_role,
                )
                for node in blueprint.step_nodes()
            ),
            relations=(TaskPlanRelation(
                sourceKey="step:source", targetKey="step:final", relationType="depends_on",
            ),),
        )
        mission.input.update({
            "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [
                TaskImplementationBinding(
                    planNodeKey=f"step:{node.node_id}",
                    acgNodeId=node.node_id,
                ).model_dump(by_alias=True, mode="json")
                for node in blueprint.step_nodes()
            ],
        })
        runtime.workflow_store.save_mission(mission)
        _, source = runtime.prepare_run(mission.mission_id)

        with pytest.raises(RuntimeError, match="ACG superstep failed"):
            asyncio.run(runtime.execute_prepared_run(source.run_id))
        failed = runtime.get_status(source.run_id)
        failed.execution_state["activeStepIds"] = ["final"]
        runtime.workflow_store.save_run(failed)

        retry = runtime.prepare_single_step_retry(
            failed.run_id,
            "final",
            reason="resume after final-node failure",
        )

        identity_service = runtime.identity_lifecycle.lifecycle_service
        repositories = identity_service.repositories
        domain_run = repositories.runs.get(retry.run_id)
        assert domain_run is not None
        source_task = runtime.identity_lifecycle._resolve_semantic_task(
            domain_run.blueprint_id, "source"
        )
        backfilled = [
            attempt for attempt in repositories.attempts.list_for_run(retry.run_id)
            if attempt.task_id == source_task.task_id
        ]
        assert len(backfilled) == 1
        assert backfilled[0].status is AttemptStatus.SUCCEEDED
        assert backfilled[0].attempt_number == 1
        binding = repositories.execution_bindings.get_for_attempt(backfilled[0].attempt_id)
        assert binding is not None
        assert binding.acg_node_id == "source"
        assert binding.metadata.get("reusedFromRunId") == failed.run_id
        executions = repositories.step_executions.list_for_attempt(backfilled[0].attempt_id)
        assert [execution.status for execution in executions] == [StepExecutionStatus.SUCCEEDED]
        assert retry.execution_state["attemptIds"]["source:1:root"] == backfilled[0].attempt_id
        assert retry.execution_state["stepExecutionIds"]["source:1:root"] == executions[0].step_execution_id

        workspace = MissionWorkspaceProjector(
            repositories, runtime.content_manifest_store
        ).project(mission.mission_id, run_id=retry.run_id)
        source_entry = next(
            entry for entry in workspace.entries
            if entry.kind is WorkspaceEntryKind.TASK and entry.semantic_task_key == "step:source"
        )
        assert source_entry.status == "completed"
        assert source_entry.attempt_count == 1

        result = asyncio.run(runtime.execute_prepared_run(retry.run_id))
        assert result.status is WorkflowStatus.COMPLETED
        assert result.completed_step_ids == ["source", "final"]
        assert agent.source_calls == 1
        assert agent.final_calls == 2

        # 补投影入账不挤占真实执行Attempt：source 任务 1 条（补投影），
        # final 任务 1 条（继任 Run 真实执行）。
        final_task = runtime.identity_lifecycle._resolve_semantic_task(
            domain_run.blueprint_id, "final"
        )
        assert [
            attempt.task_id for attempt in repositories.attempts.list_for_run(retry.run_id)
        ].count(final_task.task_id) == 1
        assert repositories.runs.get(retry.run_id).status is RunStatus.SUCCEEDED
    finally:
        if runtime.identity_lifecycle is not None:
            runtime.identity_lifecycle.lifecycle_service.close()


def test_resume_projection_builder_locks_event_contract() -> None:
    """补投影事件构建器：四事件链形状、状态写回条目与 fail-fast 错误路径。"""
    kwargs = dict(
        run_id="run_child",
        mission_id="mission_x",
        reused_step_ids=["source"],
        copied_refs={"source": "ref-1"},
        copied_summaries={"source": "ok"},
        source_run_id="run_parent",
        source_execution_state={
            "executionBindings": {"source": {"resourceId": "agent-x", "bindingId": "binding:old"}},
        },
        source_step_counters={"source": (0, 0)},
        attempt_id_for=lambda step_id: f"attempt_{step_id}",
        step_execution_id_for=lambda step_id: f"step_execution_{step_id}",
    )
    events, state_updates = build_reused_step_projection_events(**kwargs)
    assert [event["eventType"] for event in events] == [
        "attempt.ensured", "resource.bound", "step.started", "step.succeeded",
    ]
    assert [event["eventId"] for event in events] == [
        "attempt.ensured:attempt_source",
        "resource.bound:attempt_source",
        "step.started:step_execution_source",
        "step.succeeded:step_execution_source",
    ]
    assert events[3]["payload"]["result"]["outputRef"] == "ref-1"
    binding = events[1]["payload"]["binding"]
    assert binding["runId"] == "run_child"
    assert binding["metadata"]["reusedFromRunId"] == "run_parent"
    assert binding["metadata"]["reusedFromBindingId"] == "binding:old"
    assert state_updates["attemptIds"] == {"source:1:root": "attempt_source"}
    assert state_updates["stepExecutionIds"] == {"source:1:root": "step_execution_source"}
    assert state_updates["executionBindings"]["source"]["bindingId"] == "binding:run_child:source:attempt_source"

    with pytest.raises(ValueError, match="source execution binding: ghost"):
        build_reused_step_projection_events(**dict(kwargs, reused_step_ids=["ghost"]))
    with pytest.raises(ValueError, match="no committed outputRef"):
        build_reused_step_projection_events(**dict(kwargs, copied_refs={}))

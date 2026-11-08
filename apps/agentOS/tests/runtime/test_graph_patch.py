"""Runtime transition tests for derived GraphPatch artifacts."""

from __future__ import annotations

import asyncio

import pytest

from components.executor import InMemoryExecutionValueStore
from components.mission_manager.store import WorkflowRegistry
from components.recovery.checkpoint import ACGCheckpointStore
from contracts.planning import (
    PlannedTask,
    TaskPlanPatch,
    TaskPlanRelation,
)
from contracts.recovery import SemanticPatchRequest
from contracts.workflow import (
    ReviewDecision,
    ReviewDecisionType,
    WorkflowDefinition,
    WorkflowStepDefinition,
)
from runtime import ExecutionRuntime
from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.models import ACGBlueprint
from support.stores.memory_workflow_store import MemoryWorkflowStore


class _Agent(BaseAgent):
    def __init__(self, agent_id="runner", name="runner", calls=None, priority=0):
        super().__init__(AgentProfile(
            agentId=agent_id,
            agentName=name,
            domain="general",
            capabilities=[
                "analysis",
                *(["task_understanding"] if name == "runner" else []),
            ],
            bindingPriority=priority,
        ))
        self.calls = calls if calls is not None else []

    async def run(self, context):
        self.calls.append(self.profile.agent_id)
        return AgentOutput(output={"value": self.profile.agent_id})


def _workflow():
    return WorkflowDefinition(
        workflowId="patchable",
        name="patchable",
        domain="general",
        runtimeEngine="acg",
        planningNodes=(
            PlannedTask(
                key="step:review",
                title="review",
                objective="review",
                capabilityRequirements=("task_understanding",),
            ),
            PlannedTask(
                key="step:deliver",
                title="deliver",
                objective="deliver",
                capabilityRequirements=("analysis",),
            ),
        ),
        planningRelations=(TaskPlanRelation(
            sourceKey="step:review",
            targetKey="step:deliver",
            relationType="depends_on",
        ),),
        steps=(
            WorkflowStepDefinition(
                stepId="review",
                name="review",
                agentName="runner",
                capability="task_understanding",
                reviewRequired=True,
            ),
            WorkflowStepDefinition(
                stepId="deliver",
                name="deliver",
                agentName="primary",
                capability="analysis",
            ),
        ),
    )


def _runtime(tmp_path, *, identity=True, agents=None):
    registry = agents or AgentRegistry()
    if not registry.all():
        registry.register(_Agent())
        registry.register(_Agent("primary", "primary"))
    workflows = WorkflowRegistry()
    workflows.register(_workflow())
    lifecycle = None
    bridge = None
    if identity:
        lifecycle = AcgIdentityLifecycleService(
            SQLiteV2Repositories(SQLiteV2Storage(":memory:"))
        )
        bridge = IdentityProjectionBridge(lifecycle, lifecycle.repositories)
    runtime = ExecutionRuntime(
        agent_registry=registry,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "cp.sqlite3"),
        execution_value_store=InMemoryExecutionValueStore(),
        identity_lifecycle=bridge,
    )
    return runtime, lifecycle


def _add_request(mission_id, paused, blueprint):
    relation = TaskPlanRelation(
        sourceKey="step:review", targetKey="step:deliver", relationType="depends_on"
    )
    return SemanticPatchRequest(
        patchId="add-enrich",
        idempotencyKey="add-enrich:v1",
        runId=paused.run_id,
        graphId=blueprint.graph_id,
        baseGraphVersion=blueprint.version,
        taskPlanPatch=TaskPlanPatch(
            missionId=mission_id,
            basePlanVersion=1,
            planVersion=2,
            addNodes=(PlannedTask(
                key="step:enrich",
                title="enrich",
                objective="enrich",
                capabilityRequirements=("analysis",),
            ),),
            removeRelations=(relation,),
            relations=(
                TaskPlanRelation(
                    sourceKey="step:review",
                    targetKey="step:enrich",
                    relationType="depends_on",
                ),
                TaskPlanRelation(
                    sourceKey="step:enrich",
                    targetKey="step:deliver",
                    relationType="depends_on",
                ),
            ),
        ),
    )


def test_semantic_revision_creates_atomic_replacement_identity_run(tmp_path):
    runtime, lifecycle = _runtime(tmp_path)
    try:
        mission = runtime.create_mission("patch", workflow_id="patchable")
        paused = asyncio.run(runtime.start(mission.mission_id, workflow_id="patchable"))
        blueprint = ACGBlueprint.model_validate(paused.acg_blueprint)
        result = asyncio.run(runtime.apply_semantic_patch(
            _add_request(mission.mission_id, paused, blueprint)
        ))
        old_run = lifecycle.repositories.runs.get(paused.run_id)
        new_run = lifecycle.repositories.runs.get(result.run_id)
        assert old_run.status.value == "superseded"
        assert new_run.graph_version == blueprint.version + 1
        assert new_run.metadata["parentRunId"] == paused.run_id
        assert len(lifecycle.repositories.task_bindings.find_for_acg_node(
            "enrich", new_run.blueprint_id
        )) == 1
    finally:
        lifecycle.close()


def test_semantic_revision_rolls_back_identity_when_supersede_fails(tmp_path, monkeypatch):
    runtime, lifecycle = _runtime(tmp_path)
    try:
        mission = runtime.create_mission("rollback", workflow_id="patchable")
        paused = asyncio.run(runtime.start(mission.mission_id, workflow_id="patchable"))
        blueprint = ACGBlueprint.model_validate(paused.acg_blueprint)
        original_finish = runtime.identity_lifecycle.lifecycle_service.finish_run

        def fail(run_id, status):
            if status.value == "superseded":
                raise RuntimeError("simulated supersede failure")
            return original_finish(run_id, status)

        monkeypatch.setattr(
            runtime.identity_lifecycle.lifecycle_service, "finish_run", fail
        )
        with pytest.raises(RuntimeError, match="simulated supersede failure"):
            asyncio.run(runtime.apply_semantic_patch(
                _add_request(mission.mission_id, paused, blueprint)
            ))
        assert [item.run_id for item in lifecycle.repositories.runs.list_for_mission(
            mission.mission_id
        )] == [paused.run_id]
    finally:
        lifecycle.close()


def test_resource_rebind_changes_runtime_binding_without_graph_revision(tmp_path):
    calls = []
    agents = AgentRegistry()
    agents.register(_Agent())
    agents.register(_Agent("primary", "primary", calls, 10))
    agents.register(_Agent("alternate", "alternate", calls, 5))
    runtime, lifecycle = _runtime(tmp_path, identity=True, agents=agents)
    mission = runtime.create_mission("rebind", workflow_id="patchable")
    paused = asyncio.run(runtime.start(mission.mission_id, workflow_id="patchable"))
    graph_version = paused.execution_state["graphVersion"]
    task_plan = paused.execution_state["taskPlan"]
    paused.execution_state["resourceBindings"]["deliver"] = "primary"
    paused.execution_state["bindingRequirements"]["deliver"]["preferences"] = {
        "resourceId": "primary"
    }
    runtime.workflow_store.save_run(paused)

    selected = asyncio.run(runtime.rebind_step(
        run_id=paused.run_id, step_id="deliver", reason="primary unavailable"
    ))
    after = runtime.workflow_store.get_run(paused.run_id)
    assert selected == "alternate"
    assert after.execution_state["graphVersion"] == graph_version
    assert after.execution_state["taskPlan"] == task_plan

    asyncio.run(runtime.apply_review(ReviewDecision(
        runId=paused.run_id,
        stepId="review",
        decision=ReviewDecisionType.APPROVED,
        operationId="approve-rebound",
    )))
    assert calls == ["alternate"]
    lifecycle.close()

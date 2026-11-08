from __future__ import annotations

from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec
from support.acg.models import ACGEdge, EdgeType


import sqlite3
from types import SimpleNamespace

import pytest

from components.content import SQLiteContentManifestStore
from components.executor.node_runner import ACGNodeRunner
from contracts.artifacts import final_synthesis_output_schema
from contracts.content import ContentKind
from contracts.planning import PlannedTask, TaskImplementationBinding, TaskPlan
from contracts.resource import ExecutionBinding as RuntimeExecutionBinding, RuntimeKind
from domain.identity_graph import RunArtifactDisposition
from domain.repository import IdentityConflictError
from runtime import (
    AcgIdentityLifecycleService,
    IdentityProjectionBridge,
    IdentityQueryService,
    PlannerIdentityBridge,
)
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.models import ACGBlueprint, StepNode


def test_final_synthesis_output_schema_accepts_canonical_run_deliverable_type() -> None:
    schema = {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "properties": {"type": {"type": "string", "enum": ["report"]}},
            },
        },
    }

    compatible = final_synthesis_output_schema(schema, "finalization")

    assert schema["properties"]["artifact"]["properties"]["type"]["enum"] == ["report"]
    assert compatible["properties"]["artifact"]["properties"]["type"]["enum"] == [
        "report", "run_deliverable",
    ]


def _foundation(tmp_path):
    storage = SQLiteV2Storage(tmp_path / "identity.sqlite3")
    repositories = SQLiteV2Repositories(storage)
    service = AcgIdentityLifecycleService(repositories)
    content = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    bridge = IdentityProjectionBridge(service, repositories, content)
    return storage, service, bridge, content


def _runtime_binding(run_id: str, attempt_id: str, step_id: str) -> RuntimeExecutionBinding:
    return RuntimeExecutionBinding(
        bindingId=f"binding:{run_id}:{step_id}:{attempt_id}",
        runId=run_id,
        stepId=step_id,
        attemptId=attempt_id,
        resourceId="agent-equipment",
        runtimeKind=RuntimeKind.EXECUTION_BACKEND,
        snapshotVersion=1,
    )


def _prepare_identity_chain(service, bridge):
    mission = service.create_mission(user_id="user-1", goal="设备人员规划")
    plan = TaskPlan(
        missionId=mission.mission_id,
        planVersion=1,
        nodes=(PlannedTask(
            key="equipment_staff_plan",
            title="设备人员规划",
            objective="形成设备与人员配置方案",
        ),),
    )
    planner = PlannerIdentityBridge(service)
    first = planner.record_task_plan(plan)["equipment_staff_plan"]
    changed = planner.record_task_plan(TaskPlan(
        missionId=mission.mission_id,
        planVersion=2,
        nodes=(PlannedTask(
            key="equipment_staff_plan",
            title="设备人员规划（补充约束）",
            objective="在新的预算约束下形成设备与人员配置方案",
            constraints=[{"type": "budget", "value": "updated"}],
        ),),
    ))["equipment_staff_plan"]
    assert changed.task_id == first.task_id

    blueprint = bridge.register_blueprint(
        mission_id=mission.mission_id,
        version=1,
        runtime_blueprint=ACGBlueprint(
            graphId="acg_equipment_staff",
            missionId=mission.mission_id,
            nodes=[StepNode(
                nodeId="equipment-node",
                name="设备人员规划",

                capability="planning",
            )],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="equipment-node", plannedAgentId="planning-agent"),)),
        edges=[]),
        task_bindings={changed.task_id: "equipment-node"},
    )
    return mission, changed, blueprint


def _produce_artifacts(service, bridge, content, run, task, *items):
    attempt = service.create_attempt(run_id=run.run_id, task_id=task.task_id)
    bridge.record_scheduling_binding(
        attempt_id=attempt.attempt_id,
        runtime_binding=_runtime_binding(run.run_id, attempt.attempt_id, "equipment-node"),
        agent_id="agent-equipment",
        model_id="model-1",
    )
    execution = bridge.start_execution(
        service.create_context(run.run_id),
        input={"acgNodeId": "equipment-node"},
    )
    descriptors = []
    for artifact_key, body in items:
        manifest = content.create_from_bytes(
            content=body.encode("utf-8"),
            kind=ContentKind.ARTIFACT,
            owner_type="run",
            owner_id=run.run_id,
            media_type="text/markdown",
        )
        descriptors.append({
            "artifactKey": artifact_key,
            "title": artifact_key,
            "type": "report",
            "manifestId": manifest.manifest_id,
            "checksum": manifest.checksum,
        })
    bridge.on_step_succeeded(
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        step_execution_id=execution.step_execution_id,
        result={"outputSummary": "done", "artifacts": descriptors},
    )
    return attempt


def test_node_runner_persists_bodies_as_sealed_manifests_and_returns_references(tmp_path):
    content = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    try:
        runner = object.__new__(ACGNodeRunner)
        runner.content_manifest_store = content
        runner.task = SimpleNamespace(input={"attachmentIds": ["att_contract", "att_contract"]})
        normalized = runner._persist_artifact_manifest(
            run_id="run_0123456789ab",
            step_id="equipment-node",
            controlled={
                "artifact": {
                    "title": "primary",
                    "type": "report",
                    "mediaType": "text/markdown",
                    "content": "# immutable body",
                },
                "artifacts": [{
                    "artifactKey": "assumptions",
                    "title": "assumptions",
                    "type": "report",
                    "mediaType": "text/markdown",
                    "content": "- assumption",
                }],
            },
        )
        descriptors = runner._safe_artifact_descriptors(normalized)
        assert {item["artifactKey"] for item in descriptors} == {"assumptions"}
        assert all("content" not in item for item in descriptors)
        assert descriptors[0]["metadata"]["sourceAttachmentIds"] == ["att_contract"]
        manifest_id = descriptors[0]["manifestId"]
        manifest = content.get_manifest(manifest_id)
        assert manifest.kind is ContentKind.ARTIFACT
        assert manifest.sealed is True
        assert content.assemble(manifest_id) == b"- assumption"
    finally:
        content.close()


def test_artifact_projection_supports_multiple_artifacts_and_reverse_identity(tmp_path):
    storage, service, bridge, content = _foundation(tmp_path)
    try:
        mission, task, blueprint = _prepare_identity_chain(service, bridge)
        run_one = service.create_run(
            mission_id=mission.mission_id, blueprint_id=blueprint.blueprint_id
        )
        attempt_one = _produce_artifacts(
            service,
            bridge,
            content,
            run_one,
            task,
            ("primary", "# plan\nrun one"),
            ("equipment_table", "| equipment | count |\n| - | - |\n| A | 1 |"),
        )
        artifacts_one = service.repositories.artifacts.list_for_attempt(attempt_one.attempt_id)
        assert {item.artifact_key for item in artifacts_one} == {
            "primary", "equipment_table"
        }
        assert all(item.origin_run_id == run_one.run_id for item in artifacts_one)
        assert all(item.content_ref.startswith("manifest_") for item in artifacts_one)

        run_two = service.create_run(
            mission_id=mission.mission_id, blueprint_id=blueprint.blueprint_id
        )
        attempt_two = _produce_artifacts(
            service,
            bridge,
            content,
            run_two,
            task,
            ("primary", "# plan\nrun two"),
        )
        binding = service.repositories.run_artifact_bindings.find_for_slot(
            run_two.run_id, "equipment_staff_plan", "primary"
        )
        assert binding is not None
        assert binding.disposition is RunArtifactDisposition.GENERATED
        assert binding.source_run_id is None

        query = IdentityQueryService(service.repositories)
        attempt_detail = query.get_attempt(attempt_one.attempt_id)
        assert len(attempt_detail.artifacts) == 2
        run_details = query.artifacts_for_run(run_two.run_id)
        assert len(run_details) == 1
        assert run_details[0].artifact.producer_attempt_id == attempt_two.attempt_id

        # The reverse chain is represented by immutable foreign-key relations.
        artifact = artifacts_one[0]
        producer = service.repositories.attempts.get(artifact.producer_attempt_id)
        semantic_task = service.repositories.semantic_tasks.get(producer.task_id)
        origin_run = service.repositories.runs.get(producer.run_id)
        assert producer.run_id == run_one.run_id
        assert semantic_task.semantic_task_key == "equipment_staff_plan"
        assert origin_run.mission_id == mission.mission_id
        assert service.repositories.missions.get(origin_run.mission_id).mission_id == mission.mission_id

        with storage.read() as conn:
            with pytest.raises(sqlite3.IntegrityError, match="Artifact is immutable"):
                conn.execute(
                    "UPDATE artifacts SET name = 'rewritten' WHERE artifact_id = ?",
                    (artifact.artifact_id,),
                )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "DELETE FROM artifacts WHERE artifact_id = ?",
                    (artifact.artifact_id,),
                )
        assert not hasattr(service.repositories.artifacts, "update")
        assert not hasattr(service.repositories.artifacts, "delete")
    finally:
        content.close()
        service.close()


def test_run_preparation_allocates_snapshot_version_without_changing_logical_key(tmp_path):
    _storage, service, bridge, content = _foundation(tmp_path)
    try:
        mission = service.create_mission(user_id="user-1", goal="稳定任务身份")
        blueprint = ACGBlueprint(
            graphId="acg_stable_task",
            missionId=mission.mission_id,
            nodes=[StepNode(nodeId="stable-node", name="稳定步骤")],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="stable-node", plannedAgentId="agent"),)),
        edges=[])
        binding = TaskImplementationBinding(
            planNodeKey="stable_logical_step", acgNodeId="stable-node"
        )
        first_plan = TaskPlan(
            missionId=mission.mission_id,
            planVersion=1,
            nodes=(PlannedTask(
                key="stable_logical_step",
                title="第一版标题",
                objective="第一版目标",
            ),),
        )
        bridge.on_run_prepared(
            SimpleNamespace(mission_id=mission.mission_id),
            SimpleNamespace(
                run_id=bridge.new_run_id(mission.mission_id),
                mission_id=mission.mission_id,
                workflow_id="stable-workflow",
            ),
            blueprint,
            first_plan,
            (binding,),
        )
        second_plan = first_plan.model_copy(update={
            "nodes": (PlannedTask(
                key="stable_logical_step",
                title="第二版标题",
                objective="第二版目标和约束",
                constraints=[{"type": "revision", "value": 2}],
            ),),
        })
        bridge.on_run_prepared(
            SimpleNamespace(mission_id=mission.mission_id),
            SimpleNamespace(
                run_id=bridge.new_run_id(mission.mission_id),
                mission_id=mission.mission_id,
                workflow_id="stable-workflow",
            ),
            blueprint,
            second_plan,
            (binding,),
        )

        tasks = service.repositories.semantic_tasks.list_for_mission(mission.mission_id)
        assert len(tasks) == 1
        assert tasks[0].semantic_task_key == "stable_logical_step"
        assert [plan.plan_version for plan in service.repositories.task_plans.list_for_mission(
            mission.mission_id
        )] == [1, 2]
    finally:
        content.close()
        service.close()


def test_run_artifact_binding_slot_is_unique_and_not_artifact_id(tmp_path):
    _storage, service, bridge, content = _foundation(tmp_path)
    try:
        mission, task, blueprint = _prepare_identity_chain(service, bridge)
        run = service.create_run(
            mission_id=mission.mission_id, blueprint_id=blueprint.blueprint_id
        )
        _produce_artifacts(service, bridge, content, run, task, ("primary", "one"))
        existing = service.repositories.run_artifact_bindings.find_for_slot(
            run.run_id, task.semantic_task_key, "primary"
        )
        assert existing is not None
        with pytest.raises(IdentityConflictError, match="slot"):
            service.repositories.run_artifact_bindings.add(existing.model_copy(update={
                "binding_id": "binding_0123456789ab",
                "artifact_id": existing.artifact_id,
            }))
    finally:
        content.close()
        service.close()


def test_v2_schema_migrates_legacy_semantic_key_only_when_unambiguous(tmp_path):
    path = tmp_path / "legacy-v2.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE semantic_tasks (
                task_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                parent_task_id TEXT,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                constraints_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        conn.execute(
            """INSERT INTO semantic_tasks(
                task_id, mission_id, title, objective, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "task_0123456789ab",
                "mission_0123456789ab",
                "设备人员规划",
                "形成配置方案",
                "created",
                '{"plannerSemanticKey":"equipment_staff_plan"}',
            ),
        )
        conn.execute("PRAGMA user_version = 1")

    with SQLiteV2Storage(path) as storage:
        with storage.read() as conn:
            row = conn.execute(
                "SELECT semantic_key FROM semantic_tasks WHERE task_id = ?",
                ("task_0123456789ab",),
            ).fetchone()
            version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert row[0] == "equipment_staff_plan"
    assert version == 3

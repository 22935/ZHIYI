from __future__ import annotations


import pytest

from components.content import SQLiteContentManifestStore
from contracts.content import ContentKind
from contracts.planning import PlannedTask, TaskPlan
from contracts.resource import ExecutionBinding as RuntimeExecutionBinding, RuntimeKind
from domain.models import RunStatus
from domain.repository import IdentityConflictError
from runtime import (
    AcgIdentityLifecycleService,
    IdentityProjectionBridge,
    IdentityQueryService,
    PlannerIdentityBridge,
    WorkspaceEntryKind,
    WorkspaceIdentityQuality,
)
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec
from support.acg.models import ACGBlueprint, ACGEdge, EdgeType, StepNode


def _foundation(tmp_path):
    storage = SQLiteV2Storage(tmp_path / "identity.sqlite3")
    repositories = SQLiteV2Repositories(storage)
    service = AcgIdentityLifecycleService(repositories)
    content = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    bridge = IdentityProjectionBridge(service, repositories, content)
    query = IdentityQueryService(repositories, content)
    return storage, service, bridge, content, query


def _runtime_binding(run_id: str, attempt_id: str, node_id: str) -> RuntimeExecutionBinding:
    return RuntimeExecutionBinding(
        bindingId=f"binding:{run_id}:{node_id}:{attempt_id}",
        runId=run_id,
        stepId=node_id,
        attemptId=attempt_id,
        resourceId="agent-workspace",
        runtimeKind=RuntimeKind.EXECUTION_BACKEND,
        snapshotVersion=1,
    )


def _mission_graph(service, bridge, *, final_role="deliverable"):
    mission = service.create_mission(user_id="user-1", goal="设备人员规划")
    plan = TaskPlan(
        missionId=mission.mission_id,
        planVersion=1,
        nodes=(
            PlannedTask(
                key="equipment_plan",
                title="设备规划",
                objective="形成设备配置方案",
                constraints=[{"type": "budget", "value": "fixed"}],
                capabilityRequirements=("resource_planning",),
            ),
            PlannedTask(
                key="final_delivery",
                title="最终交付",
                objective="汇总并交付最终方案",
                capabilityRequirements=("artifact_generation",),
                logicalRole=final_role,
            ),
        ),
    )
    tasks = PlannerIdentityBridge(service).record_task_plan(plan)
    blueprint = bridge.register_blueprint(
        mission_id=mission.mission_id,
        version=1,
        runtime_blueprint=ACGBlueprint(
            graphId="acg_workspace",
            missionId=mission.mission_id,
            nodes=[
                StepNode(
                    nodeId="equipment-node",
                    name="设备规划",

                    capability="resource_planning",
                ),
                StepNode(
                    nodeId="final-node",
                    name="最终交付",

                    capability="artifact_generation",
                    logicalRole=final_role,
                )],
            resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="equipment-node", plannedAgentId="planning-agent"), AgentBindingSpec(stepId="final-node", plannedAgentId="delivery-agent"),)),
        edges=[ACGEdge(sourceId="equipment-node", targetId="final-node", edgeType=EdgeType.DEPENDENCY)],
        ),
        task_bindings={
            tasks["equipment_plan"].task_id: "equipment-node",
            tasks["final_delivery"].task_id: "final-node",
        },
    )
    return mission, tasks, blueprint


def _run(service, mission_id: str, blueprint_id: str, *, status: RunStatus | None = None, metadata=None):
    run = service.create_run(
        mission_id=mission_id,
        blueprint_id=blueprint_id,
        metadata={"taskPlanVersion": 1, **(metadata or {})},
    )
    if status is not None:
        run = service.repositories.runs.update_status(run.run_id, status)
    return run


def _artifacts(service, bridge, content, run, task_id: str, node_id: str, items):
    attempt = service.create_attempt(run_id=run.run_id, task_id=task_id)
    bridge.record_scheduling_binding(
        attempt_id=attempt.attempt_id,
        runtime_binding=_runtime_binding(run.run_id, attempt.attempt_id, node_id),
        agent_id="agent-workspace",
        model_id="model-workspace",
    )
    execution = bridge.start_execution(
        service.create_context(run.run_id),
        input={"acgNodeId": node_id},
    )
    manifests = []
    descriptors = []
    for artifact_key, body in items:
        manifest = content.create_from_bytes(
            content=body.encode("utf-8"),
            kind=ContentKind.ARTIFACT,
            owner_type="run",
            owner_id=run.run_id,
            media_type="text/markdown",
        )
        manifests.append(manifest)
        descriptors.append({
            "artifactKey": artifact_key,
            "title": artifact_key,
            "artifactType": (
                "run_deliverable"
                if artifact_key == "final"
                else "primary_artifact"
            ),
            "type": "run_deliverable" if artifact_key == "final" else "primary_artifact",
            "manifestId": manifest.manifest_id,
            "checksum": manifest.checksum,
        })
    bridge.on_step_succeeded(
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        step_execution_id=execution.step_execution_id,
        result={"artifacts": descriptors},
    )
    return attempt, manifests


def _artifact(service, bridge, content, run, task_id: str, node_id: str, artifact_key: str, body: str):
    attempt, manifests = _artifacts(
        service, bridge, content, run, task_id, node_id, [(artifact_key, body)]
    )
    return attempt, manifests[0]


def _close(foundation):
    _storage, service, _bridge, content, _query = foundation
    content.close()
    service.close()


def test_workspace_mission_one_run_has_default_virtual_structure_and_no_store(tmp_path):
    foundation = _foundation(tmp_path)
    storage, service, bridge, _content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        projection = query.mission_workspace(mission.mission_id)

        assert projection.active_run.run_id == run.run_id
        assert projection.active_graph["graphId"] == blueprint.graph_id
        assert projection.active_graph["graphVersion"] == run.graph_version
        assert {
            entry.entry_id for entry in projection.entries if entry.kind is WorkspaceEntryKind.FOLDER
        } == {"folder:overview", "folder:steps", "folder:output", "folder:runs"}
        assert {entry.entry_id for entry in projection.entries} >= {
            "folder:overview", "folder:steps", "folder:output", "folder:runs",
            "overview:graph.acg", "overview:mission.md", f"run:{run.run_id}",
        }
        task_entries = [entry for entry in projection.entries if entry.kind is WorkspaceEntryKind.TASK]
        assert [entry.semantic_task_key for entry in task_entries] == ["equipment_plan", "final_delivery"]
        assert all(entry.artifact_count == 0 for entry in task_entries)
        with storage.read() as conn:
            assert conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'workspace'"
            ).fetchone() is None
    finally:
        _close(foundation)


def test_workspace_multiple_runs_and_explicit_historical_selection(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, _content, query = foundation
    try:
        mission, _tasks, blueprint = _mission_graph(service, bridge)
        first = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        second = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.RUNNING)

        latest = query.mission_workspace(mission.mission_id)
        historical = query.mission_workspace(mission.mission_id, run_id=first.run_id)
        assert latest.active_run.run_id == second.run_id
        assert historical.active_run.run_id == first.run_id
        assert [item.run_id for item in latest.runs] == [first.run_id, second.run_id]
        assert sum(item.is_active for item in latest.runs) == 1
        assert latest.runs[-1].is_active is True
    finally:
        _close(foundation)


def test_workspace_graph_entry_and_graph_node_mapping_do_not_create_content(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.RUNNING)
        _attempt, _manifest = _artifact(
            service, bridge, content, run, tasks["equipment_plan"].task_id,
            "equipment-node", "primary", "equipment body",
        )
        projection = query.mission_workspace(mission.mission_id)
        graph_entry = next(item for item in projection.entries if item.kind is WorkspaceEntryKind.GRAPH)
        assert graph_entry.run_id == run.run_id
        assert graph_entry.graph_id == blueprint.graph_id
        assert graph_entry.content_ref is None
        assert {node.semantic_task_key for node in projection.graph_nodes} >= {"equipment_plan", "final_delivery"}
        assert all(node.acg_node_id != "equipment_plan" for node in projection.graph_nodes)
        equipment_task = next(entry for entry in projection.entries if entry.entry_id == "task:equipment_plan")
        assert equipment_task.status == "completed"
        assert equipment_task.attempt_count == 1
        assert equipment_task.latest_attempt_id is not None
        equipment_artifact = next(entry for entry in projection.entries if entry.kind is WorkspaceEntryKind.ARTIFACT)
        assert equipment_artifact.parent_entry_id == equipment_task.entry_id
        assert equipment_artifact.created_at.utcoffset().total_seconds() == 0
        # Existing rows predate timezone-aware ContentManifest serialization.
        with _storage.transaction() as db:
            legacy = dict(db.execute("SELECT * FROM artifacts WHERE origin_run_id = ?", (run.run_id,)).fetchone())
            legacy.update(artifact_id="artifact_0123456789ab", created_at="2026-10-04 14:49:39")
            legacy["content_ref"] += "-legacy"
            db.execute(f"INSERT INTO artifacts ({','.join(legacy)}) VALUES ({','.join('?' for _ in legacy)})",
                       tuple(legacy.values()))
        historical = service.repositories.artifacts.get("artifact_0123456789ab")
        assert historical.model_dump(by_alias=True, mode="json")["createdAt"] == "2026-10-04T14:49:39Z"
    finally:
        _close(foundation)


def test_workspace_mission_document_is_virtual_and_contains_plan_context(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, _content, query = foundation
    try:
        mission, _tasks, blueprint = _mission_graph(service, bridge)
        _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        document = next(item for item in query.mission_workspace(mission.mission_id).entries if item.name == "mission.md")
        assert document.kind is WorkspaceEntryKind.VIRTUAL_DOCUMENT
        assert "设备人员规划" in document.content
        assert "形成设备配置方案" in document.content
        assert "fixed" in document.content
    finally:
        _close(foundation)


def test_workspace_artifact_entries_support_multiple_slots_and_final_output(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, run, tasks["equipment_plan"].task_id, "equipment-node", "primary", "table")
        attempt, _manifests = _artifacts(
            service, bridge, content, run,
            tasks["final_delivery"].task_id,
            "final-node",
            [("final", "final"), ("assumptions", "assumptions")],
        )
        projection = query.mission_workspace(mission.mission_id)
        artifacts = [item for item in projection.entries if item.kind is WorkspaceEntryKind.ARTIFACT]
        assert {item.artifact_key for item in artifacts} == {"primary", "final", "assumptions"}
        assert {item.group for item in artifacts} == {"steps", "output"}
        final = next(item for item in artifacts if item.artifact_key == "final" and item.group == "output")
        assert final.name == "final.md"
        assert final.parent_entry_id == "folder:output"
        assert final.logical_role == "final_synthesis"
        assert final.artifact_type == "run_deliverable"
        assert next(item for item in projection.entries if item.entry_id == "task:final_delivery").artifact_count == 2
        assert all(item.content is None for item in artifacts)
    finally:
        _close(foundation)


def test_workspace_rejects_a_second_run_deliverable_slot(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, _query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, run, tasks["final_delivery"].task_id, "final-node", "final", "first final")
        with pytest.raises(IdentityConflictError, match="RunArtifactBinding slot"):
            _artifact(service, bridge, content, run, tasks["final_delivery"].task_id, "final-node", "final", "second final")
    finally:
        _close(foundation)


def test_workspace_aggregate_primary_artifact_is_projected_to_output(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge, final_role="aggregate")
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, run, tasks["final_delivery"].task_id, "final-node", "final", "final report")

        artifacts = [
            item for item in query.mission_workspace(mission.mission_id).entries
            if item.kind is WorkspaceEntryKind.ARTIFACT
        ]

        assert len(artifacts) == 1
        assert artifacts[0].group == "output"
        assert artifacts[0].name == "final.md"
        assert artifacts[0].parent_entry_id == "folder:output"
    finally:
        _close(foundation)


def test_workspace_artifact_entry_id_and_graph_mapping_are_stable(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        first = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, first, tasks["equipment_plan"].task_id, "equipment-node", "primary", "first")
        second = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, second, tasks["equipment_plan"].task_id, "equipment-node", "primary", "second")
        first_projection = query.mission_workspace(mission.mission_id, run_id=first.run_id)
        second_projection = query.mission_workspace(mission.mission_id, run_id=second.run_id)
        first_entry = next(item for item in first_projection.entries if item.kind is WorkspaceEntryKind.ARTIFACT)
        second_entry = next(item for item in second_projection.entries if item.kind is WorkspaceEntryKind.ARTIFACT)
        assert first_entry.entry_id == second_entry.entry_id == "task:equipment_plan:primary"
        assert first_entry.artifact_id != second_entry.artifact_id
        assert first_entry.semantic_task_key == second_entry.semantic_task_key == "equipment_plan"
        assert first_entry.acg_node_id == second_entry.acg_node_id == "equipment-node"
        assert first_entry.identity_quality is WorkspaceIdentityQuality.CANONICAL
    finally:
        _close(foundation)


def test_workspace_legacy_identity_is_explicit_and_never_guessed(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission = service.create_mission(user_id="user-1", goal="legacy workspace")
        legacy_task = service.create_task(
            mission_id=mission.mission_id,
            title="旧任务",
            objective="旧任务目标",
        )
        blueprint = bridge.register_blueprint(
            mission_id=mission.mission_id,
            version=1,
            runtime_blueprint=ACGBlueprint(
                graphId="acg_legacy_workspace",
                missionId=mission.mission_id,
                nodes=[StepNode(nodeId="legacy-node", name="旧任务")],
            resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="legacy-node", plannedAgentId="legacy-agent"),)),
        edges=[]),
            task_bindings={legacy_task.task_id: "legacy-node"},
        )
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.FAILED)
        content.create_from_bytes(
            content=b"legacy body",
            kind=ContentKind.ARTIFACT,
            owner_type="run",
            owner_id=run.run_id,
            media_type="text/markdown",
        )
        projection = query.mission_workspace(mission.mission_id)
        legacy = next(item for item in projection.entries if item.entry_id.startswith("legacy:"))
        assert legacy.identity_quality is WorkspaceIdentityQuality.LEGACY
        assert legacy.semantic_task_key is None
        assert legacy.artifact_id is None
        legacy_task = next(item for item in projection.entries if item.kind is WorkspaceEntryKind.TASK)
        assert legacy_task.entry_id == f"task:legacy:{legacy_task.task_id}"
        assert legacy_task.identity_quality is WorkspaceIdentityQuality.LEGACY
        assert any(item.code == "LEGACY_ARTIFACT_IDENTITY" for item in projection.diagnostics)
        graph_node = next(item for item in projection.graph_nodes if item.acg_node_id == "legacy-node")
        assert graph_node.identity_quality is WorkspaceIdentityQuality.LEGACY
        assert graph_node.semantic_task_key is None
    finally:
        _close(foundation)


def test_workspace_missing_active_run_failed_run_and_partial_run_are_readable(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission = service.create_mission(user_id="user-1", goal="empty workspace")
        empty = query.mission_workspace(mission.mission_id)
        assert empty.active_run is None
        assert "overview:graph.acg" not in {item.entry_id for item in empty.entries}
        assert any(item.code == "NO_ACTIVE_RUN" for item in empty.diagnostics)

        mission, tasks, blueprint = _mission_graph(service, bridge)
        failed = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.FAILED)
        failed_projection = query.mission_workspace(mission.mission_id)
        assert failed_projection.active_run.run_id == failed.run_id
        assert failed_projection.active_run.status is RunStatus.FAILED

        partial = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.RUNNING)
        _artifact(service, bridge, content, partial, tasks["equipment_plan"].task_id, "equipment-node", "primary", "partial")
        partial_projection = query.mission_workspace(mission.mission_id)
        assert partial_projection.active_run.run_id == partial.run_id
        assert any(item.run_id == partial.run_id for item in partial_projection.entries if item.kind is WorkspaceEntryKind.ARTIFACT)
    finally:
        _close(foundation)


def test_workspace_entry_order_is_deterministic_and_unique(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, run, tasks["final_delivery"].task_id, "final-node", "assumptions", "a")
        _artifact(service, bridge, content, run, tasks["equipment_plan"].task_id, "equipment-node", "primary", "b")
        first = query.mission_workspace(mission.mission_id).model_dump(by_alias=True, mode="json", exclude_none=True)
        second = query.mission_workspace(mission.mission_id).model_dump(by_alias=True, mode="json", exclude_none=True)
        first_ids = [item["entryId"] for item in first["entries"]]
        second_ids = [item["entryId"] for item in second["entries"]]
        assert first_ids == second_ids
        assert len(first_ids) == len(set(first_ids))
        assert first_ids.index("task:equipment_plan") < first_ids.index("task:equipment_plan:primary")
        assert first_ids.index("task:final_delivery") < first_ids.index("task:final_delivery:assumptions")
    finally:
        _close(foundation)


def test_workspace_does_not_treat_latest_task_plan_as_historical_run_truth(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, _content, query = foundation
    try:
        mission, _tasks, blueprint = _mission_graph(service, bridge)
        run = _run(
            service,
            mission.mission_id,
            blueprint.blueprint_id,
            status=RunStatus.SUCCEEDED,
            metadata={"taskPlanVersion": None},
        )

        projection = query.mission_workspace(mission.mission_id, run_id=run.run_id)
        document = next(item for item in projection.entries if item.entry_id == "overview:mission.md")

        assert any(item.code == "PLAN_SNAPSHOT_UNRESOLVED" for item in projection.diagnostics)
        assert "## Semantic tasks" in document.content
        assert "## Planned steps" not in document.content
    finally:
        _close(foundation)


def test_workspace_keeps_artifact_generation_capability_in_steps_without_final_role(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission = service.create_mission(user_id="user-1", goal="capability is not final")
        plan = TaskPlan(
            missionId=mission.mission_id,
            planVersion=1,
            nodes=(PlannedTask(
                key="draft_artifact",
                title="草稿产物",
                objective="生成一个中间草稿",
                capabilityRequirements=("artifact_generation",),
            ),),
        )
        tasks = PlannerIdentityBridge(service).record_task_plan(plan)
        blueprint = bridge.register_blueprint(
            mission_id=mission.mission_id,
            version=1,
            runtime_blueprint=ACGBlueprint(
                graphId="acg_capability_only",
                missionId=mission.mission_id,
                    nodes=[StepNode(
                        nodeId="draft-node",
                        name="草稿产物",

                        capability="artifact_generation",
                    )],
            resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="draft-node", plannedAgentId="draft-agent"),)),
        edges=[]),
            task_bindings={tasks["draft_artifact"].task_id: "draft-node"},
        )
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.SUCCEEDED)
        _artifact(service, bridge, content, run, tasks["draft_artifact"].task_id, "draft-node", "primary", "draft")

        artifacts = [
            item for item in query.mission_workspace(mission.mission_id).entries
            if item.kind is WorkspaceEntryKind.ARTIFACT
        ]
        assert len(artifacts) == 1
        assert artifacts[0].group == "steps"
        assert any(item.code == "RUN_DELIVERABLE_MISSING" for item in query.mission_workspace(mission.mission_id).diagnostics)
    finally:
        _close(foundation)


def test_workspace_task_status_does_not_depend_on_artifact_count(tmp_path):
    foundation = _foundation(tmp_path)
    _storage, service, bridge, content, query = foundation
    try:
        mission, tasks, blueprint = _mission_graph(service, bridge)
        run = _run(service, mission.mission_id, blueprint.blueprint_id, status=RunStatus.RUNNING)
        _artifact(service, bridge, content, run, tasks["equipment_plan"].task_id, "equipment-node", "primary", "equipment")

        task_entries = {
            entry.semantic_task_key: entry
            for entry in query.mission_workspace(mission.mission_id).entries
            if entry.kind is WorkspaceEntryKind.TASK
        }
        assert task_entries["equipment_plan"].status == "completed"
        assert task_entries["equipment_plan"].artifact_count == 1
        assert task_entries["final_delivery"].status == "pending"
        assert task_entries["final_delivery"].artifact_count == 0
    finally:
        _close(foundation)

"""Read-only Mission Workspace projection over the V2 identity graph.

This module deliberately contains no persistence.  A workspace is a product
read model assembled from the existing Mission, Run, planning, graph,
Attempt, Artifact, binding and ContentManifest authorities.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field

from contracts.content import ContentKind
from contracts.artifacts import FINAL_SYNTHESIS_LOGICAL_ROLE, is_run_deliverable_identity
from contracts.planning import SemanticTaskRelationType
from contracts.mission_semantic import MissionIntentBasis, MissionSemanticView
from domain.identity_graph import RunArtifactDisposition
from domain.models import (
    AcgBlueprint,
    AttemptStatus,
    Artifact,
    Mission,
    RunStatus,
    SemanticTask,
    SemanticTaskStatus,
    WorkflowRun,
    DomainModel,
)
from domain.repository import EntityNotFoundError, IdentityConflictError, RepositorySet


def artifact_is_public(run, artifact):
    """Canonical final stays internal evidence until successful Run completion.

    Read only the existing terminal Identity fact. This is a
    publication projection, not a new execution or review state machine.
    """
    if not is_run_deliverable_identity(artifact.model_dump(by_alias=True)):
        return True
    return run.status is RunStatus.SUCCEEDED


class WorkspaceEntryKind(str, Enum):
    FOLDER = "folder"
    GRAPH = "graph"
    VIRTUAL_DOCUMENT = "virtual_document"
    TASK = "task"
    ARTIFACT = "artifact"
    RUN = "run"


class WorkspaceIdentityQuality(str, Enum):
    CANONICAL = "canonical"
    LEGACY = "legacy"


class WorkspaceRunSummary(DomainModel):
    """Small Run history projection; it never embeds execution state."""

    run_id: str = Field(alias="runId")
    status: RunStatus
    parent_run_id: str | None = Field(default=None, alias="parentRunId")
    source_run_id: str | None = Field(default=None, alias="sourceRunId")
    created_at: datetime = Field(alias="createdAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    is_active: bool = Field(alias="isActive")


class WorkspaceEntry(DomainModel):
    """A virtual explorer entry, not a persisted domain entity."""

    entry_id: str = Field(alias="entryId")
    kind: WorkspaceEntryKind
    name: str
    group: str
    title: str | None = None
    parent_entry_id: str | None = Field(default=None, alias="parentEntryId")
    display_order: int = Field(default=0, alias="displayOrder", ge=0)
    semantic_task_key: str | None = Field(default=None, alias="semanticTaskKey")
    artifact_key: str | None = Field(default=None, alias="artifactKey")
    task_id: str | None = Field(default=None, alias="taskId")
    logical_role: str | None = Field(default=None, alias="logicalRole")
    objective: str | None = None
    dependency_keys: list[str] = Field(default_factory=list, alias="dependencyKeys")
    attempt_count: int = Field(default=0, alias="attemptCount", ge=0)
    latest_attempt_id: str | None = Field(default=None, alias="latestAttemptId")
    artifact_count: int = Field(default=0, alias="artifactCount", ge=0)
    artifact_id: str | None = Field(default=None, alias="artifactId")
    content_ref: str | None = Field(default=None, alias="contentRef")
    artifact_type: str | None = Field(default=None, alias="artifactType")
    media_type: str | None = Field(default=None, alias="mediaType")
    checksum: str | None = None
    attempt_id: str | None = Field(default=None, alias="attemptId")
    acg_node_id: str | None = Field(default=None, alias="acgNodeId")
    disposition: RunArtifactDisposition | None = None
    source_run_id: str | None = Field(default=None, alias="sourceRunId")
    identity_quality: WorkspaceIdentityQuality | None = Field(default=None, alias="identityQuality")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    run_id: str | None = Field(default=None, alias="runId")
    status: str | None = None
    blueprint_id: str | None = Field(default=None, alias="blueprintId")
    graph_id: str | None = Field(default=None, alias="graphId")
    graph_version: int | None = Field(default=None, alias="graphVersion")
    parent_run_id: str | None = Field(default=None, alias="parentRunId")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    is_active: bool | None = Field(default=None, alias="isActive")
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceGraphNode(DomainModel):
    acg_node_id: str = Field(alias="acgNodeId")
    node_type: str = Field(alias="nodeType")
    name: str
    semantic_task_key: str | None = Field(default=None, alias="semanticTaskKey")
    task_id: str | None = Field(default=None, alias="taskId")
    identity_quality: WorkspaceIdentityQuality | None = Field(default=None, alias="identityQuality")
    display_order: int = Field(alias="displayOrder", ge=0)
    status: str | None = None
    attempt_id: str | None = Field(default=None, alias="attemptId")
    artifact_count: int = Field(default=0, alias="artifactCount", ge=0)
    artifact_ids: list[str] = Field(default_factory=list, alias="artifactIds")


class WorkspaceDiagnostic(DomainModel):
    code: str
    message: str
    severity: Literal["info", "warning"] = "warning"
    details: dict[str, Any] = Field(default_factory=dict)


class WorkspaceMissionDisplay(DomainModel):
    """Request-local display selection; never written back to Identity or Mission."""
    objective: str | None = None
    source_type: Literal["SEMANTIC", "IDENTITY_COMPATIBILITY", "LEGACY_INPUT", "LEGACY_TITLE", "NONE"] = Field(alias="sourceType")


class MissionWorkspaceProjection(DomainModel):
    """Stable, read-only projection consumed by a future Workspace UI."""

    mission: Mission
    mission_semantic_view: MissionSemanticView | None = Field(default=None, alias="missionSemanticView")
    mission_display: WorkspaceMissionDisplay | None = Field(default=None, alias="missionDisplay")
    selected_run_basis: MissionIntentBasis | None = Field(default=None, alias="selectedRunBasis")
    selected_run_basis_status: Literal["BOUND", "UNBOUND", "RUNTIME_UNAVAILABLE", "NO_RUN"] | None = Field(default=None, alias="selectedRunBasisStatus")
    active_run: WorkspaceRunSummary | None = Field(default=None, alias="activeRun")
    active_graph: dict[str, Any] | None = Field(default=None, alias="activeGraph")
    runs: list[WorkspaceRunSummary] = Field(default_factory=list)
    entries: list[WorkspaceEntry] = Field(default_factory=list)
    graph_nodes: list[WorkspaceGraphNode] = Field(default_factory=list, alias="graphNodes")
    input_attachments: list[dict[str, Any]] = Field(default_factory=list, alias="inputAttachments")
    diagnostics: list[WorkspaceDiagnostic] = Field(default_factory=list)


def with_mission_semantics(
    projection: MissionWorkspaceProjection, view: MissionSemanticView, *,
    basis: MissionIntentBasis | None, basis_status: Literal["BOUND", "UNBOUND", "RUNTIME_UNAVAILABLE", "NO_RUN"],
    legacy_input: dict[str, Any], legacy_title: str,
) -> MissionWorkspaceProjection:
    """Compose already authorized data without capturing a new Run basis."""
    view = MissionSemanticView.model_validate(view.model_dump())
    if view.mission_id != projection.mission.mission_id:
        raise ValueError("Workspace semantics belong to another Mission")
    if (basis is not None) != (basis_status == "BOUND"):
        raise ValueError("Workspace Run basis status does not match its payload")
    if (projection.active_run is None) != (basis_status == "NO_RUN"):
        raise ValueError("Workspace Run basis status does not match its selection")
    if basis is not None:
        basis = MissionIntentBasis.model_validate(basis.model_dump())
        if basis.mission_id != view.mission_id or projection.active_run is None:
            raise ValueError("Workspace Run basis belongs to another Mission or has no selected Run")
    if view.semantic_status == "INITIALIZED":
        display = WorkspaceMissionDisplay(objective=view.objective, sourceType="SEMANTIC")
    else:
        objective = projection.mission.goal.strip()
        source = "IDENTITY_COMPATIBILITY" if objective else "NONE"
        if not objective:
            objective = next((legacy_input[k].strip() for k in ("objective", "userIntent", "taskGoal", "intent")
                              if isinstance(legacy_input.get(k), str) and legacy_input[k].strip()), "")
            source = "LEGACY_INPUT" if objective else "NONE"
        if not objective and legacy_title.strip():
            objective, source = legacy_title.strip(), "LEGACY_TITLE"
        display = WorkspaceMissionDisplay(objective=objective or None, sourceType=source)
    lines = [f"# {display.objective or 'Mission'}", "", "## 当前 Mission 语义",
             f"- 状态：`{view.semantic_status}`", f"- Mission revision：`{view.mission_revision}`",
             f"- 展示来源：`{display.source_type}`"]
    if view.semantic_status == "UNINITIALIZED":
        lines.append("- 正式目标尚未初始化；兼容展示内容未经正式语义提交。")
    else:
        lines.append(f"- Commit：`{view.commit_id}`")
        lines.extend(["", "### 已确认约束", *[f"- {c.text}" for c in view.constraints]])
        if not view.constraints:
            lines.append("无已确认约束。")
        lines.append(f"- 来源状态：`{view.source_status}`（引用不等于已验证事实）")
    lines.extend(["", "## 所选 Run 的历史语义依据"])
    diagnostics = list(projection.diagnostics)
    if basis is not None:
        lines.extend([f"- Run：`{projection.active_run.run_id}`", f"- 来源：`{basis.source_type}`",
                      f"- 依据 revision：`{basis.source_revision}`", f"- 当时目标：{basis.objective}",
                      f"- 来源状态：`{basis.source_status}`", *[f"- 当时约束：{c.text}" for c in basis.constraints]])
        if basis.source_type != "SEMANTIC":
            lines.append("- 此 Run 使用旧输入兼容依据，不代表正式语义。")
        if basis.source_revision != view.mission_revision:
            lines.append("- 此 Run 的历史依据与当前 Mission revision 不同；不会自动更新或重规划。")
            diagnostics.append(WorkspaceDiagnostic(code="MISSION_RUN_REVISION_DIFFERS", severity="info",
                message="Selected Run uses a historical Mission basis, distinct from current semantics.",
                details={"missionRevision": view.mission_revision, "baseMissionRevision": basis.source_revision}))
    else:
        lines.append({"UNBOUND": "旧 Run 未绑定语义依据，不从当前 Mission 回填。",
                      "RUNTIME_UNAVAILABLE": "所选 Run 的运行记录不可用，无法核验冻结依据。",
                      "NO_RUN": "尚无所选 Run。"}[basis_status])
    original = next((entry for entry in projection.entries if entry.entry_id == "overview:mission.md"), None)
    if original and original.content and "## Mission metadata" in original.content:
        # Keep plan/task/attachment context, without retaining the old goal heading.
        lines.extend(["", "## Mission metadata" + original.content.split("## Mission metadata", 1)[1]])
    document = (original or WorkspaceEntry(entryId="overview:mission.md", kind=WorkspaceEntryKind.VIRTUAL_DOCUMENT,
                name="mission.md", group="overview", parentEntryId="folder:overview", displayOrder=1)).model_copy(
                    update={"content": "\n".join(lines) + "\n"})
    return projection.model_copy(update={"mission_semantic_view": view, "mission_display": display,
        "selected_run_basis": basis, "selected_run_basis_status": basis_status, "diagnostics": diagnostics,
        "entries": [document if entry.entry_id == document.entry_id else entry for entry in projection.entries]
                   if original else [document, *projection.entries]})


class MissionWorkspaceProjector:
    """Build a workspace without creating or mutating any persistent state."""

    _ACTIVE_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING}
    def __init__(self, repositories: RepositorySet, content_manifest_store: Any | None = None) -> None:
        self.repositories = repositories
        self.content_manifest_store = content_manifest_store

    def project(self, mission_id: str, *, run_id: str | None = None) -> MissionWorkspaceProjection:
        mission = self.repositories.missions.get(mission_id)
        if mission is None:
            raise EntityNotFoundError(f"Mission not found: {mission_id}")
        all_runs = sorted(
            self.repositories.runs.list_for_mission(mission_id),
            key=lambda item: (item.created_at, item.run_id),
        )
        selected_run = self._select_run(mission_id, all_runs, run_id)
        diagnostics: list[WorkspaceDiagnostic] = []
        if selected_run is None:
            diagnostics.append(WorkspaceDiagnostic(
                code="NO_ACTIVE_RUN",
                message="Mission has no Run available for the active Workspace projection.",
                severity="info",
            ))
        summaries = [
            self._run_summary(item, is_active=selected_run is not None and item.run_id == selected_run.run_id)
            for item in all_runs
        ]
        entries = self._folders()
        attachment_repository = getattr(self.repositories, "input_attachments", None)
        input_attachments = (
            attachment_repository.list_for_run(selected_run.run_id)
            if attachment_repository is not None and selected_run is not None
            else attachment_repository.list_for_mission(mission_id)
            if attachment_repository is not None
            else []
        )
        graph_nodes: list[WorkspaceGraphNode] = []
        plan = None
        active_graph: dict[str, Any] | None = None
        tasks = self.repositories.semantic_tasks.list_for_mission(mission_id)
        if selected_run is not None:
            plan = self._plan_for_run(selected_run, diagnostics)
            blueprint = self.repositories.blueprints.get(selected_run.blueprint_id)
            if blueprint is None:
                raise EntityNotFoundError(f"AcgBlueprint not found: {selected_run.blueprint_id}")
            active_graph = self._graph_snapshot(selected_run, blueprint, plan)
            graph_nodes = self._graph_nodes(selected_run, blueprint, tasks, diagnostics)
            entries.extend(self._graph_entries(selected_run, blueprint, plan))
        else:
            blueprint = None

        entries.append(WorkspaceEntry(
            entry_id="overview:mission.md",
            kind=WorkspaceEntryKind.VIRTUAL_DOCUMENT,
            name="mission.md",
            group="overview",
            parent_entry_id="folder:overview",
            display_order=1,
            content=self._mission_document(mission, selected_run, plan, tasks, input_attachments),
        ))
        if selected_run is not None:
            artifact_entries = self._artifact_entries(
                selected_run,
                tasks,
                plan,
                blueprint,
                diagnostics,
            )
            entries.extend(self._task_entries(
                selected_run,
                tasks,
                plan,
                blueprint,
                artifact_entries,
                diagnostics,
            ))
            entries.extend(artifact_entries)
            if selected_run.status is RunStatus.SUCCEEDED and not any(
                entry.group == "output" and entry.kind is WorkspaceEntryKind.ARTIFACT
                for entry in artifact_entries
            ):
                diagnostics.append(WorkspaceDiagnostic(
                    code="RUN_DELIVERABLE_MISSING",
                    message="Run completed without a canonical run_deliverable; supporting artifacts are not promoted.",
                    severity="warning",
                    details={"runId": selected_run.run_id},
                ))
            entries.extend(self._run_entries(summaries))
        else:
            entries.extend(self._run_entries(summaries))
        entries = self._sort_entries(entries)
        self._assert_unique_entry_ids(entries)
        return MissionWorkspaceProjection(
            mission=mission,
            active_run=(next((item for item in summaries if item.is_active), None)),
            active_graph=active_graph,
            runs=summaries,
            entries=entries,
            graph_nodes=graph_nodes,
            input_attachments=[
                item.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude={"owner_user_id", "owner_tenant_id", "storage_key"},
                )
                for item in input_attachments
            ],
            diagnostics=diagnostics,
        )

    def _select_run(
        self,
        mission_id: str,
        runs: list[WorkflowRun],
        requested_run_id: str | None,
    ) -> WorkflowRun | None:
        if requested_run_id is not None:
            selected = self.repositories.runs.get(requested_run_id)
            if selected is None or selected.mission_id != mission_id:
                raise EntityNotFoundError(f"Run not found for Mission: {requested_run_id}")
            return selected
        active = [item for item in runs if item.status in self._ACTIVE_STATUSES]
        if active:
            return active[-1]
        succeeded = [item for item in runs if item.status is RunStatus.SUCCEEDED]
        if succeeded:
            return succeeded[-1]
        return runs[-1] if runs else None

    @staticmethod
    def _run_summary(run: WorkflowRun, *, is_active: bool) -> WorkspaceRunSummary:
        metadata = dict(run.metadata or {})
        return WorkspaceRunSummary(
            run_id=run.run_id,
            status=run.status,
            parent_run_id=(str(metadata["parentRunId"]) if metadata.get("parentRunId") else None),
            source_run_id=(str(metadata["sourceRunId"]) if metadata.get("sourceRunId") else None),
            created_at=run.created_at,
            completed_at=run.finished_at,
            is_active=is_active,
        )

    @staticmethod
    def _folders() -> list[WorkspaceEntry]:
        return [
            WorkspaceEntry(entry_id="folder:overview", kind=WorkspaceEntryKind.FOLDER, name="Overview", group="overview", display_order=0),
            WorkspaceEntry(entry_id="folder:steps", kind=WorkspaceEntryKind.FOLDER, name="Steps", group="steps", display_order=0),
            WorkspaceEntry(entry_id="folder:output", kind=WorkspaceEntryKind.FOLDER, name="Output", group="output", display_order=0),
            WorkspaceEntry(entry_id="folder:runs", kind=WorkspaceEntryKind.FOLDER, name="Runs", group="runs", display_order=0),
        ]

    @staticmethod
    def _graph_entries(run: WorkflowRun, blueprint: AcgBlueprint, plan: Any | None = None) -> list[WorkspaceEntry]:
        return [WorkspaceEntry(
            entry_id="overview:graph.acg",
            kind=WorkspaceEntryKind.GRAPH,
            name="graph.acg",
            group="overview",
            parent_entry_id="folder:overview",
            display_order=0,
            run_id=run.run_id,
            blueprint_id=blueprint.blueprint_id,
            graph_id=blueprint.graph_id,
            graph_version=run.graph_version,
            metadata={"taskPlanVersion": plan.plan_version} if plan is not None else {},
        )]

    @staticmethod
    def _graph_snapshot(run: WorkflowRun, blueprint: AcgBlueprint, plan: Any | None = None) -> dict[str, Any]:
        return {
            **dict(blueprint.graph),
            "blueprintId": blueprint.blueprint_id,
            "graphId": blueprint.graph_id,
            "missionId": blueprint.mission_id,
            "graphVersion": run.graph_version,
            "taskPlanVersion": plan.plan_version if plan is not None else None,
        }

    def _graph_nodes(
        self,
        run: WorkflowRun,
        blueprint: AcgBlueprint,
        tasks: list[SemanticTask],
        diagnostics: list[WorkspaceDiagnostic],
    ) -> list[WorkspaceGraphNode]:
        task_by_id = {task.task_id: task for task in tasks}
        attempts_by_task: dict[str, list[Any]] = {}
        for attempt in self.repositories.attempts.list_for_run(run.run_id):
            attempts_by_task.setdefault(attempt.task_id, []).append(attempt)
        result: list[WorkspaceGraphNode] = []
        raw_nodes = blueprint.graph.get("nodes") if isinstance(blueprint.graph, dict) else []
        for index, raw in enumerate(raw_nodes if isinstance(raw_nodes, list) else []):
            if not isinstance(raw, dict) or not raw.get("nodeId"):
                continue
            acg_node_id = str(raw["nodeId"])
            bindings = self.repositories.task_bindings.find_for_acg_node(acg_node_id, blueprint.blueprint_id)
            binding = self._primary_binding(bindings)
            task = task_by_id.get(binding.task_id) if binding is not None else None
            key = self._task_key(task) if task is not None else None
            attempts = attempts_by_task.get(task.task_id, []) if task is not None else []
            latest_attempt = max(
                attempts,
                key=lambda item: (item.attempt_number, item.attempt_id),
                default=None,
            )
            artifact_ids = [
                artifact.artifact_id
                for attempt in attempts
                for artifact in self.repositories.artifacts.list_for_attempt(attempt.attempt_id)
            ]
            if binding is not None and task is None:
                diagnostics.append(WorkspaceDiagnostic(
                    code="GRAPH_TASK_NOT_FOUND",
                    message="Graph binding references a missing SemanticTask.",
                    details={"acgNodeId": acg_node_id, "taskId": binding.task_id},
                ))
            result.append(WorkspaceGraphNode(
                acg_node_id=acg_node_id,
                node_type=str(raw.get("nodeType") or "unknown"),
                name=str(raw.get("name") or raw.get("stepName") or acg_node_id),
                semantic_task_key=key,
                task_id=(task.task_id if task is not None else None),
                identity_quality=(
                    WorkspaceIdentityQuality.CANONICAL if key and task and task.semantic_task_key
                    else WorkspaceIdentityQuality.LEGACY if task is not None else None
                ),
                display_order=index,
                status=(latest_attempt.status.value if latest_attempt is not None else None),
                attempt_id=(latest_attempt.attempt_id if latest_attempt is not None else None),
                artifact_count=len(artifact_ids),
                artifact_ids=artifact_ids,
            ))
        return result

    def _task_entries(
        self,
        run: WorkflowRun,
        tasks: list[SemanticTask],
        plan: Any | None,
        blueprint: AcgBlueprint,
        artifact_entries: list[WorkspaceEntry],
        diagnostics: list[WorkspaceDiagnostic],
    ) -> list[WorkspaceEntry]:
        """Project the current Run's logical tasks independently of artifacts."""
        task_by_key = {
            key: task for task in tasks
            if (key := self._task_key(task)) is not None
        }
        attempts_by_task: dict[str, list[Any]] = {}
        for attempt in self.repositories.attempts.list_for_run(run.run_id):
            attempts_by_task.setdefault(attempt.task_id, []).append(attempt)

        primary_bindings: dict[str, Any] = {}
        for task in tasks:
            binding = self._primary_binding(
                self.repositories.task_bindings.find_for_task(
                    task.task_id,
                    blueprint.blueprint_id,
                )
            )
            if binding is not None:
                primary_bindings[task.task_id] = binding

        artifact_counts: dict[str, int] = {}
        for entry in artifact_entries:
            if entry.task_id is not None:
                artifact_counts[entry.task_id] = artifact_counts.get(entry.task_id, 0) + 1

        candidates: list[tuple[int, str, SemanticTask, Any | None]] = []
        if plan is not None:
            for index, node in enumerate(plan.nodes):
                task = task_by_key.get(node.key)
                if task is None:
                    diagnostics.append(WorkspaceDiagnostic(
                        code="TASK_PLAN_TASK_NOT_FOUND",
                        message="TaskPlan references a SemanticTask that is not available in the Mission projection.",
                        details={"semanticTaskKey": node.key, "runId": run.run_id},
                    ))
                    continue
                candidates.append((index, node.key, task, node))
        else:
            # Without a historical plan snapshot, show only tasks proven by
            # this Run's Attempt or Blueprint TaskBinding.
            proven_ids = set(attempts_by_task) | set(primary_bindings)
            for index, task in enumerate(tasks):
                if task.task_id not in proven_ids:
                    continue
                key = self._task_key(task) or f"legacy:{task.task_id}"
                candidates.append((index, key, task, None))

        entries: list[WorkspaceEntry] = []
        for display_order, key, task, plan_node in candidates:
            attempts = sorted(
                attempts_by_task.get(task.task_id, []),
                key=lambda item: (item.attempt_number, item.attempt_id),
            )
            latest_attempt = attempts[-1] if attempts else None
            task_key = self._task_key(task) or key
            binding = primary_bindings.get(task.task_id)
            plan_role = str(getattr(plan_node, "logical_role", "") or "").strip()
            metadata = dict(task.metadata or {})
            logical_role = plan_role or str(metadata.get("logicalRole") or "task")
            objective = getattr(plan_node, "objective", None) or task.objective
            dependencies = [
                relation.source_key
                for relation in (plan.relations if plan is not None else ())
                if relation.target_key == key
                and relation.relation_type is SemanticTaskRelationType.DEPENDS_ON
            ]
            entries.append(WorkspaceEntry(
                entry_id=f"task:{task_key}",
                kind=WorkspaceEntryKind.TASK,
                name=getattr(plan_node, "title", None) or task.title,
                title=getattr(plan_node, "title", None) or task.title,
                group="steps",
                parent_entry_id="folder:steps",
                display_order=display_order,
                semantic_task_key=task_key,
                task_id=task.task_id,
                logical_role=logical_role,
                objective=objective,
                dependency_keys=dependencies,
                attempt_count=len(attempts),
                latest_attempt_id=(latest_attempt.attempt_id if latest_attempt is not None else None),
                acg_node_id=(binding.acg_node_id if binding is not None else None),
                artifact_count=artifact_counts.get(task.task_id, 0),
                identity_quality=(
                    WorkspaceIdentityQuality.CANONICAL
                    if self._task_key(task) is not None
                    else WorkspaceIdentityQuality.LEGACY
                ),
                status=self._workspace_task_status(task, latest_attempt),
                run_id=run.run_id,
                metadata={
                    "runtimeStatus": latest_attempt.status.value if latest_attempt is not None else None,
                    "parentTaskId": task.parent_task_id,
                },
            ))
        return entries

    @staticmethod
    def _workspace_task_status(task: SemanticTask, latest_attempt: Any | None) -> str:
        if latest_attempt is not None:
            return {
                AttemptStatus.PENDING: "pending",
                AttemptStatus.RUNNING: "running",
                AttemptStatus.FAILED: "failed",
                AttemptStatus.SUCCEEDED: "completed",
                AttemptStatus.CANCELLED: "skipped",
            }.get(latest_attempt.status, latest_attempt.status.value)
        return {
            SemanticTaskStatus.CREATED: "pending",
            SemanticTaskStatus.READY: "ready",
            SemanticTaskStatus.RUNNING: "running",
            SemanticTaskStatus.BLOCKED: "pending",
            SemanticTaskStatus.COMPLETED: "completed",
            SemanticTaskStatus.CANCELLED: "skipped",
            SemanticTaskStatus.RETIRED: "skipped",
            SemanticTaskStatus.SUPERSEDED: "skipped",
        }.get(task.status, "pending")

    def _artifact_entries(
        self,
        run: WorkflowRun,
        tasks: list[SemanticTask],
        plan: Any,
        blueprint: AcgBlueprint,
        diagnostics: list[WorkspaceDiagnostic],
    ) -> list[WorkspaceEntry]:
        task_by_id = {task.task_id: task for task in tasks}
        plan_by_key = {node.key: node for node in (plan.nodes if plan is not None else ())}
        graph_by_id = {
            str(node.get("nodeId")): node
            for node in (blueprint.graph.get("nodes", []) if isinstance(blueprint.graph, dict) else [])
            if isinstance(node, dict) and node.get("nodeId")
        }
        details = self._v2_artifacts_for_run(run.run_id)
        entries: list[WorkspaceEntry] = []
        known_refs = {detail.artifact.content_ref for detail in details}
        ordered_details = sorted(
            details,
            key=lambda detail: (
                self._task_order(detail.artifact.task_id, detail.artifact.semantic_task_key, tasks, plan),
                detail.artifact.artifact_key,
                detail.artifact.artifact_id,
            ),
        )
        for detail in ordered_details:
            artifact = detail.artifact
            if not artifact_is_public(run, artifact):
                continue
            task = task_by_id.get(artifact.task_id)
            task_key = artifact.semantic_task_key
            plan_node = plan_by_key.get(task_key)
            graph_node = graph_by_id.get(artifact.acg_node_id, {})
            final = self._is_final_artifact(task, plan_node, graph_node, artifact)
            group = "output" if final else "steps"
            entry_id = f"task:{task_key}:{artifact.artifact_key}"
            name = (
                "final.md" if final and artifact.artifact_key == "primary"
                else f"{artifact.artifact_key}.md" if final
                else artifact.name
            )
            entries.append(WorkspaceEntry(
                entry_id=entry_id,
                kind=WorkspaceEntryKind.ARTIFACT,
                name=name,
                group=group,
                parent_entry_id=(
                    f"task:{task_key}" if not final else f"folder:{group}"
                ),
                display_order=self._task_order(
                    artifact.task_id,
                    artifact.semantic_task_key,
                    tasks,
                    plan,
                ),
                semantic_task_key=task_key,
                artifact_key=artifact.artifact_key,
                task_id=artifact.task_id,
                artifact_id=artifact.artifact_id,
                content_ref=artifact.content_ref,
                artifact_type=artifact.artifact_type,
                media_type=artifact.media_type,
                checksum=artifact.checksum,
                attempt_id=artifact.producer_attempt_id,
                acg_node_id=artifact.acg_node_id,
                logical_role=(
                    FINAL_SYNTHESIS_LOGICAL_ROLE
                    if final
                    else str(artifact.metadata.get("logicalRole"))
                    if artifact.metadata.get("logicalRole") else None
                ),
                run_id=run.run_id,
                disposition=detail.binding.disposition,
                source_run_id=detail.binding.source_run_id,
                identity_quality=WorkspaceIdentityQuality.CANONICAL,
                created_at=artifact.created_at,
                metadata=dict(artifact.metadata),
            ))
        self._append_legacy_manifest_entries(run.run_id, known_refs, entries, diagnostics)
        return entries

    def _v2_artifacts_for_run(self, run_id: str) -> list[Any]:
        details: list[Any] = []
        for binding in self.repositories.run_artifact_bindings.list_for_run(run_id):
            artifact = self.repositories.artifacts.get(binding.artifact_id)
            if artifact is None:
                raise EntityNotFoundError(f"Artifact not found for binding: {binding.binding_id}")
            details.append(type("ArtifactDetail", (), {"binding": binding, "artifact": artifact})())
        return details

    def _append_legacy_manifest_entries(
        self,
        run_id: str,
        known_content_refs: set[str],
        entries: list[WorkspaceEntry],
        diagnostics: list[WorkspaceDiagnostic],
    ) -> None:
        if self.content_manifest_store is None:
            return
        manifests = self.content_manifest_store.list_manifests(
            owner_type="run", owner_id=run_id, kind=ContentKind.ARTIFACT
        )
        legacy = [item for item in manifests if item.sealed and item.manifest_id not in known_content_refs]
        if legacy:
            diagnostics.append(WorkspaceDiagnostic(
                code="LEGACY_ARTIFACT_IDENTITY",
                message="Some artifact content has no canonical V2 Artifact identity.",
                details={"count": len(legacy)},
            ))
        start = max((item.display_order for item in entries), default=0) + 1
        for offset, manifest in enumerate(legacy):
            entries.append(WorkspaceEntry(
                entry_id=f"legacy:{manifest.manifest_id}",
                kind=WorkspaceEntryKind.ARTIFACT,
                name=manifest.manifest_id,
                group="steps",
                parent_entry_id="folder:steps",
                display_order=start + offset,
                content_ref=manifest.manifest_id,
                media_type=manifest.media_type,
                artifact_type="legacy_artifact",
                identity_quality=WorkspaceIdentityQuality.LEGACY,
                created_at=manifest.created_at,
            ))

    def _run_entries(self, summaries: list[WorkspaceRunSummary]) -> list[WorkspaceEntry]:
        return [WorkspaceEntry(
            entry_id=f"run:{summary.run_id}",
            kind=WorkspaceEntryKind.RUN,
            name=summary.run_id,
            group="runs",
            parent_entry_id="folder:runs",
            display_order=index,
            run_id=summary.run_id,
            status=summary.status,
            source_run_id=summary.source_run_id,
            created_at=summary.created_at,
            parent_run_id=summary.parent_run_id,
            completed_at=summary.completed_at,
            is_active=summary.is_active,
            metadata={
                "projection": "run-history",
            },
        ) for index, summary in enumerate(summaries)]

    def _plan_for_run(self, run: WorkflowRun, diagnostics: list[WorkspaceDiagnostic]) -> Any | None:
        metadata = dict(run.metadata or {})
        task_plans = self.repositories.task_plans
        version = metadata.get("taskPlanVersion")
        plan = None
        if version is not None:
            try:
                plan = task_plans.get(run.mission_id, int(version))
            except (TypeError, ValueError):
                plan = None
        if plan is None:
            diagnostics.append(WorkspaceDiagnostic(
                code="PLAN_SNAPSHOT_UNRESOLVED",
                message="Run has no resolvable TaskPlan snapshot pointer; the projection falls back to Run-proven SemanticTask and Artifact order.",
                details={"runId": run.run_id, "taskPlanVersion": version},
            ))
        return plan

    @staticmethod
    def _task_key(task: SemanticTask | None) -> str | None:
        if task is None:
            return None
        return task.semantic_task_key or (
            str(task.metadata.get("plannerSemanticKey"))
            if task.metadata.get("plannerSemanticKey") else None
        )

    def _task_key_map(self, tasks: list[SemanticTask]) -> dict[str, SemanticTask]:
        result: dict[str, SemanticTask] = {}
        for task in tasks:
            key = self._task_key(task)
            if key is not None and key not in result:
                result[key] = task
        return result

    @staticmethod
    def _primary_binding(bindings: list[Any]) -> Any | None:
        if not bindings:
            return None
        return sorted(bindings, key=lambda item: (item.binding_type.value != "primary", item.created_at, item.binding_id))[0]

    @staticmethod
    def _task_order(task_id: str, key: str, tasks: list[SemanticTask], plan: Any | None) -> int:
        if plan is not None:
            for index, node in enumerate(plan.nodes):
                if node.key == key:
                    return index
        for index, task in enumerate(tasks):
            if task.task_id == task_id:
                return index
        return 10**9

    def _is_final_artifact(
        self,
        task: SemanticTask | None,
        plan_node: Any | None,
        graph_node: dict[str, Any],
        artifact: Artifact,
    ) -> bool:
        # Final status is an Artifact identity, never a capability or task-role
        # inference.  Older primary/report products remain supporting artifacts.
        return is_run_deliverable_identity(artifact.model_dump(by_alias=True))

    @staticmethod
    def _mission_document(
        mission: Mission,
        run: WorkflowRun | None,
        plan: Any | None,
        tasks: list[SemanticTask],
        input_attachments: list[Any],
    ) -> str:
        lines = [f"# {mission.goal}"]
        if mission.description:
            lines.extend(["", mission.description])
        lines.extend(["", "## Mission metadata"])
        if mission.metadata:
            lines.append("```json")
            lines.append(json.dumps(mission.metadata, ensure_ascii=False, indent=2, sort_keys=True, default=str))
            lines.append("```")
        else:
            lines.append("No additional mission metadata.")
        lines.extend(["", "## Current Run"])
        if run is None:
            lines.append("No Run has been created.")
        else:
            lines.append(f"- Run: `{run.run_id}`")
            lines.append(f"- Status: `{run.status.value}`")
            if run.finished_at is not None:
                lines.append(f"- Completed: `{run.finished_at.isoformat()}`")
        lines.extend(["", "## Input attachments"])
        if input_attachments:
            for attachment in input_attachments:
                lines.append(
                    f"- **{attachment.original_filename}** (`{attachment.attachment_id}`) "
                    f"- {attachment.status.value}, {attachment.size_bytes} bytes, `{attachment.sha256}`"
                )
        else:
            lines.append("No input attachments.")
        nodes = list(plan.nodes) if plan is not None else []
        if nodes:
            lines.extend(["", "## Planned steps"])
            for node in nodes:
                lines.append(f"- **{node.title}** (`{node.key}`): {node.objective}")
                if node.constraints:
                    lines.append(f"  - Constraints: `{json.dumps(node.constraints, ensure_ascii=False, sort_keys=True, default=str)}`")
        elif tasks:
            lines.extend(["", "## Semantic tasks"])
            for task in tasks:
                key = task.semantic_task_key or f"legacy:{task.task_id}"
                lines.append(f"- **{task.title}** (`{key}`): {task.objective}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _sort_entries(entries: list[WorkspaceEntry]) -> list[WorkspaceEntry]:
        group_order = {"overview": 0, "steps": 1, "output": 2, "runs": 3}
        return sorted(
            entries,
            key=lambda item: (
                group_order.get(item.group, 99),
                0 if item.kind is WorkspaceEntryKind.FOLDER else 1,
                item.display_order,
                item.entry_id,
            ),
        )

    @staticmethod
    def _assert_unique_entry_ids(entries: list[WorkspaceEntry]) -> None:
        entry_ids = [item.entry_id for item in entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise IdentityConflictError("MissionWorkspaceProjection contains duplicate entryId")


__all__ = [
    "MissionWorkspaceProjection",
    "MissionWorkspaceProjector",
    "WorkspaceDiagnostic",
    "WorkspaceEntry",
    "WorkspaceEntryKind",
    "WorkspaceGraphNode",
    "WorkspaceIdentityQuality",
    "WorkspaceRunSummary",
]

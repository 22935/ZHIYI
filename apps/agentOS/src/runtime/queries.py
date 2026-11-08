"""从 V2 Identity Graph 读取产品查询模型。"""

from __future__ import annotations

from collections.abc import Callable, Collection

from .query_models import (
    AttemptDetail,
    AttemptHistory,
    CompiledPackageIdentity,
    ExecutionProvenance,
    IdentityProjectionHealth,
    RunExecutionNode,
    RunExecutionTree,
    RunLineage,
    RunOperationalState,
    StepExecutionDetail,
    MissionDetail,
    MissionListItem,
    MissionRunHistory,
    RunArtifactDetail,
)
from domain.identity_graph import IdentityResolver
from domain.models import Artifact, Mission, MissionStatus
from domain.repository import EntityNotFoundError, RepositorySet
from .workspace import MissionWorkspaceProjection, MissionWorkspaceProjector, artifact_is_public


class IdentityQueryService:
    """Phase 4 查询真源；只组合 Repository，不读取 Execution Runtime 运行快照。"""

    def __init__(self, repositories: RepositorySet, content_manifest_store: object | None = None) -> None:
        self.repositories = repositories
        self.resolver = IdentityResolver(repositories)
        self.workspace_projector = MissionWorkspaceProjector(
            repositories,
            content_manifest_store,
        )

    def list_missions(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        status: MissionStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MissionDetail], int]:
        missions, total = self.repositories.missions.list(
            user_id=user_id,
            tenant_id=tenant_id,
            status=status,
            offset=(max(1, page) - 1) * max(1, page_size),
            limit=page_size,
        )
        return ([self.get_mission(mission.mission_id) for mission in missions], total)

    def list_mission_items(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        status: MissionStatus | None = None,
        page: int = 1,
        page_size: int = 20,
        mission_visibility: Callable[[str], bool] | None = None,
        visible_mission_ids: Collection[str] | None = None,
        include_run_summaries: bool = True,
    ) -> tuple[list[MissionListItem], int]:
        """Return a Mission-level Project list without treating Runs as projects.

        ``MissionRecordState`` lives in the Execution Runtime rather than the
        identity projection. Callers that need a user-facing visibility
        boundary can provide a predicate; it is applied before pagination so
        deleted or archived runtime records cannot leave stale Project rows.
        """
        safe_page = max(1, page)
        safe_page_size = max(1, page_size)
        filters = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "status": status,
        }
        if mission_visibility is None and visible_mission_ids is None:
            missions, total = self.repositories.missions.list(
                **filters,
                offset=(safe_page - 1) * safe_page_size,
                limit=safe_page_size,
            )
        else:
            visible_ids = set(visible_mission_ids or ())
            visibility = mission_visibility or (lambda mission_id: mission_id in visible_ids)
            all_missions: list[Mission] = []
            offset = 0
            scan_limit = max(100, safe_page_size)
            source_total = 0
            while True:
                batch, source_total = self.repositories.missions.list(
                    **filters,
                    offset=offset,
                    limit=scan_limit,
                )
                all_missions.extend(
                    mission
                    for mission in batch
                    if visibility(mission.mission_id)
                )
                offset += len(batch)
                if not batch or offset >= source_total:
                    break
            total = len(all_missions)
            start = (safe_page - 1) * safe_page_size
            missions = all_missions[start:start + safe_page_size]
        mission_ids = [mission.mission_id for mission in missions]
        if not include_run_summaries:
            runs_by_mission = {mission_id: [] for mission_id in mission_ids}
        else:
            list_for_missions = getattr(self.repositories.runs, "list_for_missions", None)
            if callable(list_for_missions):
                runs_by_mission = list_for_missions(mission_ids)
            else:
                runs_by_mission = {
                    mission_id: self.repositories.runs.list_for_mission(mission_id)
                    for mission_id in mission_ids
                }
        items: list[MissionListItem] = []
        for mission in missions:
            runs = runs_by_mission.get(mission.mission_id, [])
            latest = max(runs, key=lambda item: (item.updated_at, item.run_id), default=None)
            items.append(MissionListItem(
                missionId=mission.mission_id,
                userId=mission.user_id,
                title=mission.goal,
                description=mission.description,
                status=mission.status,
                latestRunId=latest.run_id if latest is not None else None,
                latestRunStatus=latest.status.value if latest is not None else None,
                createdAt=mission.created_at.isoformat(),
                updatedAt=mission.updated_at.isoformat(),
                runCount=len(runs),
            ))
        return items, total

    def get_mission(self, mission_id: str) -> MissionDetail:
        mission = self.repositories.missions.get(mission_id)
        if mission is None:
            raise EntityNotFoundError(f"Mission not found: {mission_id}")
        return MissionDetail(
            mission=mission,
            tasks=self.repositories.semantic_tasks.list_for_mission(mission_id),
            blueprints=self.repositories.blueprints.list_for_mission(mission_id),
            runs=self.repositories.runs.list_for_mission(mission_id),
        )

    def mission_workspace(
        self,
        mission_id: str,
        *,
        run_id: str | None = None,
    ) -> MissionWorkspaceProjection:
        """Build the read-only Workspace projection from V2 authorities."""
        return self.workspace_projector.project(mission_id, run_id=run_id)

    def mission_run_history(self, mission_id: str) -> MissionRunHistory:
        self.get_mission(mission_id)
        return MissionRunHistory(
            missionId=mission_id,
            runs=self.repositories.runs.list_for_mission(mission_id),
        )

    def get_attempt(self, attempt_id: str) -> AttemptDetail:
        attempt = self.repositories.attempts.get(attempt_id)
        if attempt is None:
            raise EntityNotFoundError(f"Attempt not found: {attempt_id}")
        return AttemptDetail(
            attempt=attempt,
            executionBinding=self.repositories.execution_bindings.get_for_attempt(
                attempt_id
            ),
            executions=self.repositories.step_executions.list_for_attempt(attempt_id),
            artifacts=self.repositories.artifacts.list_for_attempt(attempt_id),
        )

    def artifacts_for_run(self, run_id: str) -> list[RunArtifactDetail]:
        """Return logical Run slots joined to immutable Artifact identities."""
        run = self.repositories.runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"WorkflowRun not found: {run_id}")
        details: list[RunArtifactDetail] = []
        for binding in self.repositories.run_artifact_bindings.list_for_run(run_id):
            artifact = self.repositories.artifacts.get(binding.artifact_id)
            if artifact is None:
                raise EntityNotFoundError(
                    f"Artifact not found for binding: {binding.binding_id}"
                )
            if artifact_is_public(run, artifact):
                details.append(RunArtifactDetail(binding=binding, artifact=artifact))
        return details

    def get_artifact(self, artifact_id: str) -> Artifact:
        artifact = self.repositories.artifacts.get(artifact_id)
        if artifact is None:
            raise EntityNotFoundError(f"Artifact not found: {artifact_id}")
        return artifact

    def attempt_history(
        self,
        run_id: str,
        *,
        task_id: str | None = None,
    ) -> AttemptHistory:
        if self.repositories.runs.get(run_id) is None:
            raise EntityNotFoundError(f"WorkflowRun not found: {run_id}")
        attempts = self.repositories.attempts.list_for_run(run_id)
        if task_id is not None:
            attempts = [attempt for attempt in attempts if attempt.task_id == task_id]
        return AttemptHistory(
            runId=run_id,
            taskId=task_id,
            attempts=[self.get_attempt(attempt.attempt_id) for attempt in attempts],
        )

    def run_execution_tree(self, run_id: str) -> RunExecutionTree:
        run = self.repositories.runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"WorkflowRun not found: {run_id}")
        blueprint = self.repositories.blueprints.get(run.blueprint_id)
        if blueprint is None:
            raise EntityNotFoundError(f"AcgBlueprint not found: {run.blueprint_id}")
        attempts = self.repositories.attempts.list_for_run(run_id)
        attempts_by_node: dict[str, list[AttemptDetail]] = {}
        for attempt in attempts:
            attempts_by_node.setdefault(attempt.task_id, []).append(
                self.get_attempt(attempt.attempt_id)
            )
        nodes: list[RunExecutionNode] = []
        for semantic_task in self.repositories.semantic_tasks.list_for_mission(run.mission_id):
            bindings = self.repositories.task_bindings.find_for_task(
                semantic_task.task_id,
                run.blueprint_id,
            )
            nodes.append(RunExecutionNode(
                task=semantic_task,
                acgNodeId=(bindings[0].acg_node_id if bindings else None),
                attempts=attempts_by_node.get(semantic_task.task_id, []),
            ))
        return RunExecutionTree(
            run=run,
            blueprint=blueprint,
            nodes=nodes,
            operational=self.run_operational_state(run_id),
        )

    def run_operational_state(self, run_id: str) -> RunOperationalState:
        run = self.repositories.runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"WorkflowRun not found: {run_id}")
        metadata = dict(run.metadata or {})
        projection = dict(metadata.get("executionProjection") or {})
        package = None
        if all(metadata.get(key) is not None for key in (
            "compiledPackageId", "compiledPackageVersion", "compiledPackageChecksum"
        )):
            package = CompiledPackageIdentity(
                packageId=str(metadata["compiledPackageId"]),
                packageVersion=int(metadata["compiledPackageVersion"]),
                checksum=str(metadata["compiledPackageChecksum"]),
                blueprintHash=metadata.get("compiledPackageBlueprintHash"),
            )

        raw_context_refs = projection.get("contextRefs")
        context_refs = (
            {
                str(step_id): context_ref
                for step_id, context_ref in raw_context_refs.items()
                if isinstance(context_ref, str) and context_ref
            }
            if isinstance(raw_context_refs, dict)
            else {}
        )
        node_executions = []
        communication_refs: list[str] = []
        memory_refs: list[str] = []
        evidence_refs: list[str] = []
        for attempt in self.repositories.attempts.list_for_run(run_id):
            for execution in self.repositories.step_executions.list_for_attempt(
                attempt.attempt_id
            ):
                output = dict(execution.output or {})
                raw_record = output.get("nodeExecution")
                if isinstance(raw_record, dict):
                    from contracts.execution import NodeExecutionRecord

                    node_executions.append(NodeExecutionRecord.model_validate(raw_record))
                communication_refs.extend(
                    str(item) for item in output.get("communicationRefs") or []
                )
                evidence_refs.extend(
                    str(item) for item in output.get("evidenceRefs") or []
                )
                memory_ref = output.get("memoryRef")
                if isinstance(memory_ref, str) and memory_ref != "memory:none":
                    memory_refs.append(memory_ref)
        for value in (projection.get("memoryRefs") or {}).values():
            if isinstance(value, str) and value != "memory:none":
                memory_refs.append(value)

        lease_statuses: dict[str, str] = {}
        for item in projection.get("schedulingDecisions") or []:
            if not isinstance(item, dict):
                continue
            lease = item.get("lease")
            if isinstance(lease, dict) and lease.get("leaseId"):
                lease_statuses[str(lease["leaseId"])] = str(
                    lease.get("status") or "unknown"
                )
        return RunOperationalState(
            package=package,
            lineage=RunLineage(
                parentRunId=metadata.get("parentRunId"),
                sourceRunId=metadata.get("sourceRunId"),
                rerunReason=metadata.get("rerunReason"),
                supersedesRunId=metadata.get("supersedesRunId"),
                supersededByRunId=(
                    metadata.get("supersededByRunId")
                    or projection.get("supersededByRunId")
                ),
                sourcePatchId=metadata.get("sourcePatchId"),
            ),
            nodeExecutions=node_executions,
            controlFrames=list(projection.get("controlFrames") or []),
            contextRefs=context_refs,
            communicationRefs=list(dict.fromkeys(communication_refs)),
            memoryRefs=list(dict.fromkeys(memory_refs)),
            evidenceRefs=list(dict.fromkeys(evidence_refs)),
            leaseStatuses=lease_statuses,
            loopIterations=dict(projection.get("loopIterations") or {}),
            consensusResults=dict(projection.get("consensusResults") or {}),
            debateSessions=dict(projection.get("debateSessions") or {}),
            recoveryOutcome=projection.get("recoveryOutcome"),
        )

    def projection_health(self) -> IdentityProjectionHealth:
        inbox = self.repositories.inbox_events.stats()
        projection = self.repositories.projection_events.stats()
        timestamps = [
            value
            for value in (inbox.get("oldestEventAt"), projection.get("oldestEventAt"))
            if value is not None
        ]
        return IdentityProjectionHealth(
            inboxBacklog=int(inbox.get("backlog") or 0),
            inboxFailed=int(inbox.get("failed") or 0),
            projectionBacklog=int(projection.get("backlog") or 0),
            projectionFailed=int(projection.get("failed") or 0),
            oldestEventAt=min(timestamps) if timestamps else None,
        )

    def step_execution_detail(self, step_execution_id: str) -> StepExecutionDetail:
        origin = self.resolver.resolve_execution_origin(step_execution_id)
        return StepExecutionDetail(
            origin=origin,
            provenanceLinks=self.repositories.provenance_links.list_from(
                step_execution_id
            ),
        )

    def execution_provenance(self, step_execution_id: str) -> ExecutionProvenance:
        if self.repositories.step_executions.get(step_execution_id) is None:
            raise EntityNotFoundError(
                f"StepExecution not found: {step_execution_id}"
            )
        return ExecutionProvenance(
            stepExecutionId=step_execution_id,
            outgoing=self.repositories.provenance_links.list_from(step_execution_id),
            incoming=self.repositories.provenance_links.list_to(step_execution_id),
        )


__all__ = ["IdentityQueryService"]

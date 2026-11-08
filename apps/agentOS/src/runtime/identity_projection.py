"""把执行运行时事件投影到 AgentOS 身份与生命周期。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
import hashlib
import json
import logging
from types import SimpleNamespace
from typing import Any

from components.executor import ACGGraphCompiler
from contracts.content import ContentKind
from contracts.identity import (
    AttemptId,
    BlueprintId,
    RunId,
    TaskId,
    new_run_id,
    new_mission_id,
)
from contracts.planning import (
    TaskBindingPatch,
    TaskImplementationBinding,
    TaskPlan,
    TaskPlanPatch,
)
from contracts.resource import ExecutionBinding as RuntimeExecutionBinding
from domain.identity_graph import (
    BlueprintNodeBinding,
    BlueprintRelationType,
    ExecutionBinding,
    IdentityRelation,
    ProvenanceLink,
    RunArtifactBinding,
    RunArtifactDisposition,
    TaskBinding,
)
from domain.models import (
    AcgBlueprint,
    Artifact,
    RunStatus,
    StepExecution,
    StepExecutionStatus,
)
from domain.lifecycle_projection import LifecycleProjectionEvent
from domain.repository import EntityNotFoundError, IdentityConflictError, RepositorySet
from support.acg.capabilities import CapabilityCatalog
from support.acg.native_capabilities import build_default_capability_catalog
from support.acg.schema import EdgeType, RuntimeBlueprintSpec
from support.acg.validation import validate_blueprint
from components.planner.service import apply_task_plan_patch

from .context import ExecutionContext
from .planner_bridge import PlannerIdentityBridge
from .runner import AcgIdentityLifecycleService

logger = logging.getLogger(__name__)

# Delivery cap shared by projection replay and outbox consumption: an event
# whose delivery keeps failing becomes a dead letter that stays persisted for
# manual repair instead of poisoning every later flush (2026-09-10 incident).
DEAD_LETTER_MAX_ATTEMPTS = 5


_EDGE_RELATIONS = {
    EdgeType.DEPENDENCY: BlueprintRelationType.DEPENDENCY,
}


class IdentityProjectionBridge:
    """只投影执行事实；不实现 Planner、Compiler、Scheduler 或 Executor。"""

    def __init__(
        self,
        lifecycle_service: AcgIdentityLifecycleService,
        repositories: RepositorySet,
        content_manifest_store: Any | None = None,
        capability_catalog: CapabilityCatalog | None = None,
    ) -> None:
        self.lifecycle_service = lifecycle_service
        self.repositories = repositories
        self.content_manifest_store = content_manifest_store
        self.capability_catalog = capability_catalog or build_default_capability_catalog()
        self.catalog_source = "injected" if capability_catalog is not None else "default_compatibility"

    @property
    def runtime(self) -> AcgIdentityLifecycleService:
        """兼容 Phase 3 初版属性名；新代码使用 ``lifecycle_service``。"""
        return self.lifecycle_service

    def resolve_task_plan_snapshot(self, task_plan: TaskPlan) -> TaskPlan:
        """Resolve a Run's immutable TaskPlan snapshot version before Runtime saves it."""
        return self._resolve_run_task_plan_snapshot(task_plan)

    def new_mission_id(self) -> str:
        """由 AgentOS 身份合同为 Execution Runtime 新任务分配唯一 taskId。"""
        return new_mission_id()

    def on_mission_created(self, task: Any) -> None:
        """使用 Execution Runtime 已持久化任务的同一个 taskId 建立 Mission。"""
        payload = {
            "missionId": task.mission_id,
            "goal": self._task_goal(task),
            "description": str(task.input.get("description") or ""),
            "domain": task.domain,
            "intent": task.intent,
            "userId": str(task.input.get("authenticatedUserId") or "system:agentos"),
            "tenantId": str(task.input.get("authenticatedTenantId") or ""),
        }
        with self._projection(
            f"mission.created:{task.mission_id}",
            "mission.created",
            task.mission_id,
            payload,
        ):
            self._on_mission_created(task)

    def _on_mission_created(self, task: Any) -> None:
        existing = self.repositories.missions.get(task.mission_id)
        if existing is not None:
            if existing.goal != self._task_goal(task):
                raise IdentityConflictError("missionId already belongs to another Mission goal")
            self._bind_mission_attachments(task)
            return
        owner = str(task.input.get("authenticatedUserId") or "system:agentos")
        self.lifecycle_service.create_mission(
            mission_id=task.mission_id,
            user_id=owner,
            goal=self._task_goal(task),
            description=str(task.input.get("description") or ""),
            metadata={
                "identityGeneration": "v2",
                "runtimeDomain": task.domain,
                "runtimeIntent": task.intent,
                "principalSource": (
                    "authenticatedUserId"
                    if task.input.get("authenticatedUserId")
                    else "system"
                ),
                **(
                    {"tenantId": str(task.input["authenticatedTenantId"])}
                    if task.input.get("authenticatedTenantId")
                    else {}
                ),
            },
        )
        self._bind_mission_attachments(task)

    def _bind_mission_attachments(self, task: Any) -> None:
        repository = getattr(self.repositories, "input_attachments", None)
        task_input = getattr(task, "input", {})
        attachment_ids = [
            str(item) for item in (task_input.get("attachmentIds") or []) if str(item)
        ]
        if repository is not None and attachment_ids:
            repository.bind_mission(task.mission_id, attachment_ids)

    def new_run_id(self, mission_id: str) -> str:
        """为新执行分配随后由 Execution Runtime 全链路复用的 runId。"""
        if self.repositories.missions.get(mission_id) is None:
            raise EntityNotFoundError(f"Mission not found: {mission_id}")
        return new_run_id()

    def on_run_prepared(
        self,
        task: Any,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan: TaskPlan,
        task_bindings: Sequence[TaskImplementationBinding],
    ) -> None:
        """登记真实 Execution Runtime Blueprint，并用同一 runId 建立 OS 运行身份。"""
        task_plan = self._resolve_run_task_plan_snapshot(task_plan)
        payload = {
            "missionId": task.mission_id,
            "runId": run.run_id,
            "workflowId": run.workflow_id,
            "blueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": task_plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [
                item.model_dump(by_alias=True, mode="json")
                for item in task_bindings
            ],
            "runProjection": self._safe_run_projection(run),
        }
        with self._projection(
            f"run.prepared:{run.run_id}",
            "run.prepared",
            run.run_id,
            payload,
        ):
            self._on_run_prepared(
                task,
                run,
                blueprint,
                task_plan,
                task_bindings,
            )

    def _on_run_prepared(
        self,
        task: Any,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan: TaskPlan,
        task_bindings: Sequence[TaskImplementationBinding],
    ) -> None:
        with self.repositories.storage.transaction():
            self._on_run_prepared_atomic(
                task,
                run,
                blueprint,
                task_plan,
                task_bindings,
            )

    def _on_run_prepared_atomic(
        self,
        task: Any,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan: TaskPlan,
        task_bindings: Sequence[TaskImplementationBinding],
    ) -> None:
        existing_run = self.repositories.runs.get(run.run_id)
        if existing_run is not None:
            if existing_run.mission_id != task.mission_id:
                raise IdentityConflictError("runId already belongs to another Mission")
            existing_blueprint = self.repositories.blueprints.get(
                existing_run.blueprint_id
            )
            if (
                existing_blueprint is None
                or existing_blueprint.graph
                != blueprint.model_dump(by_alias=True, mode="json")
            ):
                raise IdentityConflictError(
                    "runId already identifies another Blueprint version"
                )
        if task_plan.mission_id != task.mission_id:
            raise IdentityConflictError("TaskPlan does not belong to the Mission")
        bindings_by_key = {
            binding.plan_node_key: binding.acg_node_id
            for binding in task_bindings
        }
        if len(bindings_by_key) != len(task_bindings):
            raise IdentityConflictError("Blueprint contains duplicate SemanticTask bindings")
        if len(set(bindings_by_key.values())) != len(task_bindings):
            raise IdentityConflictError(
                "Each TaskPlan node requires a distinct executable Blueprint node"
            )
        plan_node_keys = {node.key for node in task_plan.nodes}
        if set(bindings_by_key) != plan_node_keys:
            raise IdentityConflictError("Blueprint bindings must cover the complete TaskPlan")
        executable_node_ids = {node.node_id for node in blueprint.step_nodes()}
        if set(bindings_by_key.values()) != executable_node_ids:
            raise IdentityConflictError(
                "Every executable Blueprint node requires an explicit SemanticTask binding"
            )

        # 先完成纯校验，再写入 SemanticTask，避免非法绑定留下部分身份数据。
        planned_nodes = PlannerIdentityBridge(
            self.lifecycle_service, self.capability_catalog
        ).record_task_plan(
            task_plan
        )
        explicit_bindings = {
            planned_nodes[key].task_id: acg_node_id
            for key, acg_node_id in bindings_by_key.items()
        }
        domain_blueprint = self._ensure_blueprint(
            task.mission_id,
            blueprint,
            explicit_bindings,
            plan_version=task_plan.plan_version,
        )
        if existing_run is not None:
            if (
                existing_run.blueprint_id != domain_blueprint.blueprint_id
                or existing_run.graph_version != domain_blueprint.version
            ):
                raise IdentityConflictError(
                    "runId already identifies another execution definition"
                )
            self._bind_run_attachments(run)
            return
        execution_state = getattr(run, "execution_state", {})
        lineage = {
            key: execution_state[key]
            for key in (
                "parentRunId",
                "supersedesRunId",
                "sourceRunId",
                "sourcePatchId",
                "rerunReason",
            )

            if isinstance(execution_state, dict) and execution_state.get(key)
        }
        self.lifecycle_service.create_run(
            mission_id=task.mission_id,
            blueprint_id=domain_blueprint.blueprint_id,
            run_id=run.run_id,
            metadata={
                "identityGeneration": "v2",
                "workflowId": run.workflow_id,
                "runtimeGraphId": blueprint.graph_id,
                # The Run points at the immutable planning snapshot while the
                # SemanticTask row remains the stable logical identity.
                "taskPlanVersion": task_plan.plan_version,
                **self._identity_run_metadata(run),
                **lineage,
            },
        )
        self._bind_run_attachments(run)

    def _bind_run_attachments(self, run: Any) -> None:
        repository = getattr(self.repositories, "input_attachments", None)
        run_input = getattr(run, "input", {})
        attachment_ids = [
            str(item) for item in (run_input.get("attachmentIds") or []) if str(item)
        ]
        if repository is not None and attachment_ids:
            repository.bind_run(run.run_id, attachment_ids)

    def _resolve_run_task_plan_snapshot(self, task_plan: TaskPlan) -> TaskPlan:
        """Allocate a new snapshot version only when a new Run changes plan content.

        Planner keys remain the logical identity.  The version here distinguishes
        immutable planning snapshots and is never derived from title/objective.
        Direct Planner repository calls keep their strict same-version conflict
        behavior; this resolution is only the Run preparation boundary.
        """
        latest = self.repositories.task_plans.latest(task_plan.mission_id)
        if latest is None:
            return task_plan

        def snapshot_payload(plan: TaskPlan) -> dict[str, Any]:
            payload = plan.model_dump(by_alias=True, mode="json")
            payload.pop("planVersion", None)
            return payload

        existing = self.repositories.task_plans.get(
            task_plan.mission_id, task_plan.plan_version
        )
        if existing is not None:
            if snapshot_payload(existing) == snapshot_payload(task_plan):
                return task_plan
            return task_plan.model_copy(
                update={"plan_version": latest.plan_version + 1}
            )
        if task_plan.plan_version <= latest.plan_version:
            if snapshot_payload(latest) == snapshot_payload(task_plan):
                return task_plan.model_copy(update={"plan_version": latest.plan_version})
            return task_plan.model_copy(
                update={"plan_version": latest.plan_version + 1}
            )
        return task_plan

    def on_run_snapshot(self, run_id: str, projection: dict[str, Any]) -> None:
        """Refresh reference-only operational state without reading Execution Runtime."""
        payload = {"runId": run_id, "projection": dict(projection)}
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._projection(
            f"run.snapshot:{run_id}:{digest}",
            "run.snapshot",
            run_id,
            payload,
        ):
            self._on_run_snapshot(run_id, projection)

    def _on_run_snapshot(self, run_id: str, projection: dict[str, Any]) -> None:
        self._run(run_id)
        self.repositories.runs.merge_metadata(
            run_id,
            self._identity_run_metadata(
                SimpleNamespace(execution_state=dict(projection or {}))
            ),
        )

    def on_blueprint_revised(
        self,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan_patch: TaskPlanPatch | None = None,
        task_binding_patch: TaskBindingPatch | None = None,
    ) -> str:
        """把 Execution Runtime 审核屏障产生的图修订登记为新 Blueprint 版本。"""
        payload = {
            "missionId": run.mission_id,
            "runId": run.run_id,
            "blueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlanPatch": (
                task_plan_patch.model_dump(by_alias=True, mode="json")
                if task_plan_patch is not None
                else None
            ),
            "taskBindingPatch": (
                task_binding_patch.model_dump(by_alias=True, mode="json")
                if task_binding_patch is not None else None
            ),
        }
        with self._projection(
            f"blueprint.revised:{run.run_id}:{blueprint.version}",
            "blueprint.revised",
            run.run_id,
            payload,
        ):
            return self._on_blueprint_revised_as_new_run(
                run,
                blueprint,
                task_plan_patch,
                task_binding_patch,
            )

    def on_execution_permit_blueprint_promoted(
        self,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan: TaskPlan,
        task_bindings: Sequence[TaskImplementationBinding],
        permit_id: str,
    ) -> None:
        """Promote the existing Identity Run only under the durable permit saga.

        This projection intentionally does not create or supersede a Run. The
        permit authority first records PREPARING and retries this idempotent
        event if a process exits between Identity and Workflow commits.
        """
        payload = {
            "permitId": permit_id,
            "missionId": run.mission_id,
            "runId": run.run_id,
            "blueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": task_plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [item.model_dump(by_alias=True, mode="json") for item in task_bindings],
        }
        with self._projection(
            f"execution.permit.identity:{permit_id}",
            "execution.permit.identity.promoted",
            run.run_id,
            payload,
        ):
            self._promote_execution_permit_identity(run, blueprint, task_plan, task_bindings)

    def _promote_execution_permit_identity(
        self,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan: TaskPlan,
        task_bindings: Sequence[TaskImplementationBinding],
    ) -> None:
        domain_run = self._run(run.run_id)
        if domain_run.mission_id != run.mission_id:
            raise IdentityConflictError("execution permit candidate belongs to another Mission")
        prior = self.repositories.blueprints.get(domain_run.blueprint_id)
        if prior is None:
            raise EntityNotFoundError("source Identity Blueprint is missing")
        current_plan = self.repositories.task_plans.latest(run.mission_id)
        if (prior.graph == blueprint.model_dump(by_alias=True, mode="json")
                and current_plan == task_plan and domain_run.graph_version == blueprint.version):
            return
        prior_graph = RuntimeBlueprintSpec.model_validate(prior.graph)
        if not {node.node_id for node in prior_graph.step_nodes()} <= {node.node_id for node in blueprint.step_nodes()}:
            raise IdentityConflictError("execution permit cannot remove executable Identity nodes")
        if task_plan.mission_id != run.mission_id or task_plan.plan_version != int(prior.metadata.get("plannerPlanVersion") or 1) + 1:
            raise IdentityConflictError("execution permit TaskPlan must extend the current Identity plan")
        persisted = PlannerIdentityBridge(self.lifecycle_service, self.capability_catalog).record_task_plan(task_plan)
        by_key = {item.plan_node_key: item.acg_node_id for item in task_bindings}
        if set(by_key) != {node.key for node in task_plan.nodes}:
            raise IdentityConflictError("execution permit bindings must cover the accepted TaskPlan")
        task_bindings_by_id = {persisted[key].task_id: by_key[key] for key in by_key}
        revised = self._ensure_blueprint(
            run.mission_id, blueprint, task_bindings_by_id, plan_version=task_plan.plan_version
        )
        self.repositories.runs.update_blueprint(run.run_id, revised.blueprint_id, revised.version)

    def on_graph_patch_prepared(
        self,
        task: Any,
        old_run: Any,
        new_run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan: TaskPlan,
        task_bindings: Sequence[TaskImplementationBinding],
        patch_id: str,
    ) -> None:
        """Atomically create the replacement identity Run and supersede its parent."""
        payload = {
            "missionId": task.mission_id,
            "oldRunId": old_run.run_id,
            "newRunId": new_run.run_id,
            "workflowId": new_run.workflow_id,
            "patchId": patch_id,
            "blueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": task_plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [
                item.model_dump(by_alias=True, mode="json")
                for item in task_bindings
            ],
            "executionState": dict(getattr(new_run, "execution_state", {}) or {}),
        }
        with self._projection(
            f"graph.patch.prepared:{old_run.run_id}:{patch_id}",
            "graph.patch.prepared",
            old_run.run_id,
            payload,
        ):
            with self.repositories.storage.transaction():
                self._on_run_prepared_atomic(
                    task,
                    new_run,
                    blueprint,
                    task_plan,
                    task_bindings,
                )
                self._on_run_superseded(old_run.run_id)

    def _on_blueprint_revised_as_new_run(
        self,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan_patch: TaskPlanPatch | None,
        task_binding_patch: TaskBindingPatch | None,
    ) -> str:
        domain_run = self._run(run.run_id)
        if domain_run.mission_id != run.mission_id:
            raise IdentityConflictError("revised Blueprint does not belong to Run task")
        prior_graph = RuntimeBlueprintSpec.model_validate(
            self.repositories.blueprints.get(domain_run.blueprint_id).graph
        )
        prior_step_ids = {node.node_id for node in prior_graph.step_nodes()}
        revised_step_ids = {node.node_id for node in blueprint.step_nodes()}
        if prior_step_ids - revised_step_ids:
            raise IdentityConflictError("Blueprint revision cannot remove executable nodes")
        current_plan = self.repositories.task_plans.latest(run.mission_id)
        if current_plan is None:
            raise EntityNotFoundError("TaskPlan is missing for Blueprint revision")
        next_plan = current_plan
        if revised_step_ids - prior_step_ids:
            if task_plan_patch is None or task_binding_patch is None:
                raise IdentityConflictError("new executable nodes require TaskPlanPatch and TaskBindingPatch")
            next_plan = apply_task_plan_patch(
                current_plan, task_plan_patch, self.capability_catalog,
                catalog_source=self.catalog_source,
            )
            binding_patch = task_binding_patch.bindings
        else:
            if task_plan_patch is not None or task_binding_patch is not None:
                raise IdentityConflictError("patch data is only valid when executable nodes are added")
            binding_patch = ()
        by_key: dict[str, Any] = {}
        for node in self.repositories.semantic_tasks.list_for_mission(run.mission_id):
            semantic_key = node.semantic_task_key or node.metadata.get("plannerSemanticKey")
            if semantic_key:
                by_key[str(semantic_key)] = node
        binding_items: list[TaskImplementationBinding] = []
        for node in next_plan.nodes:
            semantic_task = by_key.get(node.key)
            if semantic_task is None:
                continue
            existing = self.repositories.task_bindings.find_for_task(
                semantic_task.task_id,
                domain_run.blueprint_id,
            )
            if existing:
                binding_items.append(TaskImplementationBinding(
                    planNodeKey=node.key,
                    acgNodeId=existing[0].acg_node_id,
                ))
        binding_items.extend(binding_patch)
        new_run_id = self.new_run_id(run.mission_id)
        new_run = SimpleNamespace(
            run_id=new_run_id,
            mission_id=run.mission_id,
            workflow_id=run.workflow_id,
        )
        task = SimpleNamespace(mission_id=run.mission_id)
        self.on_run_prepared(task, new_run, blueprint, next_plan, tuple(binding_items))
        self.on_run_superseded(run.run_id, new_run_id, str(getattr(run, "run_id", "blueprint-revision")))
        return new_run_id

    def _on_blueprint_revised(
        self,
        run: Any,
        blueprint: RuntimeBlueprintSpec,
        task_plan_patch: TaskPlanPatch | None,
        task_binding_patch: TaskBindingPatch | None,
    ) -> None:
        domain_run = self._run(run.run_id)
        if domain_run.mission_id != run.mission_id:
            raise IdentityConflictError("revised Blueprint does not belong to Run task")
        prior_blueprint = self.repositories.blueprints.get(domain_run.blueprint_id)
        if prior_blueprint is None:
            raise EntityNotFoundError(
                f"AcgBlueprint not found: {domain_run.blueprint_id}"
            )
        if prior_blueprint.graph == blueprint.model_dump(by_alias=True, mode="json"):
            return
        prior_graph = RuntimeBlueprintSpec.model_validate(prior_blueprint.graph)
        prior_step_ids = {node.node_id for node in prior_graph.step_nodes()}
        revised_step_ids = {node.node_id for node in blueprint.step_nodes()}
        added_step_ids = revised_step_ids - prior_step_ids
        if prior_step_ids - revised_step_ids:
            raise IdentityConflictError(
                "Blueprint revision cannot remove executable nodes from the identity graph"
            )
        prior_bindings: dict[str, str] = {}
        for node in self.repositories.semantic_tasks.list_for_mission(run.mission_id):
            matches = self.repositories.task_bindings.find_for_task(
                node.task_id,
                domain_run.blueprint_id,
            )
            for binding in matches:
                prior_bindings[node.task_id] = binding.acg_node_id
        prior_plan_version = int(prior_blueprint.metadata.get("plannerPlanVersion") or 1)
        next_plan_version = prior_plan_version
        if added_step_ids:
            if task_plan_patch is None:
                raise IdentityConflictError(
                    "new executable Blueprint nodes require a TaskPlanPatch"
                )
            if task_plan_patch.mission_id != run.mission_id:
                raise IdentityConflictError("TaskPlanPatch does not belong to Run task")
            if task_plan_patch.base_plan_version != prior_plan_version:
                raise IdentityConflictError(
                    "TaskPlanPatch basePlanVersion does not match active Blueprint plan"
                )
            if task_binding_patch is None:
                raise IdentityConflictError("new executable Blueprint nodes require TaskBindingPatch")
            patch_binding_ids = {item.acg_node_id for item in task_binding_patch.bindings}
            if patch_binding_ids != added_step_ids:
                raise IdentityConflictError(
                    "TaskPlanPatch bindings must cover exactly the added executable nodes"
                )
            planned_nodes = PlannerIdentityBridge(
                self.lifecycle_service, self.capability_catalog
            ).record_task_plan_patch(task_plan_patch)
            for binding in task_binding_patch.bindings:
                prior_bindings[
                    planned_nodes[binding.plan_node_key].task_id
                ] = binding.acg_node_id
            next_plan_version = task_plan_patch.plan_version
        elif task_plan_patch is not None:
            raise IdentityConflictError(
                "TaskPlanPatch is only valid when executable Blueprint nodes are added"
            )
        revised = self._ensure_blueprint(
            run.mission_id,
            blueprint,
            prior_bindings,
            plan_version=next_plan_version,
        )
        if domain_run.blueprint_id == revised.blueprint_id:
            return
        self.repositories.runs.update_blueprint(
            run.run_id,
            revised.blueprint_id,
            revised.version,
        )

    def ensure_attempt(self, run: Any, step_id: str, attempt_number: int) -> str:
        """幂等创建 ACGNode 对应的 Attempt，并把其 ID 交回 Execution Runtime Scheduler。"""
        payload = {
            "runId": run.run_id,
            "missionId": run.mission_id,
            "stepId": step_id,
            "attemptNumber": attempt_number,
        }
        with self._projection(
            f"attempt.ensured:{run.run_id}:{step_id}:{attempt_number}",
            "attempt.ensured",
            run.run_id,
            payload,
        ):
            return self._ensure_attempt(run, step_id, attempt_number)

    def _ensure_attempt(self, run: Any, step_id: str, attempt_number: int, attempt_id: str | None = None) -> str:
        domain_run = self.repositories.runs.get(run.run_id)
        if domain_run is None:
            raise EntityNotFoundError(f"WorkflowRunV2 not found: {run.run_id}")
        node = self._resolve_semantic_task(domain_run.blueprint_id, step_id)
        return self.lifecycle_service.create_attempt(
            run_id=run.run_id,
            task_id=node.task_id,
            # Events carry the emitter's attemptId, so the projection owns
            # contiguous numbering; the emitter's attemptNumber may drift after
            # checkpoint resumes or loop re-entry and must not poison applies.
            # Id-less direct calls keep the number as their only idempotency key.
            attempt_number=None if attempt_id is not None else attempt_number,
            attempt_id=attempt_id,
        ).attempt_id

    def next_attempt_number(self, run_id: str, step_id: str) -> int:
        """Return the next contiguous Attempt number for one Run node."""
        domain_run = self._run(run_id)
        node = self._resolve_semantic_task(domain_run.blueprint_id, step_id)
        attempts = [
            attempt
            for attempt in self.repositories.attempts.list_for_run(run_id)
            if attempt.task_id == node.task_id
        ]
        return max((attempt.attempt_number for attempt in attempts), default=0) + 1

    def on_resource_bound(
        self,
        *,
        attempt_id: str,
        binding: RuntimeExecutionBinding,
        agent_id: str,
        model_id: str,
    ) -> None:
        payload = {
            "attemptId": attempt_id,
            "binding": binding.model_dump(by_alias=True, mode="json"),
            "agentId": agent_id,
            "modelId": model_id,
        }
        with self._projection(
            f"resource.bound:{attempt_id}",
            "resource.bound",
            attempt_id,
            payload,
        ):
            self.record_scheduling_binding(
                attempt_id=attempt_id,
                runtime_binding=binding,
                agent_id=agent_id,
                model_id=model_id,
            )

    def on_step_started(self, *, run_id: str, attempt_id: str, step_id: str) -> str:
        payload = {"runId": run_id, "attemptId": attempt_id, "stepId": step_id}
        with self._projection(
            f"step.started:{attempt_id}",
            "step.started",
            attempt_id,
            payload,
        ):
            return self._on_step_started(
                run_id=run_id,
                attempt_id=attempt_id,
                step_id=step_id,
            )

    def _on_step_started(self, *, run_id: str, attempt_id: str, step_id: str, step_execution_id: str | None = None) -> str:
        attempt = self.repositories.attempts.get(attempt_id)
        if attempt is None or attempt.run_id != run_id:
            raise IdentityConflictError("Step start does not belong to Attempt run")
        node = self._resolve_semantic_task(
            self._run(run_id).blueprint_id,
            step_id,
        )
        if node.task_id != attempt.task_id:
            raise IdentityConflictError("Step start does not match Attempt SemanticTask")
        existing = self.repositories.step_executions.list_for_attempt(attempt_id)
        if existing:
            if len(existing) != 1:
                raise IdentityConflictError("Attempt has multiple StepExecutions")
            return existing[0].step_execution_id
        context = self.lifecycle_service.create_context(run_id)
        return self.lifecycle_service.start_step_execution(
            context,
            attempt_id=attempt_id,
            input={"acgNodeId": step_id},
            step_execution_id=step_execution_id,
        ).step_execution_id

    def on_step_succeeded(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_execution_id: str,
        result: dict[str, Any],
    ) -> None:
        payload = {
            "runId": run_id,
            "attemptId": attempt_id,
            "stepExecutionId": step_execution_id,
            "result": self._safe_projection_result(result),
        }
        with self._projection(
            f"step.succeeded:{step_execution_id}",
            "step.succeeded",
            step_execution_id,
            payload,
        ):
            self._on_step_succeeded(
                run_id=run_id,
                attempt_id=attempt_id,
                step_execution_id=step_execution_id,
                result=result,
            )

    def _on_step_succeeded(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_execution_id: str,
        result: dict[str, Any],
    ) -> None:
        execution = self._execution(step_execution_id, run_id, attempt_id)
        evidence_ids = self._provenance_event_ids(result)
        memory_ref = result.get("memoryRef")
        memory_ids = (
            [str(memory_ref)]
            if isinstance(memory_ref, str) and memory_ref and memory_ref != "memory:none"
            else []
        )
        if execution.status is StepExecutionStatus.SUCCEEDED:
            self._project_artifacts(
                run_id=run_id,
                attempt_id=attempt_id,
                result=result,
            )
            self._record_provenance(execution, evidence_ids, memory_ids)
            return
        if execution.status is not StepExecutionStatus.RUNNING:
            raise IdentityConflictError("terminal StepExecution cannot become succeeded")
        safe_output = {
            key: result[key]
            for key in (
                "commitId",
                "outputRef",
                "outputSummary",
                "contextRef",
                "memoryRef",
                "traceRef",
                "auditDecisionRef",
                "nodeExecution",
                "communicationRefs",
                "evidenceRefs",
            )
            if result.get(key) is not None
        }
        artifacts = self._safe_artifact_descriptors(result)
        if artifacts:
            safe_output["artifacts"] = artifacts
        context = self.lifecycle_service.create_context(run_id)
        finished = self.lifecycle_service.complete_step_execution(
            context,
            step_execution_id,
            output=safe_output,
        )
        self._project_artifacts(
            run_id=run_id,
            attempt_id=attempt_id,
            result=result,
        )
        self._record_provenance(finished, evidence_ids, memory_ids)

    def _project_artifacts(
        self,
        *,
        run_id: str,
        attempt_id: str,
        result: dict[str, Any],
    ) -> None:
        """Project sealed ContentManifest references into immutable Artifacts."""
        descriptors = self._artifact_descriptors(result)
        if not descriptors:
            return
        if self.content_manifest_store is None:
            raise IdentityConflictError(
                "Artifact projection requires the shared ContentManifestStore"
            )
        run = self.repositories.runs.get(run_id)
        attempt = self.repositories.attempts.get(attempt_id)
        if run is None or attempt is None or attempt.run_id != run_id:
            raise IdentityConflictError("Artifact producer Attempt does not belong to Run")
        task = self.repositories.semantic_tasks.get(attempt.task_id)
        if task is None or task.semantic_task_key is None:
            raise IdentityConflictError(
                "Artifact producer Attempt requires a canonical SemanticTask key"
            )
        execution_binding = self.repositories.execution_bindings.get_for_attempt(attempt_id)
        if execution_binding is None:
            raise EntityNotFoundError(f"ExecutionBinding not found: {attempt_id}")
        artifact_keys = [str(item.get("artifactKey") or "primary") for item in descriptors]
        if len(artifact_keys) != len(set(artifact_keys)):
            raise IdentityConflictError(
                "one Attempt cannot produce multiple Artifact variants for the same artifactKey"
            )
        # Artifact and binding writes share the V2 transaction.  ContentManifest
        # sealing already happened in the content store; this prevents a malformed
        # multi-artifact event from leaving an unbound Artifact behind.
        with self.repositories.storage.transaction():
            for descriptor in descriptors:
                manifest_id = descriptor.get("manifestId")
                checksum = descriptor.get("checksum")
                if not isinstance(manifest_id, str) or not manifest_id:
                    raise IdentityConflictError("Artifact descriptor requires manifestId")
                if not isinstance(checksum, str) or not checksum:
                    raise IdentityConflictError("Artifact descriptor requires checksum")
                manifest = self.content_manifest_store.get_manifest(manifest_id)
                if (
                    manifest.kind is not ContentKind.ARTIFACT
                    or not manifest.sealed
                    or manifest.owner_type != "run"
                    or manifest.owner_id != run_id
                    or manifest.checksum != checksum
                ):
                    raise IdentityConflictError(
                        "Artifact descriptor must reference a sealed matching ContentManifest"
                    )
                semantic_task_key = descriptor.get("semanticTaskKey") or task.semantic_task_key
                if semantic_task_key != task.semantic_task_key:
                    raise IdentityConflictError(
                        "Artifact descriptor semanticTaskKey does not match producer SemanticTask"
                    )
                artifact_key = str(descriptor.get("artifactKey") or "primary")
                artifact_id = "artifact_" + hashlib.sha256(
                    f"content-manifest:{manifest_id}".encode("utf-8")
                ).hexdigest()[:12]
                artifact = Artifact(
                    artifactId=artifact_id,
                    missionId=run.mission_id,
                    originRunId=run_id,
                    taskId=task.task_id,
                    semanticTaskKey=task.semantic_task_key,
                    artifactKey=artifact_key,
                    acgNodeId=execution_binding.acg_node_id,
                    producerAttemptId=attempt_id,
                    name=str(descriptor.get("name") or descriptor.get("title") or artifact_key),
                    artifactType=str(
                        descriptor.get("artifactType") or descriptor.get("type") or "artifact"
                    ),
                    mediaType=manifest.media_type,
                    contentRef=manifest.manifest_id,
                    checksum=manifest.checksum,
                    createdAt=manifest.created_at,
                    metadata=(descriptor.get("metadata") if isinstance(descriptor.get("metadata"), dict) else {}),
                )
                self.repositories.artifacts.add(artifact)
                self.repositories.run_artifact_bindings.add(
                    RunArtifactBinding(
                        runId=run_id,
                        taskId=task.task_id,
                        semanticTaskKey=task.semantic_task_key,
                        artifactKey=artifact_key,
                        artifactId=artifact.artifact_id,
                        disposition=RunArtifactDisposition.GENERATED,
                        createdAt=artifact.created_at,
                    )
                )

    @staticmethod
    def _artifact_descriptors(result: dict[str, Any]) -> list[dict[str, Any]]:
        raw = result.get("artifacts")
        if raw is None and isinstance(result.get("artifact"), dict):
            raw = [result["artifact"]]
        elif isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def on_step_failed(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_execution_id: str,
        reason: str,
    ) -> None:
        payload = {
            "runId": run_id,
            "attemptId": attempt_id,
            "stepExecutionId": step_execution_id,
            "reason": reason,
        }
        with self._projection(
            f"step.failed:{step_execution_id}",
            "step.failed",
            step_execution_id,
            payload,
        ):
            self._on_step_failed(
                run_id=run_id,
                attempt_id=attempt_id,
                step_execution_id=step_execution_id,
                reason=reason,
            )

    def _on_step_failed(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_execution_id: str,
        reason: str,
    ) -> None:
        execution = self._execution(step_execution_id, run_id, attempt_id)
        if execution.status is StepExecutionStatus.FAILED:
            return
        if execution.status is not StepExecutionStatus.RUNNING:
            raise IdentityConflictError("terminal StepExecution cannot become failed")
        self.lifecycle_service.fail_step_execution(
            self.lifecycle_service.create_context(run_id),
            step_execution_id,
            failure_reason=reason,
        )

    def on_step_cancelled(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_execution_id: str,
        reason: str,
    ) -> None:
        payload = {
            "runId": run_id,
            "attemptId": attempt_id,
            "stepExecutionId": step_execution_id,
            "reason": reason,
        }
        with self._projection(
            f"step.cancelled:{step_execution_id}",
            "step.cancelled",
            step_execution_id,
            payload,
        ):
            self._on_step_cancelled(
                run_id=run_id,
                attempt_id=attempt_id,
                step_execution_id=step_execution_id,
                reason=reason,
            )

    def _on_step_cancelled(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_execution_id: str,
        reason: str,
    ) -> None:
        execution = self._execution(step_execution_id, run_id, attempt_id)
        if execution.status is StepExecutionStatus.CANCELLED:
            return
        if execution.status is not StepExecutionStatus.RUNNING:
            raise IdentityConflictError("terminal StepExecution cannot become cancelled")
        self.lifecycle_service.cancel_step_execution(
            self.lifecycle_service.create_context(run_id),
            step_execution_id,
            reason=reason,
        )

    def on_run_finished(self, run_id: str, status: str) -> None:
        payload = {"runId": run_id, "status": status}
        with self._projection(
            f"run.finished:{run_id}:{status}",
            "run.finished",
            run_id,
            payload,
        ):
            self._on_run_finished(run_id, status)

    def on_run_retry_prepared(self, run_id: str, recovery_count: int) -> None:
        payload = {"runId": run_id, "recoveryCount": recovery_count}
        with self._projection(
            f"run.retry_prepared:{run_id}:{recovery_count}",
            "run.retry_prepared",
            run_id,
            payload,
        ):
            run = self._run(run_id)
            if run.status is RunStatus.PENDING:
                return
            if run.status is not RunStatus.FAILED:
                raise IdentityConflictError("only a failed WorkflowRunV2 can be retried in place")
            self.lifecycle_service.retry_failed_run(run_id)

    def on_run_superseded(
        self,
        run_id: str,
        new_run_id: str,
        patch_id: str,
    ) -> None:
        payload = {
            "runId": run_id,
            "newRunId": new_run_id,
            "patchId": patch_id,
        }
        with self._projection(
            f"run.superseded:{run_id}:{patch_id}",
            "run.superseded",
            run_id,
            payload,
        ):
            self._on_run_superseded(run_id)

    def _on_run_superseded(self, run_id: str) -> None:
        run = self._run(run_id)
        if run.status is RunStatus.SUPERSEDED:
            return
        if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise IdentityConflictError("terminal WorkflowRunV2 cannot be superseded")
        self.lifecycle_service.finish_run(run_id, RunStatus.SUPERSEDED)

    def _on_run_finished(self, run_id: str, status: str) -> None:
        target = {
            "succeeded": RunStatus.SUCCEEDED,
            "failed": RunStatus.FAILED,
            "cancelled": RunStatus.CANCELLED,
        }.get(status)
        if target is None:
            raise ValueError(f"unsupported terminal run status: {status}")
        run = self._run(run_id)
        if run.status is target:
            return
        if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise IdentityConflictError("terminal WorkflowRunV2 status cannot be rewritten")
        self.lifecycle_service.finish_run(run_id, target)

    def register_blueprint(
        self,
        *,
        mission_id: str,
        version: int,
        runtime_blueprint: RuntimeBlueprintSpec,
        task_bindings: Mapping[TaskId, str],
        metadata: dict[str, Any] | None = None,
    ) -> AcgBlueprint:
        """登记 Execution Runtime 权威蓝图，并显式记录 SemanticTask 到其 nodeId 的实现关系。"""
        if runtime_blueprint.mission_id is not None and runtime_blueprint.mission_id != mission_id:
            raise IdentityConflictError("Blueprint missionId does not match Mission")
        validate_blueprint(runtime_blueprint)
        runtime_node_ids = {node.node_id for node in runtime_blueprint.nodes}
        if not task_bindings:
            raise ValueError("Blueprint requires at least one SemanticTask binding")
        for semantic_task_id, acg_node_id in task_bindings.items():
            if semantic_task_id == acg_node_id:
                raise IdentityConflictError("SemanticTask identity must remain distinct from ACG nodeId")
            if acg_node_id not in runtime_node_ids:
                raise IdentityConflictError(f"ACG node does not exist: {acg_node_id}")
            node = self.repositories.semantic_tasks.get(semantic_task_id)
            if node is None:
                raise EntityNotFoundError(f"SemanticTask not found: {semantic_task_id}")
            if node.mission_id != mission_id:
                raise IdentityConflictError("SemanticTask does not belong to Mission")

        graph = runtime_blueprint.model_dump(by_alias=True, mode="json")
        blueprint = self.lifecycle_service.create_blueprint(
            mission_id=mission_id,
            version=version,
            graph_id=runtime_blueprint.graph_id,
            graph=graph,
            metadata={**(metadata or {}), "runtime": "acg"},
        )
        self._ensure_blueprint_relations(
            blueprint,
            runtime_blueprint,
            task_bindings,
        )
        return blueprint

    def _ensure_blueprint_relations(
        self,
        blueprint: AcgBlueprint,
        runtime_blueprint: RuntimeBlueprintSpec,
        task_bindings: Mapping[TaskId, str],
    ) -> None:
        """幂等补齐 Blueprint 关系，供中断后的投影日志重放。"""
        for semantic_task_id, acg_node_id in task_bindings.items():
            existing = self.repositories.task_bindings.find_for_acg_node(
                acg_node_id,
                blueprint.blueprint_id,
            )
            if existing:
                if len(existing) != 1 or existing[0].task_id != semantic_task_id:
                    raise IdentityConflictError(
                        "Blueprint ACG node already has another primary SemanticTask binding"
                    )
                continue
            self.repositories.task_bindings.add(TaskBinding(
                taskId=semantic_task_id,
                blueprintId=blueprint.blueprint_id,
                acgNodeId=acg_node_id,
            ))
        existing_edges = {
            (
                item.source_node_id,
                item.target_node_id,
                item.relation_type,
            )
            for item in self.repositories.blueprint_node_bindings.list_for_blueprint(
                blueprint.blueprint_id
            )
        }
        for edge in runtime_blueprint.edges:
            relation = _EDGE_RELATIONS.get(edge.edge_type)
            if relation is None:
                continue
            if (edge.source_id, edge.target_id, relation) in existing_edges:
                continue
            self.repositories.blueprint_node_bindings.add(BlueprintNodeBinding(
                blueprintId=blueprint.blueprint_id,
                sourceNodeId=edge.source_id,
                targetNodeId=edge.target_id,
                relationType=relation,
            ))

    def compile(self, blueprint_id: BlueprintId, *, run_id: RunId):
        """直接委托 Execution Runtime ``ACGGraphCompiler``，返回其原生执行图。"""
        blueprint = self.repositories.blueprints.get(blueprint_id)
        if blueprint is None:
            raise EntityNotFoundError(f"AcgBlueprint not found: {blueprint_id}")
        run = self.repositories.runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"WorkflowRunV2 not found: {run_id}")
        if run.blueprint_id != blueprint_id or run.mission_id != blueprint.mission_id:
            raise IdentityConflictError("Compilation identities do not belong to the Run")
        runtime_blueprint = RuntimeBlueprintSpec.model_validate(blueprint.graph)
        return ACGGraphCompiler().compile(runtime_blueprint, run_id=run_id)

    def record_scheduling_binding(
        self,
        *,
        attempt_id: AttemptId,
        runtime_binding: RuntimeExecutionBinding,
        agent_id: str,
        model_id: str,
    ) -> ExecutionBinding:
        """把 Execution Runtime Scheduler 的真实资源选择登记为 OS 级执行绑定。"""
        attempt = self.repositories.attempts.get(attempt_id)
        if attempt is None:
            raise EntityNotFoundError(f"Attempt not found: {attempt_id}")
        if runtime_binding.attempt_id != attempt_id or runtime_binding.run_id != attempt.run_id:
            raise IdentityConflictError("Scheduling binding does not match Attempt identity")
        existing = self.repositories.execution_bindings.get_for_attempt(attempt_id)
        if existing is not None:
            if (
                existing.acg_node_id != runtime_binding.step_id
                or existing.resource_id != runtime_binding.resource_id
                or existing.agent_id != agent_id
                or existing.model_id != model_id
            ):
                raise IdentityConflictError("Attempt already has another ExecutionBinding")
            return existing
        binding = ExecutionBinding(
            attemptId=attempt_id,
            acgNodeId=runtime_binding.step_id,
            resourceId=runtime_binding.resource_id,
            agentId=agent_id,
            modelId=model_id,
            metadata={
                "runtimeBindingId": runtime_binding.binding_id,
                "runtimeKind": runtime_binding.runtime_kind.value,
                "snapshotVersion": runtime_binding.snapshot_version,
                **runtime_binding.metadata,
            },
        )
        self.repositories.execution_bindings.add(binding)
        return binding

    def start_execution(
        self,
        context: ExecutionContext,
        *,
        input: dict[str, Any],
    ) -> StepExecution:
        """在 Execution Runtime NodeRunner 开始工作时创建生命周期投影。"""
        return self.lifecycle_service.start_step_execution(context, input=input)

    def finish_execution(
        self,
        context: ExecutionContext,
        step_execution_id: str,
        *,
        output: dict[str, Any],
        evidence_ids: Sequence[str] = (),
        memory_ids: Sequence[str] = (),
    ) -> StepExecution:
        """在 Execution Runtime NodeRunner 完成后结束投影并登记产物血缘。"""
        execution = self.lifecycle_service.complete_step_execution(
            context,
            step_execution_id,
            output=output,
        )
        self._record_provenance(execution, evidence_ids, memory_ids)
        return execution

    def fail_execution(
        self,
        context: ExecutionContext,
        step_execution_id: str,
        *,
        failure_reason: str,
        output: dict[str, Any] | None = None,
    ) -> StepExecution:
        """在 Execution Runtime NodeRunner 失败时记录相同 Attempt 的失败生命周期。"""
        return self.lifecycle_service.fail_step_execution(
            context,
            step_execution_id,
            failure_reason=failure_reason,
            output=output,
        )

    def _record_provenance(
        self,
        execution: StepExecution,
        evidence_ids: Sequence[str],
        memory_ids: Sequence[str],
    ) -> None:
        for evidence_id in evidence_ids:
            self._add_provenance(ProvenanceLink(
                sourceId=execution.step_execution_id,
                targetId=evidence_id,
                relationType=IdentityRelation.PRODUCES,
            ))
        for memory_id in memory_ids:
            self._add_provenance(ProvenanceLink(
                sourceId=execution.step_execution_id,
                targetId=memory_id,
                relationType=IdentityRelation.WRITES,
            ))

    def _ensure_blueprint(
        self,
        mission_id: str,
        runtime_blueprint: RuntimeBlueprintSpec,
        task_bindings: Mapping[TaskId, str],
        *,
        plan_version: int,
    ) -> AcgBlueprint:
        step_ids = {step.node_id for step in runtime_blueprint.step_nodes()}
        if set(task_bindings.values()) != step_ids:
            raise IdentityConflictError(
                "Blueprint requires explicit SemanticTask binding for every executable node"
            )
        graph = runtime_blueprint.model_dump(by_alias=True, mode="json")
        existing_blueprints = self.repositories.blueprints.list_for_mission(mission_id)
        for blueprint in existing_blueprints:
            if blueprint.graph == graph:
                self._ensure_blueprint_relations(
                    blueprint,
                    runtime_blueprint,
                    task_bindings,
                )
                return blueprint
        version = max((item.version for item in existing_blueprints), default=0) + 1
        return self.register_blueprint(
            mission_id=mission_id,
            version=version,
            runtime_blueprint=runtime_blueprint,
            task_bindings=task_bindings,
            metadata={
                "plannerPlanVersion": plan_version,
                "sourceGraphVersion": runtime_blueprint.version,
            },
        )

    def _resolve_semantic_task(self, blueprint_id: BlueprintId, step_id: str):
        bindings = self.repositories.task_bindings.find_for_acg_node(
            step_id, blueprint_id
        )
        if len(bindings) != 1:
            raise IdentityConflictError("ACG node must have exactly one SemanticTask binding")
        node = self.repositories.semantic_tasks.get(bindings[0].task_id)
        if node is None:
            raise EntityNotFoundError(f"SemanticTask not found: {bindings[0].task_id}")
        return node

    def _run(self, run_id: str):
        run = self.repositories.runs.get(run_id)
        if run is None:
            raise EntityNotFoundError(f"WorkflowRunV2 not found: {run_id}")
        return run

    def _execution(self, step_execution_id: str, run_id: str, attempt_id: str):
        execution = self.repositories.step_executions.get(step_execution_id)
        if execution is None:
            raise EntityNotFoundError(f"StepExecution not found: {step_execution_id}")
        if execution.run_id != run_id or execution.attempt_id != attempt_id:
            raise IdentityConflictError("StepExecution does not belong to Execution Runtime execution identity")
        return execution

    def _add_provenance(self, link: ProvenanceLink) -> None:
        if any(
            item.target_id == link.target_id and item.relation_type is link.relation_type
            for item in self.repositories.provenance_links.list_from(link.source_id)
        ):
            return
        self.repositories.provenance_links.add(link)

    @contextmanager
    def _projection(
        self,
        event_id: str,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ):
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        event = LifecycleProjectionEvent(
            eventId=event_id,
            eventType=event_type,
            aggregateId=aggregate_id,
            payload=payload,
            payloadHash=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )
        self.repositories.projection_events.begin(event)
        try:
            yield
        except Exception as exc:
            self.repositories.projection_events.mark_failed(event_id, str(exc))
            raise
        else:
            self.repositories.projection_events.mark_applied(event_id)

    def replay_unapplied(self, *, limit: int = 200) -> dict[str, int]:
        """按持久化安全载荷重放失败或中断的身份投影。"""
        events = self.repositories.projection_events.list_unapplied(limit=limit)
        applied = 0
        failed = 0
        dead_lettered = 0
        for event in events:
            if int(event.attempts or 0) >= DEAD_LETTER_MAX_ATTEMPTS:
                dead_lettered += 1
                logger.warning(
                    "identity_projection_dead_letter_bypassed",
                    extra={
                        "eventId": event.event_id,
                        "eventType": event.event_type,
                        "attempts": event.attempts,
                    },
                )
                continue
            try:
                self._replay_event(event.event_type, event.payload)
            except Exception as exc:
                failed += 1
                self.repositories.projection_events.record_replay_failure(
                    event.event_id, str(exc)
                )
            else:
                applied += 1
                self.repositories.projection_events.mark_applied(event.event_id)
        return {
            "examined": len(events),
            "applied": applied,
            "failed": failed,
            "dead_lettered": dead_lettered,
        }

    def apply_lifecycle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Apply one event already admitted by the Identity Inbox."""
        self._replay_event(event_type, payload)

    def _replay_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "mission.created":
            task = SimpleNamespace(
                mission_id=payload["missionId"],
                title=payload["goal"],
                domain=payload["domain"],
                intent=payload["intent"],
                input={
                    "taskGoal": payload["goal"],
                    "description": payload.get("description", ""),
                    "authenticatedUserId": payload["userId"],
                    **(
                        {"authenticatedTenantId": payload["tenantId"]}
                        if payload.get("tenantId")
                        else {}
                    ),
                },
            )
            self.on_mission_created(task)
            return
        if event_type == "run.prepared":
            task = SimpleNamespace(mission_id=payload["missionId"])
            run = SimpleNamespace(
                run_id=payload["runId"],
                workflow_id=payload["workflowId"],
                execution_state=payload.get("runProjection") or {},
            )
            self.on_run_prepared(
                task,
                run,
                RuntimeBlueprintSpec.model_validate(payload["blueprint"]),
                TaskPlan.model_validate(payload["taskPlan"]),
                tuple(
                    TaskImplementationBinding.model_validate(item)
                    for item in payload["taskBindings"]
                ),
            )
            return
        if event_type == "run.snapshot":
            self.on_run_snapshot(
                payload["runId"],
                payload.get("projection") or payload.get("executionState") or {},
            )
            return
        if event_type == "graph.patch.prepared":
            task = SimpleNamespace(mission_id=payload["missionId"])
            old_run = SimpleNamespace(run_id=payload["oldRunId"])
            new_run = SimpleNamespace(
                run_id=payload["newRunId"],
                workflow_id=payload["workflowId"],
                execution_state=payload.get("executionState") or {},
            )
            self.on_graph_patch_prepared(
                task,
                old_run,
                new_run,
                RuntimeBlueprintSpec.model_validate(payload["blueprint"]),
                TaskPlan.model_validate(payload["taskPlan"]),
                tuple(
                    TaskImplementationBinding.model_validate(item)
                    for item in payload["taskBindings"]
                ),
                payload["patchId"],
            )
            return
        if event_type == "blueprint.revised":
            self.on_blueprint_revised(
                SimpleNamespace(
                    run_id=payload["runId"],
                    mission_id=payload["missionId"],
                ),
                RuntimeBlueprintSpec.model_validate(payload["blueprint"]),
                (
                    TaskPlanPatch.model_validate(payload["taskPlanPatch"])
                    if payload.get("taskPlanPatch") is not None
                    else None
                ),
                (
                    TaskBindingPatch.model_validate(payload["taskBindingPatch"])
                    if payload.get("taskBindingPatch") is not None
                    else None
                ),
            )
            return
        if event_type == "execution.permit.identity.promoted":
            self._promote_execution_permit_identity(
                SimpleNamespace(run_id=payload["runId"], mission_id=payload["missionId"]),
                RuntimeBlueprintSpec.model_validate(payload["blueprint"]),
                TaskPlan.model_validate(payload["taskPlan"]),
                tuple(TaskImplementationBinding.model_validate(item) for item in payload["taskBindings"]),
            )
            return
        if event_type == "attempt.ensured":
            run = SimpleNamespace(run_id=payload["runId"], mission_id=payload["missionId"])
            self._ensure_attempt(
                run, payload["stepId"], int(payload["attemptNumber"]), payload.get("attemptId")
            )
            return
        if event_type == "resource.bound":
            self.on_resource_bound(
                attempt_id=payload["attemptId"],
                binding=RuntimeExecutionBinding.model_validate(payload["binding"]),
                agent_id=payload["agentId"],
                model_id=payload["modelId"],
            )
            return
        if event_type == "step.started":
            self._on_step_started(
                run_id=payload["runId"],
                attempt_id=payload["attemptId"],
                step_id=payload["stepId"],
                step_execution_id=payload.get("stepExecutionId"),
            )
            return
        if event_type == "step.succeeded":
            self.on_step_succeeded(
                run_id=payload["runId"],
                attempt_id=payload["attemptId"],
                step_execution_id=payload["stepExecutionId"],
                result=payload["result"],
            )
            return
        if event_type in {"step.failed", "step.cancelled"}:
            handler = (
                self.on_step_failed
                if event_type == "step.failed"
                else self.on_step_cancelled
            )
            handler(
                run_id=payload["runId"],
                attempt_id=payload["attemptId"],
                step_execution_id=payload["stepExecutionId"],
                reason=payload["reason"],
            )
            return
        if event_type == "run.finished":
            self.on_run_finished(payload["runId"], payload["status"])
            return
        if event_type == "run.retry_prepared":
            self.on_run_retry_prepared(
                payload["runId"], int(payload.get("recoveryCount") or 0)
            )
            return
        if event_type == "run.superseded":
            self.on_run_superseded(
                payload["runId"],
                payload["newRunId"],
                payload["patchId"],
            )
            return
        raise ValueError(f"unsupported lifecycle projection event: {event_type}")

    @staticmethod
    def _safe_projection_result(result: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            key: result[key]
            for key in (
                "commitId",
                "outputRef",
                "outputSummary",
                "contextRef",
                "memoryRef",
                "traceRef",
                "auditDecisionRef",
                "provenanceEvents",
                "nodeExecution",
                "communicationRefs",
                "evidenceRefs",
            )
            if result.get(key) is not None
        }
        artifacts = IdentityProjectionBridge._safe_artifact_descriptors(result)
        if artifacts:
            allowed["artifacts"] = artifacts
        return allowed

    @staticmethod
    def _safe_artifact_descriptors(result: dict[str, Any]) -> list[dict[str, Any]]:
        raw = result.get("artifacts")
        if raw is None and isinstance(result.get("artifact"), dict):
            raw = [result["artifact"]]
        elif isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        allowed = {
            "artifactKey", "semanticTaskKey", "name", "title", "artifactType",
            "type", "mediaType", "manifestId", "checksum", "metadata",
        }
        descriptors: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            descriptor = {
                key: item[key]
                for key in allowed
                if item.get(key) is not None
            }
            descriptor.setdefault("artifactKey", "primary")
            descriptors.append(descriptor)
        return descriptors

    @staticmethod
    def _safe_run_projection(run: Any) -> dict[str, Any]:
        state = dict(getattr(run, "execution_state", {}) or {})
        allowed = {
            "activeStepIds",
            "blackboardSnapshots",
            "checkpointId",
            "communicationUsage",
            "compiledPackageBlueprintHash",
            "compiledPackageChecksum",
            "compiledPackageId",
            "compiledPackageVersion",
            "consensusResults",
            "contextRefs",
            "controlFrames",
            "debateSessions",
            "graphPatchRefs",
            "loopIterations",
            "loopPaths",
            "memoryRefs",
            "outputRefs",
            "parentRunId",
            "provenanceRefs",
            "recoveryOutcome",
            "schedulingDecisions",
            "sourcePatchId",
            "sourceRunId",
            "supersedesRunId",
            "supersededByRunId",
            "rerunReason",
            "traceRefs",
        }
        return {key: state[key] for key in allowed if state.get(key) is not None}

    @classmethod
    def _identity_run_metadata(cls, run: Any) -> dict[str, Any]:
        projection = cls._safe_run_projection(run)
        immutable = {
            key: projection.pop(key)
            for key in (
                "compiledPackageId",
                "compiledPackageChecksum",
                "compiledPackageVersion",
                "compiledPackageBlueprintHash",
                "parentRunId",
                "supersedesRunId",
                "sourceRunId",
                "sourcePatchId",
                "rerunReason",
            )
            if key in projection
        }
        return {
            **immutable,
            **({"executionProjection": projection} if projection else {}),
        }

    @staticmethod
    def _task_goal(task: Any) -> str:
        return str(
            task.input.get("taskGoal")
            or task.input.get("userIntent")
            or task.title
        ).strip()

    @staticmethod
    def _provenance_event_ids(result: dict[str, Any]) -> list[str]:
        event_ids: list[str] = []
        for event in result.get("provenanceEvents") or []:
            payload = event.get("payload") if isinstance(event, dict) else None
            event_id = payload.get("eventId") if isinstance(payload, dict) else None
            if isinstance(event_id, str) and event_id:
                event_ids.append(event_id)
        return list(dict.fromkeys(event_ids))


__all__ = ["IdentityProjectionBridge"]

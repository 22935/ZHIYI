"""把 Planner 的语义任务树登记为 AgentOS SemanticTask，不参与 ACG 设计或执行。"""

from __future__ import annotations

from collections.abc import Sequence

from contracts.identity import MissionId
from contracts.artifacts import canonicalize_final_synthesis_nodes
from contracts.planning import TaskPlan, PlannedTask, TaskPlanPatch
from domain.models import SemanticTask
from domain.repository import IdentityConflictError
from components.planner.service import apply_task_plan_patch
from components.planner.topology import EdgeOrigin, validate_task_plan_for_execution
from support.acg.capabilities import CapabilityCatalog
from support.acg.native_capabilities import build_default_capability_catalog

from .runner import AcgIdentityLifecycleService


class PlannerIdentityBridge:
    """持久化 Planner 语义输出；不选择 Agent、模型、资源或 ACG 节点。"""

    def __init__(
        self, lifecycle_service: AcgIdentityLifecycleService,
        capability_catalog: CapabilityCatalog | None = None,
    ) -> None:
        self.lifecycle_service = lifecycle_service
        self.capability_catalog = capability_catalog or build_default_capability_catalog()
        self.catalog_source = "injected" if capability_catalog is not None else "default_compatibility"

    def record_task_tree(
        self,
        mission_id: MissionId,
        nodes: Sequence[PlannedTask],
    ) -> list[SemanticTask]:
        nodes = canonicalize_final_synthesis_nodes(nodes, ())
        plan = validate_task_plan_for_execution(
            capability_catalog=self.capability_catalog,
            mission_id=mission_id,
            nodes=nodes,
            relation_origin=EdgeOrigin.FALLBACK_GENERATED,
            producer_kind="identity",
            catalog_source=self.catalog_source,
            metadata={"strategy": "identity_bridge_compatibility"},
        )
        return list(self.record_task_plan(plan).values())

    def record_task_plan(self, plan: TaskPlan) -> dict[str, SemanticTask]:
        """按稳定逻辑键登记计划；新 Run 的内容变化留在新的 TaskPlan 快照中。"""
        persisted = self.lifecycle_service.repositories.persist_task_plan(plan)
        if set(persisted) != {node.key for node in plan.nodes}:
            raise IdentityConflictError("TaskPlan persistence did not cover every semantic node")
        return persisted

    def record_task_plan_patch(self, patch: TaskPlanPatch) -> dict[str, SemanticTask]:
        """Apply Planner output only against the immutable prior plan snapshot."""
        current = self.lifecycle_service.repositories.task_plans.latest(patch.mission_id)
        if current is None:
            raise IdentityConflictError("TaskPlanPatch requires a persisted base TaskPlan")
        return self.record_task_plan(apply_task_plan_patch(
            current, patch, self.capability_catalog, catalog_source=self.catalog_source
        ))


__all__ = ["PlannerIdentityBridge", "PlannedTask"]

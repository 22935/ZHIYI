"""Planner-owned production of execution-agnostic TaskPlan contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from contracts.planning import (
    SemanticTaskRelationType,
    TaskPlan,
    PlannedTask,
    TaskPlanRelation,
)
from contracts.artifacts import (
    FINAL_SYNTHESIS_LOGICAL_ROLE,
    canonicalize_final_synthesis_nodes,
)
from support.acg.capabilities import CapabilityCatalog
from support.acg.semantic_profile import TaskSemanticProfile
from .intent_analyzer import IntentLLM
from .task_decomposer import TaskDecomposer
from .topology import EdgeOrigin, validate_task_plan_for_execution


class SemanticPlanningError(ValueError):
    pass


class SemanticPlanner:
    def __init__(self, capability_catalog: CapabilityCatalog, llm: IntentLLM | None = None,
                 progress_callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.capability_catalog = capability_catalog
        self.task_decomposer = TaskDecomposer(capability_catalog, llm, progress_callback=progress_callback)
        self.last_topology_audit: dict[str, Any] = {}

    def plan_profile(
        self,
        *,
        mission_id: str,
        profile: TaskSemanticProfile,
        strategy: str,
        task_input: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        use_llm: bool = True,
        existing_semantic_tasks: Sequence[Mapping[str, Any]] = (),
        planning_deadline: float | None = None,
        run_id: str | None = None,
    ) -> TaskPlan:
        return self.task_decomposer.decompose(
            mission_id=mission_id,
            profile=profile,
            strategy=strategy,
            task_input=task_input,
            reasoning_effort=reasoning_effort,
            use_llm=use_llm,
            existing_semantic_tasks=tuple(existing_semantic_tasks),
            planning_deadline=planning_deadline,
            run_id=run_id,
        )

    def plan_capabilities(
        self,
        *,
        mission_id: str,
        capabilities: Sequence[str],
        strategy: str,
        plan_version: int = 1,
    ) -> TaskPlan:
        ordered = list(dict.fromkeys(capabilities))
        if not ordered:
            raise SemanticPlanningError("Planner produced no semantic capabilities")
        selected = set(ordered)
        nodes: list[PlannedTask] = []
        for capability in ordered:
            descriptor = self.capability_catalog.get(capability)
            dependencies = [item for item in descriptor.depends_on if item in selected]
            nodes.append(PlannedTask(
                key=f"capability:{descriptor.capability_id}",
                title=descriptor.display_name,
                objective=f"Use {descriptor.display_name} to satisfy the mission objective with traceable results.",
                constraints=[
                    {"type": "required_capability", "value": descriptor.capability_id},
                    *(
                        [{"type": "depends_on", "values": dependencies}]
                        if dependencies else []
                    ),
                ],
                capabilityRequirements=(descriptor.capability_id,),
                acceptanceCriteria=tuple(descriptor.prompt_profile.quality_criteria[:1]),
                decompositionRationale="Compatibility plan generated from the capability dependency graph.",
                logicalRole=(
                    FINAL_SYNTHESIS_LOGICAL_ROLE
                    if capability == "artifact_generation"
                    else descriptor.planning_stage
                ),
                metadata={"plannerStrategy": strategy},
            ))
        relations = tuple(
            TaskPlanRelation(
                sourceKey=f"capability:{dependency}",
                targetKey=f"capability:{capability}",
                relationType=SemanticTaskRelationType.DEPENDS_ON,
            )
            for capability in ordered
            for dependency in self.capability_catalog.get(capability).depends_on
            if dependency in selected
        )
        return validate_task_plan_for_execution(
            capability_catalog=self.capability_catalog,
            mission_id=mission_id,
            plan_version=plan_version,
            nodes=nodes,
            relations=relations,
            relation_origin=EdgeOrigin.FALLBACK_GENERATED,
            producer_kind="compatibility",
            audit_sink=self._capture_topology_audit,
            metadata={"strategy": strategy},
        )

    def plan_template(
        self,
        *,
        mission_id: str,
        workflow: Any,
        strategy: str,
        plan_version: int = 1,
    ) -> TaskPlan:
        """把工作流的 Planner 语义声明(planningNodes)落成可执行 TaskPlan。

        声明式(HTN/模板声明)工作流的确定性规划入口:节点与关系全部来自
        服务端持有的声明,不经 LLM,也不从 workflow.steps 推断任何语义。
        """
        declared_nodes = tuple(getattr(workflow, "planning_nodes", ()) or ())
        if not declared_nodes:
            raise SemanticPlanningError(
                f"workflow template {workflow.workflow_id} has no Planner semantic declaration"
            )
        nodes = tuple(
            node.model_copy(update={
                "metadata": {**node.metadata, "plannerStrategy": strategy},
            })
            for node in declared_nodes
        )
        nodes = tuple(canonicalize_final_synthesis_nodes(
            nodes, tuple(getattr(workflow, "planning_relations", ()) or ())
        ))
        return validate_task_plan_for_execution(
            capability_catalog=self.capability_catalog,
            mission_id=mission_id,
            plan_version=plan_version,
            nodes=nodes,
            relations=tuple(getattr(workflow, "planning_relations", ()) or ()),
            relation_origin=EdgeOrigin.TEMPLATE_DECLARED,
            producer_kind="template",
            audit_sink=self._capture_topology_audit,
            metadata={"strategy": strategy},
        )

    def _capture_topology_audit(self, audit: dict[str, Any]) -> None:
        self.last_topology_audit = dict(audit)


__all__ = ["SemanticPlanner", "SemanticPlanningError"]

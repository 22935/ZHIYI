"""Planning-side preparation of the frozen input consumed by ``ACGLowerer``."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from contracts.planning import (
    SemanticTaskRelationType,
    TaskImplementationBinding,
    TaskPlan,
)
from support.acg.capabilities import CapabilityCatalog, PlanningCapabilityDescriptor
from support.acg.planning import (
    ACGResourcePlan,
    AgentBindingSpec,
    CommunicationSpec,
    EvidenceSpec,
    MemoryAccessSpec,
)
from support.acg.schema import ACGBlueprint, ACGEdge, ComplexityLevel, EdgeType, StepNode
from support.acg.semantic_profile import TaskSemanticProfile
from .acg_lowerer import ACGLoweringInput, ACGLoweringStep
from .cognitive_router import CollaborationNetwork


def build_acg_lowering_input(
    *,
    mission_id: str,
    profile: TaskSemanticProfile,
    network: CollaborationNetwork,
    task_plan: TaskPlan,
    capability_catalog: CapabilityCatalog,
    variant_id: str | None = None,
) -> ACGLoweringInput:
    """Resolve planning decisions and freeze them for deterministic lowering."""

    capability_catalog.validate()
    if not network.bindings:
        raise ValueError("ACG planning produced no capability bindings")
    if task_plan.mission_id != mission_id:
        raise ValueError("TaskPlan missionId does not match lowering mission")
    if any(len(node.capability_requirements) != 1 for node in task_plan.nodes):
        raise ValueError("Every executable TaskPlan node must select exactly one capability")

    binding_by_capability = {}
    for binding in network.bindings:
        if binding.capability in binding_by_capability:
            raise ValueError(f"duplicate capability binding: {binding.capability}")
        binding_by_capability[binding.capability] = binding
    planned_capabilities = {
        str(node.capability_requirements[0]) for node in task_plan.nodes
    }
    missing = sorted(planned_capabilities - set(binding_by_capability))
    if missing:
        raise ValueError(
            "TaskPlan capabilities lack an Agent binding: "
            f"missing={','.join(missing)}"
        )

    descriptors = {
        node.key: capability_catalog.get(node.capability_requirements[0])
        for node in task_plan.nodes
    }
    dependencies = {node.key: [] for node in task_plan.nodes}
    for relation in task_plan.relations:
        if relation.relation_type is SemanticTaskRelationType.DEPENDS_ON:
            dependencies[relation.target_key].append(relation.source_key)

    node_id_by_task: dict[str, str] = {}
    used_ids: set[str] = set()
    for task in task_plan.nodes:
        capability = task.capability_requirements[0]
        binding = binding_by_capability[capability]
        node_id = _step_id(binding.logical_agent_id, capability, used_ids)
        used_ids.add(node_id)
        node_id_by_task[task.key] = node_id

    implementation_bindings = tuple(
        TaskImplementationBinding(planNodeKey=task.key, acgNodeId=node_id_by_task[task.key])
        for task in task_plan.nodes
    )
    agent_bindings = tuple(
        AgentBindingSpec(
            stepId=node_id_by_task[task.key],
            plannedAgentId=binding_by_capability[task.capability_requirements[0]].logical_agent_id,
            role=descriptors[task.key].display_name,
            requiredCapabilities=(descriptors[task.key].capability_id,),
            ephemeral=binding_by_capability[task.capability_requirements[0]].ephemeral,
        )
        for task in task_plan.nodes
    )

    evidence_specs: list[EvidenceSpec] = []
    memory_specs: list[MemoryAccessSpec] = []
    for task in task_plan.nodes:
        descriptor = descriptors[task.key]
        node_id = node_id_by_task[task.key]
        if descriptor.requires_evidence:
            evidence_specs.append(EvidenceSpec(
                evidenceId=f"evidence::{node_id}",
                evidenceType="retrieved",
                producerStepId=node_id,
                source="planner",
                schema={"capabilityId": descriptor.capability_id},
            ))
        if descriptor.writes_memory:
            memory_specs.append(MemoryAccessSpec(
                stepId=node_id,
                memoryId=f"memory::{node_id}",
                access="write",
                memoryType="episodic",
                storageType="inline",
                retentionPolicy="task",
                schema={"capabilityId": descriptor.capability_id},
            ))

    evidence_by_producer = {
        spec.producer_step_id: spec.evidence_id
        for spec in evidence_specs
        if spec.producer_step_id
    }
    evidence_consumers: dict[str, list[str]] = {
        spec.evidence_id: list(spec.consumer_step_ids)
        for spec in evidence_specs
    }
    memory_by_producer = {
        spec.step_id: spec.memory_id
        for spec in memory_specs
        if spec.access == "write"
    }
    memory_reads = list(memory_specs)
    communication: list[CommunicationSpec] = []
    for target_task in task_plan.nodes:
        target_id = node_id_by_task[target_task.key]
        for source_key in dependencies[target_task.key]:
            source_id = node_id_by_task[source_key]
            source_descriptor = descriptors[source_key]
            communication.append(CommunicationSpec(
                producerStepId=source_id,
                consumerStepId=target_id,
                allowedFields=tuple(output_fields(source_descriptor.output_contract)),
                channel=f"{source_id}:{target_id}",
                mode="STRICT_CONTRACT",
            ))
            evidence_id = evidence_by_producer.get(source_id)
            if evidence_id:
                evidence_consumers.setdefault(evidence_id, []).append(target_id)
            memory_id = memory_by_producer.get(source_id)
            if memory_id:
                memory_reads.append(MemoryAccessSpec(
                    stepId=target_id,
                    memoryId=memory_id,
                    access="read",
                ))

    resource_plan = ACGResourcePlan(
        bindings=agent_bindings,
        memory=tuple(memory_reads),
        evidence=tuple(
            spec.model_copy(update={
                "consumer_step_ids": tuple(dict.fromkeys(
                    evidence_consumers.get(spec.evidence_id, spec.consumer_step_ids)
                ))
            })
            for spec in evidence_specs
        ),
        communication=tuple(communication),
    )

    steps = tuple(
        lowering_step_from_task(
            task=task,
            descriptor=descriptors[task.key],
            node_id=node_id_by_task[task.key],
            dependencies=dependencies[task.key],
            node_id_by_task=node_id_by_task,
            descriptors=descriptors,
            expected_artifacts=task_plan.expected_artifacts,
            router_score=binding_by_capability[task.capability_requirements[0]].score,
        )
        for task in task_plan.nodes
    )
    metadata: dict[str, Any] = {
        "generatedBy": "acg_lowerer",
        "domainHint": profile.domain_hint,
        "entropyBudget": profile.entropy_budget,
        "estimatedEntropy": network.estimated_entropy,
        "expectedArtifacts": list(task_plan.expected_artifacts),
        "evidenceScope": profile.evidence_scope,
        "webExtraction": profile.web_extraction,
    }
    if variant_id is not None:
        metadata["planningVariantId"] = variant_id
    return ACGLoweringInput(
        mission_id=mission_id,
        objective=profile.primary_goal,
        complexity_level=profile.estimated_complexity,
        task_plan=task_plan,
        steps=steps,
        implementation_bindings=implementation_bindings,
        resource_plan=resource_plan,
        metadata=metadata,
    )


def build_template_lowering_input(*, workflow, task_plan: TaskPlan) -> ACGLoweringInput:
    """Freeze a declarative (planningNodes) workflow into lowering input.

    语义顺序由 TaskPlan 声明拥有:steps 只提供节点骨架、通信合同与逻辑绑定,
    任何 nextStepId/input.from 边都必须能对齐到 TaskPlan 的语义依赖,否则拒绝。
    """

    blueprint = _template_blueprint_from_workflow(
        workflow,
        mission_id=task_plan.mission_id,
    )
    plan_keys = {node.key for node in task_plan.nodes}
    steps = blueprint.step_nodes()
    if len(steps) == 1 and len(plan_keys) == 1:
        steps[0].metadata["taskPlanKey"] = next(iter(plan_keys))
    else:
        for step in steps:
            step.metadata["taskPlanKey"] = f"step:{step.node_id}"
    step_by_key = {step.metadata["taskPlanKey"]: step for step in steps}
    if len(step_by_key) != len(steps) or set(step_by_key) != plan_keys:
        raise ValueError("Template Steps must bind exactly to TaskPlan nodes")

    plan_adjacency: dict[str, list[str]] = {}
    for relation in task_plan.relations:
        if relation.relation_type is SemanticTaskRelationType.DEPENDS_ON:
            plan_adjacency.setdefault(relation.source_key, []).append(relation.target_key)
            _add_dependency(
                blueprint,
                step_by_key[relation.source_key].node_id,
                step_by_key[relation.target_key].node_id,
            )

    def authorized_order(source_key: str, target_key: str) -> bool:
        pending = [source_key]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target_key:
                return True
            if current not in visited:
                visited.add(current)
                pending.extend(plan_adjacency.get(current, ()))
        return False

    key_by_step_id = {step.node_id: key for key, step in step_by_key.items()}
    for definition in workflow.steps:
        target_id = definition.next_step_id
        if target_id in (None, "", "done", "completed"):
            continue
        if target_id not in key_by_step_id or not authorized_order(
            key_by_step_id[definition.step_id], key_by_step_id[target_id]
        ):
            raise ValueError(
                "Template nextStepId requires a TaskPlan semantic dependency: "
                f"{definition.step_id} -> {target_id}"
            )
    for spec in blueprint.resource_plan.communication:
        if not authorized_order(
            key_by_step_id[spec.producer_step_id], key_by_step_id[spec.consumer_step_id]
        ):
            raise ValueError(
                "Template input.from requires a TaskPlan semantic dependency: "
                f"{spec.producer_step_id} -> {spec.consumer_step_id}"
            )
    return lowering_input_from_blueprint(blueprint=blueprint, task_plan=task_plan)


def lowering_input_from_blueprint(
    *,
    blueprint: ACGBlueprint,
    task_plan: TaskPlan,
) -> ACGLoweringInput:
    """Freeze an already-adapted canonical template without making new decisions."""

    step_specs = tuple(
        ACGLoweringStep(
            task_key=str(step.metadata["taskPlanKey"]),
            node_id=step.node_id,
            name=step.name,
            goal=step.goal,
            acceptance_criteria=tuple(step.acceptance_criteria),
            source_refs=tuple(step.source_refs),
            logical_role=step.logical_role,
            capability=step.capability,
            input_spec=deepcopy(step.input_spec),
            output_spec=deepcopy(step.output_spec),
            step_type=step.step_type,
            timeout=step.timeout,
            retry_limit=step.retry_limit,
            priority=step.priority,
            status=step.status,
            review_required=step.review_required,
            metadata=deepcopy(step.metadata),
        )
        for step in blueprint.step_nodes()
    )
    bindings = tuple(
        TaskImplementationBinding(
            planNodeKey=step.task_key,
            acgNodeId=step.node_id,
        )
        for step in step_specs
    )
    return ACGLoweringInput(
        mission_id=task_plan.mission_id,
        objective=blueprint.objective,
        complexity_level=blueprint.complexity_level,
        task_plan=task_plan,
        steps=step_specs,
        implementation_bindings=bindings,
        resource_plan=blueprint.resource_plan.model_copy(deep=True),
        metadata=deepcopy(blueprint.metadata),
        control_nodes=tuple(
            node.model_copy(deep=True)
            for node in blueprint.nodes
            if not isinstance(node, StepNode)
        ),
        control_edges=tuple(edge.model_copy(deep=True) for edge in blueprint.edges),
    )


def _template_blueprint_from_workflow(workflow, *, mission_id: str) -> ACGBlueprint:
    """机械翻译声明式 workflow 的 steps 为蓝图骨架。

    原 legacy 提升适配器(promote_workflow_to_acg)退役后的最小内核:只服务
    声明式(planningNodes)工作流的材料化路径。不推断 nextStepId 依赖、不构造
    语义身份;拓扑语义完全由 TaskPlan 声明拥有。
    """
    steps = list(workflow.steps)
    blueprint = ACGBlueprint(
        missionId=mission_id,
        objective=workflow.description or workflow.name,
        complexityLevel=_complexity_from_step_count(len(steps)),
        metadata={
            "sourceWorkflowId": workflow.workflow_id,
            "sourceWorkflowVersion": workflow.version,
            "promotedFromLinear": True,
            "runtimeEngine": workflow.effective_runtime_engine,
        },
    )

    for definition in steps:
        blueprint.nodes.append(StepNode(
            nodeId=definition.step_id,
            name=definition.name,
            stepType="agent",
            goal=definition.name,
            capability=definition.capability,
            logicalRole=definition.logical_role,
            inputSpec=dict(definition.input),
            outputSpec=dict(definition.output_spec),
            reviewRequired=definition.review_required,
            retryLimit=definition.max_retries,
            timeout=definition.timeout,
            priority=definition.priority,
        ))

    step_ids = {definition.step_id for definition in steps}
    # input.from 是通信合同;依赖边只在 TaskPlan 声明中产生。
    for definition in steps:
        from_map = definition.input.get("from") if isinstance(definition.input, dict) else None
        if not isinstance(from_map, dict):
            continue
        for source_id, fields in from_map.items():
            if source_id not in step_ids or source_id == definition.step_id:
                continue
            data_fields = [str(field) for field in fields] if isinstance(fields, list) else []
            blueprint.resource_plan.communication += (CommunicationSpec(
                producerStepId=source_id,
                consumerStepId=definition.step_id,
                allowedFields=tuple(data_fields),
                channel=f"{source_id}:{definition.step_id}",
            ),)

    for definition in steps:
        agent_name = definition.agent_name or definition.step_id
        capability = definition.capability or ""
        blueprint.resource_plan.bindings += (AgentBindingSpec(
            stepId=definition.step_id,
            plannedAgentId=agent_name,
            role=capability or agent_name,
            requiredCapabilities=((capability,) if capability else ()),
        ),)

    _inject_template_context_specs(blueprint, steps)
    blueprint.touch()
    return blueprint


def _complexity_from_step_count(count: int) -> ComplexityLevel:
    if count <= 3:
        return ComplexityLevel.SIMPLE
    if count <= 7:
        return ComplexityLevel.MEDIUM
    if count <= 15:
        return ComplexityLevel.COMPLEX
    return ComplexityLevel.EXTREME


_MEMORY_KEYWORDS = (
    "risk", "风险", "suggest", "revision", "建议", "report",
    "报告", "analysis", "分析", "summary", "结论",
)
_EVIDENCE_KEYWORDS = (
    "evidence", "证据", "依据", "statute", "法条", "citation",
)


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(keyword in low for keyword in keywords)


def _inject_template_context_specs(blueprint: ACGBlueprint, steps) -> None:
    """把可选的记忆/证据声明落成 typed spec,保持模板材料化旧行为等价。"""
    memory_ids: dict[str, str] = {}
    evidence_ids: dict[str, str] = {}

    for definition in steps:
        step_id = definition.step_id
        signature = f"{definition.capability or ''} {step_id}"
        output_properties = (
            definition.output_spec.get("properties", {})
            if isinstance(definition.output_spec, dict)
            else {}
        )
        declares_evidence_output = any(
            field in output_properties for field in ("evidence_refs", "evidenceRefs")
        )
        if declares_evidence_output or _matches(signature, _EVIDENCE_KEYWORDS):
            evidence_id = f"evidence::{step_id}"
            blueprint.resource_plan.evidence += (EvidenceSpec(
                evidenceId=evidence_id,
                evidenceType="retrieved",
                producerStepId=step_id,
                source="workflow",
            ),)
            evidence_ids[step_id] = evidence_id

        memory_policy = (
            definition.input.get("memoryPolicy", {})
            if isinstance(definition.input, dict)
            else {}
        )
        declares_memory_write = (
            isinstance(memory_policy, dict) and memory_policy.get("write") is True
        )
        if declares_memory_write or _matches(signature, _MEMORY_KEYWORDS):
            memory_type = (
                str(memory_policy.get("writeType") or "episodic")
                if declares_memory_write
                else "episodic"
            )
            memory_id = f"memory::{step_id}"
            blueprint.resource_plan.memory += (MemoryAccessSpec(
                stepId=step_id,
                memoryId=memory_id,
                access="write",
                memoryType=memory_type,
            ),)
            memory_ids[step_id] = memory_id

    for definition in steps:
        from_map = definition.input.get("from") if isinstance(definition.input, dict) else None
        if not isinstance(from_map, dict):
            continue
        for source_id in from_map:
            if source_id in memory_ids:
                blueprint.resource_plan.memory += (MemoryAccessSpec(
                    stepId=definition.step_id,
                    memoryId=memory_ids[source_id],
                    access="read",
                ),)
            if source_id in evidence_ids:
                for index, spec in enumerate(blueprint.resource_plan.evidence):
                    if spec.evidence_id == evidence_ids[source_id]:
                        blueprint.resource_plan.evidence = (
                            *blueprint.resource_plan.evidence[:index],
                            spec.model_copy(update={
                                "consumer_step_ids": tuple(dict.fromkeys(
                                    (*spec.consumer_step_ids, definition.step_id)
                                ))
                            }),
                            *blueprint.resource_plan.evidence[index + 1:],
                        )
                        break


def lowering_step_from_task(
    *,
    task,
    descriptor: PlanningCapabilityDescriptor,
    node_id: str,
    dependencies: list[str],
    node_id_by_task: dict[str, str],
    descriptors: dict[str, PlanningCapabilityDescriptor],
    expected_artifacts: tuple[str, ...],
    router_score: float,
    dependency_output_contracts: dict[str, dict] | None = None,
) -> ACGLoweringStep:
    from_map = {
        node_id_by_task[dependency]: output_fields(
            (
                dependency_output_contracts[dependency]
                if dependency_output_contracts is not None
                else descriptors[dependency].output_contract
            )
        )
        for dependency in dependencies
    }
    input_spec = deepcopy(descriptor.input_contract)
    workset = (
        task.workset.model_dump(by_alias=True, mode="json")
        if task.workset is not None
        else None
    )
    if from_map:
        input_spec = {
            "from": from_map,
            "schema": deepcopy(descriptor.input_contract),
            **({"workset": workset} if workset is not None else {}),
        }
    elif workset is not None:
        input_spec = {**input_spec, "workset": workset}
    metadata = {
        "capabilityId": descriptor.capability_id,
        "planningStage": descriptor.planning_stage,
        "role": descriptor.planning_stage,
        "dependsOn": list(dependencies),
        "producesArtifact": descriptor.produces_artifact,
        "requiresEvidence": descriptor.requires_evidence,
        "writesMemory": descriptor.writes_memory,
        "memoryPolicy": {
            "policyId": f"capability:{descriptor.capability_id}:v1",
            "read": True,
            "write": descriptor.writes_memory,
            "readTypes": ["episodic"],
            "writeType": "episodic" if descriptor.writes_memory else None,
            "limit": 10,
            "tokenBudget": None,
            "requireAudit": descriptor.writes_memory,
        },
        "routerScore": router_score,
        "taskPlanKey": task.key,
        "expectedArtifacts": list(expected_artifacts),
        "producedArtifacts": list(task.produced_artifacts),
        "decompositionRationale": task.decomposition_rationale,
        "workset": workset,
        "capabilityPromptProfileVersion": descriptor.prompt_profile.prompt_profile_version,
        "reasoningEffort": _reasoning_effort(task, descriptor),
        "reasoningPolicyReason": _reasoning_policy_reason(task, descriptor),
    }
    return ACGLoweringStep(
        task_key=task.key,
        node_id=node_id,
        name=task.title,
        goal=task.objective,
        acceptance_criteria=tuple(task.acceptance_criteria),
        source_refs=tuple(task.source_refs),
        logical_role=task.logical_role,
        capability=descriptor.capability_id,
        input_spec=input_spec,
        output_spec=deepcopy(descriptor.output_contract),
        timeout=0,
        retry_limit=0,
        review_required=descriptor.requires_review,
        metadata=metadata,
    )


def _reasoning_effort(task, descriptor) -> str:
    explicit = str(task.metadata.get("reasoningEffort") or "").strip().lower()
    if explicit in {"low", "high", "max"}:
        return explicit
    role = str(task.logical_role or "").strip().lower()
    if (
        descriptor.risk_level_hint in {"high", "critical"}
        or descriptor.requires_review
        or descriptor.produces_artifact
        or role in {"decision", "review", "verification", "join", "sink", "final"}
        or descriptor.capability_id in {
            "solution_design", "comparative_analysis", "verification",
            "artifact_generation", "industrial_safety_analysis",
            "industrial_acceptance_validation",
        }
    ):
        return "max"
    if descriptor.capability_id in {"information_extraction", "information_retrieval"}:
        return "low"
    return "high"


def _reasoning_policy_reason(task, descriptor) -> str:
    if str(task.metadata.get("reasoningEffort") or "").strip().lower() in {"low", "high", "max"}:
        return "task_plan_explicit"
    if descriptor.risk_level_hint in {"high", "critical"} or descriptor.requires_review:
        return "risk_or_review_critical"
    if descriptor.produces_artifact or str(task.logical_role or "").strip().lower() in {
        "decision", "review", "verification", "join", "sink", "final",
    }:
        return "topology_or_delivery_critical"
    if descriptor.capability_id in {"information_extraction", "information_retrieval"}:
        return "bounded_retrieval_or_extraction"
    return "analytical_default"


def _step_id(agent_name: str, capability_id: str, used_ids: set[str]) -> str:
    base = agent_name.strip() or capability_id.strip() or "step"
    node_id = base
    suffix = 2
    while node_id in used_ids:
        node_id = f"{base}_{suffix}"
        suffix += 1
    return node_id


def output_fields(contract: dict) -> list[str]:
    required = contract.get("required") if isinstance(contract, dict) else None
    return [str(item) for item in required] if isinstance(required, list) else []


def _add_dependency(blueprint: ACGBlueprint, source_id: str, target_id: str) -> None:
    if source_id == target_id:
        raise ValueError(f"self dependency is not allowed: {source_id}")
    if any(
        edge.source_id == source_id and edge.target_id == target_id
        for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY)
    ):
        return
    blueprint.edges.append(
        ACGEdge(sourceId=source_id, targetId=target_id, edgeType=EdgeType.DEPENDENCY)
    )


__all__ = [
    "build_acg_lowering_input",
    "build_template_lowering_input",
    "lowering_step_from_task",
    "lowering_input_from_blueprint",
    "output_fields",
]

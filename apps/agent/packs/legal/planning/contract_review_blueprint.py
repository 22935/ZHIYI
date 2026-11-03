"""Executable ACG blueprint for the Legal contract-review vertical slice."""

from __future__ import annotations

from copy import deepcopy

from contracts.workflow import WorkflowDefinition, WorkflowStepDefinition
from support.acg.models import (
    ACGBlueprint,
    ACGEdge,
    ConditionOperator,
    ConditionSpec,
    ControlNode,
    ControlType,
    EdgeType,
    StepNode,
    validate_blueprint,
)
from support.acg.planning import (
    ACGResourcePlan,
    AgentBindingSpec,
    CommunicationSpec,
    EvidenceSpec,
    MemoryAccessSpec,
)


def _step(definition: WorkflowStepDefinition, **updates) -> StepNode:
    values = {
        "nodeId": definition.step_id,
        "name": definition.name,
        "goal": definition.name,
        "capability": definition.capability,
        "inputSpec": deepcopy(definition.input),
        "outputSpec": deepcopy(definition.output_spec),
        "reviewRequired": definition.review_required,
        "retryLimit": definition.max_retries,
        "timeout": definition.timeout,
        "priority": definition.priority,
    }
    values.update(updates)
    return StepNode(**values)


def build_contract_review_blueprint(
    workflow: WorkflowDefinition,
    *,
    task_id: str | None = None,
) -> ACGBlueprint:
    """Promote the canonical Legal workflow into its audited non-linear ACG.

    The function lives in the domain Pack: it declares Legal ordering and data
    contracts while the execution runtime remains the sole scheduler. It adds one
    real tool-backed retrieval step and a bounded IF route; ordinary fan-out/fan-in
    remains direct TaskPlan dependency topology.
    """

    definitions = {item.step_id: item for item in workflow.steps}
    required = {
        "parse_contract",
        "classify_clauses",
        "risk_detect",
        "legal_evidence_match",
        "suggestion_generate",
        "human_review",
        "report_generate",
    }
    missing = sorted(required - definitions.keys())
    if missing:
        raise ValueError(f"contract review workflow is missing steps: {', '.join(missing)}")

    evidence_input = deepcopy(definitions["legal_evidence_match"].input)
    evidence_from = evidence_input.setdefault("from", {})
    evidence_from["statute_retrieve"] = ["legal_basis", "sources", "evidence_refs"]
    evidence_input["memoryPolicy"] = {
        "policyId": "legal-evidence-v1",
        "read": False,
        "write": True,
        "writeType": "evidence",
        "requireAudit": True,
    }

    retrieval_input = {
        "memoryPolicy": {
            "policyId": "legal-source-evidence-v1",
            "read": False,
            "write": True,
            "writeType": "evidence",
            "requireAudit": True,
        }
    }

    report_input = deepcopy(definitions["report_generate"].input)
    report_input.setdefault("from", {})["auto_review"] = ["review_status", "review_focus"]

    nodes = [
        _step(definitions["parse_contract"]),
        _step(definitions["classify_clauses"]),
            StepNode(
                nodeId="statute_retrieve",
                name="Legal basis retrieval",
                goal="Retrieve bounded legal sources through the injected Tool Runtime",
                # The retrieval agent is an application-owned helper in this fixed
            # vertical slice; it is selected by its frozen agent identity and
            # is not advertised as a planner capability.
            capability=None,
            inputSpec=retrieval_input,
            outputSpec={
                "type": "object",
                "required": ["legal_basis", "sources", "evidence_refs"],
                "properties": {
                    "legal_basis": {"type": "array"},
                    "query": {"type": "string"},
                    "retrieval_status": {"type": "string"},
                    "retrieval_mode": {"type": "string"},
                    "retrieval_errors": {"type": "array"},
                    "sources": {"type": "array"},
                    "evidence_refs": {"type": "array"},
                },
            },
        ),
        _step(definitions["risk_detect"]),
        _step(definitions["legal_evidence_match"], inputSpec=evidence_input),
        _step(definitions["suggestion_generate"]),
        ControlNode(
            nodeId="route_high_risk_review",
            name="High-risk review route",
            controlType=ControlType.IF,
            conditionSpec=ConditionSpec(
                sourceNodeId="suggestion_generate",
                jsonPointer="/risk_level",
                operator=ConditionOperator.EQUALS,
                cases={"high": "route_to_human_review"},
                defaultEdgeId="route_to_auto_review",
            ),
            branchEdgeIds=["route_to_human_review", "route_to_auto_review"],
        ),
        _step(definitions["human_review"]),
        _step(
            definitions["human_review"],
            nodeId="auto_review",
            name="Automatic low-risk review",
            reviewRequired=False,
        ),
        _step(definitions["report_generate"], inputSpec=report_input),
    ]

    dependency_pairs = [
        ("parse_contract", "classify_clauses"),
        ("parse_contract", "statute_retrieve"),
        ("classify_clauses", "risk_detect"),
        ("statute_retrieve", "risk_detect"),
        ("risk_detect", "legal_evidence_match"),
        ("statute_retrieve", "legal_evidence_match"),
        ("legal_evidence_match", "suggestion_generate"),
        ("suggestion_generate", "route_high_risk_review"),
        ("human_review", "report_generate"),
        ("auto_review", "report_generate"),
    ]
    edges = [
        ACGEdge(sourceId=source, targetId=target, edgeType=EdgeType.DEPENDENCY)
        for source, target in dependency_pairs
    ]
    edges.extend(
        [
            ACGEdge(
                edgeId="route_to_human_review",
                sourceId="route_high_risk_review",
                targetId="human_review",
                edgeType=EdgeType.DEPENDENCY,
            ),
            ACGEdge(
                edgeId="route_to_auto_review",
                sourceId="route_high_risk_review",
                targetId="auto_review",
                edgeType=EdgeType.DEPENDENCY,
            ),
        ]
    )

    communication = {
        "classify_clauses": {"parse_contract": ["contract_type", "scope", "payment_terms", "acceptance_terms", "ip_terms", "dispute_resolution"]},
        "risk_detect": {
            "parse_contract": ["contract_summary", "payment_terms", "acceptance_terms", "ip_terms"],
            "classify_clauses": ["clauses"],
        },
        "legal_evidence_match": {
            "parse_contract": ["contract_type"],
            "risk_detect": ["risks", "risk_level", "risk_score"],
            "statute_retrieve": ["legal_basis", "sources", "evidence_refs"],
        },
        "suggestion_generate": {
            "risk_detect": ["risks", "risk_summary"],
            "legal_evidence_match": ["evidences", "citations"],
        },
        "human_review": {
            "risk_detect": ["risks", "risk_summary"],
            "suggestion_generate": ["revision_suggestions", "manual_review_focus"],
        },
        "auto_review": {
            "risk_detect": ["risks", "risk_summary"],
            "suggestion_generate": ["revision_suggestions", "manual_review_focus"],
        },
        "report_generate": report_input["from"],
    }
    step_nodes = [node for node in nodes if isinstance(node, StepNode)]
    bindings = []
    memory_specs = []
    for node in step_nodes:
        definition = definitions.get(node.node_id) or definitions.get("human_review")
        planned_agent_id = ("statute" if node.node_id == "statute_retrieve"
                            else (definition.agent_name if definition is not None else None) or node.node_id)
        bindings.append(AgentBindingSpec(
            stepId=node.node_id,
            plannedAgentId=planned_agent_id,
            role=node.logical_role,
            requiredCapabilities=((node.capability,) if node.capability else ()),
        ))
        policy = node.input_spec.get("memoryPolicy") if isinstance(node.input_spec, dict) else None
        if isinstance(policy, dict) and policy.get("write") is True:
            memory_specs.append(MemoryAccessSpec(
                stepId=node.node_id,
                memoryId=f"memory::{node.node_id}",
                access="write",
                memoryType=str(policy.get("writeType") or "episodic"),
            ))

    communication_specs = tuple(
        CommunicationSpec(
            producerStepId=source,
            consumerStepId=target,
            allowedFields=tuple(str(field) for field in fields),
            channel=f"{source}:{target}",
        )
        for target, sources in communication.items()
        for source, fields in sources.items()
    )
    resource_plan = ACGResourcePlan(
        bindings=tuple(bindings),
        memory=tuple(memory_specs),
        evidence=(
            EvidenceSpec(
                evidenceId="legal_source_evidence",
                evidenceType="legal-source",
                source="tool-runtime-or-task-input",
                producerStepId="statute_retrieve",
                consumerStepIds=("legal_evidence_match",),
            ),
            EvidenceSpec(
                evidenceId="matched_legal_evidence",
                evidenceType="legal-analysis",
                source="legal-evidence-match",
                producerStepId="legal_evidence_match",
            ),
        ),
        communication=communication_specs,
    )

    blueprint = ACGBlueprint(
        taskId=task_id,
        objective=workflow.description or workflow.name,
        complexityLevel="complex",
        metadata={
            "sourceWorkflowId": workflow.workflow_id,
            "sourceWorkflowVersion": workflow.version,
            "generatedBy": "legal_contract_review_blueprint_v1",
            "runtimeEngine": "acg",
        },
        nodes=nodes,
        edges=edges,
        resourcePlan=resource_plan,
    )
    blueprint.touch()
    validate_blueprint(blueprint)
    return blueprint


__all__ = ["build_contract_review_blueprint"]

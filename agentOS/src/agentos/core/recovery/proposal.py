"""Deterministic graph change proposals and bounded patch compilation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.acg.edges import ACGEdge
from agentos.core.acg.enums import EdgeType
from agentos.core.acg.nodes import StepNode
from agentos.core.conditions import (
    ConditionalEvaluationResult,
    conditional_branch_exclusive_nodes,
)
from agentos.core.models.types import utc_now
from agentos.core.recovery.bindings import CandidateResolver, ExecutionBinding
from agentos.core.recovery.events import RuntimeEvent, stable_hash
from agentos.core.recovery.models import RuntimeGraphPatch, SubgraphInsertionMode
from agentos.core.recovery.policy import EventPolicyAction, EventPolicyDecision
from agentos.core.recovery.recipes import RecoveryRecipeRegistry
from agentos.core.runtime_graph import RuntimeGraph


class GraphChangeType(str, Enum):
    ADD_SUBGRAPH = "ADD_SUBGRAPH"
    RETRY_ALTERNATE_BINDING = "RETRY_ALTERNATE_BINDING"
    ACTIVATE_CONDITIONAL_BRANCH = "ACTIVATE_CONDITIONAL_BRANCH"


class GraphChangeProposal(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    proposal_id: str = Field(alias="proposalId")
    idempotency_key: str = Field(alias="idempotencyKey")
    run_id: str = Field(alias="runId")
    graph_id: str = Field(alias="graphId")
    base_graph_version: int = Field(alias="baseGraphVersion", ge=1)
    source_event_id: str = Field(alias="sourceEventId")
    change_type: GraphChangeType = Field(alias="changeType")
    insertion_mode: SubgraphInsertionMode = Field(
        default=SubgraphInsertionMode.INSERT_BEFORE_TARGET,
        alias="insertionMode",
    )
    recipe_id: str | None = Field(default=None, alias="recipeId")
    recipe_version: str | None = Field(default=None, alias="recipeVersion")
    target_node_id: str | None = Field(default=None, alias="targetNodeId")
    reason: str
    required_capabilities: list[str] = Field(default_factory=list, alias="requiredCapabilities")
    proposed_nodes: list[StepNode] = Field(default_factory=list, alias="proposedNodes")
    proposed_edges: list[ACGEdge] = Field(default_factory=list, alias="proposedEdges")
    input_mappings: dict[str, Any] = Field(default_factory=dict, alias="inputMappings")
    output_mappings: dict[str, Any] = Field(default_factory=dict, alias="outputMappings")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    runtime_node_id: str | None = Field(default=None, alias="runtimeNodeId")
    failed_binding_id: str | None = Field(default=None, alias="failedBindingId")
    candidate_binding: ExecutionBinding | None = Field(default=None, alias="candidateBinding")
    excluded_binding_ids: list[str] = Field(default_factory=list, alias="excludedBindingIds")
    expected_node_status: str | None = Field(default=None, alias="expectedNodeStatus")
    expected_attempt_id: str | None = Field(default=None, alias="expectedAttemptId")
    control_node_id: str | None = Field(default=None, alias="controlNodeId")
    source_node_id: str | None = Field(default=None, alias="sourceNodeId")
    source_output_version: int | None = Field(default=None, alias="sourceOutputVersion")
    input_hash: str | None = Field(default=None, alias="inputHash")
    selected_case_key: str | None = Field(default=None, alias="selectedCaseKey")
    selected_edge_ids: list[str] = Field(default_factory=list, alias="selectedEdgeIds")
    terminated_edge_ids: list[str] = Field(default_factory=list, alias="terminatedEdgeIds")
    join_node_id: str | None = Field(default=None, alias="joinNodeId")


class DeterministicProposalFactory:
    """Resolve a registered recipe into stable nodes and edges without modifying a graph."""

    def propose(
        self,
        event: RuntimeEvent,
        decision: EventPolicyDecision,
        graph: RuntimeGraph,
        recipe_registry: RecoveryRecipeRegistry,
        candidate_resolver: CandidateResolver,
        *,
        domain: str,
        allowed_agent_ids: list[str] | tuple[str, ...] | None = None,
    ) -> GraphChangeProposal:
        if decision.patch_operation == GraphChangeType.RETRY_ALTERNATE_BINDING.value:
            node = graph.get_node(event.runtime_node_id)
            failed_binding_id = str(event.payload.get("failedBindingId") or "")
            excluded = list(dict.fromkeys(event.payload.get("excludedBindingIds") or []))
            required_skills = list(node.spec.get("skillIds") or [])
            candidates = candidate_resolver.resolve_candidates(
                domain=domain,
                capability=str(node.spec.get("capability") or event.payload.get("capability") or ""),
                required_skills=required_skills,
                excluded_binding_ids=excluded,
                allowed_agent_ids=allowed_agent_ids,
            )
            if not candidates:
                raise KeyError("ALTERNATE_BINDING_EXHAUSTED")
            candidate = candidates[0]
            proposal_key = stable_hash(
                event.event_id, node.node_id, failed_binding_id, candidate.binding_id
            )
            return GraphChangeProposal(
                proposalId=f"proposal_{proposal_key[:24]}",
                idempotencyKey=proposal_key,
                runId=graph.run_id,
                graphId=graph.graph_id,
                baseGraphVersion=graph.graph_version,
                sourceEventId=event.event_id,
                changeType=GraphChangeType.RETRY_ALTERNATE_BINDING,
                runtimeNodeId=node.node_id,
                failedBindingId=failed_binding_id,
                candidateBinding=candidate,
                excludedBindingIds=excluded,
                expectedNodeStatus=node.status.value,
                expectedAttemptId=node.attempts[-1].attempt_id if node.attempts else None,
                reason=decision.reason,
                createdAt=event.created_at,
            )
        if decision.action != EventPolicyAction.PROPOSE_PATCH or not decision.recipe_id:
            raise ValueError("policy decision does not authorize a graph proposal")
        recipe = recipe_registry.get(decision.recipe_id, decision.recipe_version)
        scope = stable_hash(graph.run_id, recipe.recipe_id, decision.target_node_id)
        proposal_key = stable_hash(event.event_id, recipe.recipe_id, recipe.version, decision.target_node_id)
        nodes: list[StepNode] = []
        for template in recipe.node_templates:
            binding = candidate_resolver.resolve(
                domain=domain,
                capability=template.capability,
                allowed_agent_ids=allowed_agent_ids,
            )
            node_key = stable_hash(scope, template.logical_name)
            nodes.append(
                StepNode(
                    nodeId=f"runtime_{node_key[:16]}",
                    name=template.name,
                    goal=f"Apply recovery capability {template.capability}",
                    inputSpec=dict(template.input_spec),
                    outputSpec=dict(template.output_spec),
                    agentName=binding.agent_name,
                    capability=template.capability,
                    retryLimit=template.retry_limit,
                    timeout=template.timeout,
                    priority=template.priority,
                    metadata={
                        "logicalName": template.logical_name,
                        "recipeId": recipe.recipe_id,
                        "recipeVersion": recipe.version,
                        "bindingId": binding.binding_id,
                    },
                )
            )
        edges: list[ACGEdge] = []
        for source, target in zip(nodes, nodes[1:]):
            edge_key = stable_hash(scope, source.node_id, target.node_id)
            edges.append(
                ACGEdge(
                    edgeId=f"runtime_edge_{edge_key[:16]}",
                    sourceId=source.node_id,
                    targetId=target.node_id,
                    edgeType=EdgeType.DEPENDENCY,
                )
            )
        final_key = stable_hash(scope, nodes[-1].node_id, decision.target_node_id)
        edges.append(
            ACGEdge(
                edgeId=f"runtime_edge_{final_key[:16]}",
                sourceId=nodes[-1].node_id,
                targetId=decision.target_node_id,
                edgeType=EdgeType.DEPENDENCY,
            )
        )
        return GraphChangeProposal(
            proposalId=f"proposal_{proposal_key[:24]}",
            idempotencyKey=proposal_key,
            runId=graph.run_id,
            graphId=graph.graph_id,
            baseGraphVersion=graph.graph_version,
            sourceEventId=event.event_id,
            changeType=GraphChangeType.ADD_SUBGRAPH,
            insertionMode=SubgraphInsertionMode.INSERT_BEFORE_TARGET,
            recipeId=recipe.recipe_id,
            recipeVersion=recipe.version,
            targetNodeId=decision.target_node_id,
            reason=decision.reason,
            requiredCapabilities=list(recipe.required_capabilities),
            proposedNodes=nodes,
            proposedEdges=edges,
            inputMappings=dict(recipe.input_mappings),
            outputMappings=dict(recipe.output_mappings),
            createdAt=event.created_at,
        )

    def propose_conditional(
        self,
        evaluation: ConditionalEvaluationResult,
        graph: RuntimeGraph,
    ) -> GraphChangeProposal:
        proposal_key = stable_hash(
            graph.run_id,
            evaluation.control_node_id,
            evaluation.source_output_version,
            evaluation.input_hash,
            evaluation.selected_edge_ids,
            evaluation.terminated_edge_ids,
        )
        return GraphChangeProposal(
            proposalId=f"proposal_{proposal_key[:24]}",
            idempotencyKey=proposal_key,
            runId=graph.run_id,
            graphId=graph.graph_id,
            baseGraphVersion=graph.graph_version,
            sourceEventId=f"condition_{proposal_key[:24]}",
            changeType=GraphChangeType.ACTIVATE_CONDITIONAL_BRANCH,
            controlNodeId=evaluation.control_node_id,
            sourceNodeId=evaluation.source_node_id,
            sourceOutputVersion=evaluation.source_output_version,
            inputHash=evaluation.input_hash,
            selectedCaseKey=evaluation.selected_case_key,
            selectedEdgeIds=evaluation.selected_edge_ids,
            terminatedEdgeIds=evaluation.terminated_edge_ids,
            joinNodeId=evaluation.join_node_id,
            reason="DETERMINISTIC_CONDITION_MATCH",
            createdAt=graph.get_node(evaluation.source_node_id).updated_at,
        )


class RuntimeGraphPatchCompiler:
    """Compile only ADD_SUBGRAPH/INSERT_BEFORE_TARGET against the latest graph view."""

    def compile(self, proposal: GraphChangeProposal, graph: RuntimeGraph) -> RuntimeGraphPatch:
        if proposal.change_type == GraphChangeType.ACTIVATE_CONDITIONAL_BRANCH:
            return self._compile_conditional(proposal, graph)
        if proposal.change_type == GraphChangeType.RETRY_ALTERNATE_BINDING:
            node = graph.get_node(str(proposal.runtime_node_id))
            current_id = str((node.current_binding or {}).get("bindingId") or "")
            patch_key = stable_hash(
                proposal.proposal_id,
                proposal.runtime_node_id,
                proposal.failed_binding_id,
                proposal.candidate_binding.binding_id,
            )
            return RuntimeGraphPatch(
                patchId=f"patch_{patch_key[:24]}",
                idempotencyKey=proposal.idempotency_key,
                runId=proposal.run_id,
                graphId=proposal.graph_id,
                baseGraphVersion=graph.graph_version,
                operationType=GraphChangeType.RETRY_ALTERNATE_BINDING,
                sourceEventId=proposal.source_event_id,
                proposalId=proposal.proposal_id,
                reason=proposal.reason,
                createdAt=proposal.created_at,
                expectedNodeStates={node.node_id: node.status},
                budgetImpact={"addedNodes": 0, "replanDepthIncrement": 0},
                runtimeNodeId=node.node_id,
                expectedAttemptId=proposal.expected_attempt_id,
                expectedCurrentBindingId=current_id,
                newBinding=proposal.candidate_binding,
                excludedBindingIds=proposal.excluded_binding_ids,
                metadata={"failureCategory": "BINDING_UNAVAILABLE"},
            )
        if proposal.change_type != GraphChangeType.ADD_SUBGRAPH:
            raise ValueError(f"unsupported change type: {proposal.change_type}")
        if proposal.insertion_mode != SubgraphInsertionMode.INSERT_BEFORE_TARGET:
            raise ValueError(f"unsupported insertion mode: {proposal.insertion_mode}")
        if proposal.base_graph_version != graph.graph_version:
            raise ValueError("proposal baseGraphVersion is stale")
        incoming = [
            edge
            for edge in graph.effective_edges(EdgeType.DEPENDENCY)
            if edge.target_id == proposal.target_node_id
        ]
        first_node_id = proposal.proposed_nodes[0].node_id
        predecessor_edges = []
        for edge in incoming:
            edge_key = stable_hash(proposal.recipe_id, proposal.target_node_id, edge.source_id, first_node_id)
            predecessor_edges.append(
                ACGEdge(
                    edgeId=f"runtime_edge_{edge_key[:16]}",
                    sourceId=edge.source_id,
                    targetId=first_node_id,
                    edgeType=EdgeType.DEPENDENCY,
                )
            )
        patch_key = stable_hash(proposal.proposal_id, proposal.recipe_id, proposal.target_node_id)
        target = graph.get_node(proposal.target_node_id)
        return RuntimeGraphPatch(
            patchId=f"patch_{patch_key[:24]}",
            idempotencyKey=proposal.idempotency_key,
            runId=proposal.run_id,
            graphId=proposal.graph_id,
            baseGraphVersion=graph.graph_version,
            operationType=GraphChangeType.ADD_SUBGRAPH.value,
            sourceEventId=proposal.source_event_id,
            proposalId=proposal.proposal_id,
            reason=proposal.reason,
            createdAt=proposal.created_at,
            expectedNodeStates={proposal.target_node_id: target.status},
            budgetImpact={"addedNodes": len(proposal.proposed_nodes), "replanDepthIncrement": 1},
            metadata={
                "recipeId": proposal.recipe_id,
                "recipeVersion": proposal.recipe_version,
                "inputMappings": proposal.input_mappings,
                "outputMappings": proposal.output_mappings,
            },
            insertionMode="INSERT_BEFORE_TARGET",
            targetNodeId=proposal.target_node_id,
            replacedIncomingEdgeIds=[edge.edge_id for edge in incoming],
            addNodes=[node.model_copy(deep=True) for node in proposal.proposed_nodes],
            addEdges=[*predecessor_edges, *[edge.model_copy(deep=True) for edge in proposal.proposed_edges]],
        )

    @staticmethod
    def _compile_conditional(
        proposal: GraphChangeProposal, graph: RuntimeGraph
    ) -> RuntimeGraphPatch:
        control = graph.get_node(str(proposal.control_node_id))
        control_spec = graph.to_blueprint(effective_only=False).get_node(control.node_id)
        exclusive = conditional_branch_exclusive_nodes(graph, control_spec)
        skipped = sorted(
            {
                node_id
                for edge_id in proposal.terminated_edge_ids
                for node_id in exclusive[edge_id]
            }
        )
        patch_key = stable_hash(
            proposal.proposal_id,
            proposal.input_hash,
            proposal.selected_edge_ids,
            proposal.terminated_edge_ids,
        )
        return RuntimeGraphPatch(
            patchId=f"patch_{patch_key[:24]}",
            idempotencyKey=proposal.idempotency_key,
            runId=proposal.run_id,
            graphId=proposal.graph_id,
            baseGraphVersion=graph.graph_version,
            operationType=GraphChangeType.ACTIVATE_CONDITIONAL_BRANCH,
            sourceEventId=proposal.source_event_id,
            proposalId=proposal.proposal_id,
            reason=proposal.reason,
            expectedNodeStates={control.node_id: control.status},
            budgetImpact={"addedNodes": 0, "replanDepthIncrement": 0},
            controlNodeId=control.node_id,
            expectedControlNodeState=control.status,
            expectedSourceOutputVersion=proposal.source_output_version,
            inputHash=proposal.input_hash,
            selectedCaseKey=proposal.selected_case_key,
            selectedEdgeIds=proposal.selected_edge_ids,
            terminatedEdgeIds=proposal.terminated_edge_ids,
            joinNodeId=proposal.join_node_id,
            nodeStateUpdates={node_id: "skipped_by_condition" for node_id in skipped},
            metadata={
                "sourceNodeId": proposal.source_node_id,
                "sourceOutputVersion": proposal.source_output_version,
            },
        )


__all__ = [
    "CandidateResolver",
    "DeterministicProposalFactory",
    "GraphChangeProposal",
    "GraphChangeType",
    "RuntimeGraphPatchCompiler",
]

"""Versioned runtime graph models derived from immutable ACG blueprints.

The graph is authoritative for runtime structure, execution state, outputs,
bindings, attempts, graph versions, and patch history. ``WorkflowStep`` is a
one-way compatibility projection only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.acg.blueprint import ACGBlueprint
from agentos.core.acg.edges import ACGEdge, EdgeActivation
from agentos.core.acg.enums import ControlType, EdgeType, NodeType
from agentos.core.acg.nodes import AgentNode, ControlNode, StepNode, parse_node
from agentos.core.conditions import BranchDecision
from agentos.core.models.enums import StepStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


RuntimeNodeStatus = StepStatus


class RuntimeNodeActivation(str, Enum):
    """Runtime node activation state used by controlled graph execution."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    TERMINATED = "terminated"


class RuntimeEventType(str, Enum):
    BINDING_UNAVAILABLE = "BINDING_UNAVAILABLE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    INPUT_CONTRACT_VIOLATION = "INPUT_CONTRACT_VIOLATION"
    OUTPUT_CONTRACT_VIOLATION = "OUTPUT_CONTRACT_VIOLATION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    STEP_EXECUTION_FAILED = "STEP_EXECUTION_FAILED"


class RuntimeEventStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    REJECTED = "REJECTED"


class RuntimeEvent(BaseModel):
    """Persisted classification of one immutable execution outcome."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    event_id: str = Field(alias="eventId")
    idempotency_key: str = Field(alias="idempotencyKey")
    run_id: str = Field(alias="runId")
    graph_id: str = Field(alias="graphId")
    graph_version: int = Field(alias="graphVersion", ge=1)
    event_type: RuntimeEventType = Field(alias="eventType")
    runtime_node_id: str = Field(alias="runtimeNodeId")
    attempt_id: str = Field(alias="attemptId")
    binding_id: str = Field(default="", alias="bindingId")
    source_trace_event_id: str | None = Field(default=None, alias="sourceTraceEventId")
    payload: dict[str, Any] = Field(default_factory=dict)
    classification_version: str = Field(default="1", alias="classificationVersion")
    created_at: datetime = Field(default_factory=_utc_now, alias="createdAt")
    status: RuntimeEventStatus = RuntimeEventStatus.PENDING
    status_reason: str = Field(default="", alias="statusReason")

    @property
    def reason_code(self) -> str:
        return str(self.payload.get("reasonCode") or self.event_type.value).strip().upper()

    @property
    def target_node_id(self) -> str:
        return str(self.payload.get("targetNodeId") or self.runtime_node_id)


class RuntimePatchBudget(BaseModel):
    """Testable safety limits for controlled local replanning."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    max_graph_patches: int = Field(default=3, alias="maxGraphPatches", ge=0)
    max_added_nodes_per_patch: int = Field(
        default=4, alias="maxAddedNodesPerPatch", ge=0
    )
    max_total_runtime_nodes: int = Field(default=20, alias="maxTotalRuntimeNodes", ge=1)
    max_replan_depth: int = Field(default=2, alias="maxReplanDepth", ge=0)
    current_replan_depth: int = Field(default=0, alias="currentReplanDepth", ge=0)


class RuntimeAttempt(BaseModel):
    """Append-only record of one real execution of a RuntimeNode."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    attempt_id: str = Field(
        default_factory=lambda: f"attempt_{uuid4().hex}", alias="attemptId"
    )
    attempt_number: int = Field(alias="attemptNumber", ge=1)
    graph_version: int = Field(alias="graphVersion", ge=1)
    binding_id: str = Field(default="", alias="bindingId")
    agent_name: str = Field(default="", alias="agentName")
    model_name: str = Field(default="", alias="modelName")
    status: StepStatus = StepStatus.RUNNING
    started_at: datetime = Field(default_factory=_utc_now, alias="startedAt")
    ended_at: datetime | None = Field(default=None, alias="endedAt")
    resolved_input: dict[str, Any] = Field(default_factory=dict, alias="resolvedInput")
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    trace_context: dict[str, Any] = Field(default_factory=dict, alias="traceContext")
    logical_completion_accepted: bool = Field(default=True, alias="logicalCompletionAccepted")
    runtime_event_ids: list[str] = Field(default_factory=list, alias="runtimeEventIds")


class RuntimeNode(BaseModel):
    """Runtime copy of one ACG node plus migration-safe execution metadata."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    node_id: str = Field(alias="nodeId")
    node_type: NodeType = Field(alias="nodeType")
    spec: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    activation: RuntimeNodeActivation = RuntimeNodeActivation.ACTIVE
    current_binding: dict[str, Any] | None = Field(default=None, alias="currentBinding")
    binding_candidates: list[dict[str, Any]] = Field(
        default_factory=list, alias="bindingCandidates"
    )
    binding_history: list[dict[str, Any]] = Field(default_factory=list, alias="bindingHistory")
    binding_switch_count: int = Field(default=0, alias="bindingSwitchCount", ge=0)
    attempts: list[RuntimeAttempt] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    output_version: int = Field(default=0, alias="outputVersion", ge=0)
    error: str | None = None
    source_patch_id: str | None = Field(default=None, alias="sourcePatchId")
    created_graph_version: int = Field(default=1, alias="createdGraphVersion", ge=1)
    updated_at: datetime = Field(default_factory=_utc_now, alias="updatedAt")

    @classmethod
    def from_acg_node(
        cls,
        node,
        *,
        graph_version: int,
        source_patch_id: str | None = None,
    ) -> "RuntimeNode":
        """Deep-copy an ACG node without mutating the source blueprint."""

        spec = node.model_dump(by_alias=True, mode="json")
        binding: dict[str, Any] | None = None
        if isinstance(node, StepNode):
            binding = {
                "assignedAgentId": node.assigned_agent_id,
                "agentName": node.agent_name,
                "capability": node.capability,
                "skillIds": list(node.skill_ids),
            }
        return cls(
            nodeId=node.node_id,
            nodeType=node.node_type,
            spec=spec,
            currentBinding=binding,
            sourcePatchId=source_patch_id,
            createdGraphVersion=graph_version,
        )


class AppliedPatchRecord(BaseModel):
    """Immutable audit record used for replay and content-conflict checks."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    patch_id: str = Field(alias="patchId")
    idempotency_key: str = Field(alias="idempotencyKey")
    content_hash: str = Field(alias="contentHash")
    semantic_hash: str = Field(alias="semanticHash")
    operation_type: str = Field(alias="operationType")
    base_graph_version: int = Field(alias="baseGraphVersion")
    result_graph_version: int = Field(alias="resultGraphVersion")
    source_event_id: str = Field(alias="sourceEventId")
    checkpoint_id: str | None = Field(default=None, alias="checkpointId")
    applied_at: datetime = Field(default_factory=_utc_now, alias="appliedAt")


class RuntimeGraph(BaseModel):
    """Authoritative runtime structure and patch history for one workflow run."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    run_id: str = Field(alias="runId")
    graph_id: str = Field(alias="graphId")
    source_blueprint_version: int = Field(alias="sourceBlueprintVersion", ge=1)
    graph_version: int = Field(default=1, alias="graphVersion", ge=1)
    nodes: list[RuntimeNode] = Field(default_factory=list)
    edges: list[ACGEdge] = Field(default_factory=list)
    processed_event_ids: list[str] = Field(
        default_factory=list, alias="processedEventIds"
    )
    runtime_events: list[RuntimeEvent] = Field(default_factory=list, alias="runtimeEvents")
    pending_runtime_event_ids: list[str] = Field(
        default_factory=list, alias="pendingRuntimeEventIds"
    )
    event_to_patch: dict[str, str] = Field(default_factory=dict, alias="eventToPatch")
    applied_recipe_scopes: list[str] = Field(default_factory=list, alias="appliedRecipeScopes")
    applied_patch_ids: list[str] = Field(default_factory=list, alias="appliedPatchIds")
    applied_patch_idempotency_keys: list[str] = Field(
        default_factory=list,
        alias="appliedPatchIdempotencyKeys",
    )
    applied_patches: list[AppliedPatchRecord] = Field(
        default_factory=list, alias="appliedPatches"
    )
    branch_decisions: list[BranchDecision] = Field(
        default_factory=list, alias="branchDecisions"
    )
    patch_budget: RuntimePatchBudget = Field(
        default_factory=RuntimePatchBudget, alias="patchBudget"
    )
    created_at: datetime = Field(default_factory=_utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=_utc_now, alias="updatedAt")

    @classmethod
    def from_blueprint(
        cls,
        *,
        run_id: str,
        blueprint: ACGBlueprint,
        agent_registry: Any | None = None,
        domain: str = "",
    ) -> "RuntimeGraph":
        """Create deterministic runtime structure from a deep blueprint copy."""

        graph = cls(
            runId=run_id,
            graphId=blueprint.graph_id,
            sourceBlueprintVersion=blueprint.version,
            graphVersion=1,
            nodes=[
                RuntimeNode.from_acg_node(node, graph_version=1)
                for node in blueprint.nodes
            ],
            edges=[edge.model_copy(deep=True) for edge in blueprint.edges],
        )
        branch_edge_ids = {
            edge_id
            for node in blueprint.nodes
            if isinstance(node, ControlNode) and node.control_type == ControlType.IF
            for edge_id in node.branch_edge_ids
        }
        for edge in graph.edges:
            if edge.edge_id in branch_edge_ids:
                edge.activation = EdgeActivation.INACTIVE
        graph.enrich_bindings(agent_registry=agent_registry, domain=domain)
        return graph

    def get_node(self, node_id: str) -> RuntimeNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(f"runtime node not found: {node_id}")

    def has_node(self, node_id: str) -> bool:
        return any(node.node_id == node_id for node in self.nodes)

    def dependency_sources(self, node_id: str) -> list[str]:
        return [
            edge.source_id
            for edge in self.effective_edges()
            if edge.target_id == node_id
            and edge.edge_type in {EdgeType.DEPENDENCY, EdgeType.CONTROL_FLOW}
            and edge.activation == EdgeActivation.ACTIVE
            and self.get_node(edge.source_id).status != StepStatus.SKIPPED_BY_CONDITION
        ]

    def branch_decision_for(self, control_node_id: str) -> BranchDecision | None:
        return next(
            (item for item in self.branch_decisions if item.control_node_id == control_node_id),
            None,
        )

    def ready_set(self) -> list[RuntimeNode]:
        """Return executable nodes whose effective dependencies are completed."""

        ready: list[RuntimeNode] = []
        for node in self.nodes:
            if node.node_type != NodeType.STEP:
                continue
            if node.activation != RuntimeNodeActivation.ACTIVE:
                continue
            if node.status not in {StepStatus.PENDING, StepStatus.RETRYING}:
                continue
            incoming = [
                edge
                for edge in self.effective_edges()
                if edge.target_id == node.node_id
                and edge.edge_type in {EdgeType.DEPENDENCY, EdgeType.CONTROL_FLOW}
            ]
            if any(edge.activation == EdgeActivation.INACTIVE for edge in incoming):
                continue
            dependencies = self.dependency_sources(node.node_id)
            if all(self.get_node(source_id).status == StepStatus.COMPLETED for source_id in dependencies):
                ready.append(node)
        return sorted(ready, key=lambda item: (-int(item.spec.get("priority", 0)), item.node_id))

    def has_waiting_review(self) -> bool:
        return any(node.status == StepStatus.WAITING_REVIEW for node in self.nodes)

    def has_runnable_nodes(self) -> bool:
        return bool(self.ready_set())

    def has_running_nodes(self) -> bool:
        return any(node.status == StepStatus.RUNNING for node in self.nodes)

    def is_terminal(self) -> bool:
        steps = [node for node in self.nodes if node.node_type == NodeType.STEP]
        return bool(steps) and all(
            node.status
            in {
                StepStatus.COMPLETED,
                StepStatus.FAILED,
                StepStatus.CANCELLED,
                StepStatus.SKIPPED_BY_CONDITION,
            }
            for node in steps
        )

    def all_steps_completed(self) -> bool:
        steps = [node for node in self.nodes if node.node_type == NodeType.STEP]
        return bool(steps) and all(
            node.status in {StepStatus.COMPLETED, StepStatus.SKIPPED_BY_CONDITION}
            for node in steps
        )

    def resolve_ready_control_nodes(self) -> bool:
        """Complete dependency-ready, unconditional control nodes without versioning."""

        changed = False
        while True:
            completed_one = False
            for node in self.nodes:
                if node.node_type != NodeType.CONTROL or node.status != StepStatus.PENDING:
                    continue
                parsed = parse_node(node.spec)
                if isinstance(parsed, ControlNode) and parsed.control_type == ControlType.IF:
                    continue
                if all(
                    self.get_node(source_id).status == StepStatus.COMPLETED
                    for source_id in self.dependency_sources(node.node_id)
                ):
                    node.status = StepStatus.COMPLETED
                    node.updated_at = _utc_now()
                    changed = completed_one = True
            if not completed_one:
                return changed

    def effective_edges(self, edge_type: EdgeType | None = None) -> list[ACGEdge]:
        """Return edges not superseded by an applied runtime patch."""

        return [
            edge
            for edge in self.edges
            if not edge.metadata.get("supersededByPatchId")
            and (edge_type is None or edge.edge_type == edge_type)
        ]

    def to_blueprint(self, *, effective_only: bool = True) -> ACGBlueprint:
        """Build a validation view without changing this RuntimeGraph."""

        edges = self.effective_edges() if effective_only else list(self.edges)
        return ACGBlueprint(
            graphId=self.graph_id,
            version=self.source_blueprint_version,
            nodes=[parse_node(node.spec) for node in self.nodes],
            edges=[edge.model_copy(deep=True) for edge in edges],
            metadata={"runtimeGraphVersion": self.graph_version},
        )

    def patch_record_by_id(self, patch_id: str) -> AppliedPatchRecord | None:
        return next(
            (item for item in self.applied_patches if item.patch_id == patch_id), None
        )

    def runtime_event_by_id(self, event_id: str) -> RuntimeEvent | None:
        return next((event for event in self.runtime_events if event.event_id == event_id), None)

    @staticmethod
    def recipe_scope(recipe_id: str, target_node_id: str) -> str:
        return f"{recipe_id}::{target_node_id}"

    def patch_record_by_idempotency_key(self, key: str) -> AppliedPatchRecord | None:
        return next(
            (item for item in self.applied_patches if item.idempotency_key == key), None
        )

    def enrich_bindings(self, *, agent_registry: Any | None, domain: str) -> None:
        """Enrich runtime bindings while leaving the design blueprint untouched."""

        agent_nodes = {
            node.node_id: node
            for node in (parse_node(item.spec) for item in self.nodes)
            if isinstance(node, AgentNode)
        }
        for runtime_node in self.nodes:
            acg_node = parse_node(runtime_node.spec)
            if not isinstance(acg_node, StepNode):
                continue
            execution_edges = [
                edge
                for edge in self.effective_edges(EdgeType.EXECUTION)
                if edge.target_id == runtime_node.node_id
            ]
            assigned_id = acg_node.assigned_agent_id or (
                execution_edges[0].source_id if execution_edges else None
            )
            binding = dict(runtime_node.current_binding or {})
            binding["assignedAgentId"] = assigned_id
            if assigned_id and assigned_id in agent_nodes:
                binding["modelName"] = agent_nodes[assigned_id].model_name
            if agent_registry is not None:
                from agentos.core.recovery.bindings import CandidateResolver

                resolver = CandidateResolver(agent_registry)
                candidates = resolver.resolve_candidates(
                    domain=domain,
                    capability=str(acg_node.capability or ""),
                    required_skills=list(acg_node.skill_ids),
                )
                selected = next(
                    (
                        item
                        for item in candidates
                        if not acg_node.agent_name
                        or item.agent_name.strip().lower()
                        == acg_node.agent_name.strip().lower()
                    ),
                    candidates[0] if candidates else None,
                )
                if selected is None:
                    explicit_agent = agent_registry.resolve(
                        domain=domain,
                        agent_name=acg_node.agent_name,
                        capability=acg_node.capability,
                    )
                    from agentos.core.recovery.bindings import ExecutionBinding

                    registration_order = next(
                        index
                        for index, item in enumerate(agent_registry.all())
                        if item is explicit_agent
                    )
                    selected = ExecutionBinding.from_agent(
                        explicit_agent,
                        capability=str(acg_node.capability or ""),
                        registration_order=registration_order,
                    )
                    candidates = [selected]
                if selected is not None:
                    binding = selected.model_dump(by_alias=True, mode="json")
                    runtime_node.binding_candidates = [
                        item.model_dump(by_alias=True, mode="json") for item in candidates
                    ]
                    if not runtime_node.binding_history:
                        runtime_node.binding_history.append(
                            {
                                "bindingId": selected.binding_id,
                                "selectedAtGraphVersion": self.graph_version,
                                "reasonCode": "INITIAL_BINDING",
                                "selectedAt": _utc_now().isoformat(),
                                "sourceEventId": None,
                                "sourcePatchId": None,
                                "supersededAt": None,
                            }
                        )
            runtime_node.current_binding = binding

    def structure_hash(self) -> str:
        """Hash graph structure and patch lineage, excluding mutable node state."""

        return _canonical_hash(
            {
                "graphId": self.graph_id,
                "graphVersion": self.graph_version,
                "nodes": [node.spec for node in self.nodes],
                "edges": [
                    edge.model_dump(by_alias=True, mode="json") for edge in self.edges
                ],
                "appliedPatchIds": self.applied_patch_ids,
            }
        )


__all__ = [
    "AppliedPatchRecord",
    "RuntimeGraph",
    "RuntimeAttempt",
    "RuntimeEvent",
    "RuntimeEventStatus",
    "RuntimeEventType",
    "RuntimeNode",
    "RuntimeNodeActivation",
    "RuntimeNodeStatus",
    "RuntimePatchBudget",
]

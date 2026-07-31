"""Typed inputs and results for controlled runtime-graph patching."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentos.core.acg.edges import ACGEdge
from agentos.core.acg.nodes import ACGNode, parse_node
from agentos.core.models.types import utc_now
from agentos.core.runtime_graph import RuntimeGraph, RuntimeNodeStatus
from agentos.core.recovery.bindings import ExecutionBinding


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PatchOperationType(str, Enum):
    ADD_SUBGRAPH = "ADD_SUBGRAPH"
    RETRY_ALTERNATE_BINDING = "RETRY_ALTERNATE_BINDING"
    ACTIVATE_CONDITIONAL_BRANCH = "ACTIVATE_CONDITIONAL_BRANCH"


class SubgraphInsertionMode(str, Enum):
    INSERT_BEFORE_TARGET = "INSERT_BEFORE_TARGET"


class PatchBudgetImpact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    added_nodes: int = Field(default=0, alias="addedNodes", ge=0)
    replan_depth_increment: int = Field(default=1, alias="replanDepthIncrement", ge=0)


class RuntimeGraphPatch(BaseModel):
    """A bounded request to insert a subgraph immediately before one target."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    patch_id: str = Field(alias="patchId", min_length=1)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=1)
    run_id: str = Field(alias="runId", min_length=1)
    graph_id: str = Field(alias="graphId", min_length=1)
    base_graph_version: int = Field(alias="baseGraphVersion", ge=1)
    operation_type: PatchOperationType = Field(alias="operationType")
    source_event_id: str = Field(alias="sourceEventId", min_length=1)
    proposal_id: str = Field(alias="proposalId", min_length=1)
    reason: str = ""
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    expected_node_states: dict[str, RuntimeNodeStatus] = Field(
        default_factory=dict,
        alias="expectedNodeStates",
    )
    budget_impact: PatchBudgetImpact = Field(alias="budgetImpact")
    metadata: dict[str, Any] = Field(default_factory=dict)
    insertion_mode: SubgraphInsertionMode = Field(
        default=SubgraphInsertionMode.INSERT_BEFORE_TARGET,
        alias="insertionMode",
    )
    target_node_id: str | None = Field(default=None, alias="targetNodeId")
    replaced_incoming_edge_ids: list[str] = Field(default_factory=list, alias="replacedIncomingEdgeIds")
    add_nodes: list[ACGNode] = Field(default_factory=list, alias="addNodes")
    add_edges: list[ACGEdge] = Field(default_factory=list, alias="addEdges")
    runtime_node_id: str | None = Field(default=None, alias="runtimeNodeId")
    expected_attempt_id: str | None = Field(default=None, alias="expectedAttemptId")
    expected_current_binding_id: str | None = Field(
        default=None, alias="expectedCurrentBindingId"
    )
    new_binding: ExecutionBinding | None = Field(default=None, alias="newBinding")
    excluded_binding_ids: list[str] = Field(default_factory=list, alias="excludedBindingIds")
    control_node_id: str | None = Field(default=None, alias="controlNodeId")
    expected_control_node_state: RuntimeNodeStatus | None = Field(
        default=None, alias="expectedControlNodeState"
    )
    expected_source_output_version: int | None = Field(
        default=None, alias="expectedSourceOutputVersion"
    )
    input_hash: str | None = Field(default=None, alias="inputHash")
    selected_case_key: str | None = Field(default=None, alias="selectedCaseKey")
    selected_edge_ids: list[str] = Field(default_factory=list, alias="selectedEdgeIds")
    terminated_edge_ids: list[str] = Field(default_factory=list, alias="terminatedEdgeIds")
    join_node_id: str | None = Field(default=None, alias="joinNodeId")
    node_state_updates: dict[str, RuntimeNodeStatus] = Field(
        default_factory=dict, alias="nodeStateUpdates"
    )

    @field_validator("add_nodes", mode="before")
    @classmethod
    def _parse_nodes(cls, value):
        return [parse_node(item) for item in (value or [])]

    @model_validator(mode="after")
    def _validate_operation_payload(self):
        if self.operation_type == PatchOperationType.ADD_SUBGRAPH:
            if not self.target_node_id or not self.add_nodes or not self.add_edges:
                raise ValueError("ADD_SUBGRAPH requires targetNodeId, addNodes, and addEdges")
            if self.new_binding is not None or self.runtime_node_id is not None:
                raise ValueError("ADD_SUBGRAPH payload cannot contain binding fields")
        elif self.operation_type == PatchOperationType.RETRY_ALTERNATE_BINDING:
            if not self.runtime_node_id or self.new_binding is None:
                raise ValueError("RETRY_ALTERNATE_BINDING requires runtimeNodeId and newBinding")
            if self.target_node_id or self.add_nodes or self.add_edges or self.replaced_incoming_edge_ids:
                raise ValueError("binding patch cannot contain subgraph fields")
            if self.control_node_id or self.selected_edge_ids or self.terminated_edge_ids:
                raise ValueError("binding patch cannot contain conditional fields")
        elif self.operation_type == PatchOperationType.ACTIVATE_CONDITIONAL_BRANCH:
            if (
                not self.control_node_id
                or self.expected_source_output_version is None
                or not self.input_hash
                or not self.selected_edge_ids
                or not self.terminated_edge_ids
                or not self.join_node_id
            ):
                raise ValueError("conditional patch requires complete decision fields")
            if (
                self.target_node_id
                or self.add_nodes
                or self.add_edges
                or self.replaced_incoming_edge_ids
                or self.new_binding is not None
                or self.runtime_node_id is not None
            ):
                raise ValueError("conditional patch cannot contain subgraph or binding fields")
        return self

    def content_hash(self) -> str:
        return _hash(self.model_dump(by_alias=True, mode="json"))

    def semantic_hash(self) -> str:
        payload = self.model_dump(by_alias=True, mode="json")
        for key in (
            "patchId",
            "idempotencyKey",
            "createdAt",
            "sourceEventId",
            "proposalId",
            "reason",
        ):
            payload.pop(key, None)
        return _hash(payload)


class PatchApplyResult(BaseModel):
    """Result of applying or idempotently replaying a persisted patch."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    applied: bool
    idempotent_replay: bool = Field(default=False, alias="idempotentReplay")
    graph_version: int = Field(alias="graphVersion")
    patch_id: str = Field(alias="patchId")
    checkpoint_id: str | None = Field(default=None, alias="checkpointId")
    runtime_graph: RuntimeGraph = Field(alias="runtimeGraph")


__all__ = [
    "PatchApplyResult",
    "PatchBudgetImpact",
    "PatchOperationType",
    "RuntimeGraphPatch",
    "SubgraphInsertionMode",
]

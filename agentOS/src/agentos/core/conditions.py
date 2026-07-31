"""Safe, deterministic condition models and evaluation for runtime IF controls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentos.core.acg.enums import EdgeType


class ConditionOperator(str, Enum):
    EQUALS = "EQUALS"
    IN = "IN"
    EXISTS = "EXISTS"
    BOOLEAN = "BOOLEAN"


class ConditionSpec(BaseModel):
    """A bounded lookup and case map; it cannot execute expressions or code."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    source_node_id: str = Field(alias="sourceNodeId", min_length=1)
    json_pointer: str = Field(alias="jsonPointer")
    operator: ConditionOperator
    cases: dict[str, str]
    default_edge_id: str | None = Field(default=None, alias="defaultEdgeId")
    value_type: str = Field(default="string", alias="valueType")

    @field_validator("json_pointer")
    @classmethod
    def _valid_pointer(cls, value: str) -> str:
        if value and not value.startswith("/"):
            raise ValueError("jsonPointer must be empty or begin with '/'")
        return value

    @field_validator("value_type")
    @classmethod
    def _valid_value_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"string", "number", "boolean", "array", "object", "any"}:
            raise ValueError("unsupported condition valueType")
        return normalized


class ConditionalEvaluationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    control_node_id: str = Field(alias="controlNodeId")
    source_node_id: str = Field(alias="sourceNodeId")
    source_output_version: int = Field(alias="sourceOutputVersion", ge=0)
    input_hash: str = Field(alias="inputHash")
    resolved_value: Any = Field(alias="resolvedValue")
    selected_case_key: str = Field(alias="selectedCaseKey")
    selected_edge_ids: list[str] = Field(alias="selectedEdgeIds")
    terminated_edge_ids: list[str] = Field(alias="terminatedEdgeIds")
    join_node_id: str = Field(alias="joinNodeId")


class BranchDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)
    decision_id: str = Field(alias="decisionId")
    control_node_id: str = Field(alias="controlNodeId")
    source_node_id: str = Field(alias="sourceNodeId")
    source_output_version: int = Field(alias="sourceOutputVersion", ge=0)
    input_hash: str = Field(alias="inputHash")
    selected_case_key: str = Field(alias="selectedCaseKey")
    selected_edge_ids: list[str] = Field(alias="selectedEdgeIds")
    terminated_edge_ids: list[str] = Field(alias="terminatedEdgeIds")
    skipped_node_ids: list[str] = Field(alias="skippedNodeIds")
    join_node_id: str = Field(alias="joinNodeId")
    source_event_id: str = Field(alias="sourceEventId")
    source_patch_id: str = Field(alias="sourcePatchId")
    decided_at_graph_version: int = Field(alias="decidedAtGraphVersion", ge=1)
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="decidedAt"
    )


def condition_input_hash(
    *, source_node_id: str, output_version: int, json_pointer: str, resolved_value: Any
) -> str:
    payload = [source_node_id, output_version, json_pointer, resolved_value]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ConditionEvaluationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ConditionEvaluator:
    """Pure RFC-6901-style lookup and bounded case selection."""

    _MISSING = object()

    def evaluate(
        self,
        condition_spec: ConditionSpec,
        source_output: dict[str, Any],
        graph,
        *,
        control_node_id: str,
        join_node_id: str,
        branch_edge_ids: list[str],
    ) -> ConditionalEvaluationResult:
        source = graph.get_node(condition_spec.source_node_id)
        value = self._resolve_pointer(source_output, condition_spec.json_pointer)
        exists = value is not self._MISSING
        self._validate_type(condition_spec, value, exists)
        case_key = self._select_case(condition_spec, value, exists)
        edge_id = condition_spec.cases.get(case_key)
        if edge_id is None:
            edge_id = condition_spec.default_edge_id
            case_key = "__default__"
        if edge_id is None:
            raise ConditionEvaluationError(
                "CONDITION_NO_MATCH", "condition did not match and has no defaultEdgeId"
            )
        if edge_id not in branch_edge_ids:
            raise ConditionEvaluationError(
                "CONDITION_EDGE_NOT_DECLARED", f"selected edge is not declared: {edge_id}"
            )
        resolved = None if value is self._MISSING else value
        input_hash = condition_input_hash(
            source_node_id=source.node_id,
            output_version=source.output_version,
            json_pointer=condition_spec.json_pointer,
            resolved_value=resolved,
        )
        return ConditionalEvaluationResult(
            controlNodeId=control_node_id,
            sourceNodeId=source.node_id,
            sourceOutputVersion=source.output_version,
            inputHash=input_hash,
            resolvedValue=resolved,
            selectedCaseKey=case_key,
            selectedEdgeIds=[edge_id],
            terminatedEdgeIds=[item for item in branch_edge_ids if item != edge_id],
            joinNodeId=join_node_id,
        )

    @classmethod
    def _resolve_pointer(cls, document: Any, pointer: str) -> Any:
        if pointer == "":
            return document
        current = document
        for raw in pointer.split("/")[1:]:
            token = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and token in current:
                current = current[token]
            elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
                current = current[int(token)]
            else:
                return cls._MISSING
        return current

    @staticmethod
    def _case_key(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        return str(value)

    def _select_case(self, spec: ConditionSpec, value: Any, exists: bool) -> str:
        if spec.operator == ConditionOperator.EXISTS:
            return "true" if exists else "false"
        if not exists:
            return "__missing__"
        if spec.operator == ConditionOperator.BOOLEAN:
            if not isinstance(value, bool):
                raise ConditionEvaluationError("CONDITION_TYPE_MISMATCH", "BOOLEAN requires bool")
            return "true" if value else "false"
        if spec.operator == ConditionOperator.IN:
            if not isinstance(value, list):
                raise ConditionEvaluationError("CONDITION_TYPE_MISMATCH", "IN requires array")
            keys = {self._case_key(item) for item in value}
            return next((key for key in spec.cases if key in keys), "__no_match__")
        return self._case_key(value)

    @staticmethod
    def _validate_type(spec: ConditionSpec, value: Any, exists: bool) -> None:
        if not exists or spec.operator == ConditionOperator.EXISTS or spec.value_type == "any":
            return
        matches = {
            "string": isinstance(value, str),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }[spec.value_type]
        if not matches:
            raise ConditionEvaluationError(
                "CONDITION_TYPE_MISMATCH", f"expected {spec.value_type}"
            )


def conditional_branch_exclusive_nodes(graph, control_node) -> dict[str, set[str]]:
    """Return each declared branch's nodes strictly before its explicit join."""

    edges = {edge.edge_id: edge for edge in graph.edges}
    adjacency: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.edge_type == EdgeType.DEPENDENCY:
            adjacency.setdefault(edge.source_id, []).append(edge.target_id)
    join_id = control_node.join_node_id
    if not join_id:
        raise ConditionEvaluationError("CONDITIONAL_JOIN_MISSING", control_node.node_id)

    results: dict[str, set[str]] = {}
    for edge_id in control_node.branch_edge_ids:
        edge = edges.get(edge_id)
        if (
            edge is None
            or edge.source_id != control_node.node_id
            or edge.edge_type not in {EdgeType.DEPENDENCY, EdgeType.CONTROL_FLOW}
        ):
            raise ConditionEvaluationError("CONDITIONAL_BRANCH_EDGE_INVALID", edge_id)
        visited: set[str] = set()
        visiting: set[str] = set()

        def walk(node_id: str) -> bool:
            if node_id == join_id:
                return True
            if node_id in visiting:
                return False
            if node_id in visited:
                return True
            visiting.add(node_id)
            targets = adjacency.get(node_id, [])
            reaches = bool(targets) and all(walk(target) for target in targets)
            visiting.remove(node_id)
            if reaches:
                visited.add(node_id)
            return reaches

        if not walk(edge.target_id):
            raise ConditionEvaluationError(
                "CONDITIONAL_BRANCH_DOES_NOT_JOIN", f"branch {edge_id} does not converge"
            )
        results[edge_id] = visited

    edge_ids = list(results)
    for index, edge_id in enumerate(edge_ids):
        for other_id in edge_ids[index + 1 :]:
            shared = results[edge_id] & results[other_id]
            if shared:
                raise ConditionEvaluationError(
                    "CONDITIONAL_BRANCH_SHARED_NODE",
                    f"branches share nodes before join: {sorted(shared)}",
                )
    return results


__all__ = [
    "BranchDecision",
    "ConditionEvaluationError",
    "ConditionEvaluator",
    "ConditionOperator",
    "ConditionSpec",
    "ConditionalEvaluationResult",
    "condition_input_hash",
    "conditional_branch_exclusive_nodes",
]

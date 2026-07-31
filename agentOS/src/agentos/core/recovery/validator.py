"""Pure validation and candidate construction for bounded runtime patches."""

from __future__ import annotations

from collections import defaultdict

from agentos.core.acg.edges import EdgeActivation
from agentos.core.acg.enums import ControlType, EdgeType, NodeType
from agentos.core.acg.graph_ops import ACGValidationError, validate_blueprint
from agentos.core.acg.nodes import ControlNode, StepNode, parse_node
from agentos.core.recovery.bindings import CandidateResolver
from agentos.core.conditions import (
    ConditionEvaluationError,
    ConditionEvaluator,
    conditional_branch_exclusive_nodes,
)
from agentos.core.recovery.constants import MAX_BINDING_SWITCHES_PER_NODE
from agentos.core.recovery.errors import PatchValidationError
from agentos.core.recovery.models import (
    PatchOperationType,
    RuntimeGraphPatch,
    SubgraphInsertionMode,
)
from agentos.core.runtime_graph import RuntimeGraph, RuntimeNode, RuntimeNodeStatus


_IMMUTABLE_TARGET_STATES = {
    RuntimeNodeStatus.COMPLETED,
    RuntimeNodeStatus.CANCELLED,
}


class PatchValidator:
    """Validate a patch against a graph copy; never mutate caller-owned objects."""

    def __init__(self, agent_registry) -> None:
        self.agent_registry = agent_registry
        self.candidate_resolver = CandidateResolver(agent_registry)

    def validate(
        self,
        graph: RuntimeGraph,
        patch: RuntimeGraphPatch,
        *,
        domain: str,
    ) -> RuntimeGraph:
        """Return a validated candidate graph without advancing its version."""

        self._validate_identity(graph, patch)
        if patch.operation_type == PatchOperationType.RETRY_ALTERNATE_BINDING:
            return self._validate_alternate_binding(graph, patch, domain=domain)
        if patch.operation_type == PatchOperationType.ACTIVATE_CONDITIONAL_BRANCH:
            self._validate_budget(graph, patch)
            return self._validate_conditional(graph, patch)
        self._validate_budget(graph, patch)
        self._validate_target_and_replaced_edges(graph, patch)
        self._validate_ids(graph, patch)
        self._validate_capabilities(patch, domain=domain)

        candidate = graph.model_copy(deep=True)
        next_version = graph.graph_version + 1
        for edge in candidate.edges:
            if edge.edge_id in patch.replaced_incoming_edge_ids:
                edge.metadata["supersededByPatchId"] = patch.patch_id
                edge.metadata["supersededAtGraphVersion"] = next_version
        candidate.nodes.extend(
            RuntimeNode.from_acg_node(
                node.model_copy(deep=True),
                graph_version=next_version,
                source_patch_id=patch.patch_id,
            )
            for node in patch.add_nodes
        )
        for edge in patch.add_edges:
            copied = edge.model_copy(deep=True)
            copied.metadata["sourcePatchId"] = patch.patch_id
            copied.metadata["createdGraphVersion"] = next_version
            candidate.edges.append(copied)

        self._validate_insertion_connectivity(graph, candidate, patch)
        try:
            validate_blueprint(candidate.to_blueprint(effective_only=True))
        except (ACGValidationError, ValueError, TypeError) as exc:
            raise PatchValidationError("INVALID_RUNTIME_GRAPH", str(exc)) from exc
        candidate.enrich_bindings(agent_registry=self.agent_registry, domain=domain)
        candidate.patch_budget.current_replan_depth += (
            patch.budget_impact.replan_depth_increment
        )
        return candidate

    @staticmethod
    def _validate_identity(graph: RuntimeGraph, patch: RuntimeGraphPatch) -> None:
        if patch.run_id != graph.run_id:
            raise PatchValidationError(
                "RUN_ID_MISMATCH", "patch runId does not match RuntimeGraph"
            )
        if patch.graph_id != graph.graph_id:
            raise PatchValidationError(
                "GRAPH_ID_MISMATCH", "patch graphId does not match RuntimeGraph"
            )
        if patch.base_graph_version != graph.graph_version:
            raise PatchValidationError(
                "GRAPH_VERSION_CONFLICT",
                f"expected graphVersion {graph.graph_version}, got {patch.base_graph_version}",
            )
        if patch.operation_type not in {
            PatchOperationType.ADD_SUBGRAPH,
            PatchOperationType.RETRY_ALTERNATE_BINDING,
            PatchOperationType.ACTIVATE_CONDITIONAL_BRANCH,
        }:
            raise PatchValidationError(
                "UNSUPPORTED_PATCH_OPERATION", str(patch.operation_type)
            )
        if (
            patch.operation_type == PatchOperationType.ADD_SUBGRAPH
            and patch.insertion_mode != SubgraphInsertionMode.INSERT_BEFORE_TARGET
        ):
            raise PatchValidationError(
                "UNSUPPORTED_INSERTION_MODE", str(patch.insertion_mode)
            )
        if not patch.patch_id.strip() or not patch.idempotency_key.strip():
            raise PatchValidationError(
                "INVALID_PATCH_IDENTITY", "patchId and idempotencyKey are required"
            )

    def _validate_alternate_binding(self, graph, patch, *, domain: str) -> RuntimeGraph:
        node = graph.get_node(str(patch.runtime_node_id))
        if node.node_type != NodeType.STEP:
            raise PatchValidationError("INVALID_BINDING_TARGET", node.node_id)
        if node.status not in {RuntimeNodeStatus.FAILED, RuntimeNodeStatus.RETRYING}:
            raise PatchValidationError("TARGET_STATE_CONFLICT", node.status.value)
        if patch.expected_node_states.get(node.node_id) != node.status:
            raise PatchValidationError("EXPECTED_NODE_STATE_CONFLICT", node.node_id)
        if not node.attempts or node.attempts[-1].attempt_id != patch.expected_attempt_id:
            raise PatchValidationError("EXPECTED_ATTEMPT_CONFLICT", node.node_id)
        current_id = str((node.current_binding or {}).get("bindingId") or "")
        if current_id != patch.expected_current_binding_id:
            raise PatchValidationError("CURRENT_BINDING_CONFLICT", node.node_id)
        new_binding = patch.new_binding
        assert new_binding is not None
        if new_binding.binding_id == current_id:
            raise PatchValidationError("SAME_BINDING", new_binding.binding_id)
        if new_binding.binding_id in patch.excluded_binding_ids:
            raise PatchValidationError("EXCLUDED_BINDING", new_binding.binding_id)
        capability = str(node.spec.get("capability") or "")
        required_skills = list(node.spec.get("skillIds") or [])
        if new_binding.domain.strip().lower() != domain.strip().lower():
            raise PatchValidationError("BINDING_DOMAIN_MISMATCH", new_binding.domain)
        if new_binding.capability.strip().lower() != capability.strip().lower():
            raise PatchValidationError("BINDING_CAPABILITY_MISMATCH", new_binding.capability)
        if not self.candidate_resolver.validate_binding(
            domain=domain,
            capability=capability,
            required_skills=required_skills,
            binding=new_binding,
        ):
            raise PatchValidationError("INVALID_BINDING", new_binding.binding_id)
        retry_limit = int(node.spec.get("retryLimit") or 0)
        if len(node.attempts) > retry_limit:
            raise PatchValidationError("RETRY_LIMIT_EXCEEDED", node.node_id)
        if node.binding_switch_count >= MAX_BINDING_SWITCHES_PER_NODE:
            raise PatchValidationError("BINDING_SWITCH_BUDGET_EXCEEDED", node.node_id)
        candidate = graph.model_copy(deep=True)
        candidate_node = candidate.get_node(node.node_id)
        candidate_node.current_binding = new_binding.model_dump(by_alias=True, mode="json")
        candidate_node.status = RuntimeNodeStatus.RETRYING
        candidate_node.error = None
        candidate_node.binding_switch_count += 1
        return candidate

    @staticmethod
    def _validate_conditional(graph, patch) -> RuntimeGraph:
        try:
            control_runtime = graph.get_node(str(patch.control_node_id))
        except KeyError as exc:
            raise PatchValidationError("CONTROL_NODE_NOT_FOUND", str(patch.control_node_id)) from exc
        control = parse_node(control_runtime.spec)
        if not isinstance(control, ControlNode) or control.control_type != ControlType.IF:
            raise PatchValidationError("INVALID_CONDITIONAL_CONTROL", control_runtime.node_id)
        if control_runtime.status != RuntimeNodeStatus.PENDING:
            raise PatchValidationError("CONTROL_STATE_CONFLICT", control_runtime.status.value)
        if patch.expected_control_node_state != control_runtime.status:
            raise PatchValidationError("EXPECTED_CONTROL_STATE_CONFLICT", control_runtime.node_id)
        if graph.branch_decision_for(control_runtime.node_id) is not None:
            raise PatchValidationError("CONDITIONAL_ALREADY_DECIDED", control_runtime.node_id)
        if control.condition_spec is None or control.join_node_id != patch.join_node_id:
            raise PatchValidationError("CONDITION_SPEC_CONFLICT", control_runtime.node_id)
        source = graph.get_node(control.condition_spec.source_node_id)
        if source.status != RuntimeNodeStatus.COMPLETED:
            raise PatchValidationError("CONDITION_SOURCE_NOT_COMPLETED", source.node_id)
        if source.output_version <= 0:
            raise PatchValidationError("CONDITION_SOURCE_OUTPUT_MISSING", source.node_id)
        if source.output_version != patch.expected_source_output_version:
            raise PatchValidationError("SOURCE_OUTPUT_VERSION_CONFLICT", source.node_id)
        try:
            evaluation = ConditionEvaluator().evaluate(
                control.condition_spec,
                source.output,
                graph,
                control_node_id=control.node_id,
                join_node_id=control.join_node_id,
                branch_edge_ids=control.branch_edge_ids,
            )
            exclusive = conditional_branch_exclusive_nodes(graph, control)
        except ConditionEvaluationError as exc:
            raise PatchValidationError(exc.code, str(exc)) from exc
        if evaluation.input_hash != patch.input_hash:
            raise PatchValidationError("CONDITION_INPUT_HASH_CONFLICT", control.node_id)
        if evaluation.selected_case_key != patch.selected_case_key:
            raise PatchValidationError("CONDITION_CASE_CONFLICT", control.node_id)
        if set(evaluation.selected_edge_ids) != set(patch.selected_edge_ids):
            raise PatchValidationError("SELECTED_BRANCH_CONFLICT", control.node_id)
        if set(evaluation.terminated_edge_ids) != set(patch.terminated_edge_ids):
            raise PatchValidationError("TERMINATED_BRANCH_CONFLICT", control.node_id)
        declared = set(control.branch_edge_ids)
        selected = set(patch.selected_edge_ids)
        terminated = set(patch.terminated_edge_ids)
        if selected & terminated or selected | terminated != declared:
            raise PatchValidationError("INCOMPLETE_BRANCH_PARTITION", control.node_id)
        skipped = {
            node_id for edge_id in terminated for node_id in exclusive[edge_id]
        }
        expected_updates = {
            node_id: RuntimeNodeStatus.SKIPPED_BY_CONDITION for node_id in skipped
        }
        if patch.node_state_updates != expected_updates:
            raise PatchValidationError("INVALID_CONDITIONAL_NODE_UPDATES", control.node_id)
        if control.join_node_id in skipped:
            raise PatchValidationError("CONDITIONAL_JOIN_SKIPPED", control.join_node_id)
        for node_id in skipped:
            if graph.get_node(node_id).status != RuntimeNodeStatus.PENDING:
                raise PatchValidationError("BRANCH_ALREADY_STARTED", node_id)

        node_count = len(graph.nodes)
        edge_count = len(graph.edges)
        bindings = {node.node_id: node.current_binding for node in graph.nodes}
        candidate = graph.model_copy(deep=True)
        candidate.get_node(control.node_id).status = RuntimeNodeStatus.COMPLETED
        for edge in candidate.edges:
            if edge.edge_id in selected:
                edge.activation = EdgeActivation.ACTIVE
            elif edge.edge_id in terminated:
                edge.activation = EdgeActivation.TERMINATED
        for node_id in skipped:
            candidate.get_node(node_id).status = RuntimeNodeStatus.SKIPPED_BY_CONDITION
        if len(candidate.nodes) != node_count or len(candidate.edges) != edge_count:
            raise PatchValidationError("CONDITIONAL_STRUCTURE_CHANGED", control.node_id)
        if {node.node_id: node.current_binding for node in candidate.nodes} != bindings:
            raise PatchValidationError("CONDITIONAL_BINDING_CHANGED", control.node_id)
        return candidate

    @staticmethod
    def _validate_budget(graph: RuntimeGraph, patch: RuntimeGraphPatch) -> None:
        budget = graph.patch_budget
        if len(graph.applied_patch_ids) >= budget.max_graph_patches:
            raise PatchValidationError(
                "PATCH_BUDGET_EXCEEDED", "maximum graph patch count reached"
            )
        if len(patch.add_nodes) > budget.max_added_nodes_per_patch:
            raise PatchValidationError(
                "ADDED_NODE_BUDGET_EXCEEDED", "too many nodes in one patch"
            )
        if len(graph.nodes) + len(patch.add_nodes) > budget.max_total_runtime_nodes:
            raise PatchValidationError(
                "TOTAL_NODE_BUDGET_EXCEEDED", "runtime graph node budget exceeded"
            )
        if patch.budget_impact.added_nodes != len(patch.add_nodes):
            raise PatchValidationError(
                "BUDGET_IMPACT_MISMATCH", "budgetImpact.addedNodes is inaccurate"
            )
        depth = budget.current_replan_depth + patch.budget_impact.replan_depth_increment
        if depth > budget.max_replan_depth:
            raise PatchValidationError(
                "REPLAN_DEPTH_EXCEEDED", "maximum replan depth exceeded"
            )

    @staticmethod
    def _validate_target_and_replaced_edges(
        graph: RuntimeGraph,
        patch: RuntimeGraphPatch,
    ) -> None:
        try:
            target = graph.get_node(patch.target_node_id)
        except KeyError as exc:
            raise PatchValidationError(
                "TARGET_NODE_NOT_FOUND", patch.target_node_id
            ) from exc
        if target.node_type != NodeType.STEP:
            raise PatchValidationError(
                "INVALID_TARGET_NODE", "target must be a Step node"
            )
        target_status = target.status
        if target_status in _IMMUTABLE_TARGET_STATES:
            raise PatchValidationError(
                "TARGET_STATE_CONFLICT", f"target is {target_status.value}"
            )
        for node_id, expected in patch.expected_node_states.items():
            try:
                runtime_status = graph.get_node(node_id).status
            except KeyError as exc:
                raise PatchValidationError("EXPECTED_NODE_NOT_FOUND", node_id) from exc
            actual = runtime_status
            if actual != expected:
                raise PatchValidationError(
                    "EXPECTED_NODE_STATE_CONFLICT",
                    f"{node_id}: expected {expected.value}, got {actual.value}",
                )

        if len(set(patch.replaced_incoming_edge_ids)) != len(
            patch.replaced_incoming_edge_ids
        ):
            raise PatchValidationError(
                "DUPLICATE_REPLACED_EDGE_ID", "replaced edge ids must be unique"
            )
        incoming = {
            edge.edge_id: edge
            for edge in graph.effective_edges(EdgeType.DEPENDENCY)
            if edge.target_id == patch.target_node_id
        }
        invalid = [
            edge_id
            for edge_id in patch.replaced_incoming_edge_ids
            if edge_id not in incoming
        ]
        if invalid:
            raise PatchValidationError(
                "INVALID_REPLACED_EDGE",
                f"edges are not active incoming dependencies of target: {invalid}",
            )
        if incoming and not patch.replaced_incoming_edge_ids:
            raise PatchValidationError(
                "MISSING_REPLACED_EDGE", "target has incoming dependencies"
            )

    @staticmethod
    def _validate_ids(graph: RuntimeGraph, patch: RuntimeGraphPatch) -> None:
        node_ids = [node.node_id for node in patch.add_nodes]
        edge_ids = [edge.edge_id for edge in patch.add_edges]
        if len(node_ids) != len(set(node_ids)):
            raise PatchValidationError(
                "DUPLICATE_NODE_ID", "patch contains duplicate node ids"
            )
        if len(edge_ids) != len(set(edge_ids)):
            raise PatchValidationError(
                "DUPLICATE_EDGE_ID", "patch contains duplicate edge ids"
            )
        existing_nodes = {node.node_id for node in graph.nodes}
        existing_edges = {edge.edge_id for edge in graph.edges}
        collisions = sorted(existing_nodes.intersection(node_ids))
        if collisions:
            raise PatchValidationError("NODE_ID_CONFLICT", str(collisions))
        collisions = sorted(existing_edges.intersection(edge_ids))
        if collisions:
            raise PatchValidationError("EDGE_ID_CONFLICT", str(collisions))

        all_nodes = existing_nodes.union(node_ids)
        completed_nodes = {
            node.node_id
            for node in graph.nodes
            if node.status == RuntimeNodeStatus.COMPLETED
        }
        added_nodes = set(node_ids)
        replaced_predecessors = {
            edge.source_id
            for edge in graph.effective_edges(EdgeType.DEPENDENCY)
            if edge.edge_id in patch.replaced_incoming_edge_ids
        }
        for edge in patch.add_edges:
            if edge.source_id not in all_nodes or edge.target_id not in all_nodes:
                raise PatchValidationError(
                    "EDGE_ENDPOINT_NOT_FOUND",
                    f"{edge.edge_id}: {edge.source_id} -> {edge.target_id}",
                )
            if edge.target_id in completed_nodes:
                raise PatchValidationError(
                    "COMPLETED_NODE_MODIFICATION",
                    f"new edge {edge.edge_id} targets completed node {edge.target_id}",
                )
            if edge.edge_type == EdgeType.DEPENDENCY:
                allowed_target = (
                    edge.target_id in added_nodes
                    or edge.target_id == patch.target_node_id
                )
                allowed_source = (
                    edge.source_id in added_nodes
                    or edge.source_id in replaced_predecessors
                )
                if not allowed_target or not allowed_source:
                    raise PatchValidationError(
                        "OUT_OF_SCOPE_DEPENDENCY_EDIT",
                        f"dependency {edge.edge_id} is outside INSERT_BEFORE_TARGET",
                    )
                if (
                    edge.target_id == patch.target_node_id
                    and edge.source_id not in added_nodes
                ):
                    raise PatchValidationError(
                        "TARGET_BYPASSES_SUBGRAPH",
                        f"dependency {edge.edge_id} reaches target without an added node",
                    )

    def _validate_capabilities(self, patch: RuntimeGraphPatch, *, domain: str) -> None:
        for node in patch.add_nodes:
            if not isinstance(node, StepNode):
                continue
            try:
                self.agent_registry.resolve(
                    domain=domain,
                    agent_name=node.agent_name,
                    capability=node.capability,
                )
            except KeyError as exc:
                raise PatchValidationError(
                    "UNREGISTERED_CAPABILITY",
                    f"node {node.node_id}: {node.agent_name}/{node.capability}",
                ) from exc

    @staticmethod
    def _validate_insertion_connectivity(
        original: RuntimeGraph,
        candidate: RuntimeGraph,
        patch: RuntimeGraphPatch,
    ) -> None:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in candidate.effective_edges(EdgeType.DEPENDENCY):
            adjacency[edge.source_id].add(edge.target_id)

        def has_path(source: str, target: str) -> bool:
            frontier = [source]
            seen: set[str] = set()
            while frontier:
                current = frontier.pop()
                if current == target:
                    return True
                if current in seen:
                    continue
                seen.add(current)
                frontier.extend(adjacency.get(current, ()))
            return False

        replaced = {
            edge.edge_id: edge
            for edge in original.effective_edges(EdgeType.DEPENDENCY)
            if edge.edge_id in patch.replaced_incoming_edge_ids
        }
        new_ids = {node.node_id for node in patch.add_nodes}
        if not any(
            edge.edge_type == EdgeType.DEPENDENCY
            and edge.source_id in new_ids
            and edge.target_id == patch.target_node_id
            for edge in patch.add_edges
        ):
            raise PatchValidationError(
                "SUBGRAPH_NOT_CONNECTED_TO_TARGET", patch.target_node_id
            )
        for predecessor in {edge.source_id for edge in replaced.values()}:
            if not any(has_path(predecessor, new_id) for new_id in new_ids):
                raise PatchValidationError("PREDECESSOR_NOT_CONNECTED", predecessor)
        for node_id in new_ids:
            if not has_path(node_id, patch.target_node_id):
                raise PatchValidationError("ADDED_NODE_NOT_CONNECTED", node_id)


__all__ = ["PatchValidator"]

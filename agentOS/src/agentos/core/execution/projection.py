"""One-way compatibility projections from RuntimeGraph to WorkflowRun fields."""

from __future__ import annotations

from agentos.core.acg.enums import NodeType
from agentos.core.acg.nodes import StepNode, parse_node
from agentos.core.models.enums import StepStatus
from agentos.core.models.types import WorkflowRun, WorkflowStep


def project_runtime_graph_to_workflow_steps(run: WorkflowRun) -> list[WorkflowStep]:
    """Build legacy API steps exclusively from the authoritative RuntimeGraph."""

    graph = run.runtime_graph
    if graph is None:
        return list(run.steps)
    projected: list[WorkflowStep] = []
    for runtime_node in graph.nodes:
        if runtime_node.node_type != NodeType.STEP:
            continue
        node = parse_node(runtime_node.spec)
        assert isinstance(node, StepNode)
        attempt = runtime_node.attempts[-1] if runtime_node.attempts else None
        binding = runtime_node.current_binding or {}
        projected.append(
            WorkflowStep(
                stepId=runtime_node.node_id,
                name=node.name or runtime_node.node_id,
                agentName=str(binding.get("agentName") or node.agent_name or runtime_node.node_id),
                capability=node.capability,
                status=runtime_node.status,
                input=dict(node.input_spec),
                resolvedInput=dict(attempt.resolved_input) if attempt else {},
                outputSpec=dict(node.output_spec),
                output=dict(runtime_node.output),
                error=runtime_node.error,
                retryCount=max(0, len(runtime_node.attempts) - 1),
                attempt=len(runtime_node.attempts),
                maxRetries=node.retry_limit,
                timeout=node.timeout,
                priority=node.priority,
                reviewRequired=node.review_required,
                startedAt=attempt.started_at if attempt else None,
                completedAt=(attempt.ended_at if attempt and runtime_node.status == StepStatus.COMPLETED else None),
            )
        )
    return projected


def refresh_run_execution_projection(run: WorkflowRun) -> None:
    """Refresh every legacy execution field from RuntimeGraph in one direction."""

    graph = run.runtime_graph
    if graph is None:
        return
    run.steps = project_runtime_graph_to_workflow_steps(run)
    run.completed_step_ids = sorted(
        node.node_id
        for node in graph.nodes
        if node.node_type == NodeType.STEP and node.status == StepStatus.COMPLETED
    )
    run.active_step_ids = sorted(
        node.node_id
        for node in graph.nodes
        if node.node_type == NodeType.STEP and node.status == StepStatus.RUNNING
    )
    current = next(
        (
            node.node_id
            for node in graph.nodes
            if node.node_type == NodeType.STEP
            and node.status in {
                StepStatus.RUNNING,
                StepStatus.WAITING_REVIEW,
                StepStatus.RETRYING,
                StepStatus.FAILED,
            }
        ),
        None,
    )
    run.current_step_id = current


__all__ = ["project_runtime_graph_to_workflow_steps", "refresh_run_execution_projection"]

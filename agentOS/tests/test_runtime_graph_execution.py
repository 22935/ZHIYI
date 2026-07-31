"""Execution-authority semantics owned by RuntimeGraph."""

import pytest

from agentos.core.acg import ACGBlueprint, ACGEdge, StepNode
from agentos.core.communication import ContextAssembler
from agentos.core.execution.projection import refresh_run_execution_projection
from agentos.core.models.types import StepStatus, WorkflowRun, WorkflowStep
from agentos.core.runtime_graph import RuntimeAttempt, RuntimeGraph
from agentos.core.workflow.state_machine import InvalidStateTransition, StateMachine


def _graph() -> RuntimeGraph:
    blueprint = ACGBlueprint(
        graphId="execution_graph",
        version=7,
        nodes=[
            StepNode(nodeId="a", name="A", agentName="worker", priority=2),
            StepNode(nodeId="b", name="B", agentName="worker"),
            StepNode(nodeId="c", name="C", agentName="worker"),
        ],
        edges=[
            ACGEdge(edgeId="a_b", sourceId="a", targetId="b"),
            ACGEdge(edgeId="b_c", sourceId="b", targetId="c"),
        ],
    )
    return RuntimeGraph.from_blueprint(run_id="run_1", blueprint=blueprint)


def _run(graph: RuntimeGraph) -> WorkflowRun:
    return WorkflowRun(
        runId="run_1",
        taskId="task_1",
        workflowId="workflow_1",
        domain="test",
        runtimeEngine="acg",
        runtimeGraph=graph,
        steps=[WorkflowStep(stepId="legacy", name="Legacy", agentName="legacy")],
        completedStepIds=["invented"],
    )


def test_ready_set_uses_runtime_node_status_not_legacy_completed_ids():
    graph = _graph()
    run = _run(graph)
    assert [node.node_id for node in graph.ready_set()] == ["a"]
    run.completed_step_ids = ["a", "b", "c"]
    assert [node.node_id for node in graph.ready_set()] == ["a"]


def test_dependency_completion_and_retrying_control_ready_set():
    graph = _graph()
    graph.get_node("a").status = StepStatus.COMPLETED
    assert [node.node_id for node in graph.ready_set()] == ["b"]
    graph.get_node("b").status = StepStatus.RUNNING
    assert graph.ready_set() == []
    graph.get_node("b").status = StepStatus.RETRYING
    assert [node.node_id for node in graph.ready_set()] == ["b"]


@pytest.mark.parametrize(
    "status",
    [StepStatus.RUNNING, StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED],
)
def test_non_runnable_statuses_never_enter_ready_set(status):
    graph = _graph()
    graph.get_node("a").status = status
    assert "a" not in {node.node_id for node in graph.ready_set()}


def test_terminal_and_deadlock_predicates_are_graph_owned():
    graph = _graph()
    assert not graph.is_terminal()
    graph.get_node("a").status = StepStatus.FAILED
    assert not graph.has_runnable_nodes()
    assert not graph.has_running_nodes()
    assert not graph.has_waiting_review()
    for node_id in ("b", "c"):
        graph.get_node(node_id).status = StepStatus.CANCELLED
    assert graph.is_terminal()


def test_projection_copies_output_attempt_and_derived_sets_one_way():
    graph = _graph()
    node = graph.get_node("a")
    node.status = StepStatus.COMPLETED
    node.output = {"answer": 42}
    node.output_version = 1
    node.attempts.append(
        RuntimeAttempt(
            attemptId="attempt_1",
            attemptNumber=1,
            graphVersion=graph.graph_version,
            bindingId="worker",
            agentName="worker",
            status=StepStatus.COMPLETED,
            resolvedInput={"question": "life"},
            output={"answer": 42},
        )
    )
    run = _run(graph)
    refresh_run_execution_projection(run)
    projected = run.get_step("a")
    assert projected.output == {"answer": 42}
    assert projected.resolved_input == {"question": "life"}
    assert projected.attempt == 1
    assert run.completed_step_ids == ["a"]
    assert run.active_step_ids == []

    projected.status = StepStatus.CANCELLED
    projected.output = {"tampered": True}
    assert graph.get_node("a").status == StepStatus.COMPLETED
    assert graph.get_node("a").output == {"answer": 42}


def test_step_state_machine_rejects_terminal_and_failed_shortcuts():
    machine = StateMachine()
    with pytest.raises(InvalidStateTransition):
        machine.transition(StepStatus.FAILED, StepStatus.COMPLETED)
    with pytest.raises(InvalidStateTransition):
        machine.transition(StepStatus.CANCELLED, StepStatus.RUNNING)
    with pytest.raises(InvalidStateTransition):
        machine.transition(StepStatus.COMPLETED, StepStatus.RUNNING)


def test_attempts_are_append_only_and_do_not_change_graph_version():
    graph = _graph()
    node = graph.get_node("a")
    for number, status in ((1, StepStatus.FAILED), (2, StepStatus.COMPLETED)):
        node.attempts.append(
            RuntimeAttempt(
                attemptId=f"attempt_{number}",
                attemptNumber=number,
                graphVersion=graph.graph_version,
                bindingId="worker",
                status=status,
            )
        )
    node.status = StepStatus.COMPLETED
    assert [attempt.status for attempt in node.attempts] == [StepStatus.FAILED, StepStatus.COMPLETED]
    assert graph.graph_version == 1


def test_context_pack_carries_runtime_graph_and_attempt_identity():
    graph = _graph()
    graph.get_node("a").status = StepStatus.COMPLETED
    graph.get_node("a").output = {"value": 7}
    step_node = StepNode.model_validate(graph.get_node("b").spec)
    pack = ContextAssembler().assemble(
        run_id=graph.run_id,
        runtime_graph=graph,
        step_node=step_node,
        objective="execute",
        upstream_outputs={"a": {"value": 7}},
        attempt=2,
        attempt_id="attempt_2",
        binding_id="worker",
    )
    assert pack.data == {"value": 7}
    assert pack.graph_version == 1
    assert pack.attempt_id == "attempt_2"
    assert pack.binding_id == "worker"
    assert len(pack.input_revision) == 64

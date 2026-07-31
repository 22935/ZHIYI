from copy import deepcopy

import pytest

from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.models.types import (
    AgentTask,
    StepStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepDefinition,
)
from agentos.core.workflow.progress import (
    ProgressAssembler,
    ProgressCalculator,
    WorkflowProgressPhase,
)
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.workflow.task_manager import TaskManager
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from agentos.core.runtime_graph import RuntimeGraph


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflowId="legal_contract_review_v1",
        name="Legal Contract Review",
        domain="legal",
        intent="contract_review",
        runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(stepId="risk", name="Risk", agentName="risk"),
            WorkflowStepDefinition(stepId="review", name="Review", agentName="review", reviewRequired=True),
            WorkflowStepDefinition(stepId="draft", name="Draft", agentName="draft"),
        ],
    )


def _step(step_id: str, status: StepStatus, *, name: str | None = None) -> WorkflowStep:
    return WorkflowStep(
        stepId=step_id,
        name=name or step_id.replace("_", " ").title(),
        agentName=f"{step_id}_agent",
        status=status,
    )


def _run(
    status: WorkflowStatus,
    step_statuses: list[StepStatus],
    *,
    active_step_ids: list[str] | None = None,
    current_step_id: str | None = None,
    recovery_count: int = 0,
    with_blueprint: bool = False,
) -> WorkflowRun:
    steps = [_step(f"step_{index + 1}", step_status) for index, step_status in enumerate(step_statuses)]
    return WorkflowRun(
        taskId="task_progress",
        workflowId="workflow_progress",
        domain="legal",
        runtimeEngine="acg",
        status=status,
        currentStepId=current_step_id,
        steps=steps,
        activeStepIds=active_step_ids or [],
        recoveryCount=recovery_count,
        acgBlueprint={"nodes": [], "edges": []} if with_blueprint else None,
    )


def test_empty_run_projects_understanding_with_unknown_percent():
    run = _run(WorkflowStatus.PENDING, [])

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.UNDERSTANDING
    assert progress.percent is None
    assert progress.total_steps == 0
    assert progress.active_step_ids == []
    assert progress.started_at is None
    assert progress.updated_at == run.updated_at


def test_explicit_planning_phase_has_unknown_percent():
    run = _run(WorkflowStatus.PENDING, [])

    progress = ProgressAssembler().assemble(
        run,
        explicit_phase=WorkflowProgressPhase.PLANNING,
        phase_message="Planning override",
    )

    assert progress.phase == WorkflowProgressPhase.PLANNING
    assert progress.message == "Planning override"
    assert progress.percent is None
    assert progress.total_steps == 0


def test_explicit_graph_building_phase_has_unknown_percent():
    run = _run(WorkflowStatus.RUNNING, [StepStatus.PENDING, StepStatus.PENDING])

    progress = ProgressAssembler().assemble(run, explicit_phase=WorkflowProgressPhase.GRAPH_BUILDING)

    assert progress.phase == WorkflowProgressPhase.GRAPH_BUILDING
    assert progress.percent is None
    assert progress.total_steps == 2


def test_normal_execution_uses_completed_steps_only():
    run = _run(
        WorkflowStatus.RUNNING,
        [StepStatus.COMPLETED, StepStatus.COMPLETED, StepStatus.RUNNING, StepStatus.PENDING],
        active_step_ids=["step_3"],
        current_step_id="step_3",
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.EXECUTING
    assert progress.total_steps == 4
    assert progress.completed_steps == 2
    assert progress.running_steps == 1
    assert progress.pending_steps == 1
    assert progress.percent == pytest.approx(50.0)
    assert progress.current_step_id == "step_3"
    assert progress.message == "正在执行 ACG 步骤：Step 3"


def test_runtime_patch_expands_progress_total_and_reports_graph_metadata():
    run = _run(
        WorkflowStatus.RUNNING,
        [
            StepStatus.COMPLETED,
            StepStatus.COMPLETED,
            StepStatus.RETRYING,
            StepStatus.PENDING,
            StepStatus.PENDING,
        ],
    )
    blueprint = ACGBlueprint(
        graphId="progress_graph",
        nodes=[StepNode(nodeId=f"step_{index}") for index in range(1, 6)],
    )
    graph = RuntimeGraph.from_blueprint(run_id=run.run_id, blueprint=blueprint)
    graph.graph_version = 2
    graph.nodes[-2].created_graph_version = 2
    graph.nodes[-1].created_graph_version = 2
    run.runtime_graph = graph

    progress = ProgressAssembler().assemble(run)

    assert progress.total_steps == 5
    assert progress.percent == pytest.approx(40.0)
    assert progress.graph_version == 2
    assert progress.dynamic_step_count == 2


def test_parallel_active_steps_preserve_run_order_then_definition_order():
    run = _run(
        WorkflowStatus.RUNNING,
        [StepStatus.PENDING, StepStatus.RUNNING, StepStatus.RUNNING, StepStatus.WAITING_REVIEW],
        active_step_ids=["step_3"],
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.active_step_ids == ["step_3", "step_2", "step_4"]
    assert progress.current_step_id == "step_3"


def test_waiting_review_does_not_increase_completed_progress():
    run = _run(
        WorkflowStatus.WAITING_REVIEW,
        [StepStatus.COMPLETED, StepStatus.COMPLETED, StepStatus.WAITING_REVIEW, StepStatus.PENDING],
        current_step_id="step_3",
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.REVIEW
    assert progress.completed_steps == 2
    assert progress.waiting_review_steps == 1
    assert progress.percent == pytest.approx(50.0)
    assert progress.active_step_ids == ["step_3"]


def test_retrying_step_projects_recovery_without_increasing_percent():
    run = _run(
        WorkflowStatus.RETRYING,
        [StepStatus.COMPLETED, StepStatus.RETRYING, StepStatus.PENDING, StepStatus.PENDING],
        current_step_id="step_2",
        recovery_count=2,
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.RECOVERY
    assert progress.recovery_count == 2
    assert progress.retrying_steps == 1
    assert progress.percent == pytest.approx(25.0)
    assert progress.active_step_ids == ["step_2"]


def test_completed_run_is_always_one_hundred_percent():
    run = _run(
        WorkflowStatus.COMPLETED,
        [StepStatus.COMPLETED, StepStatus.COMPLETED, StepStatus.FAILED],
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.COMPLETED
    assert progress.percent == pytest.approx(100.0)


def test_failed_run_preserves_actual_completion_ratio():
    run = _run(
        WorkflowStatus.FAILED,
        [StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.PENDING, StepStatus.PENDING],
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.FAILED
    assert progress.percent == pytest.approx(25.0)


def test_cancelled_run_is_distinct_and_preserves_actual_completion_ratio():
    run = _run(
        WorkflowStatus.CANCELLED,
        [StepStatus.COMPLETED, StepStatus.COMPLETED, StepStatus.CANCELLED, StepStatus.PENDING],
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.CANCELLED
    assert progress.percent == pytest.approx(50.0)


def test_compatibility_fields_and_alias_serialization_are_preserved():
    run = _run(
        WorkflowStatus.RUNNING,
        [StepStatus.COMPLETED, StepStatus.RUNNING],
        active_step_ids=["step_2"],
    )

    progress = ProgressAssembler().assemble(run)
    payload = progress.model_dump(by_alias=True, mode="json")

    assert progress.progress == pytest.approx(0.5)
    assert progress.percentage == pytest.approx(50.0)
    assert payload["percent"] == pytest.approx(50.0)
    assert payload["progress"] == pytest.approx(0.5)
    assert payload["percentage"] == pytest.approx(50.0)
    assert payload["activeStepIds"] == ["step_2"]
    assert payload["phase"] == "executing"


def test_projection_is_deterministic_and_does_not_mutate_run():
    run = _run(
        WorkflowStatus.RUNNING,
        [StepStatus.COMPLETED, StepStatus.RUNNING, StepStatus.PENDING],
        active_step_ids=["step_2"],
        current_step_id="step_2",
        recovery_count=1,
        with_blueprint=True,
    )
    before = deepcopy(run.model_dump(by_alias=True, mode="python"))
    assembler = ProgressAssembler()

    first = assembler.assemble(run)
    second = assembler.assemble(run)

    assert first == second
    assert run.model_dump(by_alias=True, mode="python") == before


def test_progress_calculator_keeps_task_manager_compatibility():
    registry = WorkflowRegistry()
    workflow = _workflow()
    registry.register(workflow)
    manager = TaskManager(workflow_store=MemoryWorkflowStore(), workflow_registry=registry)
    task = manager.create_task(title="Contract review", domain="legal", intent="contract_review")

    progress = manager.calculate_progress(task)

    assert progress.task_id == task.task_id
    assert progress.workflow_id == workflow.workflow_id
    assert progress.phase == WorkflowProgressPhase.UNDERSTANDING
    assert progress.percent is None
    assert progress.total_steps == 3
    assert progress.pending_steps == 3
    assert progress.completed_steps == 0
    assert progress.progress == 0.0
    assert progress.percentage == 0.0


def test_progress_calculator_delegates_run_projection_to_assembler():
    task = AgentTask(title="Contract review", domain="legal", intent="contract_review")
    run = _run(
        WorkflowStatus.WAITING_REVIEW,
        [StepStatus.COMPLETED, StepStatus.WAITING_REVIEW, StepStatus.PENDING],
        current_step_id="step_2",
    )

    progress = ProgressCalculator().calculate(task=task, run=run, workflow=_workflow())

    assert progress.run_id == run.run_id
    assert progress.phase == WorkflowProgressPhase.REVIEW
    assert progress.percent == pytest.approx(33.33)
    assert progress.progress == pytest.approx(0.3333)
    assert progress.percentage == pytest.approx(33.33)

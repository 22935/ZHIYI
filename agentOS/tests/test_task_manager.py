import pytest

from agentos.core.models.types import WorkflowDefinition, WorkflowStepDefinition, WorkflowStatus
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.workflow.state_machine import InvalidStateTransition
from agentos.core.workflow.task_manager import TaskManager
from agentos.stores.memory_workflow_store import MemoryWorkflowStore


def _workflow_registry() -> WorkflowRegistry:
    registry = WorkflowRegistry() # 获取工作流
    registry.register(
        WorkflowDefinition(
            workflowId="legal_contract_review_v1",
            name="TestWorkflow",
            domain="legal",
            intent="contract_review",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="risk",
                    name="Risk Review",
                    agentName="risk",
                )
            ],
        )
    )
    registry.register(
        WorkflowDefinition(
            workflowId="education_lesson_plan_v1",
            name="Education Lesson Plan",
            domain="education",
            intent="lesson_plan",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="plan",
                    name="Plan Lesson",
                    agentName="planner",
                )
            ],
        )
    )
    return registry


def _task_manager() -> tuple[TaskManager, MemoryWorkflowStore]:
    store = MemoryWorkflowStore()
    return TaskManager(workflow_store=store, workflow_registry=_workflow_registry()), store


def test_create_task_ignores_blank_role_and_task_aliases_when_domain_and_intent_are_present():
    manager, store = _task_manager()

    task = manager.create_task(
        title="合同审查",
        domain="legal",
        intent="contract_review",
        role_type="   ",
        task_type="",
        input={"source": "workbench"},
    )

    assert task.domain == "legal"
    assert task.intent == "contract_review"
    assert task.recommended_workflow == "legal_contract_review_v1"
    assert store.get_task(task.task_id).recommended_workflow == "legal_contract_review_v1"


def test_create_task_prefers_nonblank_role_and_task_aliases_over_domain_and_intent():
    manager, _ = _task_manager()

    task = manager.create_task(
        title="课程设计",
        domain="legal",
        intent="contract_review",
        role_type="education",
        task_type="lesson_plan",
    )

    assert task.domain == "education"
    assert task.intent == "lesson_plan"
    assert task.recommended_workflow == "education_lesson_plan_v1"


def test_bind_workflow_updates_task_recommendation_when_task_was_created_without_match():
    manager, store = _task_manager()
    task = manager.create_task(title="待分配任务", domain="general", intent="general")

    workflow = manager.bind_workflow(task.task_id, workflow_id="legal_contract_review_v1")

    assert workflow.workflow_id == "legal_contract_review_v1"
    assert store.get_task(task.task_id).recommended_workflow == "legal_contract_review_v1"


def test_list_tasks_filters_by_status_domain_source_and_paginates():
    manager, _ = _task_manager()
    first = manager.create_task(
        title="合同审查 1",
        domain="legal",
        intent="contract_review",
        input={"source": "workbench"},
    )
    second = manager.create_task(
        title="合同审查 2",
        domain="legal",
        intent="contract_review",
        input={"source": "workbench"},
    )
    manager.create_task(
        title="课程设计",
        domain="education",
        intent="lesson_plan",
        input={"source": "workbench"},
    )
    manager.mark_running(first.task_id)
    manager.mark_running(second.task_id)

    page = manager.list_tasks(
        status=WorkflowStatus.RUNNING,
        domain="legal",
        source="workbench",
        page=1,
        page_size=1,
    )

    assert page.total == 2
    assert page.page == 1
    assert page.page_size == 1
    assert len(page.items) == 1
    assert page.items[0].domain == "legal"
    assert page.items[0].status == WorkflowStatus.RUNNING


def test_transition_rejects_invalid_task_lifecycle_jump():
    manager, _ = _task_manager()
    task = manager.create_task(title="合同审查", domain="legal", intent="contract_review")

    manager.mark_running(task.task_id)
    manager.mark_completed(task.task_id)

    with pytest.raises(InvalidStateTransition):
        manager.mark_running(task.task_id)

"""Task Manager 任务创建、状态流转、取消同步和 roleType/taskType 入参兼容测试。"""


import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.agents.base import AgentOutput, AgentProfile, AgentRunContext, BaseAgent
from agentos.agents import AgentRegistry
from agentos.core.workflow.state_machine import InvalidStateTransition
from agentos.core.workflow.task_manager import TaskManager
from agentos.core.models.types import WorkflowDefinition, WorkflowStatus, WorkflowStepDefinition
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.runtime import WorkflowRuntime
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from app.api.agentos_core import create_router


class EchoAgent(BaseAgent):
    def __init__(self, name: str):
        super().__init__(
            AgentProfile(
                agentName=name,
                domain="legal",
                capabilities=[name],
                allowedSkills=[],
            )
        )

    async def run(self, context: AgentRunContext) -> AgentOutput:
        return AgentOutput(output={"final_answer": f"{context.step.step_id} done"}, summary="done")


def _workflow_registry() -> WorkflowRegistry:
    registry = WorkflowRegistry()
    registry.register(
        WorkflowDefinition(
            workflowId="legal_contract_review_v1",
            name="Legal Contract Review",
            domain="legal",
            intent="contract_review",
            version="1.0.0",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="risk",
                    name="Risk",
                    agentName="risk",
                    reviewRequired=True,
                )
            ],
        )
    )
    return registry


def test_task_manager_creates_task_and_recommends_workflow_from_role_and_task_type():
    store = MemoryWorkflowStore()
    registry = _workflow_registry()
    manager = TaskManager(workflow_store=store, workflow_registry=registry)

    task = manager.create_task(
        title="合同审查",
        role_type="legal",
        task_type="contract_review",
        input={"caseText": "合同逾期交付"},
    )

    assert task.domain == "legal"
    assert task.intent == "contract_review"
    assert task.recommended_workflow == "legal_contract_review_v1"
    assert store.get_task(task.task_id).recommended_workflow == "legal_contract_review_v1"


def test_task_manager_updates_task_state_through_valid_lifecycle_and_rejects_invalid_jumps():
    store = MemoryWorkflowStore()
    registry = _workflow_registry()
    manager = TaskManager(workflow_store=store, workflow_registry=registry)

    task = manager.create_task(title="合同审查", domain="legal", intent="contract_review")

    manager.mark_running(task.task_id)
    assert store.get_task(task.task_id).status == WorkflowStatus.RUNNING

    manager.mark_waiting_review(task.task_id)
    assert store.get_task(task.task_id).status == WorkflowStatus.WAITING_REVIEW

    manager.mark_completed(task.task_id)
    assert store.get_task(task.task_id).status == WorkflowStatus.COMPLETED

    with pytest.raises(InvalidStateTransition):
        manager.mark_running(task.task_id)


def test_runtime_cancelling_run_marks_task_cancelled():
    asyncio.run(_test_runtime_cancelling_run_marks_task_cancelled())


async def _test_runtime_cancelling_run_marks_task_cancelled():
    agent_registry = AgentRegistry()
    agent_registry.register(EchoAgent("risk"))

    workflow_registry = _workflow_registry()
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    task = runtime.create_task(
        title="合同审查",
        domain="legal",
        intent="contract_review",
        input={"caseText": "需要人工终审"},
    )

    run = await runtime.start(task.task_id, workflow_id="legal_contract_review_v1", review_mode="human_in_loop")

    assert run.status == WorkflowStatus.WAITING_REVIEW

    cancelled = runtime.cancel(run.run_id)

    assert cancelled.status == WorkflowStatus.CANCELLED
    assert runtime.workflow_store.get_task(task.task_id).status == WorkflowStatus.CANCELLED


def test_core_tasks_route_accepts_role_type_and_task_type_aliases():
    agent_registry = AgentRegistry()
    workflow_registry = _workflow_registry()
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/core/tasks",
        json={
            "title": "合同审查",
            "roleType": "legal",
            "taskType": "contract_review",
            "input": {"caseText": "合同逾期交付"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] == "legal"
    assert payload["intent"] == "contract_review"
    assert payload["recommendedWorkflow"] == "legal_contract_review_v1"

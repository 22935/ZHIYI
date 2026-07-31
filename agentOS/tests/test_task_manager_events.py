import pytest

from agentos.agents.base import AgentOutput, AgentProfile, AgentRunContext, BaseAgent
from agentos.agents.registry import AgentRegistry
from agentos.core.governance.trace import TraceStore
from agentos.core.models.types import (
    ReviewDecision,
    ReviewDecisionType,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.workflow.state_machine import InvalidStateTransition
from agentos.core.workflow.task_manager import TaskManager
from agentos.stores.memory_workflow_store import MemoryWorkflowStore


class EchoAgent(BaseAgent):
    def __init__(self, name: str):
        super().__init__(
            AgentProfile(
                agentName=name,
                domain="legal",
                capabilities=[name],
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


def test_task_manager_records_creation_and_status_change_events():
    trace_store = TraceStore()
    manager = TaskManager(
        workflow_store=MemoryWorkflowStore(),
        workflow_registry=_workflow_registry(),
        trace_store=trace_store,
    )

    task = manager.create_task(title="合同审查", domain="legal", intent="contract_review")
    manager.mark_running(task.task_id)

    events = trace_store.task_events(task.task_id)

    assert [event.event_type for event in events] == [
        TraceEventType.TASK_CREATED,
        TraceEventType.TASK_STATUS_CHANGED,
    ]
    assert events[0].payload["taskId"] == task.task_id
    assert events[1].payload == {
        "fromStatus": WorkflowStatus.PENDING.value,
        "toStatus": WorkflowStatus.RUNNING.value,
    }


def test_task_manager_records_event_for_invalid_transition_before_raising():
    trace_store = TraceStore()
    manager = TaskManager(
        workflow_store=MemoryWorkflowStore(),
        workflow_registry=_workflow_registry(),
        trace_store=trace_store,
    )
    task = manager.create_task(title="合同审查", domain="legal", intent="contract_review")
    manager.mark_running(task.task_id)
    manager.mark_completed(task.task_id)

    with pytest.raises(InvalidStateTransition):
        manager.mark_running(task.task_id)

    events = trace_store.task_events(task.task_id)

    assert events[-1].event_type == TraceEventType.TASK_ERROR
    assert events[-1].payload["fromStatus"] == WorkflowStatus.COMPLETED.value
    assert events[-1].payload["toStatus"] == WorkflowStatus.RUNNING.value


async def test_runtime_uses_state_machine_for_review_wait_and_approval_flow():
    trace_store = TraceStore()
    agent_registry = AgentRegistry()
    agent_registry.register(EchoAgent("risk"))
    runtime = WorkflowRuntime(
        agent_registry=agent_registry,
        workflow_registry=_workflow_registry(),
        trace_store=trace_store,
    )
    task = runtime.create_task(title="合同审查", domain="legal", intent="contract_review")

    run = await runtime.start(task.task_id, review_mode="human_in_loop")

    assert run.status == WorkflowStatus.WAITING_REVIEW
    assert run.steps[0].status == StepStatus.WAITING_REVIEW

    approved = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="risk",
            decision=ReviewDecisionType.APPROVED,
            reviewer="tester",
        )
    )

    assert approved.status == WorkflowStatus.COMPLETED
    assert approved.steps[0].status == StepStatus.COMPLETED
    assert [event.event_type for event in trace_store.task_events(task.task_id)] == [
        TraceEventType.TASK_CREATED,
        TraceEventType.TASK_STATUS_CHANGED,
        TraceEventType.TASK_STATUS_CHANGED,
        TraceEventType.TASK_STATUS_CHANGED,
        TraceEventType.TASK_STATUS_CHANGED,
    ]

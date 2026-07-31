import asyncio
from datetime import datetime, timezone
from threading import Event
from time import perf_counter

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.execution import RunExecutionCoordinator
from agentos.core.execution.projection import refresh_run_execution_projection
from agentos.core.conditions import BranchDecision
from agentos.core.models.enums import WorkflowProgressPhase
from agentos.core.models.types import (
    StepStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepDefinition,
)
from agentos.core.runtime import WorkflowRuntime
from agentos.core.runtime_graph import RuntimeGraph
from agentos.core.workflow.progress import ProgressAssembler
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from app.api.agentos_core import create_router
from app.security.internal_auth import InternalServiceAuthMiddleware


class _CountingStore(MemoryWorkflowStore):
    def __init__(self):
        super().__init__()
        self.get_run_calls = 0
        self.save_run_calls = 0

    def get_run(self, run_id):
        self.get_run_calls += 1
        return super().get_run(run_id)

    def save_run(self, run):
        self.save_run_calls += 1
        super().save_run(run)


class _Agent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="worker",
                domain="test",
                capabilities=["work"],
                allowedSkills=[],
            )
        )

    async def run(self, context):
        return AgentOutput(output={"done": True}, summary="done")


def _runtime(store=None):
    agents = AgentRegistry()
    agents.register(_Agent())
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="progress_test_v1",
            name="Progress test",
            domain="test",
            intent="work",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="work",
                    name="Work",
                    agentName="worker",
                    capability="work",
                )
            ],
        )
    )
    return WorkflowRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=store or MemoryWorkflowStore(),
    )


def _client(runtime, coordinator=None):
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator), prefix="/ai")
    return TestClient(app)


def _step(index, status):
    return WorkflowStep(
        stepId=f"step_{index}",
        name=f"Step {index}",
        agentName="worker",
        status=status,
    )


def _save_run(
    runtime,
    *,
    status=WorkflowStatus.PENDING,
    phase=WorkflowProgressPhase.UNDERSTANDING,
    steps=None,
    current_step_id=None,
    active_step_ids=None,
    recovery_count=0,
    message=None,
):
    run = WorkflowRun(
        taskId="task_progress_api",
        workflowId="progress_test_v1",
        domain="test",
        runtimeEngine="acg",
        status=status,
        lifecyclePhase=phase,
        lifecycleMessage=message or f"phase:{phase.value}",
        currentStepId=current_step_id,
        activeStepIds=active_step_ids or [],
        recoveryCount=recovery_count,
        steps=steps or [],
        startedAt=(
            datetime(2026, 7, 22, 1, 6, 26, tzinfo=timezone.utc)
            if phase != WorkflowProgressPhase.UNDERSTANDING
            else None
        ),
        updatedAt=datetime(2026, 7, 22, 1, 7, 20, tzinfo=timezone.utc),
    )
    runtime.workflow_store.save_run(run)
    return run


def test_unknown_run_returns_404_and_store_failure_returns_503():
    runtime = _runtime()
    client = _client(runtime)

    assert client.get("/ai/core/workflows/runs/run_unknown/progress").status_code == 404

    runtime.get_status = lambda run_id: (_ for _ in ()).throw(RuntimeError("database offline"))
    response = client.get("/ai/core/workflows/runs/run_any/progress")
    assert response.status_code == 503
    assert response.json()["detail"] == "workflow progress is temporarily unavailable"


@pytest.mark.parametrize(
    (
        "status",
        "phase",
        "statuses",
        "expected_message",
        "expected_percent",
        "expected_completed",
    ),
    [
        (
            WorkflowStatus.PENDING,
            WorkflowProgressPhase.UNDERSTANDING,
            [],
            "Safe lifecycle message",
            None,
            0,
        ),
        (
            WorkflowStatus.RUNNING,
            WorkflowProgressPhase.PLANNING,
            [],
            "Safe lifecycle message",
            None,
            0,
        ),
        (
            WorkflowStatus.RUNNING,
            WorkflowProgressPhase.GRAPH_BUILDING,
            [],
            "Safe lifecycle message",
            None,
            0,
        ),
        (
            WorkflowStatus.RUNNING,
            WorkflowProgressPhase.EXECUTING,
            [StepStatus.COMPLETED, StepStatus.COMPLETED, StepStatus.RUNNING, StepStatus.PENDING],
            "正在执行 ACG 步骤：Step 2",
            50.0,
            2,
        ),
        (
            WorkflowStatus.WAITING_REVIEW,
            WorkflowProgressPhase.REVIEW,
            [StepStatus.COMPLETED, StepStatus.COMPLETED, StepStatus.WAITING_REVIEW, StepStatus.PENDING],
            "正在等待步骤审核：Step 2",
            50.0,
            2,
        ),
        (
            WorkflowStatus.RETRYING,
            WorkflowProgressPhase.RECOVERY,
            [StepStatus.COMPLETED, StepStatus.RETRYING, StepStatus.PENDING, StepStatus.PENDING],
            "正在恢复 ACG 步骤：Step 1",
            25.0,
            1,
        ),
        (
            WorkflowStatus.COMPLETED,
            WorkflowProgressPhase.COMPLETED,
            [StepStatus.COMPLETED, StepStatus.COMPLETED],
            "Safe lifecycle message",
            100.0,
            2,
        ),
        (
            WorkflowStatus.FAILED,
            WorkflowProgressPhase.FAILED,
            [StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.PENDING, StepStatus.PENDING],
            "Safe lifecycle message",
            25.0,
            1,
        ),
        (
            WorkflowStatus.CANCELLED,
            WorkflowProgressPhase.CANCELLED,
            [StepStatus.COMPLETED, StepStatus.CANCELLED, StepStatus.PENDING, StepStatus.PENDING],
            "Safe lifecycle message",
            25.0,
            1,
        ),
    ],
)
def test_progress_contract_for_every_phase(
    status,
    phase,
    statuses,
    expected_message,
    expected_percent,
    expected_completed,
):
    runtime = _runtime()
    steps = [_step(index, step_status) for index, step_status in enumerate(statuses)]
    active = [step.step_id for step in steps if step.status in {
        StepStatus.RUNNING,
        StepStatus.RETRYING,
        StepStatus.WAITING_REVIEW,
    }]
    run = _save_run(
        runtime,
        status=status,
        phase=phase,
        steps=steps,
        current_step_id=active[0] if active else None,
        active_step_ids=active,
        recovery_count=2 if phase == WorkflowProgressPhase.RECOVERY else 0,
        message="Safe lifecycle message",
    )

    response = _client(runtime).get(f"/ai/core/workflows/runs/{run.run_id}/progress")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == status.value
    assert payload["phase"] == phase.value
    assert payload["message"] == expected_message
    assert payload["percent"] == expected_percent
    assert payload["completedSteps"] == expected_completed
    assert payload["totalSteps"] == len(statuses)
    assert payload["recoveryCount"] == (2 if phase == WorkflowProgressPhase.RECOVERY else 0)
    assert payload["activeStepIds"] == active
    if expected_percent is None:
        assert payload["progress"] == 0.0
        assert payload["percentage"] == 0.0
    else:
        assert payload["percentage"] == expected_percent
    assert payload["updatedAt"] == "2026-07-22T01:07:20Z"


def test_progress_api_exposes_runtime_graph_version_and_dynamic_step_count():
    runtime = _runtime()
    run = _save_run(
        runtime,
        status=WorkflowStatus.RUNNING,
        phase=WorkflowProgressPhase.RECOVERY,
        steps=[_step(1, StepStatus.COMPLETED), _step(2, StepStatus.RETRYING)],
    )
    blueprint = ACGBlueprint(
        graphId="progress_api_graph",
        nodes=[StepNode(nodeId="step_1"), StepNode(nodeId="step_2")],
    )
    graph = RuntimeGraph.from_blueprint(run_id=run.run_id, blueprint=blueprint)
    graph.graph_version = 2
    graph.nodes[0].status = StepStatus.COMPLETED
    graph.nodes[-1].created_graph_version = 2
    graph.nodes[-1].binding_switch_count = 1
    graph.nodes[-1].status = StepStatus.SKIPPED_BY_CONDITION
    graph.branch_decisions = [
        BranchDecision(
            decisionId="decision_progress",
            controlNodeId="route",
            sourceNodeId="step_1",
            sourceOutputVersion=1,
            inputHash="hash",
            selectedCaseKey="high",
            selectedEdgeIds=["high"],
            terminatedEdgeIds=["low"],
            skippedNodeIds=["step_2"],
            joinNodeId="join",
            sourceEventId="condition_progress",
            sourcePatchId="patch_progress",
            decidedAtGraphVersion=2,
        )
    ]
    run.runtime_graph = graph
    refresh_run_execution_projection(run)
    runtime.workflow_store.save_run(run)

    payload = _client(runtime).get(
        f"/ai/core/workflows/runs/{run.run_id}/progress"
    ).json()

    assert payload["graphVersion"] == 2
    assert payload["dynamicStepCount"] == 1
    assert payload["bindingSwitchCount"] == 1
    assert payload["skippedByConditionCount"] == 1
    assert payload["conditionalDecisionCount"] == 1
    assert payload["percent"] == 100.0
    assert payload["totalSteps"] == 2


def test_repeated_progress_query_is_read_only_and_stable():
    store = _CountingStore()
    runtime = _runtime(store)
    run = _save_run(
        runtime,
        status=WorkflowStatus.RUNNING,
        phase=WorkflowProgressPhase.PLANNING,
        message="Planning safely",
    )
    client = _client(runtime)
    saves_before = store.save_run_calls

    first = client.get(f"/ai/core/workflows/runs/{run.run_id}/progress")
    second = client.get(f"/ai/core/workflows/runs/{run.run_id}/progress")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["percent"] is None
    assert first.json()["message"] == "Planning safely"
    assert store.save_run_calls == saves_before
    assert store.get_run_calls == 2


def test_progress_rejects_a_different_owner_without_revealing_run():
    runtime = _runtime()
    run = WorkflowRun(
        taskId="task_owned",
        workflowId="progress_test_v1",
        domain="test",
        runtimeEngine="acg",
        input={"authenticatedUserId": "user-a", "authenticatedTenantId": "tenant-a"},
        lifecyclePhase="understanding",
    )
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.add_middleware(
        InternalServiceAuthMiddleware,
        token="0123456789abcdef0123456789abcdef",
    )
    app.include_router(create_router(runtime), prefix="/ai")
    headers = {
        "X-Internal-Service-Token": "0123456789abcdef0123456789abcdef",
        "X-Authenticated-User-Id": "user-b",
        "X-Authenticated-User-Subject": "bob",
        "X-Authenticated-User-Role": "USER",
        "X-Authenticated-Tenant-Id": "tenant-a",
    }

    response = TestClient(app).get(
        f"/ai/core/workflows/runs/{run.run_id}/progress",
        headers=headers,
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_progress_is_available_while_planner_is_blocked():
    runtime = _runtime()
    coordinator = RunExecutionCoordinator(runtime)
    entered = Event()
    release = Event()
    original = runtime._build_acg_blueprint

    def blocking(*args, **kwargs):
        entered.set()
        release.wait(timeout=3)
        return original(*args, **kwargs)

    runtime._build_acg_blueprint = blocking
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator), prefix="/ai")
    with TestClient(app) as client:
        start = client.post(
            "/ai/core/workflows/start-async",
            json={
                "title": "Blocked planner",
                "domain": "test",
                "intent": "work",
                "workflowId": "progress_test_v1",
                "clientRequestId": "progress-immediate",
            },
        )
        assert start.status_code == 202
        run_id = start.json()["run"]["runId"]
        assert entered.wait(timeout=0.5)

        progress = client.get(f"/ai/core/workflows/runs/{run_id}/progress")

        assert progress.status_code == 200
        assert progress.json()["phase"] == "planning"
        assert progress.json()["percent"] is None
        release.set()
        for _ in range(100):
            latest = client.get(f"/ai/core/workflows/runs/{run_id}").json()
            if latest["status"] == "completed":
                break
            asyncio.run(asyncio.sleep(0.01))
        assert latest["status"] == "completed"


def test_1000_step_progress_is_single_read_linear_projection():
    store = _CountingStore()
    runtime = _runtime(store)
    steps = [
        _step(index, StepStatus.COMPLETED if index < 500 else StepStatus.PENDING)
        for index in range(1000)
    ]
    run = _save_run(
        runtime,
        status=WorkflowStatus.RUNNING,
        phase=WorkflowProgressPhase.EXECUTING,
        steps=steps,
    )
    client = _client(runtime)
    projection_started = perf_counter()
    projected = ProgressAssembler().assemble(run)
    projection_ms = (perf_counter() - projection_started) * 1000
    store.get_run_calls = 0
    saves_before = store.save_run_calls
    started = perf_counter()

    response = client.get(f"/ai/core/workflows/runs/{run.run_id}/progress")
    elapsed_ms = (perf_counter() - started) * 1000

    assert response.status_code == 200
    assert projected.total_steps == 1000
    assert projected.completed_steps == 500
    assert response.json()["totalSteps"] == 1000
    assert response.json()["completedSteps"] == 500
    assert response.json()["percent"] == 50.0
    assert store.get_run_calls == 1
    assert store.save_run_calls == saves_before
    assert projection_ms < 2000
    assert elapsed_ms < 2000
    print(
        f"1000-step local elapsed: projection={projection_ms:.3f} ms, "
        f"api={elapsed_ms:.3f} ms"
    )

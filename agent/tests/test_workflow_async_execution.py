import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
from threading import Event
from time import monotonic

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.execution import RunExecutionCoordinator
from agentos.core.models.enums import WorkflowProgressPhase
from agentos.core.models.types import (
    AgentTask,
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
from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore
from app.api.agentos_core import create_router
from app.security.internal_auth import InternalServiceAuthMiddleware


class _RecordingStore(MemoryWorkflowStore):
    def __init__(self):
        super().__init__()
        self.lifecycle_writes: list[tuple[str, str | None]] = []
        self.graph_persisted_before_execution = False

    def save_run(self, run):
        super().save_run(run)
        persisted = self.get_run(run.run_id)
        self.lifecycle_writes.append(
            (
                persisted.status.value,
                persisted.lifecycle_phase.value if persisted.lifecycle_phase else None,
            )
        )
        if (
            persisted.lifecycle_phase == WorkflowProgressPhase.GRAPH_BUILDING
            and persisted.acg_blueprint is not None
            and persisted.steps
        ):
            self.graph_persisted_before_execution = True


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


def _step(step_id: str, status: StepStatus) -> WorkflowStep:
    return WorkflowStep(
        stepId=step_id,
        name=step_id,
        agentName="worker",
        status=status,
    )


def _runtime(store=None) -> WorkflowRuntime:
    agents = AgentRegistry()
    agents.register(_Agent())
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="async_test_v1",
            name="Async test",
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


async def _wait_inactive(coordinator: RunExecutionCoordinator, run_id: str) -> None:
    for _ in range(200):
        if not coordinator.is_active(run_id):
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"run remained active: {run_id}")


def test_prepare_run_persists_empty_understanding_run_without_planning():
    runtime = _runtime()
    task = runtime.create_task(title="Prepare", domain="test", intent="work")
    original = runtime._build_acg_blueprint
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    runtime._build_acg_blueprint = counted
    prepared_task, run = runtime.prepare_run(task.task_id)

    persisted = runtime.workflow_store.get_run(run.run_id)
    assert prepared_task.task_id == task.task_id
    assert persisted.status == WorkflowStatus.PENDING
    assert persisted.lifecycle_phase == WorkflowProgressPhase.UNDERSTANDING
    assert persisted.steps == []
    assert persisted.started_at is None
    assert calls == 0


def test_sync_start_reuses_prepare_and_execute_with_real_lifecycle_writes():
    async def scenario():
        store = _RecordingStore()
        runtime = _runtime(store)
        task = runtime.create_task(title="Lifecycle", domain="test", intent="work")

        run = await runtime.start(task.task_id)

        assert run.status == WorkflowStatus.COMPLETED
        assert run.lifecycle_phase == WorkflowProgressPhase.COMPLETED
        assert run.started_at is not None
        assert store.graph_persisted_before_execution is True
        phases = [phase for _, phase in store.lifecycle_writes]
        for expected in [
            "understanding",
            "planning",
            "graph_building",
            "executing",
            "completed",
        ]:
            assert expected in phases
        assert phases.index("understanding") < phases.index("planning")
        assert phases.index("planning") < phases.index("graph_building")
        assert phases.index("graph_building") < phases.index("executing")
        assert phases.index("executing") < phases.index("completed")

    asyncio.run(scenario())


def test_planner_is_thread_isolated_and_duplicate_submit_runs_once():
    async def scenario():
        runtime = _runtime()
        task = runtime.create_task(title="Blocking plan", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        coordinator = RunExecutionCoordinator(runtime)
        entered = Event()
        release = Event()
        calls = 0
        original = runtime._build_acg_blueprint

        def blocking(*args, **kwargs):
            nonlocal calls
            calls += 1
            entered.set()
            release.wait(timeout=2)
            return original(*args, **kwargs)

        runtime._build_acg_blueprint = blocking
        assert await coordinator.submit(run.run_id) is True
        assert await coordinator.submit(run.run_id) is False

        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        ticked = False

        async def tick():
            nonlocal ticked
            await asyncio.sleep(0)
            ticked = True

        await asyncio.wait_for(tick(), timeout=0.1)
        assert ticked is True
        assert runtime.get_status(run.run_id).lifecycle_phase == WorkflowProgressPhase.PLANNING
        release.set()
        await _wait_inactive(coordinator, run.run_id)
        assert calls == 1
        assert runtime.get_status(run.run_id).status == WorkflowStatus.COMPLETED

    asyncio.run(scenario())


def test_planner_failure_is_persisted_and_managed_task_is_cleaned_up():
    async def scenario():
        runtime = _runtime()
        task = runtime.create_task(title="Fail plan", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        coordinator = RunExecutionCoordinator(runtime)

        def fail(*args, **kwargs):
            raise RuntimeError("planner unavailable")

        runtime._build_acg_blueprint = fail
        await coordinator.submit(run.run_id)
        await _wait_inactive(coordinator, run.run_id)

        failed = runtime.get_status(run.run_id)
        assert failed.status == WorkflowStatus.FAILED
        assert failed.lifecycle_phase == WorkflowProgressPhase.FAILED
        assert failed.error["code"] == "workflow_execution_failed"
        assert "planner unavailable" in failed.error["message"]
        assert runtime.task_manager.get_task(task.task_id).status == WorkflowStatus.FAILED
        assert coordinator.is_active(run.run_id) is False
        assert sum(event.event_type.value == "run_failed" for event in failed.trace) == 1

    asyncio.run(scenario())


def test_coordinator_shutdown_marks_unfinished_run_as_worker_shutdown():
    async def scenario():
        runtime = _runtime()
        task = runtime.create_task(title="Shutdown", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        coordinator = RunExecutionCoordinator(runtime)
        entered = asyncio.Event()

        class WaitingAdapter:
            async def start(self, **kwargs):
                entered.set()
                await asyncio.Event().wait()

        runtime._workflow_adapter = lambda workflow: WaitingAdapter()
        await coordinator.submit(run.run_id)
        await asyncio.wait_for(entered.wait(), timeout=0.5)
        await coordinator.shutdown()

        failed = runtime.get_status(run.run_id)
        assert failed.status == WorkflowStatus.FAILED
        assert failed.lifecycle_phase == WorkflowProgressPhase.FAILED
        assert failed.error["code"] == "worker_shutdown"
        assert coordinator.is_active(run.run_id) is False

    asyncio.run(scenario())


def test_orphan_cleanup_closes_persisted_nonterminal_run():
    async def scenario():
        runtime = _runtime()
        task = runtime.create_task(title="Orphan", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        run = await runtime.update_run_lifecycle(
            run.run_id,
            status=WorkflowStatus.RUNNING,
            phase=WorkflowProgressPhase.PLANNING,
            set_started_at=True,
        )

        closed = await RunExecutionCoordinator(runtime).startup()

        assert closed == [run.run_id]
        failed = runtime.get_status(run.run_id)
        assert failed.status == WorkflowStatus.FAILED
        assert failed.error["code"] == "interrupted_after_restart"

    asyncio.run(scenario())


def test_restart_recovery_persists_one_consistent_failed_snapshot():
    async def scenario():
        store = _RecordingStore()
        runtime = _runtime(store)
        task = runtime.create_task(title="Interrupted", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        blueprint = ACGBlueprint(
            graphId="graph_restart",
            nodes=[StepNode(nodeId="work", agentName="worker")],
            edges=[],
        )
        run.runtime_graph = RuntimeGraph.from_blueprint(
            run_id=run.run_id, blueprint=blueprint
        )
        run.runtime_graph.get_node("work").status = StepStatus.RUNNING
        run.steps = [
            WorkflowStep(
                stepId="work",
                name="Work",
                agentName="worker",
                status=StepStatus.RUNNING,
            )
        ]
        run.current_step_id = "work"
        run.status = WorkflowStatus.RUNNING
        run.lifecycle_phase = WorkflowProgressPhase.EXECUTING
        store.save_run(run)
        store.lifecycle_writes.clear()

        closed = await RunExecutionCoordinator(runtime).startup()

        assert closed == [run.run_id]
        assert len(store.lifecycle_writes) == 1
        failed = store.get_run(run.run_id)
        assert failed.status == WorkflowStatus.FAILED
        assert failed.steps[0].status == StepStatus.FAILED
        assert failed.runtime_graph.get_node("work").status == StepStatus.FAILED
        assert failed.error == {
            "code": "interrupted_after_restart",
            "message": "任务因服务重启而中断。",
        }

    asyncio.run(scenario())


def test_restart_keeps_waiting_review_and_aligns_graph_once():
    async def scenario():
        store = _RecordingStore()
        runtime = _runtime(store)
        task = runtime.create_task(title="Review", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        blueprint = ACGBlueprint(
            graphId="graph_review_restart",
            nodes=[StepNode(nodeId="work", agentName="worker")],
            edges=[],
        )
        run.runtime_graph = RuntimeGraph.from_blueprint(
            run_id=run.run_id, blueprint=blueprint
        )
        run.runtime_graph.get_node("work").status = StepStatus.WAITING_REVIEW
        run.steps = [
            WorkflowStep(
                stepId="work",
                name="Work",
                agentName="worker",
                status=StepStatus.WAITING_REVIEW,
            )
        ]
        run.current_step_id = "work"
        run.status = WorkflowStatus.WAITING_REVIEW
        run.lifecycle_phase = WorkflowProgressPhase.EXECUTING
        store.save_run(run)
        store.lifecycle_writes.clear()

        closed = await RunExecutionCoordinator(runtime).startup()

        assert closed == []
        assert len(store.lifecycle_writes) == 1
        restored = store.get_run(run.run_id)
        assert restored.status == WorkflowStatus.WAITING_REVIEW
        assert restored.lifecycle_phase == WorkflowProgressPhase.REVIEW
        assert restored.steps[0].status == StepStatus.WAITING_REVIEW
        assert restored.runtime_graph.get_node("work").status == StepStatus.WAITING_REVIEW

    asyncio.run(scenario())


def test_terminal_run_cannot_be_overwritten_by_stale_sqlite_snapshot(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "workflow.db")
    store.save_task(AgentTask(taskId="task_terminal", title="Terminal"))
    run = WorkflowRun(
        taskId="task_terminal",
        workflowId="workflow_terminal",
        domain="test",
        runtimeEngine="acg",
        lifecyclePhase="planning",
    )
    store.save_run(run)
    stale = deepcopy(store.get_run(run.run_id))
    cancelled = store.get_run(run.run_id)
    cancelled.status = WorkflowStatus.CANCELLED
    cancelled.lifecycle_phase = WorkflowProgressPhase.CANCELLED
    store.save_run(cancelled)

    stale.status = WorkflowStatus.RUNNING
    stale.lifecycle_phase = WorkflowProgressPhase.EXECUTING
    store.save_run(stale)

    persisted = store.get_run(run.run_id)
    assert persisted.status == WorkflowStatus.CANCELLED
    assert persisted.lifecycle_phase == WorkflowProgressPhase.CANCELLED


def test_cancel_during_planning_stops_before_executor_and_preserves_terminal_state(tmp_path):
    async def scenario():
        runtime = _runtime(SQLiteWorkflowStore(tmp_path / "cancel.db"))
        task = runtime.create_task(title="Cancel plan", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        coordinator = RunExecutionCoordinator(runtime)
        entered = Event()
        release = Event()
        original = runtime._build_acg_blueprint

        def blocking(*args, **kwargs):
            entered.set()
            release.wait(timeout=2)
            return original(*args, **kwargs)

        runtime._build_acg_blueprint = blocking
        await coordinator.submit(run.run_id)
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        runtime.cancel(run.run_id)
        release.set()
        await _wait_inactive(coordinator, run.run_id)

        cancelled = runtime.get_status(run.run_id)
        assert cancelled.status == WorkflowStatus.CANCELLED
        assert cancelled.lifecycle_phase == WorkflowProgressPhase.CANCELLED
        assert cancelled.steps == []

    asyncio.run(scenario())


def test_progress_prefers_terminal_and_step_special_state_over_persisted_phase():
    failed = WorkflowRun(
        taskId="task_failed",
        workflowId="workflow",
        domain="test",
        runtimeEngine="acg",
        status="failed",
        lifecyclePhase="executing",
    )
    retrying = WorkflowRun(
        taskId="task_retrying",
        workflowId="workflow",
        domain="test",
        runtimeEngine="acg",
        status="running",
        lifecyclePhase="executing",
        steps=[
            WorkflowStep(
                stepId="retry",
                name="Retry",
                agentName="worker",
                status=StepStatus.RETRYING,
            )
        ],
    )

    assert ProgressAssembler().assemble(failed).phase == WorkflowProgressPhase.FAILED
    assert ProgressAssembler().assemble(retrying).phase == WorkflowProgressPhase.RECOVERY


def test_progress_projects_persisted_lifecycle_message_and_real_started_at():
    run = WorkflowRun(
        taskId="task_planning",
        workflowId="workflow",
        domain="test",
        runtimeEngine="acg",
        status="running",
        lifecyclePhase="planning",
        lifecycleMessage="Planning from runtime",
    )

    progress = ProgressAssembler().assemble(run)

    assert progress.phase == WorkflowProgressPhase.PLANNING
    assert progress.message == "Planning from runtime"
    assert progress.started_at is None


def test_async_start_returns_before_planner_and_is_idempotent():
    runtime = _runtime()
    coordinator = RunExecutionCoordinator(runtime)
    entered = Event()
    release = Event()
    calls = 0
    original = runtime._build_acg_blueprint

    def blocking(*args, **kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=3)
        return original(*args, **kwargs)

    runtime._build_acg_blueprint = blocking

    @asynccontextmanager
    async def lifespan(app):
        yield
        release.set()
        await coordinator.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_router(runtime, coordinator), prefix="/ai")
    payload = {
        "title": "Async API",
        "domain": "test",
        "intent": "work",
        "workflowId": "async_test_v1",
        "clientRequestId": "request-123",
    }

    with TestClient(app) as client:
        started = monotonic()
        response = client.post("/ai/core/workflows/start-async", json=payload)
        elapsed = monotonic() - started
        assert response.status_code == 202
        assert elapsed < 0.5
        first = response.json()
        assert first["accepted"] is True
        assert first["run"]["runId"]
        assert "idempotencyKey" not in first["run"]
        assert first["run"]["status"] in {"pending", "running"}
        assert first["run"]["lifecyclePhase"] in {"understanding", "planning"}
        assert entered.wait(timeout=0.5)

        status = client.get(f"/ai/core/workflows/runs/{first['run']['runId']}")
        assert status.status_code == 200
        assert status.json()["lifecyclePhase"] == "planning"

        duplicate = client.post("/ai/core/workflows/start-async", json=payload)
        assert duplicate.status_code == 202
        second = duplicate.json()
        assert second["task"]["taskId"] == first["task"]["taskId"]
        assert second["run"]["runId"] == first["run"]["runId"]
        assert calls == 1

        conflict = client.post(
            "/ai/core/workflows/start-async",
            json={**payload, "title": "Conflicting title"},
        )
        assert conflict.status_code == 409

        different = client.post(
            "/ai/core/workflows/start-async",
            json={**payload, "clientRequestId": "request-456"},
        )
        assert different.status_code == 202
        assert different.json()["run"]["runId"] != first["run"]["runId"]

        release.set()
        for _ in range(100):
            latest = client.get(f"/ai/core/workflows/runs/{first['run']['runId']}").json()
            if latest["status"] == "completed":
                break
            asyncio.run(asyncio.sleep(0.01))
        assert latest["status"] == "completed"


def test_store_nonterminal_query_is_bounded_and_idempotency_is_persisted(tmp_path):
    store = SQLiteWorkflowStore(tmp_path / "workflow.db")
    for index, status in enumerate(
        [WorkflowStatus.PENDING, WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED]
    ):
        task = AgentTask(title=f"Task {index}")
        store.save_task(task)
        store.save_run(
            WorkflowRun(
                taskId=task.task_id,
                workflowId="workflow",
                domain="test",
                runtimeEngine="acg",
                status=status,
                idempotencyKey=f"key-{index}",
            )
        )

    unfinished = store.list_non_terminal_runs(limit=1)
    assert len(unfinished) == 1
    assert unfinished[0].status in {WorkflowStatus.PENDING, WorkflowStatus.RUNNING}
    assert store.find_run_by_idempotency_key("key-1").idempotency_key == "key-1"


def test_coordinator_does_not_resubmit_a_run_that_already_started():
    async def scenario():
        runtime = _runtime()
        task = runtime.create_task(title="Review", domain="test", intent="work")
        _, run = runtime.prepare_run(task.task_id)
        run.status = WorkflowStatus.WAITING_REVIEW
        run.lifecycle_phase = WorkflowProgressPhase.REVIEW
        run.started_at = run.created_at
        runtime.workflow_store.save_run(run)
        coordinator = RunExecutionCoordinator(runtime)

        assert await coordinator.submit(run.run_id) is False
        assert coordinator.is_active(run.run_id) is False
        assert runtime.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW

    asyncio.run(scenario())


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_store_terminal_protection_has_consistent_snapshot_semantics(store_kind, tmp_path):
    store = (
        MemoryWorkflowStore()
        if store_kind == "memory"
        else SQLiteWorkflowStore(tmp_path / "terminal-contract.db")
    )
    run = WorkflowRun(
        taskId="task_terminal_contract",
        workflowId="workflow",
        domain="test",
        runtimeEngine="acg",
        status=WorkflowStatus.RUNNING,
        lifecyclePhase=WorkflowProgressPhase.EXECUTING,
        steps=[_step("step", StepStatus.PENDING)],
    )
    store.save_task(AgentTask(taskId=run.task_id, title="Terminal contract"))
    store.save_run(run)
    stale = store.get_run(run.run_id)
    cancelled = store.get_run(run.run_id)
    cancelled.status = WorkflowStatus.CANCELLED
    cancelled.lifecycle_phase = WorkflowProgressPhase.CANCELLED
    cancelled.steps[0].status = StepStatus.CANCELLED
    cancelled.updated_at = cancelled.updated_at + timedelta(seconds=2)
    store.save_run(cancelled)

    stale.status = WorkflowStatus.COMPLETED
    stale.lifecycle_phase = WorkflowProgressPhase.COMPLETED
    stale.steps[0].status = StepStatus.COMPLETED
    stale.updated_at = stale.updated_at + timedelta(seconds=1)
    store.save_run(stale)

    persisted = store.get_run(run.run_id)
    assert persisted.status == WorkflowStatus.CANCELLED
    assert persisted.lifecycle_phase == WorkflowProgressPhase.CANCELLED
    assert persisted.steps[0].status == StepStatus.CANCELLED
    assert persisted.updated_at == cancelled.updated_at


def test_memory_store_does_not_persist_mutation_before_save():
    store = MemoryWorkflowStore()
    run = WorkflowRun(
        taskId="task_snapshot",
        workflowId="workflow",
        domain="test",
        runtimeEngine="acg",
        status=WorkflowStatus.RUNNING,
    )
    store.save_run(run)

    loaded = store.get_run(run.run_id)
    loaded.status = WorkflowStatus.COMPLETED

    assert store.get_run(run.run_id).status == WorkflowStatus.RUNNING


def test_same_client_request_id_is_scoped_by_authenticated_user():
    runtime = _runtime()
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.add_middleware(
        InternalServiceAuthMiddleware,
        token="0123456789abcdef0123456789abcdef",
    )
    app.include_router(create_router(runtime, coordinator), prefix="/ai")
    payload = {
        "title": "Scoped request",
        "domain": "test",
        "intent": "work",
        "workflowId": "async_test_v1",
        "clientRequestId": "same-client-id",
    }

    def headers(user_id):
        return {
            "X-Internal-Service-Token": "0123456789abcdef0123456789abcdef",
            "X-Authenticated-User-Id": user_id,
            "X-Authenticated-User-Subject": user_id,
            "X-Authenticated-User-Role": "USER",
            "X-Authenticated-Tenant-Id": "tenant-a",
        }

    with TestClient(app) as client:
        first = client.post(
            "/ai/core/workflows/start-async",
            json=payload,
            headers=headers("user-a"),
        )
        second = client.post(
            "/ai/core/workflows/start-async",
            json=payload,
            headers=headers("user-b"),
        )

        assert first.status_code == second.status_code == 202
        assert first.json()["run"]["runId"] != second.json()["run"]["runId"]

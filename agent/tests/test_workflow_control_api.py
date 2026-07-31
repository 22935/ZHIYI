import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
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
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from app.api.agentos_core import create_router
from app.security.internal_auth import InternalServiceAuthMiddleware


TOKEN = "0123456789abcdef0123456789abcdef"


class _ReviewAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentProfile(
            agentName="reviewer",
            domain="test",
            capabilities=[],
            allowedSkills=[],
        ))

    async def run(self, context):
        return AgentOutput(output={"reviewed": True}, summary="reviewed")


def _headers(user_id: str, tenant_id: str = "tenant-a"):
    return {
        "X-Internal-Service-Token": TOKEN,
        "X-Authenticated-User-Id": user_id,
        "X-Authenticated-User-Subject": user_id,
        "X-Authenticated-User-Role": "USER",
        "X-Authenticated-Tenant-Id": tenant_id,
    }


def _runtime():
    agents = AgentRegistry()
    agents.register(_ReviewAgent())
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="review_control_v1",
            name="Review control",
            domain="test",
            intent="review",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="human_gate",
                    name="Human gate",
                    agentName="reviewer",
                    reviewRequired=True,
                )
            ],
        )
    )
    return WorkflowRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
    )


def _client(runtime):
    app = FastAPI()
    app.add_middleware(InternalServiceAuthMiddleware, token=TOKEN)
    app.include_router(create_router(runtime), prefix="/ai")
    return TestClient(app)


def _save_summary_run(runtime, *, user_id, status, phase, suffix):
    run = WorkflowRun(
        runId=f"run_{suffix}",
        taskId=f"task_{suffix}",
        workflowId="review_control_v1",
        domain="test",
        runtimeEngine="acg",
        status=status,
        lifecyclePhase=phase,
        lifecycleMessage=f"safe:{phase.value}",
        input={
            "authenticatedUserId": user_id,
            "authenticatedTenantId": "tenant-a",
            "source": "chat",
            "sensitiveDocument": "must-not-leak",
        },
        output={"secret": True},
        steps=[WorkflowStep(stepId="work", name="Work", agentName="worker", status=StepStatus.PENDING)],
        updatedAt=datetime(2026, 7, 22, 6, int(suffix[-1]), tzinfo=timezone.utc),
    )
    runtime.workflow_store.save_run(run)
    return run


def _waiting_review_run(runtime, user_id="user-a"):
    task = runtime.create_task(
        title="Review task",
        domain="test",
        intent="review",
        input={"authenticatedUserId": user_id, "authenticatedTenantId": "tenant-a"},
        workflow_id="review_control_v1",
    )
    run = asyncio.run(runtime.start(
        task_id=task.task_id,
        workflow_id="review_control_v1",
        review_mode="human_in_loop",
    ))
    assert run.status == WorkflowStatus.WAITING_REVIEW
    return run


def test_summary_list_is_bounded_owner_scoped_prioritized_and_safe():
    runtime = _runtime()
    _save_summary_run(
        runtime, user_id="user-a", status=WorkflowStatus.RUNNING,
        phase=WorkflowProgressPhase.EXECUTING, suffix="a1",
    )
    review = _save_summary_run(
        runtime, user_id="user-a", status=WorkflowStatus.WAITING_REVIEW,
        phase=WorkflowProgressPhase.REVIEW, suffix="a2",
    )
    _save_summary_run(
        runtime, user_id="user-a", status=WorkflowStatus.RUNNING,
        phase=WorkflowProgressPhase.PLANNING, suffix="a4",
    )
    _save_summary_run(
        runtime, user_id="user-b", status=WorkflowStatus.WAITING_REVIEW,
        phase=WorkflowProgressPhase.REVIEW, suffix="b3",
    )

    response = _client(runtime).get(
        "/ai/core/workflows/runs",
        params={
            "statuses": "pending,running,waiting_review,completed",
            "summary": "true",
            "page": 1,
            "pageSize": 50,
        },
        headers=_headers("user-a"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["items"][0]["runId"] == review.run_id
    assert payload["items"][0]["phase"] == "review"
    assert "title" in payload["items"][0]
    assert any(item["percent"] is None for item in payload["items"])
    for item in payload["items"]:
        assert not {"input", "output", "steps", "trace", "checkpoints", "acgBlueprint"}.intersection(item)
        assert "sensitiveDocument" not in str(item)


def test_run_detail_and_review_hide_other_owners():
    runtime = _runtime()
    run = _waiting_review_run(runtime, "user-a")
    client = _client(runtime)

    owner_run = client.get(f"/ai/core/workflows/runs/{run.run_id}", headers=_headers("user-a"))
    assert owner_run.status_code == 200
    assert owner_run.json()["title"] == "Review task"
    assert client.get(f"/ai/core/workflows/runs/{run.run_id}", headers=_headers("user-b")).status_code == 404
    denied = client.post(
        f"/ai/core/workflows/runs/{run.run_id}/reviews",
        json={"stepId": "human_gate", "decision": "approved", "operationId": "operation-denied"},
        headers=_headers("user-b"),
    )
    assert denied.status_code == 404


def test_reject_is_atomic_idempotent_and_conflict_aware():
    runtime = _runtime()
    run = _waiting_review_run(runtime)
    client = _client(runtime)
    request = {
        "stepId": "human_gate",
        "decision": "rejected",
        "comment": "unsafe output",
        "operationId": "operation-reject-001",
        "expectedRunUpdatedAt": run.updated_at.isoformat().replace("+00:00", "Z"),
        "expectedStepStatus": "waiting_review",
    }

    first = client.post(f"/ai/core/workflows/runs/{run.run_id}/reviews", json=request, headers=_headers("user-a"))
    duplicate = client.post(f"/ai/core/workflows/runs/{run.run_id}/reviews", json=request, headers=_headers("user-a"))
    reused = client.post(
        f"/ai/core/workflows/runs/{run.run_id}/reviews",
        json={**request, "decision": "approved"},
        headers=_headers("user-a"),
    )

    assert first.status_code == duplicate.status_code == 200
    assert first.json()["status"] == duplicate.json()["status"] == "failed"
    assert reused.status_code == 409
    reviews = client.get(f"/ai/core/workflows/runs/{run.run_id}/reviews", headers=_headers("user-a")).json()
    assert reviews["total"] == 1
    assert reviews["items"][0]["operationId"] == "operation-reject-001"


def test_review_rejects_stale_revision_and_approve_uses_backend_state_machine():
    runtime = _runtime()
    stale_run = _waiting_review_run(runtime)
    client = _client(runtime)
    stale = client.post(
        f"/ai/core/workflows/runs/{stale_run.run_id}/reviews",
        json={
            "stepId": "human_gate",
            "decision": "approved",
            "operationId": "operation-stale-001",
            "expectedRunUpdatedAt": "2020-01-01T00:00:00Z",
            "expectedStepStatus": "waiting_review",
        },
        headers=_headers("user-a"),
    )
    assert stale.status_code == 409

    approved_run = _waiting_review_run(runtime)
    approved = client.post(
        f"/ai/core/workflows/runs/{approved_run.run_id}/reviews",
        json={
            "stepId": "human_gate",
            "decision": "approved",
            "operationId": "operation-approve-001",
            "expectedRunUpdatedAt": approved_run.updated_at.isoformat().replace("+00:00", "Z"),
            "expectedStepStatus": "waiting_review",
        },
        headers=_headers("user-a"),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert approved.json()["steps"][0]["status"] == "completed"


def test_unknown_review_run_returns_404():
    response = _client(_runtime()).post(
        "/ai/core/workflows/runs/run_missing/reviews",
        json={"stepId": "gate", "decision": "approved", "operationId": "operation-missing"},
        headers=_headers("user-a"),
    )
    assert response.status_code == 404


def test_waiting_review_run_cannot_be_deleted():
    runtime = _runtime()
    run = _waiting_review_run(runtime, "user-a")
    client = _client(runtime)

    denied = client.delete(
        f"/ai/core/workflows/runs/{run.run_id}",
        headers=_headers("user-b"),
    )
    deleted = client.delete(
        f"/ai/core/workflows/runs/{run.run_id}",
        headers=_headers("user-a"),
    )

    assert denied.status_code == 404
    assert deleted.status_code == 409
    assert deleted.json() == {
        "code": "RUN_WAITING_REVIEW",
        "message": "当前任务正在等待审核，请完成审核或取消任务后再删除。",
    }
    assert runtime.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW


def test_running_workflow_must_be_cancelled_before_delete():
    runtime = _runtime()
    run = _save_summary_run(
        runtime,
        user_id="user-a",
        status=WorkflowStatus.RUNNING,
        phase=WorkflowProgressPhase.EXECUTING,
        suffix="a5",
    )

    response = _client(runtime).delete(
        f"/ai/core/workflows/runs/{run.run_id}",
        headers=_headers("user-a"),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "RUN_NOT_TERMINAL",
        "message": "当前任务仍未结束，请先完成或取消任务。",
    }
    assert runtime.get_status(run.run_id).status == WorkflowStatus.RUNNING


@pytest.mark.parametrize(
    "status,phase,suffix",
    [
        (WorkflowStatus.COMPLETED, WorkflowProgressPhase.COMPLETED, "d1"),
        (WorkflowStatus.FAILED, WorkflowProgressPhase.FAILED, "d2"),
        (WorkflowStatus.CANCELLED, WorkflowProgressPhase.CANCELLED, "d3"),
    ],
)
def test_terminal_run_can_be_deleted_once(status, phase, suffix):
    runtime = _runtime()
    run = _save_summary_run(
        runtime,
        user_id="user-a",
        status=status,
        phase=phase,
        suffix=suffix,
    )
    runtime.workflow_store.save_task(AgentTask(taskId=run.task_id, title="Terminal"))
    client = _client(runtime)

    deleted = client.delete(
        f"/ai/core/workflows/runs/{run.run_id}", headers=_headers("user-a")
    )
    missing = client.delete(
        f"/ai/core/workflows/runs/{run.run_id}", headers=_headers("user-a")
    )

    assert deleted.status_code == 200
    assert deleted.json()["taskDeleted"] is True
    assert missing.status_code == 404


def test_material_release_failure_does_not_undo_terminal_run_delete(monkeypatch):
    from app.api import agentos_core

    runtime = _runtime()
    run = _save_summary_run(
        runtime,
        user_id="user-a",
        status=WorkflowStatus.COMPLETED,
        phase=WorkflowProgressPhase.COMPLETED,
        suffix="d4",
    )
    runtime.workflow_store.save_task(AgentTask(taskId=run.task_id, title="Material"))
    run.input["sourceMaterials"] = [{"materialId": "mat_" + "a" * 32}]
    runtime.workflow_store.save_run(run)
    monkeypatch.setattr(
        agentos_core.task_material_store,
        "release_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("material busy")),
    )

    response = _client(runtime).delete(
        f"/ai/core/workflows/runs/{run.run_id}", headers=_headers("user-a")
    )

    assert response.status_code == 200
    with pytest.raises(KeyError):
        runtime.get_status(run.run_id)

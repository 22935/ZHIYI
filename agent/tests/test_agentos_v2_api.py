from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import app.api.agentos_v2 as agentos_v2
from app.api.agentos_v2 import create_router
from app.execution.coordinator import RunExecutionCoordinator
from app.security.internal_auth import TrustedUserContext, _trusted_user_context
from components.executor import InMemoryExecutionValueStore
from components.planner import TaskDecompositionError
from components.resource.auth import build_resource_signature
from components.recovery.checkpoint import ACGCheckpointStore
from components.mission_manager.store import WorkflowRegistry
from contracts.evolution import PolicyMutation, Trajectory
from contracts.content import ContentKind
from contracts.resource import ResourceHealthStatus, ResourceProfile, ResourceSnapshot, ResourceType
from contracts.planning import PlannedTask
from contracts.runtime_events import RuntimeEvent
from contracts.workflow import (
    MissionRecordState,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowProgressPhase,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from runtime import ExecutionRuntime
from runtime.live_events import RuntimeEventBroker
from runtime.v2 import AcgIdentityLifecycleService, IdentityProjectionBridge
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from support.stores.memory_workflow_store import MemoryWorkflowStore
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage


_SECRET = "REFERENCE-ONLY-OUTPUT-BODY"


class _ApiAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentProfile(agentName="api-agent", domain="general"))

    async def run(self, context):
        return AgentOutput(output={"report": _SECRET}, summary="safe report summary")


class _GatedApiAgent(BaseAgent):
    """第一步阻塞在闸门上，为取消端点制造确定性的活跃执行窗口。"""

    def __init__(self, profile: AgentProfile) -> None:
        super().__init__(profile)
        self.arrived = asyncio.Event()
        self.gate = asyncio.Event()

    async def run(self, context):
        if context.step.step_id == "report":
            self.arrived.set()
            await self.gate.wait()
            return AgentOutput(output={"report": _SECRET}, summary="safe report summary")
        return AgentOutput(output={"report": "done"}, summary="done")


def _runtime(tmp_path, *, with_identity: bool = False, agent: BaseAgent | None = None) -> ExecutionRuntime:
    agents = AgentRegistry()
    agents.register(agent or _ApiAgent())
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="api-workflow",
            name="API workflow",
            domain="general",
            runtimeEngine="acg",
            planningNodes=[PlannedTask(
                key="report",
                title="report",
                objective="produce the requested report",
            )],
            steps=[
                WorkflowStepDefinition(
                    stepId="report",
                    name="report",
                    agentName="api-agent",
                    outputSpec={
                        "type": "object",
                        "required": ["report"],
                        "properties": {"report": {"type": "string"}},
                    },
                )
            ],
        )
    )
    identity_lifecycle = None
    if with_identity:
        identity_service = AcgIdentityLifecycleService(
            SQLiteV2Repositories(SQLiteV2Storage(":memory:"))
        )
        identity_lifecycle = IdentityProjectionBridge(
            identity_service,
            identity_service.repositories,
        )
    return ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "api-checkpoints.sqlite3"),
        execution_value_store=InMemoryExecutionValueStore(),
        identity_lifecycle=identity_lifecycle,
    )


async def test_v2_run_state_is_reference_only_and_output_requires_owned_reference(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission(
        "API projection must not leak input",
        workflow_id="api-workflow",
        input={"contractText": "PRIVATE-TASK-INPUT"},
    )
    run = await runtime.start(task.mission_id, workflow_id="api-workflow")
    runtime.trace_store.append(
        run,
        TraceEventType.RUNTIME_EVENT_CLASSIFIED,
        payload={"prompt": "PRIVATE-PROMPT", "safeCode": "classified"},
    )
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/agentos/v2/runs/{run.run_id}")
        assert response.status_code == 200
        state_body = response.json()
        serialized = response.text
        assert state_body["title"] == "API projection must not leak input"
        assert state_body["outputRef"] == run.output["outputRef"]
        assert state_body["steps"][0]["outputSummary"] == "safe report summary"
        assert _SECRET not in serialized
        assert "PRIVATE-TASK-INPUT" not in serialized
        assert "input" not in state_body
        assert "output" not in state_body["steps"][0]

        output_ref = state_body["outputRef"]
        output = await client.get(f"/agentos/v2/runs/{run.run_id}/outputs/{output_ref}")
        assert output.status_code == 200
        assert output.json()["content"] == {"report": _SECRET}
        assert (await client.get(f"/agentos/v2/runs/{run.run_id}/outputs/output:other:step:hash")).status_code == 404

        trace = await client.get(f"/agentos/v2/runs/{run.run_id}/trace")
        assert trace.status_code == 200
        assert "PRIVATE-PROMPT" not in trace.text
        assert any(event["payload"].get("prompt") == "[redacted]" for event in trace.json()["events"])


def test_v2_runtime_events_endpoint_streams_http_before_publisher_finishes(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("Runtime event HTTP stream", workflow_id="api-workflow")
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")
    broker = RuntimeEventBroker()
    monkeypatch.setattr(agentos_v2, "runtime_event_broker", broker)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    def publish_later() -> None:
        time.sleep(0.5)
        broker.publish_from_thread(run.run_id, RuntimeEvent(
            eventType="model.output.delta",
            runId=run.run_id,
            nodeId="report",
            attemptId="attempt-1",
            sequence=0,
            payload={"delta": "live"},
        ))
        time.sleep(0.3)
        broker.publish_from_thread(run.run_id, RuntimeEvent(
            eventType="node.completed",
            runId=run.run_id,
            nodeId="report",
            attemptId="attempt-1",
            sequence=0,
            payload={},
        ))
        broker.publish_from_thread(run.run_id, RuntimeEvent(
            eventType="run.completed",
            runId=run.run_id,
            sequence=0,
            payload={},
        ))

    publisher = threading.Thread(target=publish_later)
    publisher.start()
    received = []
    with TestClient(app) as client:
        with client.stream("GET", f"/agentos/v2/runs/{run.run_id}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            for line in response.iter_lines():
                if line.startswith("event:"):
                    received.append(line.split(":", 1)[1].strip())
            publisher.join(timeout=2)
    publisher.join(timeout=2)
    assert not publisher.is_alive()
    assert received == ["model.output.delta", "node.completed", "run.completed"]
    assert runtime.get_status(run.run_id).status == WorkflowStatus.PENDING


async def test_v2_run_history_applies_all_filters_and_matches_detail_visibility(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    visible_task = runtime.create_mission(
        "Visible ACG run",
        workflow_id="api-workflow",
        input={"source": "acg"},
    )
    _, visible_run = runtime.prepare_run(visible_task.mission_id, workflow_id="api-workflow")
    visible_run.status = WorkflowStatus.WAITING_REVIEW
    visible_run.lifecycle_phase = WorkflowProgressPhase.REVIEW
    visible_run.steps[0].status = StepStatus.WAITING_REVIEW
    visible_run.current_step_id = visible_run.steps[0].step_id
    visible_run.execution_state.update({
        "checkpointId": "acgckpt_api_history",
        "reviewPayload": {"stepId": visible_run.steps[0].step_id},
    })
    runtime.workflow_store.save_run(visible_run)

    hidden_task = runtime.create_mission(
        "Owned by another user",
        workflow_id="api-workflow",
        input={"source": "acg", "authenticatedUserId": "other-user"},
    )
    _, hidden_run = runtime.prepare_run(hidden_task.mission_id, workflow_id="api-workflow")
    runtime.workflow_store.save_run(hidden_run)

    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/agentos/v2/runs",
            params={
                "statuses": "running,waiting_review",
                "domain": "general",
                "workflowId": "api-workflow",
                "missionId": visible_task.mission_id,
                "lifecyclePhase": "review",
                "sources": "acg,chat",
                "summary": "true",
            },
        )
        hidden_detail = await client.get(f"/agentos/v2/runs/{hidden_run.run_id}")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["runId"] == visible_run.run_id
    assert response.json()["items"][0]["source"] == "acg"
    assert hidden_detail.status_code == 404


async def test_v2_run_history_does_not_apply_removed_architecture_heuristics(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    current_task = runtime.create_mission(
        "Current architecture run",
        workflow_id="api-workflow",
        input={"source": "acg"},
    )
    _, current_run = runtime.prepare_run(current_task.mission_id, workflow_id="api-workflow")

    legacy_task = runtime.create_mission(
        "Pre-compiled architecture run",
        workflow_id="api-workflow",
        input={"source": "acg"},
    )
    _, legacy_run = runtime.prepare_run(legacy_task.mission_id, workflow_id="api-workflow")
    legacy_run.execution_state.pop("compiledPackageId", None)
    runtime.workflow_store.save_run(legacy_run)

    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/agentos/v2/runs",
            params={"sources": "acg"},
        )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert {item["runId"] for item in response.json()["items"]} == {
        current_run.run_id,
        legacy_run.run_id,
    }


async def test_v2_projects_scheduling_and_versioned_evolution_without_bodies(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("Scheduling projection", workflow_id="api-workflow")
    run = await runtime.start(task.mission_id, workflow_id="api-workflow")
    proposal = runtime.evolution_service.propose(
        [
            Trajectory(
                trajectoryId=f"trajectory-{index}",
                task={"domain": "general"},
                outcome={"status": "completed"},
            )
            for index in range(3)
        ],
        PolicyMutation(mutationType="budget_adjustment", target="analysis", value=4096),
    )
    assert proposal is not None
    runtime.evolution_service.approve(proposal, approved_by="reviewer")
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scheduling = await client.get(f"/agentos/v2/runs/{run.run_id}/scheduling")
        assert scheduling.status_code == 200
        assert scheduling.json()["items"][0]["binding"]["resourceId"] == "api-agent"

        active = await client.get("/agentos/v2/evolution/active")
        assert active.json()["version"] == 1
        history = await client.get("/agentos/v2/evolution/history")
        assert history.json()["total"] == 2
        rolled_back = await client.post(
            "/agentos/v2/evolution/rollback",
            json={"targetVersion": 0, "reviewer": "reviewer"},
        )
        assert rolled_back.status_code == 200
        assert rolled_back.json()["version"] == 2


async def test_v2_legacy_outputs_are_read_only_and_only_available_without_refs(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("Legacy API projection", workflow_id="api-workflow")
    run = await runtime.start(task.mission_id, workflow_id="api-workflow")
    run.execution_state.pop("outputRefs", None)
    run.output = {"final_answer": _SECRET}
    run.steps[0].output = {"report": _SECRET}
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/agentos/v2/runs/{run.run_id}/legacy-outputs")
        assert response.status_code == 200
        assert response.json()["items"] == [
            {
                "stepId": "report",
                "name": "report",
                "status": "completed",
                "content": {"report": _SECRET},
            }
        ]

        run.execution_state["outputRefs"] = {"report": "output:owned"}
        runtime.workflow_store.save_run(run)
        response = await client.get(f"/agentos/v2/runs/{run.run_id}/legacy-outputs")
        assert response.status_code == 404


async def test_v2_history_config_returns_only_owner_visible_workbench_fields(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission(
        "Historical workbench",
        workflow_id="api-workflow",
        input={
            "taskGoal": "Restore the saved objective",
            "materialText": "Owner-visible material",
            "constraints": ["No external writes"],
            "expectedArtifacts": ["Report"],
            "webSearchEnabled": False,
            "apiKey": _SECRET,
        },
    )
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow", review_mode="human_in_loop")
    run.enabled_plugin_ids = ["kinlin.legal"]
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/agentos/v2/runs/{run.run_id}/history-config")

    assert response.status_code == 200
    body = response.json()
    assert body["runId"] == run.run_id
    assert body["title"] == "Historical workbench"
    assert body["reviewMode"] == "human_in_loop"
    assert body["enabledPluginIds"] == ["kinlin.legal"]
    assert body["input"]["taskGoal"] == "Restore the saved objective"
    assert body["input"]["materialText"] == "Owner-visible material"
    assert body["input"]["constraints"] == ["No external writes"]
    assert body["input"]["expectedArtifacts"] == ["Report"]
    assert body["input"]["webSearchEnabled"] is False
    assert _SECRET not in response.text


async def test_v2_provenance_falls_back_to_read_only_legacy_snapshot(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("Legacy provenance projection", workflow_id="api-workflow")
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")
    run.provenance = {
        "schemaVersion": 2,
        "integrityStatus": "valid",
        "productions": [{"eventId": "prod_000001", "producerStepId": "report", "fieldNames": ["report"]}],
        "consumptions": [{"eventId": "cons_000002", "consumerStepId": "deliver", "tokensAvailable": 100, "tokensDelivered": 40}],
        "interactions": [{"eventId": "int_000003", "interactionId": "int_000003", "consumerStepId": "deliver", "tokensAvailable": 100, "tokensDelivered": 40, "savingRatio": 0.6, "content": _SECRET}],
    }
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/agentos/v2/runs/{run.run_id}/provenance")

    assert response.status_code == 200
    assert response.json()["legacy"] is True
    assert response.json()["schemaVersion"] == 2
    assert response.json()["productions"][0]["producerStepId"] == "report"
    assert response.json()["interactions"][0]["savingRatio"] == 0.6
    assert response.json()["interactions"][0]["tokensAvailable"] == 100
    assert _SECRET not in response.text


async def test_v2_graph_provenance_and_checkpoint_are_separate_safe_resources(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("API resources", workflow_id="api-workflow")
    run = await runtime.start(task.mission_id, workflow_id="api-workflow")
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        graph = await client.get(f"/agentos/v2/runs/{run.run_id}/graph")
        assert graph.status_code == 200
        assert graph.json()["nodes"]
        assert "runtimeGraph" not in graph.json()
        assert _SECRET not in graph.text

        provenance = await client.get(f"/agentos/v2/runs/{run.run_id}/provenance")
        assert provenance.status_code == 200
        assert provenance.json()["integrityStatus"] == "valid"
        assert provenance.json()["events"]
        assert _SECRET not in provenance.text

        checkpoints = await client.get(f"/agentos/v2/runs/{run.run_id}/checkpoints")
        assert checkpoints.status_code == 200
        for item in checkpoints.json()["items"]:
            assert set(item) == {"checkpointId", "version", "canResume"}

        paths = app.openapi()["paths"]
        assert "/agentos/v2/runs/{run_id}/reviews" in paths


async def test_v2_resources_projects_authoritative_profile_and_unknown_health(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.resource_service.register(
        ResourceProfile(
            resourceId="resource-api",
            resourceType=ResourceType.AGENT,
            capabilities=["report"],
            capacity=2,
        ),
        ResourceSnapshot(
            resourceId="resource-api",
            availableSlots=2,
            utilization=0.0,
            healthStatus=ResourceHealthStatus.UNKNOWN,
        ),
    )
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/agentos/v2/resources")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    item = response.json()["items"][0]
    assert item["profile"]["resourceId"] == "resource-api"
    assert item["profile"]["resourceType"] == "agent"
    assert item["snapshot"]["healthStatus"] == "unknown"
    assert item["health"]["healthy"] is False
    assert item["health"]["status"] == "unknown"
    assert item["snapshot"]["availableSlots"] == 2
    assert "cpu" not in item["snapshot"]["metrics"]
    assert "gpu" not in item["snapshot"]["metrics"]


async def test_v2_remote_resource_observation_updates_health_and_capacity(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.resource_service.register(
        ResourceProfile(
            resourceId="edge-observe",
            resourceType=ResourceType.WORKER,
            deploymentTier="edge",
            capabilities=["vision.infer"],
            ownerScope="tenant-a",
            executionEndpoint={"protocol": "http", "address": "http://edge-observe:9000"},
        ),
        ResourceSnapshot(
            resourceId="edge-observe",
            availableSlots=0,
            utilization=1.0,
            healthStatus=ResourceHealthStatus.UNKNOWN,
        ),
    )
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    credential = runtime.resource_service.issue_credential("edge-observe")
    body = json.dumps({
        "availableSlots": 2,
        "observationSequence": 2,
        "utilization": 0.25,
        "latencyMs": 18,
        "observedAt": "2026-09-01T00:00:00Z",
    }, separators=(",", ":")).encode()
    timestamp = int(datetime.now(timezone.utc).timestamp())
    headers = {
        "content-type": "application/json",
        "X-Resource-Credential": credential.credential_id,
        "X-Resource-Timestamp": str(timestamp),
        "X-Resource-Nonce": "api-observation-1",
        "X-Resource-Signature": build_resource_signature(
            credential.secret,
            method="POST",
            path="/agentos/v2/resources/edge-observe/observation",
            timestamp=timestamp,
            nonce="api-observation-1",
            body=body,
        ),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/agentos/v2/resources/edge-observe/observation",
            content=body,
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["health"]["healthy"] is True
    assert response.json()["snapshot"]["availableSlots"] == 2

    stale_body = json.dumps({
        "availableSlots": 0,
        "observationSequence": 1,
        "utilization": 1.0,
        "observedAt": "2026-09-01T00:00:01Z",
    }, separators=(",", ":")).encode()
    stale_timestamp = int(datetime.now(timezone.utc).timestamp())
    stale_nonce = "api-observation-2"
    stale_headers = {
        "content-type": "application/json",
        "X-Resource-Credential": credential.credential_id,
        "X-Resource-Timestamp": str(stale_timestamp),
        "X-Resource-Nonce": stale_nonce,
        "X-Resource-Signature": build_resource_signature(
            credential.secret,
            method="POST",
            path="/agentos/v2/resources/edge-observe/observation",
            timestamp=stale_timestamp,
            nonce=stale_nonce,
            body=stale_body,
        ),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stale = await client.post(
            "/agentos/v2/resources/edge-observe/observation",
            content=stale_body,
            headers=stale_headers,
        )

    assert stale.status_code == 409
    assert "stale observation" in stale.json()["detail"]


def _operator_context():
    return _trusted_user_context.set(
        TrustedUserContext(
            user_id="operator-1",
            subject="operator-1",
            role="operator",
            tenant_id="tenant-a",
        )
    )


def _remote_registration_payload() -> dict:
    return {
        "profile": {
            "resourceId": "edge-registered",
            "resourceType": "worker",
            "deploymentTier": "edge",
            "capabilities": ["vision.infer"],
            "ownerScope": "tenant-a",
            "executionEndpoint": {
                "protocol": "https",
                "address": "https://edge-registered.example.test/execute",
            },
        },
        "snapshot": {
            "resourceId": "edge-registered",
            "availableSlots": 1,
            "utilization": 0.0,
            "observationSequence": 0,
        },
    }


async def test_v2_remote_resource_registration_requires_operator_and_returns_one_time_secret(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    body = json.dumps(_remote_registration_payload(), separators=(",", ":")).encode()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/agentos/v2/resources/register",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert denied.status_code == 401

        token = _operator_context()
        try:
            response = await client.post(
                "/agentos/v2/resources/register",
                content=body,
                headers={"content-type": "application/json"},
            )
            projection = await client.get("/agentos/v2/resources")
        finally:
            _trusted_user_context.reset(token)

    assert response.status_code == 201
    result = response.json()
    assert result["resourceId"] == "edge-registered"
    assert result["ownerScope"] == "tenant-a"
    assert len(result["secret"]) >= 32
    assert projection.status_code == 200
    assert result["secret"] not in projection.text


async def test_v2_remote_observation_requires_resource_signature_and_rejects_replay(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.resource_service.register(
        ResourceProfile(
            resourceId="edge-signed-api",
            resourceType=ResourceType.WORKER,
            deploymentTier="edge",
            capabilities=["vision.infer"],
            ownerScope="tenant-a",
            executionEndpoint={"protocol": "https", "address": "https://edge-signed-api.example.test/execute"},
        ),
        ResourceSnapshot(resourceId="edge-signed-api", availableSlots=1, utilization=0.0),
    )
    credential = runtime.resource_service.issue_credential("edge-signed-api")
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    path = "/agentos/v2/resources/edge-signed-api/observation"
    body = b'{"availableSlots":1,"observationSequence":1,"utilization":0.0}'
    timestamp = int(datetime.now(timezone.utc).timestamp())
    nonce = "signed-api-replay"
    signature = build_resource_signature(
        credential.secret,
        method="POST",
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    headers = {
        "content-type": "application/json",
        "X-Resource-Credential": credential.credential_id,
        "X-Resource-Timestamp": str(timestamp),
        "X-Resource-Nonce": nonce,
        "X-Resource-Signature": signature,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post(path, content=body, headers={"content-type": "application/json"})
        first = await client.post(path, content=body, headers=headers)
        replay = await client.post(path, content=body, headers=headers)

    assert missing.status_code == 401
    assert first.status_code == 200
    assert replay.status_code == 409


async def test_v2_remote_observation_rejects_expired_and_wrong_credentials(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.resource_service.register(
        ResourceProfile(
            resourceId="edge-auth-api",
            resourceType=ResourceType.WORKER,
            deploymentTier="edge",
            capabilities=["vision.infer"],
            ownerScope="tenant-a",
            executionEndpoint={"protocol": "https", "address": "https://edge-auth-api.example.test/execute"},
        ),
        ResourceSnapshot(resourceId="edge-auth-api", availableSlots=1, utilization=0.0),
    )
    credential = runtime.resource_service.issue_credential("edge-auth-api")
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    path = "/agentos/v2/resources/edge-auth-api/observation"
    body = b'{"availableSlots":1,"observationSequence":1,"utilization":0.0}'
    old_timestamp = int((datetime.now(timezone.utc) - timedelta(minutes=6)).timestamp())
    old_nonce = "expired-api"
    old_signature = build_resource_signature(
        credential.secret,
        method="POST",
        path=path,
        timestamp=old_timestamp,
        nonce=old_nonce,
        body=body,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expired = await client.post(path, content=body, headers={
            "content-type": "application/json",
            "X-Resource-Credential": credential.credential_id,
            "X-Resource-Timestamp": str(old_timestamp),
            "X-Resource-Nonce": old_nonce,
            "X-Resource-Signature": old_signature,
        })
        wrong = await client.post(path, content=body, headers={
            "content-type": "application/json",
            "X-Resource-Credential": "wrong",
            "X-Resource-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
            "X-Resource-Nonce": "wrong-credential-api",
            "X-Resource-Signature": "0" * 64,
        })

    assert expired.status_code == 401
    assert wrong.status_code == 401


async def test_v2_remote_resource_auth_distinguishes_unknown_resource_and_owner_scope(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    unknown_path = "/agentos/v2/resources/does-not-exist/observation"
    unknown_headers = {
        "content-type": "application/json",
        "X-Resource-Credential": "missing",
        "X-Resource-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "X-Resource-Nonce": "unknown-resource",
        "X-Resource-Signature": "0" * 64,
    }
    owner_mismatch = _remote_registration_payload()
    owner_mismatch["profile"]["ownerScope"] = "tenant-b"
    owner_body = json.dumps(owner_mismatch, separators=(",", ":")).encode()
    token = _operator_context()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unknown = await client.post(
                unknown_path,
                content=b'{"availableSlots":1,"observationSequence":1,"utilization":0.0}',
                headers=unknown_headers,
            )
            forbidden = await client.post(
                "/agentos/v2/resources/register",
                content=owner_body,
                headers={"content-type": "application/json"},
            )
    finally:
        _trusted_user_context.reset(token)

    assert unknown.status_code == 404
    assert forbidden.status_code == 403


async def test_v2_remote_resource_credential_rotation_is_scoped_atomic_and_invalidates_old_secret(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    runtime.resource_service.register(
        ResourceProfile(
            resourceId="edge-rotation",
            resourceType=ResourceType.WORKER,
            deploymentTier="edge",
            capabilities=["vision.infer"],
            ownerScope="tenant-a",
            executionEndpoint={"protocol": "https", "address": "https://edge-rotation.example.test/execute"},
        ),
        ResourceSnapshot(resourceId="edge-rotation", availableSlots=1, utilization=0.0),
    )
    previous = runtime.resource_service.issue_credential("edge-rotation")
    before_profile = runtime.resource_service.profile("edge-rotation")
    before_snapshot = runtime.resource_service.snapshot("edge-rotation")
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    path = "/agentos/v2/resources/edge-rotation/credential/rotate"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(path)
        viewer_token = _trusted_user_context.set(
            TrustedUserContext(user_id="viewer-1", subject="viewer-1", role="viewer", tenant_id="tenant-a")
        )
        try:
            viewer = await client.post(path)
        finally:
            _trusted_user_context.reset(viewer_token)
        wrong_tenant_token = _trusted_user_context.set(
            TrustedUserContext(user_id="operator-2", subject="operator-2", role="operator", tenant_id="tenant-b")
        )
        try:
            wrong_tenant = await client.post(path)
        finally:
            _trusted_user_context.reset(wrong_tenant_token)
        operator_token = _operator_context()
        try:
            rotated_response = await client.post(path)
            rotated_again_response = await client.post(path)
            projection = await client.get("/agentos/v2/resources")
        finally:
            _trusted_user_context.reset(operator_token)

        assert denied.status_code == 401
        assert viewer.status_code == 403
        assert wrong_tenant.status_code == 403

        first_rotated = rotated_response.json()
        second_rotated = rotated_again_response.json()
        assert rotated_response.status_code == 200
        assert rotated_again_response.status_code == 200
        assert first_rotated["credentialId"] != previous.credential_id
        assert first_rotated["secret"] != previous.secret
        assert second_rotated["credentialId"] != first_rotated["credentialId"]
        assert second_rotated["secret"] != first_rotated["secret"]

        body = b'{"availableSlots":1,"observationSequence":1,"utilization":0.0}'
        observation_path = "/agentos/v2/resources/edge-rotation/observation"
        old_nonce = "rotation-old-secret"
        old_timestamp = int(datetime.now(timezone.utc).timestamp())
        old_observation = await client.post(
            observation_path,
            content=body,
            headers={
                "content-type": "application/json",
                "X-Resource-Credential": previous.credential_id,
                "X-Resource-Timestamp": str(old_timestamp),
                "X-Resource-Nonce": old_nonce,
                "X-Resource-Signature": build_resource_signature(
                    previous.secret,
                    method="POST",
                    path=observation_path,
                    timestamp=old_timestamp,
                    nonce=old_nonce,
                    body=body,
                ),
            },
        )
        new_nonce = "rotation-new-secret"
        new_timestamp = int(datetime.now(timezone.utc).timestamp())
        new_observation = await client.post(
            observation_path,
            content=body,
            headers={
                "content-type": "application/json",
                "X-Resource-Credential": second_rotated["credentialId"],
                "X-Resource-Timestamp": str(new_timestamp),
                "X-Resource-Nonce": new_nonce,
                "X-Resource-Signature": build_resource_signature(
                    second_rotated["secret"],
                    method="POST",
                    path=observation_path,
                    timestamp=new_timestamp,
                    nonce=new_nonce,
                    body=body,
                ),
            },
        )

    assert old_observation.status_code == 401
    assert new_observation.status_code == 200
    assert runtime.resource_service.profile("edge-rotation") == before_profile
    after_snapshot = runtime.resource_service.snapshot("edge-rotation")
    assert after_snapshot.version == before_snapshot.version + 1
    assert after_snapshot.snapshot.observation_sequence == 1
    item = next(item for item in projection.json()["items"] if item["profile"]["resourceId"] == "edge-rotation")
    assert item["profile"] == before_profile.model_dump(by_alias=True, mode="json")


async def test_v2_create_mission_is_idempotent_and_rejects_fingerprint_conflicts(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator))
    payload = {
        "title": "Create through the application API",
        "workflowId": "api-workflow",
        "clientRequestId": "request-42",
        "input": {"contractText": "PRIVATE-CREATE-INPUT"},
    }

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/agentos/v2/missions", json=payload)
            assert first.status_code == 202
            assert "PRIVATE-CREATE-INPUT" not in first.text

            repeated = await client.post("/agentos/v2/missions", json=payload)
            assert repeated.status_code == 202
            assert repeated.json()["runId"] == first.json()["runId"]

            conflict = await client.post(
                "/agentos/v2/missions",
                json={**payload, "title": "Different request body"},
            )
            assert conflict.status_code == 409
            assert conflict.json() == {"detail": "clientRequestId conflict"}
    finally:
        await coordinator.shutdown()


async def test_v2_material_and_resource_projections_preserve_unknown_capacity(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("Resource projection", workflow_id="api-workflow")
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")
    runtime.trace_store.append(
        run,
        TraceEventType.MODEL_CALLED,
        step_id="report",
        payload={
            "provider": "test-provider",
            "model": "test-model",
            "latencyMs": 125,
            "finishReason": "stop",
            "outputPolicy": "API_CONTROLLED",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 40,
                "reasoning_tokens": 10,
                "cache_read_tokens": 25,
            },
            "capability": {
                "provider": "test-provider",
                "model": "test-model",
                "source": "unknown",
                "features": {},
            },
        },
    )
    runtime.workflow_store.save_run(run)
    artifact = runtime.content_manifest_store.create_manifest(
        kind=ContentKind.ARTIFACT,
        owner_type="run",
        owner_id=run.run_id,
        media_type="text/markdown",
    )
    runtime.content_manifest_store.append_fragment(
        manifest_id=artifact.manifest_id, sequence=0, content=b"# title\n"
    )
    runtime.content_manifest_store.append_fragment(
        manifest_id=artifact.manifest_id, sequence=1, content=b"\n## section\ncomplete"
    )
    artifact = runtime.content_manifest_store.seal_manifest(artifact.manifest_id)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    material_text = "完整材料" * 10000

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/agentos/v2/materials",
            json={"content": material_text, "mediaType": "text/plain"},
        )
        usage = await client.get(f"/agentos/v2/runs/{run.run_id}/resource-usage")
        calls = await client.get(f"/agentos/v2/runs/{run.run_id}/resource-usage/calls")
        invalid_cursor = await client.get(
            f"/agentos/v2/runs/{run.run_id}/resource-usage/calls", params={"cursor": "bad"}
        )
        artifacts = await client.get(f"/agentos/v2/runs/{run.run_id}/artifacts")
        fragments = await client.get(
            f"/agentos/v2/runs/{run.run_id}/artifacts/{artifact.manifest_id}/fragments",
            params={"pageSize": 1},
        )
        invalid_fragment_cursor = await client.get(
            f"/agentos/v2/runs/{run.run_id}/artifacts/{artifact.manifest_id}/fragments",
            params={"cursor": "bad"},
        )
        downloaded = await client.get(
            f"/agentos/v2/runs/{run.run_id}/artifacts/{artifact.manifest_id}/download"
        )

    assert created.status_code == 201
    manifest_id = created.json()["manifestId"]
    assert runtime.content_manifest_store.assemble(manifest_id).decode("utf-8") == material_text
    assert usage.status_code == 200
    body = usage.json()
    assert body["capability"].get("contextWindowTokens") is None
    assert body["capability"].get("maxOutputTokens") is None
    assert body["contextPressure"]["peak"] is None
    assert body["contextPressure"]["currentInputTokens"] == 100
    assert body["contextPressure"]["peakInputTokens"] == 100
    assert body["contextPressure"]["contextWindowTokens"] is None
    assert body["contextPressure"]["source"] == "unknown"
    assert body["usage"]["totalTokens"] == 140
    assert body["usage"]["reasoningTokens"] == 10
    assert calls.json()["items"][0]["outputPolicy"] == "api_controlled"
    assert invalid_cursor.status_code == 422
    assert artifacts.json()["items"][0]["checksum"] == artifact.checksum
    assert fragments.json()["nextCursor"] == "1"
    assert invalid_fragment_cursor.status_code == 422
    assert downloaded.content == b"# title\n\n## section\ncomplete"


async def test_v2_resource_projection_returns_context_pressure_details(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("Context pressure projection", workflow_id="api-workflow")
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")
    for index, input_tokens in enumerate((100, 150)):
        runtime.trace_store.append(
            run,
            TraceEventType.MODEL_CALLED,
            step_id=f"report-{index}",
            payload={
                "provider": "test-provider",
                "model": "test-model",
                "latencyMs": 125,
                "finishReason": "stop",
                "usage": {"input_tokens": input_tokens, "output_tokens": 40},
                "capability": {
                    "provider": "test-provider",
                    "model": "test-model",
                    "source": "adapter_declared",
                    "contextWindowTokens": 200,
                    "features": {},
                },
            },
        )
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/agentos/v2/runs/{run.run_id}/resource-usage")

    assert response.status_code == 200
    pressure = response.json()["contextPressure"]
    assert pressure["current"] == 0.75
    assert pressure["peak"] == 0.75
    assert pressure["currentInputTokens"] == 150
    assert pressure["peakInputTokens"] == 150
    assert pressure["contextWindowTokens"] == 200
    assert pressure["source"] == "usage_derived"


async def test_v2_create_mission_acknowledges_before_deferred_planning_finishes(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator))
    planning_started = threading.Event()
    release_planning = threading.Event()
    original = runtime._materialize_deferred_acg_run

    def block_planning(run_id: str):
        planning_started.set()
        if not release_planning.wait(timeout=5):
            raise TimeoutError("test did not release deferred planning")
        return original(run_id)

    runtime._materialize_deferred_acg_run = block_planning  # type: ignore[method-assign]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await asyncio.wait_for(
                client.post(
                    "/agentos/v2/missions",
                    json={"title": "Deferred planning", "workflowId": "api-workflow"},
                ),
                timeout=1,
            )
        assert response.status_code == 202
        assert await asyncio.to_thread(planning_started.wait, 1)
        prepared = runtime.get_status(response.json()["runId"])
        assert prepared.status is WorkflowStatus.PLANNING
        assert prepared.execution_state["planningDeferred"] is True
    finally:
        release_planning.set()
        await coordinator.shutdown()


async def test_v2_deferred_planning_preserves_identity_projection_alignment(tmp_path) -> None:
    runtime = _runtime(tmp_path, with_identity=True)
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/agentos/v2/missions",
                json={"title": "Deferred identity planning", "workflowId": "api-workflow"},
            )
            assert response.status_code == 202
            run_id = response.json()["runId"]
            for _ in range(200):
                run = runtime.get_status(run_id)
                if run.status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}:
                    break
                await asyncio.sleep(0.01)
            assert run.status is WorkflowStatus.COMPLETED

            projected = await client.get(f"/agentos/v2/runs/{run_id}")
            graph = await client.get(f"/agentos/v2/runs/{run_id}/graph")
            health = await client.get("/agentos/v2/identity/health")
        assert projected.status_code == 200
        assert projected.json()["identity"]["blueprintId"].startswith("blueprint_")
        assert graph.status_code == 200
        assert graph.json()["taskBindings"][0]["acgNodeId"] == "report"
        assert health.json()["unappliedEventCount"] == 0
    finally:
        await coordinator.shutdown()
        runtime.identity_lifecycle.lifecycle_service.close()


async def test_v2_rerun_creates_another_run_under_same_mission(tmp_path) -> None:
    runtime = _runtime(tmp_path, with_identity=True)
    task = runtime.create_mission(
        "Same Mission rerun",
        input={"taskGoal": "original goal", "planningDiversity": "stable"},
        workflow_id="api-workflow",
    )
    source = await runtime.start(task.mission_id, workflow_id="api-workflow")
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator))
    payload = {
        "workflowId": "api-workflow",
        "input": {"taskGoal": "updated run configuration", "planningDiversity": "stable"},
        "clientRequestId": "rerun-request-1",
        "sourceRunId": source.run_id,
        "rerunReason": "current_configuration",
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                f"/agentos/v2/missions/{task.mission_id}/runs",
                json=payload,
            )
            repeated = await client.post(
                f"/agentos/v2/missions/{task.mission_id}/runs",
                json=payload,
            )

        assert created.status_code == 202
        assert repeated.status_code == 202
        body = created.json()
        assert body["missionId"] == task.mission_id
        assert body["runId"] != source.run_id
        assert body["executionState"]["sourceRunId"] == source.run_id
        assert body["executionState"]["rerunReason"] == "current_configuration"
        assert repeated.json()["runId"] == body["runId"]
        rerun = runtime.get_status(body["runId"])
        assert rerun.input["taskGoal"] == "updated run configuration"
        assert rerun.execution_state["parentRunId"] == source.run_id
        assert rerun.execution_state["sourceRunId"] == source.run_id
        assert rerun.execution_state["rerunReason"] == "current_configuration"
        assert len(runtime.workflow_store.list_runs(mission_id=task.mission_id, page_size=20).items) == 2
    finally:
        await coordinator.shutdown()
        runtime.identity_lifecycle.lifecycle_service.close()


async def test_v2_deferred_planning_failure_is_classified_without_identity_backlog(tmp_path) -> None:
    runtime = _runtime(tmp_path, with_identity=True)
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator))

    def reject_plan(_run_id: str):
        raise TaskDecompositionError("private planner validation detail")

    runtime._materialize_deferred_acg_run = reject_plan  # type: ignore[method-assign]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/agentos/v2/missions",
                json={"title": "Deferred planning failure", "workflowId": "api-workflow"},
            )
            assert response.status_code == 202
            run_id = response.json()["runId"]
            for _ in range(200):
                run = runtime.get_status(run_id)
                if run.status is WorkflowStatus.FAILED:
                    break
                await asyncio.sleep(0.01)
            health = await client.get("/agentos/v2/identity/health")

        assert run.status is WorkflowStatus.FAILED
        assert run.error == {
            "code": "task_decomposition_failed",
            "message": "private planner validation detail",
        }
        assert health.json()["unappliedEventCount"] == 0
        assert not any(
            event["aggregate_id"] == run_id
            for event in runtime.workflow_store.list_outbox()
        )
    finally:
        await coordinator.shutdown()
        runtime.identity_lifecycle.lifecycle_service.close()


async def test_v2_create_mission_surfaces_safe_taskplan_validation_error(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    coordinator = RunExecutionCoordinator(runtime)
    app = FastAPI()
    app.include_router(create_router(runtime, coordinator))

    def reject_plan(*_args, **_kwargs):
        raise TaskDecompositionError("private planner validation detail")

    runtime.prepare_run = reject_plan  # type: ignore[method-assign]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/agentos/v2/missions",
                json={"title": "Planning contract failure", "workflowId": "api-workflow"},
            )
        assert response.status_code == 422
        assert response.json() == {
            "detail": "ACG task planning validation failed after one repair "
            "(TASK_PLAN_VALIDATION_FAILED)"
        }
        assert "private planner validation detail" not in response.text
    finally:
        await coordinator.shutdown()


async def test_v2_identity_queries_and_graph_read_from_identity_source(tmp_path) -> None:
    runtime = _runtime(tmp_path, with_identity=True)
    task = runtime.create_mission("Identity API source", workflow_id="api-workflow")
    run = await runtime.start(task.mission_id, workflow_id="api-workflow")
    repositories = runtime.identity_lifecycle.repositories
    attempts = repositories.attempts.list_for_run(run.run_id)
    execution = repositories.step_executions.list_for_attempt(
        attempts[0].attempt_id
    )[0]
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            tasks = await client.get("/agentos/v2/missions")
            health = await client.get("/agentos/v2/identity/health")
            detail = await client.get(f"/agentos/v2/missions/{task.mission_id}")
            history = await client.get(f"/agentos/v2/missions/{task.mission_id}/runs")
            projected_run = await client.get(f"/agentos/v2/runs/{run.run_id}")
            graph = await client.get(f"/agentos/v2/runs/{run.run_id}/graph")
            tree = await client.get(
                f"/agentos/v2/runs/{run.run_id}/execution-tree"
            )
            attempt_history = await client.get(
                f"/agentos/v2/runs/{run.run_id}/attempts",
                params={"taskId": attempts[0].task_id},
            )
            attempt = await client.get(
                f"/agentos/v2/attempts/{attempts[0].attempt_id}"
            )
            step = await client.get(
                f"/agentos/v2/step-executions/{execution.step_execution_id}"
            )
            provenance = await client.get(
                f"/agentos/v2/step-executions/{execution.step_execution_id}/provenance"
            )

        assert tasks.status_code == 200
        assert health.json()["status"] == "healthy"
        assert health.json()["unappliedEventCount"] == 0
        assert tasks.json()["source"] == "agentos-v2"
        assert tasks.json()["items"][0]["missionId"] == task.mission_id
        assert tasks.json()["items"][0]["latestRunId"] == run.run_id
        assert tasks.json()["items"][0]["runCount"] == 1
        assert detail.json()["tasks"][0]["taskId"].startswith("task_")
        assert history.json()["runs"][0]["runId"] == run.run_id
        assert projected_run.json()["identity"]["blueprintId"].startswith("blueprint_")
        assert graph.json()["source"] == "agentos-v2"
        assert graph.json()["blueprintId"].startswith("blueprint_")
        assert graph.json()["taskBindings"][0]["acgNodeId"] == "report"
        assert tree.json()["nodes"][0]["attempts"][0]["attempt"]["attemptId"] == attempts[0].attempt_id
        assert attempt_history.json()["attempts"][0]["attempt"]["attemptId"] == attempts[0].attempt_id
        assert attempt.json()["executionBinding"]["attemptId"] == attempts[0].attempt_id
        assert step.json()["origin"]["mission"]["missionId"] == task.mission_id
        assert provenance.json()["stepExecutionId"] == execution.step_execution_id
    finally:
        runtime.identity_lifecycle.lifecycle_service.close()


async def test_v2_failed_mission_can_be_deleted_and_stale_deleted_rows_are_hidden(tmp_path) -> None:
    runtime = _runtime(tmp_path, with_identity=True)
    task = runtime.create_mission("Failed mission can be deleted", workflow_id="api-workflow")
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")
    run.status = WorkflowStatus.FAILED
    runtime.workflow_store.save_run(run)
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            listed = await client.get("/agentos/v2/missions")
            deleted = await client.delete(f"/agentos/v2/missions/{task.mission_id}")
            listed_after_delete = await client.get("/agentos/v2/missions")
            repeated = await client.delete(f"/agentos/v2/missions/{task.mission_id}")

        assert listed.status_code == 200
        assert listed.json()["items"][0]["missionId"] == task.mission_id
        assert deleted.status_code == 200
        assert deleted.json()["recordState"] == MissionRecordState.DELETED.value
        assert listed_after_delete.status_code == 200
        assert task.mission_id not in {
            item["missionId"] for item in listed_after_delete.json()["items"]
        }
        assert repeated.status_code == 200
        assert repeated.json()["recordState"] == MissionRecordState.DELETED.value
    finally:
        runtime.identity_lifecycle.lifecycle_service.close()


async def test_v2_cancel_endpoint_stops_active_run_cleanly_and_is_idempotent(tmp_path) -> None:
    """取消端点必须真正终止活跃运行：终态干净收敛，且重复取消保持幂等。"""
    gated = _GatedApiAgent(AgentProfile(agentName="api-agent", domain="general"))
    runtime = _runtime(tmp_path, agent=gated)
    task = runtime.create_mission("cancel endpoint probe", workflow_id="api-workflow")
    _, prepared = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")

    exec_task = asyncio.create_task(runtime.execute_prepared_run(prepared.run_id))
    await asyncio.wait_for(gated.arrived.wait(), timeout=5)

    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post("/agentos/v2/runs/run_does_not_exist/cancel")
        assert missing.status_code == 404

        cancelled = await client.post(f"/agentos/v2/runs/{prepared.run_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        # 执行体必须在闸门打开后干净收敛为 CANCELLED，而不是崩溃或继续跑完。
        gated.gate.set()
        result = await asyncio.wait_for(exec_task, timeout=10)
        assert result.status is WorkflowStatus.CANCELLED

        again = await client.post(f"/agentos/v2/runs/{prepared.run_id}/cancel")
        assert again.status_code == 200
        assert again.json()["status"] == "cancelled"

        detail = await client.get(f"/agentos/v2/runs/{prepared.run_id}")
        assert detail.json()["status"] == "cancelled"


async def test_v2_cancel_endpoint_rejects_completed_run_as_conflict(tmp_path) -> None:
    """已完成/被取代的运行不可再取消：端点返回安全的固定冲突提示。"""
    runtime = _runtime(tmp_path)
    task = runtime.create_mission("cancel conflict probe", workflow_id="api-workflow")
    run = await runtime.start(task.mission_id, workflow_id="api-workflow")
    assert run.status is WorkflowStatus.COMPLETED

    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/agentos/v2/runs/{run.run_id}/cancel")
        assert response.status_code == 409
        assert response.json()["detail"] == "run cannot be cancelled"

        detail = await client.get(f"/agentos/v2/runs/{run.run_id}")
        assert detail.json()["status"] == "completed"


async def test_resource_usage_declares_model_before_first_call(tmp_path) -> None:
    """零调用阶段资源详情也必须能声明模型与策略（不再显示 API 未声明）。

    历史缺陷：capability 仅从已完成调用的审计投影推导，任务开始时整条资源
    横幅只剩占位符，用户要等到第一个节点跑完才知道用的是什么模型。
    """
    from types import SimpleNamespace

    from contracts.capability import ModelCapabilityEnvelope

    runtime = _runtime(tmp_path)
    envelope = ModelCapabilityEnvelope.unknown(
        provider="deepseek", model="deepseek-v4-flash"
    ).model_copy(update={"max_output_tokens": 384000, "context_window_tokens": 1000000})
    runtime.set_model_runtime(SimpleNamespace(describe_model=lambda: envelope))

    task = runtime.create_mission("declared probe", workflow_id="api-workflow")
    _, run = runtime.prepare_run(task.mission_id, workflow_id="api-workflow")
    assert run.status is WorkflowStatus.PENDING

    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/agentos/v2/runs/{run.run_id}/resource-usage")

    assert response.status_code == 200
    body = response.json()
    assert body["usage"]["callCount"] == 0
    assert body["capability"]["model"] == "deepseek-v4-flash"
    assert body["capability"]["maxOutputTokens"] == 384000
    assert body["capabilitySource"] == "declared"
    assert body["outputPolicy"] == "catalog_default"

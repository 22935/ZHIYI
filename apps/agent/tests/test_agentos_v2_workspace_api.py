from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.agentos_v2 import create_router
from app.execution.coordinator import RunExecutionCoordinator
from components.content import SQLiteContentManifestStore
from contracts.content import ContentKind
from contracts.planning import PlannedTask, TaskPlan
from contracts.resource import ExecutionBinding as RuntimeExecutionBinding, RuntimeKind
from contracts.workflow import RuntimeRunRecord, WorkflowStatus
from domain.models import RunStatus
from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge, PlannerIdentityBridge
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.models import ACGBlueprint, StepNode
from support.acg.planning import ACGResourcePlan, AgentBindingSpec


@pytest.mark.asyncio
async def test_workspace_api_projects_read_model_without_artifact_body(tmp_path):
    storage = SQLiteV2Storage(tmp_path / "identity.sqlite3")
    repositories = SQLiteV2Repositories(storage)
    service = AcgIdentityLifecycleService(repositories)
    content = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    bridge = IdentityProjectionBridge(service, repositories, content)
    try:
        mission = service.create_mission(user_id="user-1", goal="Workspace API")
        task = PlannerIdentityBridge(service).record_task_plan(TaskPlan(
            missionId=mission.mission_id,
            planVersion=1,
            nodes=(PlannedTask(
                key="api_step",
                title="API step",
                objective="Produce an API artifact",
                capabilityRequirements=("artifact_generation",),
                logicalRole="deliver",
            ),),
        ))["api_step"]
        blueprint = bridge.register_blueprint(
            mission_id=mission.mission_id,
            version=1,
            runtime_blueprint=ACGBlueprint(
                graphId="acg_workspace_api",
                missionId=mission.mission_id,
                nodes=[StepNode(
                    nodeId="api-step-node",
                    name="API step",
                    capability="artifact_generation",
                    logicalRole="deliver",
                )],
                resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(
                    stepId="api-step-node", plannedAgentId="api-agent",
                ),)),
            ),
            task_bindings={task.task_id: "api-step-node"},
        )
        run = service.create_run(
            mission_id=mission.mission_id,
            blueprint_id=blueprint.blueprint_id,
            metadata={"taskPlanVersion": 1},
        )
        attempt = service.create_attempt(run_id=run.run_id, task_id=task.task_id)
        bridge.record_scheduling_binding(
            attempt_id=attempt.attempt_id,
            runtime_binding=RuntimeExecutionBinding(
                bindingId="binding:workspace-api",
                runId=run.run_id,
                stepId="api-step-node",
                attemptId=attempt.attempt_id,
                resourceId="api-agent",
                runtimeKind=RuntimeKind.EXECUTION_BACKEND,
                snapshotVersion=1,
            ),
            agent_id="api-agent",
            model_id="api-model",
        )
        execution = bridge.start_execution(
            service.create_context(run.run_id),
            input={"acgNodeId": "api-step-node"},
        )
        manifest = content.create_from_bytes(
            content=b"secret artifact body",
            kind=ContentKind.ARTIFACT,
            owner_type="run",
            owner_id=run.run_id,
            media_type="text/markdown",
        )
        bridge.on_step_succeeded(
            run_id=run.run_id,
            attempt_id=attempt.attempt_id,
            step_execution_id=execution.step_execution_id,
            result={"artifacts": [{
                "artifactKey": "primary",
                "title": "API final",
                "type": "report",
                "manifestId": manifest.manifest_id,
                "checksum": manifest.checksum,
            }]},
        )
        repositories.runs.update_status(run.run_id, RunStatus.SUCCEEDED)

        runtime = SimpleNamespace(
            identity_lifecycle=bridge,
            workflow_store=SimpleNamespace(list_run_overviews=lambda **_kwargs: SimpleNamespace(items=[], total=0)),
            content_manifest_store=content,
            get_status=lambda run_id: RuntimeRunRecord(
                run_id=run_id,
                mission_id=mission.mission_id,
                workflow_id="workspace-test", domain="general", runtime_engine="acg",
                status=WorkflowStatus.COMPLETED,
                input={},
                execution_state={
                    "outputRefs": {"api-step-node": "output:api-step"},
                    "outputSummaries": {"api-step-node": "API step completed"},
                },
            ),
        )
        app = FastAPI()
        app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                f"/agentos/v2/missions/{mission.mission_id}/workspace",
                params={"runId": run.run_id},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["activeRun"]["runId"] == run.run_id
        assert payload["entries"]
        artifact = next(item for item in payload["entries"] if item["kind"] == "artifact")
        assert artifact["artifactId"].startswith("artifact_")
        assert artifact["contentRef"] == manifest.manifest_id
        assert "content" not in artifact
        graph = next(item for item in payload["entries"] if item["kind"] == "graph")
        assert graph["graphId"] == blueprint.graph_id
        assert payload["graphNodes"][0]["semanticTaskKey"] == "api_step"
        task_entry = next(item for item in payload["entries"] if item["kind"] == "task")
        assert task_entry["metadata"]["outputRef"] == "output:api-step"
        assert task_entry["metadata"]["outputSummary"] == "API step completed"
    finally:
        content.close()
        service.close()


@pytest.mark.asyncio
async def test_workspace_api_projects_runtime_shell_while_identity_run_is_pending(tmp_path):
    storage = SQLiteV2Storage(tmp_path / "identity-shell.sqlite3")
    repositories = SQLiteV2Repositories(storage)
    service = AcgIdentityLifecycleService(repositories)
    content = SQLiteContentManifestStore(tmp_path / "content-shell.sqlite3")
    bridge = IdentityProjectionBridge(service, repositories, content)
    try:
        mission = service.create_mission(user_id="user-1", goal="Planning shell")
        now = datetime.now(timezone.utc)
        runtime_run = SimpleNamespace(
            run_id="run_planning_shell",
            mission_id=mission.mission_id,
            status=WorkflowStatus.PLANNING,
            lifecycle_phase=None,
            error=None,
            created_at=now,
            updated_at=now,
            input={},
        )
        runtime = SimpleNamespace(
            identity_lifecycle=bridge,
            content_manifest_store=content,
            workflow_store=SimpleNamespace(
                list_run_overviews=lambda **_kwargs: SimpleNamespace(items=[runtime_run], total=1, page_size=100),
            ),
            get_status=lambda run_id: runtime_run if run_id == runtime_run.run_id else (_ for _ in ()).throw(KeyError(run_id)),
        )
        app = FastAPI()
        app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                f"/agentos/v2/missions/{mission.mission_id}/workspace",
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["activeRun"]["runId"] == runtime_run.run_id
        assert payload["activeRun"]["status"] == "pending"
        assert payload["diagnostics"][0]["code"] == "PLANNING_PROJECTION_PENDING"
        assert payload["diagnostics"][0]["details"]["runtimeStatus"] == "planning"
    finally:
        content.close()
        service.close()


@pytest.mark.asyncio
async def test_workspace_api_prefers_terminal_runtime_status_over_stale_identity_run(tmp_path):
    storage = SQLiteV2Storage(tmp_path / "identity-terminal-runtime.sqlite3")
    repositories = SQLiteV2Repositories(storage)
    service = AcgIdentityLifecycleService(repositories)
    content = SQLiteContentManifestStore(tmp_path / "content-terminal-runtime.sqlite3")
    bridge = IdentityProjectionBridge(service, repositories, content)
    try:
        mission = service.create_mission(user_id="user-1", goal="Terminal runtime status")
        task = service.create_task(
            mission_id=mission.mission_id,
            title="Runtime task",
            objective="Observe terminal status",
        )
        blueprint = service.create_blueprint(
            mission_id=mission.mission_id,
            version=1,
            graph_id="acg_terminal_runtime",
            graph={"nodes": [], "edges": []},
        )
        run = service.create_run(
            mission_id=mission.mission_id,
            blueprint_id=blueprint.blueprint_id,
        )
        repositories.runs.update_status(run.run_id, RunStatus.RUNNING)
        now = datetime.now(timezone.utc)
        runtime_run = RuntimeRunRecord(
            run_id=run.run_id,
            mission_id=mission.mission_id,
            workflow_id="workspace-test", domain="general", runtime_engine="acg",
            status=WorkflowStatus.FAILED,
            updated_at=now,
            execution_state={},
        )
        runtime = SimpleNamespace(
            identity_lifecycle=bridge,
            workflow_store=SimpleNamespace(list_run_overviews=lambda **_kwargs: SimpleNamespace(items=[], total=0)),
            content_manifest_store=content,
            get_status=lambda run_id: runtime_run if run_id == run.run_id else (_ for _ in ()).throw(KeyError(run_id)),
        )
        app = FastAPI()
        app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                f"/agentos/v2/missions/{mission.mission_id}/workspace",
                params={"runId": run.run_id},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["activeRun"]["status"] == "failed"
        assert next(item for item in payload["runs"] if item["runId"] == run.run_id)["status"] == "failed"
    finally:
        content.close()
        service.close()

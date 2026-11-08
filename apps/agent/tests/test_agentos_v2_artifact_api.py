from __future__ import annotations

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
from runtime import (
    AcgIdentityLifecycleService,
    IdentityProjectionBridge,
    PlannerIdentityBridge,
)
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.acg.models import ACGBlueprint, StepNode
from support.acg.planning import ACGResourcePlan, AgentBindingSpec
from contracts.workflow import RuntimeRunRecord


@pytest.mark.asyncio
async def test_v2_artifact_api_is_binding_first_and_manifest_backed(tmp_path):
    repositories = SQLiteV2Repositories(SQLiteV2Storage(tmp_path / "identity.sqlite3"))
    service = AcgIdentityLifecycleService(repositories)
    content = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    bridge = IdentityProjectionBridge(service, repositories, content)
    try:
        mission = service.create_mission(user_id="user-1", goal="API artifact query")
        task = PlannerIdentityBridge(service).record_task_plan(TaskPlan(
            missionId=mission.mission_id,
            nodes=(PlannedTask(
                key="api_artifact_step",
                title="生成 API 产物",
                objective="生成可查询的产物",
            ),),
        ))["api_artifact_step"]
        blueprint = bridge.register_blueprint(
            mission_id=mission.mission_id,
            version=1,
            runtime_blueprint=ACGBlueprint(
                graphId="acg_api_artifact",
                missionId=mission.mission_id,
                nodes=[StepNode(
                    nodeId="api-node",
                    name="生成 API 产物",
                )],
                resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(
                    stepId="api-node", plannedAgentId="api-agent",
                ),)),
            ),
            task_bindings={task.task_id: "api-node"},
        )
        run = service.create_run(
            mission_id=mission.mission_id, blueprint_id=blueprint.blueprint_id
        )
        attempt = service.create_attempt(run_id=run.run_id, task_id=task.task_id)
        bridge.record_scheduling_binding(
            attempt_id=attempt.attempt_id,
            runtime_binding=RuntimeExecutionBinding(
                bindingId="binding:api-artifact",
                runId=run.run_id,
                stepId="api-node",
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
            input={"acgNodeId": "api-node"},
        )
        manifest = content.create_from_bytes(
            content=b"# API artifact",
            kind=ContentKind.ARTIFACT,
            owner_type="run",
            owner_id=run.run_id,
            media_type="text/markdown",
        )
        bridge.on_step_succeeded(
            run_id=run.run_id,
            attempt_id=attempt.attempt_id,
            step_execution_id=execution.step_execution_id,
            result={
                "artifacts": [{
                    "artifactKey": "primary",
                    "title": "API artifact",
                    "type": "report",
                    "manifestId": manifest.manifest_id,
                    "checksum": manifest.checksum,
                }],
            },
        )

        fake_runtime = SimpleNamespace(
            identity_lifecycle=bridge,
            content_manifest_store=content,
            get_status=lambda run_id: RuntimeRunRecord(
                run_id=run_id,
                mission_id=run.mission_id,
                workflow_id="artifact-test", domain="general", runtime_engine="acg",
                input={},
            ),
        )
        app = FastAPI()
        app.include_router(create_router(fake_runtime, RunExecutionCoordinator(fake_runtime)))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            listed = await client.get(f"/agentos/v2/runs/{run.run_id}/artifacts")
            detail = await client.get(
                f"/agentos/v2/runs/{run.run_id}/artifacts/{manifest.manifest_id}"
            )

        assert listed.status_code == 200
        item = listed.json()["items"][0]
        assert item["artifactId"].startswith("artifact_")
        assert item["manifestId"] == manifest.manifest_id
        assert item["semanticTaskKey"] == "api_artifact_step"
        assert item["artifactKey"] == "primary"
        assert item["disposition"] == "GENERATED"
        assert detail.status_code == 200
        assert detail.json()["artifactId"] == item["artifactId"]
    finally:
        content.close()
        service.close()

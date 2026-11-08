"""HTTP semantic projections over temporary Workflow and Identity databases."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agentos_v2 import create_router
from app.security.internal_auth import TrustedUserContext, _trusted_user_context
from components.mission_manager.semantic_service import MissionSemanticService
from components.mission_manager.semantic_resolver import MissionSemanticResolver
from contracts.mission_semantic import MissionSemanticRequest, SemanticPrincipal
from contracts.workflow import MissionRecordState, RunRecordState, RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus
from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore


@pytest.fixture
def boundary(tmp_path):
    identity = AcgIdentityLifecycleService(SQLiteV2Repositories(SQLiteV2Storage(tmp_path / "identity.sqlite3")))
    mission = identity.create_mission(user_id="owner", goal="Identity compatibility goal", metadata={"tenantId": "tenant"})
    store = SQLiteWorkflowStore(tmp_path / "workflow.sqlite3", enable_mission_semantics=True)
    store.save_mission(RuntimeMissionRecord(missionId=mission.mission_id, title="legacy title",
        input={"objective": "raw goal", "authenticatedUserId": "owner", "authenticatedTenantId": "tenant"}))
    principal = SemanticPrincipal(actorId="owner", tenantId="tenant")
    service = MissionSemanticService(store=store, authorize=lambda p, m, action: p == principal and m == mission.mission_id)
    runtime = SimpleNamespace(workflow_store=store, mission_semantic_service=service,
        identity_lifecycle=IdentityProjectionBridge(identity, identity.repositories),
        get_status=store.get_run, get_status_cached=store.get_run)
    app = FastAPI()
    app.include_router(create_router(runtime, SimpleNamespace()))
    token = _trusted_user_context.set(TrustedUserContext(user_id="owner", tenant_id="tenant", subject="owner", role="user"))
    try:
        yield TestClient(app), runtime, service, principal, mission.mission_id
    finally:
        _trusted_user_context.reset(token)
        identity.close()


def commit(service, principal, mission, revision=0, op="one", objective="formal objective"):
    return service.commit(principal, MissionSemanticRequest(missionId=mission, operationId=op,
        expectedMissionRevision=revision, objective=objective, constraints=[]))


def test_formal_goal_and_deferred_historical_run_basis_are_distinct(boundary):
    client, runtime, service, principal, mission = boundary
    commit(service, principal, mission)
    basis = MissionSemanticResolver.freeze(MissionSemanticResolver.resolve(service.get_effective_snapshot(principal, mission)))
    run = RuntimeRunRecord(runId="run_test", missionId=mission, workflowId="w", domain="general", runtimeEngine="acg",
        status=WorkflowStatus.PLANNING, input={"authenticatedUserId": "owner", "authenticatedTenantId": "tenant"},
        executionState={"missionIntentBasis": basis.model_dump(by_alias=True, mode="json")})
    runtime.workflow_store.save_run(run)
    commit(service, principal, mission, 1, "two", "current formal objective")
    response = client.get(f"/agentos/v2/missions/{mission}/workspace", params={"runId": run.run_id})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["missionDisplay"]["objective"] == "current formal objective"
    assert data["missionSemanticView"]["missionRevision"] == 2
    assert data["selectedRunBasis"]["sourceRevision"] == 1
    assert data["selectedRunBasis"]["objective"] == "formal objective"
    assert data["selectedRunBasisStatus"] == "BOUND"
    assert data["mission"]["goal"] == "Identity compatibility goal"
    assert any(e["entryId"] == "overview:mission.md" for e in data["entries"])
    assert runtime.workflow_store.get_run(run.run_id) == run


def test_uninitialized_read_is_compatible_and_does_not_initialize(boundary):
    client, runtime, _, _, mission = boundary
    data = client.get(f"/agentos/v2/missions/{mission}/workspace").json()
    assert data["missionSemanticView"]["semanticStatus"] == "UNINITIALIZED"
    assert data["missionDisplay"]["sourceType"] == "IDENTITY_COMPATIBILITY"
    assert data["selectedRunBasisStatus"] == "NO_RUN"
    assert runtime.workflow_store.get_semantic_snapshot(mission).state is None


@pytest.mark.parametrize("actor,tenant", [(None, None), ("intruder", "tenant"), ("owner", "other")])
def test_current_permissions_required_even_for_compatible_display(boundary, actor, tenant):
    client, _, _, _, mission = boundary
    value = TrustedUserContext(user_id=actor, tenant_id=tenant, subject=actor, role="user") if actor else None
    token = _trusted_user_context.set(value)
    try:
        assert client.get(f"/agentos/v2/missions/{mission}/workspace").status_code == 403
    finally:
        _trusted_user_context.reset(token)


def test_corrupt_snapshot_fails_closed_instead_of_showing_identity_goal(boundary, monkeypatch):
    client, _, service, _, mission = boundary
    def fail(*_):
        raise ValueError("corrupt semantic state")
    monkeypatch.setattr(service, "get_effective_snapshot", fail)
    response = client.get(f"/agentos/v2/missions/{mission}/workspace")
    assert response.status_code == 503 and "Identity compatibility goal" not in response.text


def test_corrupt_run_basis_does_not_fall_back_to_current_goal(boundary, monkeypatch):
    client, runtime, service, principal, mission = boundary
    commit(service, principal, mission)
    basis = MissionSemanticResolver.freeze(MissionSemanticResolver.resolve(service.get_effective_snapshot(principal, mission)))
    run = RuntimeRunRecord(runId="run_corrupt", missionId=mission, workflowId="w", domain="general", runtimeEngine="acg",
        status=WorkflowStatus.PLANNING, executionState={"missionIntentBasis": basis.model_dump(by_alias=True, mode="json")})
    runtime.workflow_store.save_run(run)
    corrupt = run.model_copy(deep=True)
    corrupt.execution_state["missionIntentBasis"]["objective"] = "tampered objective"
    monkeypatch.setattr(runtime.workflow_store, "get_run", lambda _: corrupt)
    response = client.get(f"/agentos/v2/missions/{mission}/workspace", params={"runId": run.run_id})
    assert response.status_code == 503 and "formal objective" not in response.text


def test_disabled_semantics_preserves_legacy_api_shape(boundary):
    client, runtime, _, _, mission = boundary
    runtime.mission_semantic_service = None
    response = client.get(f"/agentos/v2/missions/{mission}/workspace")
    assert response.status_code == 200
    assert "missionSemanticView" not in response.json() and "missionDisplay" not in response.json()


def test_old_unbound_run_does_not_acquire_current_semantics(boundary):
    client, runtime, service, principal, mission = boundary
    run = RuntimeRunRecord(runId="run_unbound", missionId=mission, workflowId="w", domain="general", runtimeEngine="acg",
        status=WorkflowStatus.PLANNING)
    runtime.workflow_store.save_run(run)
    commit(service, principal, mission)
    response = client.get(f"/agentos/v2/missions/{mission}/workspace", params={"runId": run.run_id})
    assert response.status_code == 200
    assert response.json()["selectedRunBasisStatus"] == "UNBOUND"
    assert "selectedRunBasis" not in response.json()
    assert runtime.workflow_store.get_run(run.run_id).execution_state == {}


def test_permissions_are_rechecked_after_a_successful_read(boundary):
    client, _, service, _, mission = boundary
    assert client.get(f"/agentos/v2/missions/{mission}/workspace").status_code == 200
    service.authorize = lambda *_: False
    assert client.get(f"/agentos/v2/missions/{mission}/workspace").status_code == 403


def test_soft_deleted_mission_cannot_expose_preserved_history(boundary):
    client, runtime, service, principal, mission = boundary
    commit(service, principal, mission)
    runtime.workflow_store.set_mission_record_state(mission, MissionRecordState.DELETED)
    assert client.get(f"/agentos/v2/missions/{mission}/workspace").status_code == 404
    assert len(runtime.workflow_store.list_semantic_commits(mission)) == 1


def test_soft_deleted_selected_run_is_not_readable(boundary):
    client, runtime, _, _, mission = boundary
    run = RuntimeRunRecord(runId="run_deleted", missionId=mission, workflowId="w", domain="general", runtimeEngine="acg",
        status=WorkflowStatus.COMPLETED, recordState=RunRecordState.DELETED)
    runtime.workflow_store.save_run(run)
    assert client.get(f"/agentos/v2/missions/{mission}/workspace", params={"runId": run.run_id}).status_code == 404


@pytest.mark.parametrize("runtime_available", [True, False])
def test_identity_graph_projection_uses_runtime_basis_or_explicitly_reports_missing_record(boundary, runtime_available):
    client, runtime, service, principal, mission = boundary
    commit(service, principal, mission)
    basis = MissionSemanticResolver.freeze(MissionSemanticResolver.resolve(service.get_effective_snapshot(principal, mission)))
    identity = runtime.identity_lifecycle.lifecycle_service
    identity.create_task(mission_id=mission, title="Derived task", objective="local task scope")
    blueprint = identity.create_blueprint(mission_id=mission, version=1, graph_id="graph_workspace",
        graph={"nodes": [], "edges": []})
    selected = identity.create_run(mission_id=mission, blueprint_id=blueprint.blueprint_id)
    if runtime_available:
        runtime.workflow_store.save_run(RuntimeRunRecord(runId=selected.run_id, missionId=mission,
            workflowId="w", domain="general", runtimeEngine="acg", executionState={
                "missionIntentBasis": basis.model_dump(by_alias=True, mode="json")}))
    response = client.get(f"/agentos/v2/missions/{mission}/workspace", params={"runId": selected.run_id})
    assert response.status_code == 200, response.text
    assert response.json()["selectedRunBasisStatus"] == ("BOUND" if runtime_available else "RUNTIME_UNAVAILABLE")
    assert response.json()["missionDisplay"]["objective"] == "formal objective"
    assert runtime.workflow_store.list_semantic_commits(mission)[0].mission_revision == 1

"""Pre-04.2 persisted payloads remain readable without fabricated settlement."""
import asyncio
import importlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from app.execution.wiring import build_default_runtime, close_runtime
from test_mission_semantic_commands import application, create, HEADERS
from test_execution_runtime_application_wiring import _environment


@pytest.mark.parametrize("module_name,test_name", [
    ("test_general_golden_recovery", "test_golden_workflow_integration_survives_two_ai_service_restarts"),
])
async def test_golden_failure_releases_runtime_lock(module_name, test_name, tmp_path, monkeypatch):
    module = importlib.import_module(module_name)
    entered = []
    def build(**kwargs):
        runtime = build_default_runtime(**kwargs)
        async def fail(*args, **kwargs):
            entered.append(runtime)
            raise RuntimeError("injected planning failure")
        runtime.start = fail
        return runtime
    monkeypatch.setattr(module, "build_default_runtime", build)
    with pytest.raises(RuntimeError, match="injected planning failure"):
        await getattr(module, test_name)(tmp_path / "failed")
    assert len(entered) == 1
    # A different database can only be opened if the failed test released ownership.
    next_runtime = build_default_runtime(environment=_environment(tmp_path / "next"))
    try:
        assert tuple(next_runtime.workflow_store.list_non_terminal_runs()) == ()
    finally:
        close_runtime(next_runtime)


@pytest.mark.parametrize("status", ["completed", "cancelled", "pending", "running"])
def test_old_payload_survives_application_restart_and_cancel(status, tmp_path, monkeypatch):
    env = {**_environment(tmp_path), "AGENTOS_MISSION_SEMANTIC_CONVERGENCE": "true",
           "AGENTOS_ALLOW_LEGACY_MISSION_INTENT": "false"}
    from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
    SQLiteWorkflowStore(env["AGENTOS_WORKFLOW_DB_PATH"], enable_mission_semantics=True)
    app = application(env)
    with TestClient(app, headers=HEADERS) as client:
        runtime, coordinator, agent = app.state.boundary
        async def hold(_):
            return False
        if status != "completed":
            monkeypatch.setattr(coordinator, "submit", hold)
        created = create(client)
        run_id = created["runId"]
        if status == "completed":
            async def finish():
                await asyncio.shield(coordinator._tasks[run_id])
            client.portal.call(finish)
        elif status == "cancelled":
            assert client.post(f"/agentos/v2/runs/{run_id}/cancel", json={}).status_code == 200
        with sqlite3.connect(env["AGENTOS_WORKFLOW_DB_PATH"]) as conn:
            old = json.loads(conn.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()[0])
            # Match the pre-04.2 representation: no taskSettlement key.
            old["executionState"].pop("taskSettlement", None)
            if status == "running":
                old["status"] = "running"
            conn.execute("UPDATE runs SET payload=?,status=? WHERE run_id=?", (json.dumps(old),old["status"],run_id))
        with sqlite3.connect(env["AGENTOS_WORKFLOW_DB_PATH"]) as conn:
            before_outbox = conn.execute("SELECT event_id,event_type,aggregate_id,payload FROM lifecycle_outbox ORDER BY event_id").fetchall()
    reopened = application(env)
    with TestClient(reopened, headers=HEADERS) as client:
        runtime, coordinator, agent = reopened.state.boundary
        loaded = runtime.workflow_store.get_run(run_id)
        assert loaded.model_dump(by_alias=True, mode="json") == old
        assert "taskSettlement" not in loaded.execution_state
        with sqlite3.connect(env["AGENTOS_WORKFLOW_DB_PATH"]) as conn:
            assert conn.execute("SELECT event_id,event_type,aggregate_id,payload FROM lifecycle_outbox ORDER BY event_id").fetchall() == before_outbox
        assert agent.calls == []
        if status in {"pending", "running"}:
            revision = client.get(f"/agentos/v2/runs/{run_id}").json()["actionCapabilities"]["runtimeRevision"]
            response = client.post(f"/agentos/v2/runs/{run_id}/cancel", json={"expectedRuntimeRevision": revision})
            assert response.status_code == 200, response.text
            final = runtime.workflow_store.get_run(run_id)
            assert final.status.value == "cancelled"
            assert final.completed_step_ids == loaded.completed_step_ids
            assert final.output == loaded.output
            assert [e.event_id for e in final.trace][:len(loaded.trace)] == [e.event_id for e in loaded.trace]
            once = final.model_dump(by_alias=True, mode="json")
            assert client.post(f"/agentos/v2/runs/{run_id}/cancel", json={}).status_code == 409
            assert runtime.cancel(run_id).model_dump(by_alias=True, mode="json") == once
            assert runtime.workflow_store.get_run(run_id).model_dump(by_alias=True, mode="json") == once
        closed = client.portal.call(coordinator.startup)
        assert run_id not in closed
        assert agent.calls == []
        assert "taskSettlement" not in runtime.workflow_store.get_run(run_id).execution_state
        assert coordinator._tasks == {}

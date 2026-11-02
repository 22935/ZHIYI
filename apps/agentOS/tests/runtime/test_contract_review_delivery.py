"""C1 audit regressions using real native execution and the production router."""
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from examples.contract_review import OWNER, WORKFLOW_ID, open_runtime, prepare_revision, result_projection
from contracts.mission_semantic import MissionSemanticRequest
from contracts.workflow import RunRecordState


@pytest.fixture(scope="module")
def delivery(tmp_path_factory):
    rt, agent, rid = asyncio.run(prepare_revision(tmp_path_factory.mktemp("c1-delivery") / "sample"))
    run = asyncio.run(rt.execute_prepared_run(rid))
    assert run.status.value == "completed" and agent.calls == ["A", "B", "C", "D"]
    artifact = result_projection(rt, rid)["artifacts"][0]["artifact"]
    return rt, rid, artifact


@pytest.fixture
def client_factory(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "agent"))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.agentos_v2 import create_router
    from app.execution.coordinator import RunExecutionCoordinator
    from app.security.internal_auth import InternalServiceAuthMiddleware

    def make(rt, *, actor=OWNER.actor_id, tenant=OWNER.tenant_id, token=True):
        app = FastAPI()
        secret = "c1-delivery-regression-service-token-00001"
        app.add_middleware(InternalServiceAuthMiddleware, token=secret)
        app.include_router(create_router(rt, RunExecutionCoordinator(rt)))
        headers = {"x-authenticated-user-id": actor, "x-authenticated-tenant-id": tenant,
                   "x-authenticated-user-subject": "local-test", "x-authenticated-user-role": "user"}
        if token:
            headers["x-internal-service-token"] = secret
        return TestClient(app, headers=headers)
    return make


@pytest.mark.freeze_gate
@pytest.mark.parametrize("reference", ["artifactId", "contentRef"])
def test_revoked_formal_read_access_blocks_artifact_body(delivery, client_factory, monkeypatch, reference):
    rt, rid, artifact = delivery
    monkeypatch.setattr(rt.mission_semantic_service, "authorize", lambda *args: False)
    with client_factory(rt) as client:
        workspace = client.get(f'/agentos/v2/missions/{artifact["missionId"]}/workspace')
        body = client.get(f'/agentos/v2/runs/{rid}/artifacts/{artifact[reference]}/fragments')
        assert workspace.status_code == 403
        assert body.status_code in {403, 404}, body.text


@pytest.mark.freeze_gate
def test_artifact_and_manifest_download_aliases_are_equivalent(delivery, client_factory):
    rt, rid, artifact = delivery
    with client_factory(rt) as client:
        by_manifest = client.get(f'/agentos/v2/runs/{rid}/artifacts/{artifact["contentRef"]}/download')
        assert by_manifest.status_code == 200 and by_manifest.content
        by_artifact = client.get(f'/agentos/v2/runs/{rid}/artifacts/{artifact["artifactId"]}/download')
        assert by_artifact.status_code == 200 and by_artifact.content == by_manifest.content
        assert hashlib.sha256(by_artifact.content).hexdigest() == artifact["checksum"]


def directory_snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for p in folder.rglob("*")}


@pytest.mark.freeze_gate
def test_marker_only_reopen_does_not_create_or_upgrade_databases(tmp_path):
    folder = tmp_path / "sample"
    folder.mkdir()
    (folder / "example.json").write_text(json.dumps({"example": WORKFLOW_ID, "version": 1}), encoding="utf-8")
    before = directory_snapshot(folder)
    with pytest.raises((ValueError, RuntimeError)):
        open_runtime(folder, initialize=False)
    assert directory_snapshot(folder) == before


def clone_sample(delivery, folder):
    rt, rid, artifact = delivery
    folder.mkdir()
    source = rt.workflow_store.db_path.parent
    for path in source.iterdir():
        if not path.is_file() or path.name.endswith(("-wal", "-shm")) or path.name.startswith(".run-fence-"):
            continue
        target = folder / path.name
        if path.read_bytes()[:16] == b"SQLite format 3\0":
            with closing(sqlite3.connect(path)) as left, closing(sqlite3.connect(target)) as right:
                left.backup(right)
        else:
            shutil.copyfile(path, target)
    return folder, rid, artifact


@pytest.mark.freeze_gate
@pytest.mark.parametrize("reference", ["artifactId", "contentRef"])
@pytest.mark.parametrize("suffix", ["", "/fragments", "/download"])
def test_each_request_rechecks_current_grant(delivery, client_factory, monkeypatch, reference, suffix):
    rt, rid, artifact = delivery
    granted = [True]
    calls = []
    def authorize(principal, mission_id, action):
        calls.append((principal, mission_id, action))
        return granted[0]
    monkeypatch.setattr(rt.mission_semantic_service, "authorize", authorize)
    before = rt.workflow_store.get_run(rid).model_dump(mode='json')
    body_calls = []
    with client_factory(rt) as client:
        url = f'/agentos/v2/runs/{rid}/artifacts/{artifact[reference]}{suffix}'
        assert client.get(f'/agentos/v2/missions/{artifact["missionId"]}/workspace').status_code == 200
        start = len(calls)
        assert client.get(url).status_code == 200
        body_calls.extend(calls[start:])
        granted[0] = False
        start = len(calls)
        assert client.get(url).status_code == 403
        body_calls.extend(calls[start:])
        assert client.get(f'/agentos/v2/missions/{artifact["missionId"]}/workspace').status_code == 403
        granted[0] = True
        start = len(calls)
        assert client.get(url).status_code == 200
        body_calls.extend(calls[start:])
    # Content access keeps its original read-only authorization contract.
    # Workspace additionally probes write permission to describe UI offers;
    # a permission probe is not a mutation or a retained execution grant.
    assert body_calls and all(p == OWNER and m == artifact["missionId"] and a == "read" for p, m, a in body_calls)
    assert all(p == OWNER and m == artifact["missionId"] and a in {"read", "write"} for p, m, a in calls)
    assert any(a == 'write' for _, _, a in calls)
    assert rt.workflow_store.get_run(rid).model_dump(mode='json') == before


@pytest.mark.freeze_gate
@pytest.mark.parametrize("identity", ["other_user", "other_tenant", "no_token", "no_actor"])
def test_trusted_identity_and_ownership_required(delivery, client_factory, identity):
    rt, rid, artifact = delivery
    kwargs = {"other_user": {"actor": "other-owner"}, "other_tenant": {"tenant": "other-tenant"},
              "no_token": {"token": False}, "no_actor": {"actor": ""}}[identity]
    with client_factory(rt, **kwargs) as client:
        for reference in ("artifactId", "contentRef"):
            for suffix in ("", "/fragments", "/download"):
                response = client.get(f'/agentos/v2/runs/{rid}/artifacts/{artifact[reference]}{suffix}')
                assert response.status_code in {401, 403, 404}, response.text
                assert "800000" not in response.text


@pytest.mark.freeze_gate
@pytest.mark.parametrize("failure", ["missing_service", "unavailable", "sqlite_failure", "invalid_authorizer"])
def test_formal_content_never_downgrades_when_authority_unavailable(delivery, client_factory, monkeypatch, failure):
    rt, rid, artifact = delivery
    if failure == "missing_service":
        monkeypatch.setattr(rt, "mission_semantic_service", None)
    elif failure == "invalid_authorizer":
        monkeypatch.setattr(rt.mission_semantic_service, "authorize", None)
    else:
        def unavailable(*args):
            raise (sqlite3.OperationalError("offline") if failure == "sqlite_failure" else RuntimeError("offline"))
        monkeypatch.setattr(rt.mission_semantic_service, "get_effective_snapshot", unavailable)
    with client_factory(rt) as client:
        for reference in ("artifactId", "contentRef"):
            for suffix in ("", "/fragments", "/download"):
                assert client.get(f'/agentos/v2/runs/{rid}/artifacts/{artifact[reference]}{suffix}').status_code == 503
        output_ref = rt.workflow_store.get_run(rid).execution_state["outputRefs"]["D"]
        assert client.get(f'/agentos/v2/runs/{rid}/outputs/{output_ref}').status_code == 503


@pytest.mark.freeze_gate
def test_cross_run_and_unknown_references_are_not_aliases(delivery, client_factory):
    rt, rid, artifact = delivery
    mission = rt.create_mission("other contract", workflow_id=WORKFLOW_ID,
        input={"authenticatedUserId": OWNER.actor_id, "authenticatedTenantId": OWNER.tenant_id, "deterministicIntent": True})
    rt.mission_semantic_service.commit(OWNER, MissionSemanticRequest(missionId=mission.mission_id,
        operationId="basis", expectedMissionRevision=0, objective="review", constraints=[], sourceRefs=["input:contractText"]))
    _, other = rt.prepare_run(mission.mission_id)
    with client_factory(rt) as client:
        for ref in (artifact["artifactId"], artifact["contentRef"]):
            for suffix in ("", "/fragments", "/download"):
                assert client.get(f'/agentos/v2/runs/{other.run_id}/artifacts/{ref}{suffix}').status_code == 404
        for ref in ("artifact_missing", "manifest_missing"):
            for suffix in ("", "/fragments", "/download"):
                assert client.get(f'/agentos/v2/runs/{rid}/artifacts/{ref}{suffix}').status_code == 404


@pytest.mark.freeze_gate
def test_raw_output_and_direct_manifest_cannot_bypass_revocation(delivery, client_factory, monkeypatch):
    rt, rid, artifact = delivery
    output_ref = rt.workflow_store.get_run(rid).execution_state["outputRefs"]["D"]
    monkeypatch.setattr(rt.mission_semantic_service, "authorize", lambda *args: False)
    with client_factory(rt) as client:
        for url in (f'/agentos/v2/runs/{rid}/artifacts', f'/agentos/v2/materials/{artifact["contentRef"]}',
                    f'/agentos/v2/runs/{rid}/outputs/{output_ref}'):
            assert client.get(url).status_code == 403


@pytest.mark.freeze_gate
@pytest.mark.parametrize("failure", ["deleted_run", "missing_manifest", "unsealed", "wrong_owner"])
def test_invalid_artifact_cannot_be_restored_by_direct_reference(delivery, tmp_path, client_factory, failure):
    folder, rid, artifact = clone_sample(delivery, tmp_path / "copy")
    rt, _ = open_runtime(folder)
    if failure == "deleted_run":
        output_ref = rt.workflow_store.get_run(rid).execution_state["outputRefs"]["D"]
        rt.workflow_store.set_run_record_state(rid, RunRecordState.DELETED)
    else:
        with sqlite3.connect(folder / "content.sqlite3") as conn:
            if failure == "missing_manifest":
                conn.execute("DELETE FROM content_manifests WHERE manifest_id=?", (artifact["contentRef"],))
            elif failure == "unsealed":
                conn.execute("UPDATE content_manifests SET sealed=0 WHERE manifest_id=?", (artifact["contentRef"],))
            else:
                conn.execute("UPDATE content_manifests SET owner_id='another-run' WHERE manifest_id=?", (artifact["contentRef"],))
    with client_factory(rt) as client:
        if failure == "deleted_run":
            assert client.get(f'/agentos/v2/runs/{rid}/outputs/{output_ref}').status_code == 404
        for reference in ("artifactId", "contentRef"):
            for suffix in ("", "/fragments", "/download"):
                assert client.get(f'/agentos/v2/runs/{rid}/artifacts/{artifact[reference]}{suffix}').status_code == 404


@pytest.mark.freeze_gate
@pytest.mark.parametrize("failure", ["missing_db", "empty_db", "missing_table", "old_identity", "old_values", "bad_journal", "bad_marker",
                                     "identity_index", "workflow_index", "content_index", "hot_journal"])
def test_invalid_resume_preflight_preserves_every_file(delivery, tmp_path, monkeypatch, failure):
    folder, _, _ = clone_sample(delivery, tmp_path / "copy")
    if failure == "missing_db":
        (folder / "audit.sqlite3").unlink()
    elif failure == "empty_db":
        (folder / "content.sqlite3").write_bytes(b"")
    elif failure == "bad_marker":
        (folder / "example.json").write_text("{}", encoding="utf-8")
    elif failure == "hot_journal":
        (folder / "values.sqlite3-journal").write_bytes(b"unsettled journal")
    else:
        filename = {"missing_table": "memory.sqlite3", "old_identity": "identity.sqlite3",
                    "old_values": "values.sqlite3", "bad_journal": "workflow.sqlite3",
                    "identity_index": "identity.sqlite3", "workflow_index": "workflow.sqlite3", "content_index": "content.sqlite3"}[failure]
        with sqlite3.connect(folder / filename) as conn:
            conn.execute({"missing_table": "DROP TABLE execution_memory", "old_identity": "PRAGMA user_version=2",
                          "old_values": "ALTER TABLE execution_values DROP COLUMN operation_id",
                          "bad_journal": "UPDATE graph_execution_permit_schema SET version=99",
                          "identity_index": "DROP INDEX idx_artifacts_mission", "workflow_index": "DROP INDEX idx_runs_owner_overview",
                          "content_index": "DROP INDEX idx_content_manifest_owner"}[failure])
    before = directory_snapshot(folder)
    def no_constructor(*args, **kwargs):
        raise AssertionError("Store construction must follow successful preflight")
    monkeypatch.setattr("examples.contract_review.SQLiteWorkflowStore", no_constructor)
    with pytest.raises(ValueError):
        open_runtime(folder, initialize=False)
    assert directory_snapshot(folder) == before


@pytest.mark.freeze_gate
def test_valid_wal_only_schema_is_read_without_touching_source(delivery, tmp_path):
    from examples.contract_review import _preflight_resume
    folder, _, _ = clone_sample(delivery, tmp_path / "copy")
    # Keep a real writer open: the required table exists only in committed WAL.
    with sqlite3.connect(folder / "memory.sqlite3") as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("DROP TABLE execution_memory")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("CREATE TABLE execution_memory(memory_id TEXT PRIMARY KEY, record_json TEXT NOT NULL)")
        conn.commit()
        with closing(sqlite3.connect((folder / "memory.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True)) as base:
            assert not base.execute("SELECT 1 FROM sqlite_master WHERE name='execution_memory'").fetchone()
        before = directory_snapshot(folder)
        _preflight_resume(folder)
        assert directory_snapshot(folder) == before

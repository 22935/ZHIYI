"""S02-02 durable acceptance, real Runtime entry gates, and restart barriers."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import pytest

from components.planner.planning_commit import PlanningCommitService
from contracts.planning import TaskPlan, PlannedTask, TaskPlanPatch, TaskPlanRelation, VerificationLoopPolicy
from contracts.planning_commit import PlanningCommitRequest, PlanningCommitRejectionCode as Code
from contracts.runtime_planning import RuntimePlanningDecision, RuntimePlanningObservation, RuntimePlanningState
from contracts.workflow import WorkflowStatus
from contracts.mission_semantic import run_intent_basis
from runtime.planning_commit import RuntimePlanningCommitProvider
from support.stores.planning_commit_store import SQLitePlanningCommitStore, content_fingerprint
from test_planning_commit import TrustedProvider, sources, request
from test_horizon import ready_boundary, runtime_boundary


def durable(tmp_path):
    path = tmp_path / "workflow.sqlite3"
    SQLitePlanningCommitStore.upgrade_schema(path)
    store = SQLitePlanningCommitStore(path)
    plan = TaskPlan(missionId=sources().mission_id, nodes=tuple(PlannedTask(
        key=k, title=k, objective=k, capabilityRequirements=("task_understanding",)) for k in ("A", "B")))
    src = sources(sourceKind="initial", observationId=None, observationFingerprint=None, planVersion=None, graphVersion=None)
    req = request(proposalType="initial_plan", sources=src, expectedCommitmentRevision=0,
                  proposalFingerprint=content_fingerprint(plan))
    provider = TrustedProvider(req)
    provider.get_proposal_payload = lambda _: plan
    return path, store, provider, req


def attach(runtime, store):
    SQLitePlanningCommitStore.upgrade_schema(store.db_path)
    ledger = SQLitePlanningCommitStore(store.db_path)
    runtime.enable_planning_commit(ledger)
    with store._connect() as conn:
        run_ids = [r[0] for r in conn.execute("SELECT run_id FROM runs")]
    for run_id in run_ids:
        runtime.require_planning_commit(run_id)
    return ledger


def patch(run):
    return TaskPlanPatch(missionId=run.mission_id, basePlanVersion=run.execution_state["taskPlanVersion"],
        planVersion=run.execution_state["taskPlanVersion"] + 1,
        addNodes=(PlannedTask(key="new:work", title="new", objective="new verified work",
            capabilityRequirements=("task_understanding",), sourceRefs=("input:brief",)),),
        relations=(TaskPlanRelation(sourceKey="step:A", targetKey="new:work", relationType="depends_on"),))


def dump_databases(store, include_ledger=False):
    result = {}
    for path in store.db_path.parent.glob("*.sqlite3"):
        with sqlite3.connect(path) as conn:
            result[path.name] = tuple(line for line in conn.iterdump()
                if include_ledger or "planning_commit_" not in line)
    return result


def test_explicit_schema_no_constructor_upgrade(tmp_path):
    absent = tmp_path / "absent.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        SQLitePlanningCommitStore(absent)
    assert not absent.exists()
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE old_data(value TEXT)")
        conn.execute("INSERT INTO old_data VALUES('preserve')")
    with pytest.raises(sqlite3.OperationalError):
        SQLitePlanningCommitStore(path)
    with sqlite3.connect(path) as conn:
        assert [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")] == ["old_data"]
    SQLitePlanningCommitStore.upgrade_schema(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT value FROM old_data").fetchone()[0] == "preserve"


def test_durable_restart_payload_queries_and_outbox(tmp_path):
    path, store, provider, req = durable(tmp_path)
    first = PlanningCommitService(current_state_provider=provider, store=store).accept(req)
    assert first.status == "ACCEPTED"
    restored = SQLitePlanningCommitStore(path)
    service = PlanningCommitService(current_state_provider=provider, store=restored)
    replay = service.accept(req)
    assert replay.status == "IDEMPOTENT_REPLAY" and replay.commit_id == first.commit_id
    record = restored.get(first.commit_id)
    assert record.proposal_payload is not None
    assert content_fingerprint(record.proposal_payload) == req.proposal_fingerprint
    assert record.materialization_status == "COMMITTED_NOT_MATERIALIZED"
    assert len(restored.pending_events()) == 1
    record.proposal_payload.metadata["strategy"] = "caller mutation"
    assert "strategy" not in restored.get(first.commit_id).proposal_payload.metadata
    second = req.model_copy(update={"idempotency_key": "next", "expected_commitment_revision": 1})
    receipt = service.accept(second)
    assert receipt.commitment_revision == 2
    assert restored.get(receipt.commit_id).parent_commit_id == first.commit_id


def test_cross_connection_cas_and_duplicate(tmp_path):
    path, store, provider, req = durable(tmp_path)
    services = [PlanningCommitService(current_state_provider=provider, store=SQLitePlanningCommitStore(path)) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: services[i % 4].accept(req), range(8)))
    assert sum(r.status == "ACCEPTED" for r in results) == 1
    assert len({r.commit_id for r in results}) == 1
    assert len(store.pending_events()) == 1
    stale = req.model_copy(update={"idempotency_key": "different"})
    assert services[0].accept(stale).code == Code.STALE_COMMITMENT
    conflict = req.model_copy(update={"requested_scope": ("A",)})
    assert services[0].accept(conflict).code == Code.DUPLICATE_CONFLICT


def test_atomic_append_failure_and_retry(tmp_path, monkeypatch):
    _, store, provider, req = durable(tmp_path)
    service = PlanningCommitService(current_state_provider=provider, store=store)
    original = store._append
    def broken(*args):
        original(*args)
        raise RuntimeError("interrupted publication")
    monkeypatch.setattr(store, "_append", broken)
    assert service.accept(req).status == "REJECTED"
    assert store.get_by_idempotency_key(req.idempotency_key) is None
    assert not store.pending_events()
    monkeypatch.setattr(store, "_append", original)
    assert service.accept(req).commitment_revision == 1


def test_corrupt_payload_is_not_a_trusted_fact(tmp_path):
    _, store, provider, req = durable(tmp_path)
    receipt = PlanningCommitService(current_state_provider=provider, store=store).accept(req)
    with store._connect() as conn:
        raw = json.loads(conn.execute("SELECT payload FROM planning_commit_records").fetchone()[0])
        raw["proposalPayload"]["nodes"][0]["objective"] = "tampered"
        conn.execute("UPDATE planning_commit_records SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError):
        store.get(receipt.commit_id)


def test_initial_planning_accepts_without_materializing_or_executing(ready_boundary, monkeypatch):
    runtime, store, agent, source_id, _ = ready_boundary
    ledger = attach(runtime, store)
    source = store.get_run(source_id)
    _, run = runtime.prepare_run(source.mission_id, workflow_id=source.workflow_id)
    assert run.execution_state["planningDeferred"] and run.execution_state["planningCommitRequired"]
    assert not run.acg_blueprint and not run.steps and "taskPlan" not in run.execution_state
    def forbidden(*args, **kwargs):
        raise AssertionError("acceptance reached graph materialization or execution")
    monkeypatch.setattr(runtime.runtime_binding_service, "prepare", forbidden)
    monkeypatch.setattr(runtime.semantic_revision_service, "prepare", forbidden)
    before = dump_databases(store)
    receipt = runtime.planning_commit_authority.accept_initial(run.run_id)
    assert receipt.status == "ACCEPTED", receipt.model_dump()
    assert dump_databases(store) == before
    record = ledger.get(receipt.commit_id)
    assert record.sources.source_kind == "initial"
    assert record.sources.graph_version is None and record.sources.observation_id is None
    assert record.proposal_payload.metadata["missionIntentBasisRef"] == run_intent_basis(run).reference()
    replay = runtime.planning_commit_authority.accept_initial(run.run_id)
    assert replay.commit_id == receipt.commit_id and replay.status == "IDEMPOTENT_REPLAY"
    held = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert held.status == WorkflowStatus.PLANNING and not held.acg_blueprint and not agent.calls
    runtime.planning_commit_authority = None
    assert asyncio.run(runtime.execute_prepared_run(run.run_id)).run_id == run.run_id
    assert not store.get_run(run.run_id).acg_blueprint and not agent.calls


def test_initial_rejection_reports_the_specific_barrier_reason(ready_boundary, monkeypatch):
    from contracts.planning_commit import PlanningCommitRejection
    runtime, store, agent, source_id, _ = ready_boundary
    attach(runtime, store)
    source = store.get_run(source_id)
    _, run = runtime.prepare_run(source.mission_id, workflow_id=source.workflow_id)
    monkeypatch.setattr(runtime.planning_commit_authority, 'accept_initial', lambda _: PlanningCommitRejection(
        code=Code.CONTROL_BARRIER_BLOCKED, reason='control policies require later safe-cut support'))
    with pytest.raises(ValueError, match='CONTROL_BARRIER_BLOCKED: control policies require later safe-cut support'):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert not store.get_run(run.run_id).acg_blueprint and not agent.calls


def test_initial_loop_repair_failure_is_not_misreported_as_stale_sources(ready_boundary, monkeypatch):
    from components.planner.task_decomposer import TaskDecompositionError
    runtime, store, _, _, _ = ready_boundary
    attach(runtime, store)
    def failed(_):
        raise TaskDecompositionError('TASK_PLAN_VALIDATION_FAILED: INITIAL_CONTROL_GRAPH_UNSUPPORTED')
    monkeypatch.setattr(runtime.planning_commit_authority, '_accept_initial', failed)
    receipt = runtime.planning_commit_authority.accept_initial('run-test')
    assert receipt.code == Code.INVALID_PROPOSAL
    assert 'INITIAL_CONTROL_GRAPH_UNSUPPORTED' in receipt.reason


def test_revision_commit_does_not_mutate_formal_plan_graph_or_receipts(ready_boundary):
    runtime, store, agent, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    before = dump_databases(store)
    with runtime.run_lock_manager.lock_for(run_id):
        receipt = runtime.planning_commit_authority.accept_patch_locked(run_id, patch(run), proposal_id="revision", idempotency_key="revision")
    assert receipt.status == "ACCEPTED", receipt.model_dump()
    assert dump_databases(store) == before and not agent.calls
    assert isinstance(ledger.get(receipt.commit_id).proposal_payload, TaskPlanPatch)
    runtime.enable_planning_commit(SQLitePlanningCommitStore(store.db_path))
    with runtime.run_lock_manager.lock_for(run_id):
        replay = runtime.planning_commit_authority.accept_patch_locked(run_id, patch(run), proposal_id="revision", idempotency_key="revision")
    assert replay.status == "IDEMPOTENT_REPLAY" and replay.commit_id == receipt.commit_id


@pytest.mark.parametrize("mutation,code", [("plan", Code.STALE_PLAN), ("graph", Code.STALE_GRAPH),
    ("mission", Code.STALE_MISSION), ("content", Code.STALE_STRATEGY), ("revoke", Code.AUTHORITY_DENIED)])
def test_live_runtime_fences(ready_boundary, mutation, code):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    authority = runtime.planning_commit_authority
    proposal = patch(run)
    provider = authority._provider(run_id, proposal, False)
    req = authority._request(provider, proposal, "candidate", "candidate")
    if mutation == "plan":
        run.execution_state["taskPlan"]["planVersion"] += 1
    elif mutation == "graph":
        run.acg_blueprint["version"] += 1
    elif mutation == "content":
        run.input["materialConfig"] = "changed without version increment"
    elif mutation == "mission":
        from contracts.mission_semantic import MissionSemanticRequest
        runtime.mission_semantic_service.commit(runtime.semantic_principal_provider(), MissionSemanticRequest(
            missionId=run.mission_id, operationId="edit", expectedMissionRevision=1, objective="changed", constraints=[], sourceRefs=[]))
    else:
        runtime.mission_semantic_service.authorize = lambda *args: False
    if mutation in {"plan", "graph", "content"}:
        store.save_run(run)
    with runtime.run_lock_manager.lock_for(run_id):
        result = PlanningCommitService(current_state_provider=provider, store=ledger).accept(req)
    assert result.code == code
    assert ledger.latest(run.mission_id) is None


def test_react_revision_becomes_wait_and_restart_does_not_replace_run(ready_boundary, monkeypatch):
    runtime, store, agent, run_id, state = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    runtime.mission_manager.mark_running(runtime.mission_manager.get_mission(run.mission_id))
    before_plan, before_graph = run.execution_state["taskPlan"], run.acg_blueprint
    observation = RuntimePlanningObservation.model_validate(run.execution_state["planningLoop"]["current"]["observation"])
    class Planner:
        def decide_runtime(self, **kwargs):
            return RuntimePlanningDecision(observationId=kwargs["observation"].fingerprint(), action="revise",
                reason="propose new work", taskPlanPatch=patch(run))
    monkeypatch.setattr(runtime.runtime_planning_coordinator, "planner_for_run", lambda _: Planner())
    monkeypatch.setattr(runtime.semantic_revision_service, "prepare", lambda **kwargs: pytest.fail("replacement Run attempted"))
    result = asyncio.run(runtime.runtime_planning_coordinator.boundary(run, state, "resume"))
    assert result == "stop"
    held = store.get_run(run_id)
    assert held.status == WorkflowStatus.WAITING_REVIEW
    assert held.execution_state["planningLoop"]["current"]["decision"]["action"] == "wait"
    assert held.execution_state["taskPlan"] == before_plan and held.acg_blueprint == before_graph
    assert len(ledger.pending_events()) == 1 and not agent.calls
    assert not held.execution_state.get("supersededByRunId")
    runtime.planning_commit_authority = None
    asyncio.run(runtime._recover_pending_planning_transitions(limit=10))
    assert store.get_run(run_id).acg_blueprint == before_graph
    assert not agent.calls


def test_unconfigured_runtime_preserves_existing_execution(runtime_boundary):
    runtime, store, agent, run_id, _ = runtime_boundary
    result = asyncio.run(runtime.execute_prepared_run(run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent.calls == ["A"]


def test_replay_rejects_changed_proposal_identity_and_foreign_run(ready_boundary):
    runtime, store, _, run_id, _ = ready_boundary
    source = store.get_run(run_id)
    _, other = runtime.prepare_run(source.mission_id, workflow_id=source.workflow_id)
    ledger = attach(runtime, store)
    authority = runtime.planning_commit_authority
    with runtime.run_lock_manager.lock_for(run_id):
        first = authority.accept_patch_locked(run_id, patch(source), proposal_id="p", idempotency_key="shared")
        assert first.status == "ACCEPTED"
        changed = authority.accept_patch_locked(run_id, patch(source), proposal_id="other", idempotency_key="shared")
        assert changed.code == Code.DUPLICATE_CONFLICT
        wrong_graph = authority.accept_patch_locked(run_id, patch(source), proposal_id="p", idempotency_key="shared", graph_id="forged")
        assert wrong_graph.code == Code.STALE_GRAPH
    assert content_fingerprint(patch(source)) == content_fingerprint(patch(other))
    with runtime.run_lock_manager.lock_for(other.run_id):
        foreign = authority.accept_patch_locked(other.run_id, patch(other), proposal_id="p", idempotency_key="shared")
    assert foreign.code == Code.DUPLICATE_CONFLICT
    assert len(ledger.pending_events()) == 1


def test_read_permission_cannot_accept_initial_commit(ready_boundary, monkeypatch):
    runtime, store, _, source_id, _ = ready_boundary
    attach(runtime, store)
    source = store.get_run(source_id)
    _, run = runtime.prepare_run(source.mission_id, workflow_id=source.workflow_id)
    runtime.mission_semantic_service.authorize = lambda principal, mission, action: action == "read"
    monkeypatch.setattr(runtime, "_planning_engine_for_run", lambda _: pytest.fail("unauthorized candidate generation"))
    result = runtime.planning_commit_authority.accept_initial(run.run_id)
    assert result.code == Code.AUTHORITY_DENIED


def test_authority_revocation_and_cancel_after_validation_do_not_publish(ready_boundary, monkeypatch):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    authority = runtime.planning_commit_authority
    proposal = patch(store.get_run(run_id))
    provider = authority._provider(run_id, proposal, False)
    req = authority._request(provider, proposal, "p", "p")
    original = provider.validate_proposal
    def revoke(request):
        result = original(request)
        runtime._signal_run_cancellation(run_id)
        return result
    monkeypatch.setattr(provider, "validate_proposal", revoke)
    with runtime.run_lock_manager.lock_for(run_id):
        result = PlanningCommitService(current_state_provider=provider, store=ledger).accept(req)
    assert result.code == Code.AUTHORITY_DENIED
    assert ledger.latest(req.sources.mission_id) is None and not ledger.pending_events()


def test_complete_scope_and_no_completed_prefix_replacement(ready_boundary):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    authority = runtime.planning_commit_authority
    run = store.get_run(run_id)
    proposal = patch(run)
    provider = authority._provider(run_id, proposal, False)
    req = authority._request(provider, proposal, "p", "p")
    partial = req.model_copy(update={"requested_scope": ("new:work",)})
    with runtime.run_lock_manager.lock_for(run_id):
        assert PlanningCommitService(current_state_provider=provider, store=ledger).accept(partial).code == Code.DEPENDENCY_NOT_CLOSED
    # Pending status with existing execution evidence is still protected.
    run.steps[0].attempt = 1
    store.save_run(run)
    replacement = TaskPlanPatch(missionId=run.mission_id, basePlanVersion=1, planVersion=2,
        replaceKeys=("step:A",), addNodes=(PlannedTask(key="step:A", title="replacement", objective="replacement",
            capabilityRequirements=("task_understanding",)),))
    with runtime.run_lock_manager.lock_for(run_id):
        result = authority.accept_patch_locked(run_id, replacement, proposal_id="replace", idempotency_key="replace")
    assert result.code == Code.INVALID_PROPOSAL and ledger.latest(run.mission_id) is None


def test_direct_semantic_patch_returns_commit_without_replacement(ready_boundary, monkeypatch):
    from contracts.recovery import SemanticPatchRequest
    runtime, store, agent, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    monkeypatch.setattr(runtime.semantic_revision_service, "prepare", lambda **kwargs: pytest.fail("legacy revision authority entered"))
    req = SemanticPatchRequest(patchId="direct", idempotencyKey="direct", runId=run_id,
        graphId=run.acg_blueprint["graphId"], baseGraphVersion=run.acg_blueprint["version"],
        taskPlanPatch=patch(run), reason="accept proposal")
    receipt = asyncio.run(runtime.apply_semantic_patch(req))
    assert receipt.status == "ACCEPTED" and len(ledger.pending_events()) == 1
    assert store.get_run(run_id).execution_state["taskPlan"] == run.execution_state["taskPlan"]
    assert not store.get_run(run_id).execution_state.get("supersededByRunId") and not agent.calls
    runtime.planning_commit_authority = None
    with pytest.raises(ValueError, match="authority is required"):
        asyncio.run(runtime.apply_semantic_patch(req))


def test_ordinary_review_executes_only_original_graph(ready_boundary, monkeypatch):
    from contracts.workflow import ReviewDecision
    runtime, store, agent, run_id, state = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    runtime.mission_manager.mark_running(runtime.mission_manager.get_mission(run.mission_id))
    original_graph = json.loads(json.dumps(run.acg_blueprint))
    class Revise:
        def decide_runtime(self, **kwargs):
            return RuntimePlanningDecision(observationId=kwargs["observation"].fingerprint(), action="revise",
                reason="candidate", taskPlanPatch=patch(run))
    monkeypatch.setattr(runtime.runtime_planning_coordinator, "planner_for_run", lambda _: Revise())
    assert asyncio.run(runtime.runtime_planning_coordinator.boundary(run, state, "resume")) == "stop"
    paused = store.get_run(run_id)
    class ContinueOriginal:
        def decide_runtime(self, **kwargs):
            obs = kwargs["observation"]
            return RuntimePlanningDecision(observationId=obs.fingerprint(),
                action="continue" if obs.remaining_step_ids else "complete", reason="original work")
    monkeypatch.setattr(runtime.runtime_planning_coordinator, "planner_for_run", lambda _: ContinueOriginal())
    result = asyncio.run(runtime.apply_review(ReviewDecision(runId=run_id,
        stepId=paused.current_step_id, decision="approved", operationId="approve-original")))
    assert result.status == WorkflowStatus.COMPLETED and result.acg_blueprint == original_graph
    assert agent.calls == ["A"] and "new:work" not in {n["key"] for n in result.execution_state["taskPlan"]["nodes"]}
    assert len(ledger.pending_events()) == 1


def test_unmarked_initial_run_cannot_leave_a_commit_without_restart_fence(ready_boundary):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    old = store.get_run(run_id)
    _, run = runtime.prepare_run(old.mission_id, workflow_id=old.workflow_id)
    run.execution_state.pop("planningCommitRequired")
    # Corrupt input bypasses the store's immutable mode fence deliberately;
    # the acceptance entry must still reject this unmarked initial candidate.
    with store._connect() as conn:
        conn.execute("UPDATE runs SET payload=? WHERE run_id=?",
                     (run.model_dump_json(by_alias=True), run.run_id))
    result = runtime.planning_commit_authority.accept_initial(run.run_id)
    assert result.code == Code.INVALID_PROPOSAL
    assert ledger.latest(run.mission_id) is None


def test_legacy_applied_revision_recovery_is_fenced_after_authority_loss(ready_boundary, monkeypatch):
    runtime, store, agent, run_id, state = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    runtime.mission_manager.mark_running(runtime.mission_manager.get_mission(run.mission_id))
    obs = RuntimePlanningObservation.model_validate(run.execution_state["planningLoop"]["current"]["observation"])
    decision = RuntimePlanningDecision(observationId=obs.fingerprint(), action="revise", reason="candidate", taskPlanPatch=patch(run))
    converted = asyncio.run(runtime._gate_planning_commit_decision(run, obs, decision))
    assert converted.action == "wait" and len(ledger.pending_events()) == 1
    loop = RuntimePlanningState.model_validate(run.execution_state["planningLoop"])
    loop = loop.model_copy(update={"current": loop.current.model_copy(update={"decision": converted, "status": "applied"})})
    asyncio.run(runtime._apply_runtime_planning_decision(run, state, obs, converted, loop))
    held = store.get_run(run_id)
    # Model the legacy applied-revision half-commit window at a persisted barrier.
    held.execution_state["planningLoop"]["current"]["decision"] = decision.model_dump(by_alias=True, mode="json")
    held.execution_state["planningLoop"]["current"]["status"] = "applied"
    store.save_run(held)
    runtime.planning_commit_authority = None
    monkeypatch.setattr(runtime.semantic_revision_service, "prepare", lambda **kwargs: pytest.fail("recovery bypassed Commit fence"))
    asyncio.run(runtime._recover_pending_planning_transitions(limit=10))
    recovered = store.get_run(run_id)
    assert recovered.execution_state["planningLoop"]["current"]["decision"]["action"] == "wait"
    assert recovered.status == WorkflowStatus.WAITING_REVIEW and not agent.calls
    assert not recovered.execution_state.get("supersededByRunId")


def test_barrier_failure_after_acceptance_recovers_as_wait(ready_boundary, monkeypatch):
    runtime, store, agent, run_id, state = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    runtime.mission_manager.mark_running(runtime.mission_manager.get_mission(run.mission_id))
    class Revise:
        def decide_runtime(self, **kwargs):
            return RuntimePlanningDecision(observationId=kwargs["observation"].fingerprint(), action="revise",
                reason="candidate", taskPlanPatch=patch(run))
    monkeypatch.setattr(runtime.runtime_planning_coordinator, "planner_for_run", lambda _: Revise())
    original = runtime.acg_state_persistence.save_checkpoint
    def crash(*args, **kwargs):
        raise RuntimeError("simulated checkpoint crash")
    monkeypatch.setattr(runtime.acg_state_persistence, "save_checkpoint", crash)
    with pytest.raises(RuntimeError, match="checkpoint crash"):
        asyncio.run(runtime.runtime_planning_coordinator.boundary(run, state, "resume"))
    assert len(ledger.pending_events()) == 1
    held = store.get_run(run_id)
    assert held.execution_state["planningLoop"]["current"]["decision"]["action"] == "wait"
    runtime.planning_commit_authority = None
    assert asyncio.run(runtime.execute_prepared_run(run_id)).run_id == run_id
    assert not agent.calls
    runtime.enable_planning_commit(SQLitePlanningCommitStore(store.db_path))
    monkeypatch.setattr(runtime.acg_state_persistence, "save_checkpoint", original)
    result = asyncio.run(runtime.execute_prepared_run(run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert len(ledger.pending_events()) == 1 and not agent.calls


def test_illegal_dag_is_not_accepted(ready_boundary):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    bad = patch(run).model_copy(update={"relations": (
        TaskPlanRelation(sourceKey="step:A", targetKey="new:work", relationType="depends_on"),
        TaskPlanRelation(sourceKey="new:work", targetKey="step:A", relationType="depends_on"))})
    with runtime.run_lock_manager.lock_for(run_id):
        result = runtime.planning_commit_authority.accept_patch_locked(run_id, bad, proposal_id="cycle", idempotency_key="cycle")
    assert result.code == Code.INVALID_PROPOSAL and not ledger.pending_events()


def test_commit_query_requires_live_read_authority(ready_boundary):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    with runtime.run_lock_manager.lock_for(run_id):
        receipt = runtime.planning_commit_authority.accept_patch_locked(run_id, patch(run), proposal_id="p", idempotency_key="p")
    assert runtime.planning_commit_authority.get_commit(receipt.commit_id).commit_id == receipt.commit_id
    runtime.mission_semantic_service.authorize = lambda *args: False
    with pytest.raises(PermissionError):
        runtime.planning_commit_authority.get_commit(receipt.commit_id)


def test_control_policy_candidate_requires_later_safe_cut_support(ready_boundary):
    runtime, store, _, run_id, _ = ready_boundary
    ledger = attach(runtime, store)
    run = store.get_run(run_id)
    candidate = patch(run).model_copy(update={"control_policies": (
        VerificationLoopPolicy(bodyEntryKey="new:work", bodyExitKey="new:work",
                               conditionSourceKey="new:work"),)})
    before = dump_databases(store)
    with runtime.run_lock_manager.lock_for(run_id):
        result = runtime.planning_commit_authority.accept_patch_locked(
            run_id, candidate, proposal_id="control", idempotency_key="control")
    assert result.code == Code.CONTROL_BARRIER_BLOCKED
    assert not ledger.pending_events() and dump_databases(store) == before


def test_initial_acceptance_worker_does_not_overwrite_later_runtime_state(ready_boundary, monkeypatch):
    runtime, store, _, source_id, _ = ready_boundary
    attach(runtime, store)
    source = store.get_run(source_id)
    _, run = runtime.prepare_run(source.mission_id, workflow_id=source.workflow_id)
    original = runtime.planning_commit_authority.accept_initial
    def accept_then_operator_update(run_id):
        receipt = original(run_id)
        assert receipt.status == "ACCEPTED"
        with runtime.run_lock_manager.lock_for(run_id):
            latest = store.get_run(run_id)
            latest.input["operatorAfterAcceptance"] = "preserve"
            latest.runtime_revision += 1
            store.save_run(latest)
        return receipt
    monkeypatch.setattr(runtime.planning_commit_authority, "accept_initial", accept_then_operator_update)
    held = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert held.input.get("operatorAfterAcceptance") == "preserve"
    assert store.get_run(run.run_id).input.get("operatorAfterAcceptance") == "preserve"

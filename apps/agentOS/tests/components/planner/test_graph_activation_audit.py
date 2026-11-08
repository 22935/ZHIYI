"""Second independent audit: typed writes, real processes, atomic fault cuts."""
import asyncio
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3

import pytest
from contracts.workflow import RuntimeRunRecord, StepStatus, WorkflowDefinition
from support.stores.graph_activation_store import SQLiteGraphActivationStore
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
from test_graph_activation import activated, chain
from test_graph_activation_fix import durable
from test_horizon import ready_boundary, runtime_boundary


@pytest.mark.parametrize("change", ["plan", "plan_version", "bindings", "steps", "attempt", "output",
    "status", "completed", "active", "output_refs", "checkpoint", "scope", "requirements",
    "workflow", "domain", "engine", "false_completion"])
def test_paused_execution_and_semantic_evidence_cannot_be_rewritten(ready_boundary, change):
    _, workflow, _, run_id, _, agent, _ = activated(ready_boundary)
    before = durable(workflow)
    run = workflow.get_run(run_id)
    if change == "plan": run.execution_state["taskPlan"]["nodes"][0]["objective"] = "different accepted semantics"
    elif change == "plan_version": run.execution_state["taskPlanVersion"] += 1
    elif change == "bindings": run.execution_state["taskBindings"] = []
    elif change == "steps": run.steps = []
    elif change == "attempt": run.steps[0].attempt += 1
    elif change == "output": run.steps[0].output = {"forged": "execution"}
    elif change == "status": run.steps[0].status = StepStatus.RUNNING
    elif change == "completed": run.completed_step_ids = ["A"]
    elif change == "active": run.active_step_ids = ["A"]
    elif change == "output_refs": run.execution_state["outputRefs"] = {"A": "forged-output"}
    elif change == "checkpoint": run.execution_state["checkpointId"] = "old-v1-checkpoint"
    elif change == "scope": run.execution_scope = run.execution_scope.model_copy(update={"capability_ids": ()})
    elif change == "requirements": run.execution_state["bindingRequirements"] = {}
    elif change == "workflow": run.workflow_id = "another-workflow"
    elif change == "domain": run.domain = "another-domain"
    elif change == "engine": run.runtime_engine = "legacy"
    else:
        from contracts.workflow import WorkflowStatus
        run.status = WorkflowStatus.COMPLETED
    run = RuntimeRunRecord.model_validate_json(run.model_dump_json(by_alias=True))
    with pytest.raises(ValueError, match="activation head"):
        SQLiteWorkflowStore(workflow.db_path).save_run(run)
    assert durable(workflow) == before and agent.calls == []


@pytest.mark.parametrize("cut", ["journal", "head", "run", "commit"])
def test_each_activation_write_cut_rolls_back(ready_boundary, monkeypatch, cut):
    runtime, workflow, journal, run_id, mat_id, _ = chain(ready_boundary, prepare_key="act")
    before = durable(workflow)
    original_connect = journal._connect
    class Connection:
        def __init__(self): self.inner = original_connect()
        def __getattr__(self, name): return getattr(self.inner, name)
        def execute(self, sql, *args):
            result = self.inner.execute(sql, *args)
            target = {"journal": "UPDATE graph_activations", "head": "INSERT INTO graph_activation_heads",
                      "run": "INSERT INTO runs"}.get(cut)
            if target and target in sql:
                raise sqlite3.OperationalError("audit post-write failure: " + cut)
            return result
        def commit(self):
            if cut == "commit": raise sqlite3.OperationalError("audit before COMMIT")
            return self.inner.commit()
    monkeypatch.setattr(journal, "_connect", Connection)
    result = runtime.commit_graph_activation(mat_id, idempotency_key="act")
    assert result.status == "REJECTED", result.model_dump()
    assert durable(workflow) == before
    monkeypatch.setattr(journal, "_connect", original_connect)
    assert runtime.commit_graph_activation(mat_id, idempotency_key="act").status == "ACTIVATED_PAUSED"
    assert workflow.get_run(run_id).acg_blueprint["version"] == 2


def test_paused_diagnostics_operator_input_and_cancellation_remain_legal(ready_boundary):
    runtime, workflow, _, run_id, _, agent, _ = activated(ready_boundary)
    before = workflow.get_run(run_id)
    identity_package = runtime.identity_lifecycle.repositories.runs.get(run_id).metadata["compiledPackageId"]
    current = before.model_copy(deep=True)
    current.lifecycle_message = "paused diagnostic"
    current.input["operatorComment"] = "inspect before issuing a permit"
    workflow.save_run(current)
    cancelled = runtime.cancel(run_id)
    assert cancelled.status.value == "cancelled"
    assert cancelled.steps == before.steps and cancelled.execution_state == before.execution_state
    assert runtime.identity_lifecycle.repositories.runs.get(run_id).metadata["compiledPackageId"] == identity_package
    assert identity_package != cancelled.execution_state["compiledPackageId"]
    assert agent.calls == []


def test_lifecycle_recovery_cannot_recreate_missing_identity_from_paused_graph(ready_boundary, monkeypatch):
    runtime, workflow, _, run_id, _, agent, _ = activated(ready_boundary)
    run = workflow.get_run(run_id)
    run.lifecycle_message = "require source identity for lifecycle reconciliation"
    workflow.save_run(run)
    repos = runtime.identity_lifecycle.repositories
    original = repos.runs.get
    monkeypatch.setattr(repos.runs, "get", lambda key: None if key == run_id else original(key))
    monkeypatch.setattr(runtime.identity_lifecycle, "on_run_prepared", lambda *a, **kw: pytest.fail("implicit v2 identity handoff"))
    with pytest.raises(RuntimeError, match="existing source Identity Run"):
        runtime._flush_identity_outbox()
    assert agent.calls == []


def test_bulk_identity_scan_cannot_adopt_paused_graph(ready_boundary, monkeypatch):
    from runtime.reconciliation import IdentityProjectionReconciler
    runtime, workflow, _, run_id, _, agent, _ = activated(ready_boundary)
    runtime._flush_identity_outbox()
    assert workflow.list_outbox() == []
    bridge = runtime.identity_lifecycle
    original = bridge.repositories.runs.get
    monkeypatch.setattr(bridge.repositories.runs, "get", lambda key: None if key == run_id else original(key))
    monkeypatch.setattr(bridge, "on_run_prepared", lambda *a, **kw: pytest.fail("bulk recovery adopted paused graph"))
    report = IdentityProjectionReconciler(bridge).reconcile_workflow_store(workflow, audit_existing=True)
    assert any("existing source Identity Run" in failure for failure in report.failures), report
    assert agent.calls == []


def test_direct_execution_service_also_cannot_dispatch_paused_nodes(ready_boundary):
    runtime, workflow, _, run_id, _, agent, _ = activated(ready_boundary)
    runtime.graph_activation_authority = None
    with pytest.raises(ValueError, match="activation head"):
        asyncio.run(runtime.acg_execution_service.execute(workflow.get_run(run_id)))
    assert agent.calls == []
    assert workflow.get_run(run_id).active_step_ids == []


@pytest.mark.parametrize("damage", ["missing_schema", "missing_journal", "dangling_head", "wrong_store"])
def test_execution_evidence_fail_closed(ready_boundary, damage):
    runtime, workflow, _, run_id, _, agent, _ = activated(ready_boundary)
    run = workflow.get_run(run_id)
    runtime.graph_activation_authority = None
    if damage == "wrong_store":
        class WrongStore:
            def get_run(self, _): return run
        runtime.workflow_store = WrongStore()
    else:
        with workflow._connect() as conn:
            if damage == "missing_schema": conn.execute("DROP TABLE graph_activation_heads")
            elif damage == "missing_journal": conn.execute("DROP TABLE graph_activations")
            else: conn.execute("UPDATE graph_activation_heads SET activation_id='missing-activation'")
    with pytest.raises((ValueError, AttributeError, sqlite3.Error)):
        asyncio.run(runtime._execute_acg(run))
    assert agent.calls == []


@pytest.mark.parametrize("damage", ["head_row", "head_schema"])
def test_missing_head_cannot_erase_last_durable_activation_evidence(ready_boundary, damage):
    runtime, workflow, _, run_id, mat_id, agent = chain(ready_boundary, prepare_key="act")
    old = workflow.get_run(run_id)
    assert runtime.commit_graph_activation(mat_id, idempotency_key="act").status == "ACTIVATED_PAUSED"
    with workflow._connect() as conn:
        if damage == "head_row": conn.execute("DELETE FROM graph_activation_heads")
        else: conn.execute("DROP TABLE graph_activation_heads")
    before = workflow.get_run(run_id)
    with pytest.raises(ValueError, match="activation head"):
        SQLiteWorkflowStore(workflow.db_path).save_run(old)
    assert workflow.get_run(run_id) == before and agent.calls == []


@pytest.mark.parametrize("field", ["commitment_fingerprint", "proof_fingerprint", "sources"])
def test_materialization_full_acceptance_identity_is_rechecked(ready_boundary, field):
    from contracts import stable_checksum
    runtime, workflow, journal, run_id, mat_id, agent = chain(ready_boundary)
    materialization = journal.get_materialization(mat_id)
    if field == "sources":
        materialization = materialization.model_copy(update={"sources": materialization.sources.model_copy(update={"plan_version": 99})})
    else:
        materialization = materialization.model_copy(update={field: "0" * 64})
    # Keep the original complete package, typed record and row checksum valid.
    materialization = type(materialization).model_validate_json(materialization.model_dump_json(by_alias=True))
    with journal.connection() as conn, conn:
        conn.execute("UPDATE graph_materializations SET payload=?, checksum=? WHERE materialization_id=?",
            (materialization.model_dump_json(by_alias=True), stable_checksum(materialization), mat_id))
    receipt = runtime.prepare_graph_activation(mat_id, idempotency_key="act")
    assert receipt.status == "REJECTED", receipt.model_dump()
    assert journal.head(run_id) is None and journal.activation_for(mat_id) is None and agent.calls == []


def _reopen(folder, definition):
    from test_react_loop import runtime_at
    from contracts.mission_semantic import SemanticPrincipal
    from components.mission_manager.semantic_service import MissionSemanticService
    from support.stores.planning_commit_store import SQLitePlanningCommitStore
    from support.stores.graph_materialization_store import SQLiteGraphMaterializationStore
    runtime, store, agent = runtime_at(Path(folder))
    runtime.workflow_registry.register(WorkflowDefinition.model_validate(definition))
    owner = SemanticPrincipal(actorId="owner", tenantId="tenant")
    runtime.mission_semantic_service = MissionSemanticService(store=store, authorize=lambda p,m,a: p == owner)
    runtime.semantic_principal_provider = lambda: owner
    runtime.allow_legacy_mission_intent = False
    runtime.enable_planning_commit(SQLitePlanningCommitStore(store.db_path))
    runtime.enable_graph_materialization(SQLiteGraphMaterializationStore(store.db_path))
    runtime.enable_graph_activation(SQLiteGraphActivationStore(store.db_path))
    return runtime, store, agent


def _execute_child(folder, definition, run_id, cut, entered, release, results):
    """Spawn imports a fresh Runtime with independent SQLite connections."""
    try:
        from contracts.runtime_planning import RuntimePlanningDecision
        runtime, store, agent = _reopen(folder, definition)
        class Continue:
            def decide_runtime(self, *, observation, task_plan):
                return RuntimePlanningDecision(observationId=observation.fingerprint(),
                    action="continue" if observation.remaining_step_ids else "complete", reason="audit")
        runtime.runtime_planning_coordinator.planner_for_run = lambda _: Continue()
        original_agent = agent.run
        async def side_effect(context):
            if cut == "agent_inflight":
                entered.set()
                assert release.wait(60)
            with (Path(folder) / "external-effect.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"pid": os.getpid(), "step": context.step.step_id}) + "\n")
            return await original_agent(context)
        agent.run = side_effect
        if cut == "claimed":
            original_claim = runtime._claim_acg_execution
            def claim(run):
                original_claim(run)
                entered.set()
                assert release.wait(60)
            runtime._claim_acg_execution = claim
        elif cut == "running_persisted":
            original_save = store.save_run
            def save(run):
                original_save(run)
                if run.active_step_ids and not entered.is_set():
                    entered.set()
                    assert release.wait(60)
            store.save_run = save
        try:
            result = asyncio.run(runtime._execute_acg(store.get_run(run_id)))
            results.put({"pid": os.getpid(), "status": result.status.value, "calls": agent.calls})
        except Exception as exc:
            results.put({"pid": os.getpid(), "error": type(exc).__name__ + ": " + str(exc), "calls": agent.calls})
    except BaseException as exc:
        results.put({"setup_error": repr(exc), "pid": os.getpid()})
        entered.set()


@pytest.mark.parametrize("cut", ["claimed", "running_persisted"])
@pytest.mark.slow_multiprocess
def test_real_process_execution_activation_interleaving(ready_boundary, cut):
    runtime, workflow, journal, run_id, mat_id, _ = chain(ready_boundary, prepare_key="act")
    definition = runtime._workflow_for_run(workflow.get_run(run_id)).model_dump(mode="json", by_alias=True)
    ctx = multiprocessing.get_context("spawn")
    entered, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
    worker = ctx.Process(target=_execute_child, args=(str(workflow.db_path.parent), definition,
        run_id, cut, entered, release, results))
    worker.start()
    try:
        assert entered.wait(60), "child did not reach controlled production boundary"
        receipt = runtime.commit_graph_activation(mat_id, idempotency_key="act")
    finally:
        release.set()
        worker.join(60)
        if worker.is_alive():
            worker.terminate()
            worker.join(10)
    result = results.get(timeout=5)
    assert worker.exitcode == 0 and "setup_error" not in result, result
    assert result["pid"] != os.getpid()
    effects = workflow.db_path.parent / "external-effect.jsonl"
    print("process interleaving:", cut, receipt.model_dump(mode="json"), result,
          effects.read_text(encoding="utf-8") if effects.exists() else "no external effect")
    assert receipt.status == "REJECTED", receipt.model_dump()
    assert journal.head(run_id) is None
    assert result["calls"] == ["A"] and effects.exists(), result


def _commit_child(folder, definition, mat_id, start, results):
    try:
        runtime, _, _ = _reopen(folder, definition)
        assert start.wait(60)
        result = runtime.commit_graph_activation(mat_id, idempotency_key="act")
        results.put({"pid": os.getpid(), "receipt": result.model_dump(mode="json")})
    except BaseException as exc:
        results.put({"pid": os.getpid(), "error": repr(exc)})


def _prepare_crash_child(folder, definition, mat_id, cut):
    runtime, _, _ = _reopen(folder, definition)
    store = runtime.graph_activation_authority.store
    original = store._append_activation
    def append(record):
        if cut == "before_insert": os._exit(23)
        original(record)
        os._exit(24)  # uncommitted SQLite write; process cannot run rollback code
    if cut != "after_commit": store._append_activation = append
    receipt = runtime.prepare_graph_activation(mat_id, idempotency_key="crash")
    assert receipt.status == "ACTIVATION_PREPARED", receipt.model_dump()
    os._exit(25)  # durable preparation, acknowledgement deliberately lost


@pytest.mark.parametrize("cut", ["before_insert", "after_insert", "after_commit"])
@pytest.mark.slow_fault_injection
def test_real_process_death_at_preparation_cuts(ready_boundary, cut):
    runtime, workflow, journal, run_id, mat_id, agent = chain(ready_boundary)
    before = workflow.get_run(run_id)
    definition = runtime._workflow_for_run(before).model_dump(mode="json", by_alias=True)
    worker = multiprocessing.get_context("spawn").Process(target=_prepare_crash_child,
        args=(str(workflow.db_path.parent), definition, mat_id, cut))
    worker.start()
    worker.join(60)
    if worker.is_alive(): worker.terminate(); worker.join(10)
    assert worker.exitcode == {"before_insert": 23, "after_insert": 24, "after_commit": 25}[cut]
    assert journal.head(run_id) is None and workflow.get_run(run_id) == before
    prepared = journal.activation_for(mat_id)
    assert (prepared is not None) == (cut == "after_commit")
    replay = runtime.prepare_graph_activation(mat_id, idempotency_key="crash")
    assert replay.status == ("IDEMPOTENT_REPLAY" if prepared else "ACTIVATION_PREPARED")
    assert runtime.commit_graph_activation(mat_id, idempotency_key="crash").status == "ACTIVATED_PAUSED"
    assert agent.calls == []


@pytest.mark.slow_multiprocess
def test_two_spawned_processes_commit_one_formal_head(ready_boundary):
    runtime, workflow, journal, run_id, mat_id, _ = chain(ready_boundary, prepare_key="act")
    definition = runtime._workflow_for_run(workflow.get_run(run_id)).model_dump(mode="json", by_alias=True)
    ctx = multiprocessing.get_context("spawn")
    start, results = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_commit_child, args=(str(workflow.db_path.parent), definition, mat_id, start, results))
               for _ in range(2)]
    for worker in workers: worker.start()
    start.set()
    try:
        outcomes = [results.get(timeout=90) for _ in workers]
    finally:
        for worker in workers:
            worker.join(10)
            if worker.is_alive(): worker.terminate(); worker.join(10)
    assert len({o["pid"] for o in outcomes}) == 2
    assert all(w.exitcode == 0 for w in workers) and all("error" not in o for o in outcomes), outcomes
    assert sum(o["receipt"]["status"] == "ACTIVATED_PAUSED" for o in outcomes) == 1, outcomes
    # A contender that sampled PREPARED before the winner may be refused by
    # the immutable-preparation check. A fresh original-key reconciliation must
    # still return the one committed fact (this transient false conflict is P2).
    assert all(o["receipt"]["status"] in {"ACTIVATED_PAUSED", "IDEMPOTENT_REPLAY", "REJECTED"}
               for o in outcomes), outcomes
    assert runtime.commit_graph_activation(mat_id, idempotency_key="act").status == "IDEMPOTENT_REPLAY"
    assert journal.head(run_id).active_graph_version == 2
    with journal.connection() as conn:
        assert conn.execute("SELECT count(*) FROM graph_activation_heads").fetchone()[0] == 1
    print("process commit competition:", outcomes)


def test_stale_projection_cannot_activate_over_inflight_external_agent(ready_boundary):
    from contracts.planning import TaskPlanPatch, PlannedTask
    from test_planning_commit_runtime import attach
    from support.stores.graph_materialization_store import SQLiteGraphMaterializationStore
    runtime, workflow, agent, run_id, _ = ready_boundary
    attach(runtime, workflow)
    SQLiteGraphMaterializationStore.upgrade_schema(workflow.db_path)
    SQLiteGraphActivationStore.upgrade_schema(workflow.db_path)
    runtime.enable_graph_materialization(SQLiteGraphMaterializationStore(workflow.db_path))
    journal = SQLiteGraphActivationStore(workflow.db_path)
    runtime.enable_graph_activation(journal)
    old = workflow.get_run(run_id)
    definition = runtime._workflow_for_run(old).model_dump(mode="json", by_alias=True)
    ctx = multiprocessing.get_context("spawn")
    entered, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
    worker = ctx.Process(target=_execute_child, args=(str(workflow.db_path.parent), definition,
        run_id, "agent_inflight", entered, release, results))
    worker.start()
    prepared = committed = None
    try:
        assert entered.wait(60)
        assert any(r.get("stage") == "prepared" for r in runtime.execution_value_store.list_node_commits(run_id=run_id))
        # A second legacy snapshot writer can legitimately lose the active
        # projection before a Head exists. The external worker remains alive.
        SQLiteWorkflowStore(workflow.db_path).save_run(old)
        patch = TaskPlanPatch(missionId=old.mission_id, basePlanVersion=1, planVersion=2,
            addNodes=(PlannedTask(key="step:D", title="D", objective="independent D",
                capabilityRequirements=("task_understanding",), sourceRefs=("input:brief",)),))
        with runtime.run_lock_manager.lock_for(run_id):
            source = runtime.planning_commit_authority.accept_patch_locked(run_id, patch,
                proposal_id="D", idempotency_key="D")
        assert source.status == "ACCEPTED", source.model_dump()
        graph = runtime.accept_graph_revision(run_id, source.commit_id, idempotency_key="graph")
        assert graph.status == "ACCEPTED", graph.model_dump()
        mat = runtime.materialize_graph_revision(graph.commit_id, idempotency_key="mat")
        assert mat.status == "MATERIALIZED_INACTIVE", mat.model_dump()
        prepared = runtime.prepare_graph_activation(mat.materialization_id, idempotency_key="act")
        if prepared.status != "REJECTED":
            committed = runtime.commit_graph_activation(mat.materialization_id, idempotency_key="act")
    finally:
        release.set()
        worker.join(60)
        if worker.is_alive(): worker.terminate(); worker.join(10)
    outcome = results.get(timeout=5)
    effects = workflow.db_path.parent / "external-effect.jsonl"
    print("inflight external cut:", prepared.model_dump(mode="json") if prepared else None,
          committed.model_dump(mode="json") if committed else None, outcome,
          effects.read_text(encoding="utf-8") if effects.exists() else "no effect")
    assert worker.exitcode == 0 and "setup_error" not in outcome, outcome
    assert prepared.status == "REJECTED", {"commit": committed.model_dump(mode="json") if committed else None, "worker": outcome}
    assert journal.head(run_id) is None
    assert outcome["calls"] == ["A"] and effects.exists()


def test_unsettled_receipt_blocks_cut_even_without_a_live_worker(ready_boundary):
    from contracts.planning import TaskPlanPatch, PlannedTask
    from test_planning_commit_runtime import attach
    from support.stores.graph_materialization_store import SQLiteGraphMaterializationStore
    runtime, workflow, _, run_id, _ = ready_boundary
    runtime.execution_value_store.prepare_node_commit(run_id=run_id, commit_id=f"commit:{run_id}:A:0")
    attach(runtime, workflow)
    run = workflow.get_run(run_id)
    patch = TaskPlanPatch(missionId=run.mission_id, basePlanVersion=1, planVersion=2,
        addNodes=(PlannedTask(key="step:D", title="D", objective="independent D",
            capabilityRequirements=("task_understanding",), sourceRefs=("input:brief",)),))
    with runtime.run_lock_manager.lock_for(run_id):
        source = runtime.planning_commit_authority.accept_patch_locked(run_id, patch,
            proposal_id="D", idempotency_key="D")
    assert source.status == "ACCEPTED", source.model_dump()
    graph = runtime.accept_graph_revision(run_id, source.commit_id, idempotency_key="graph")
    assert graph.status == "ACCEPTED", graph.model_dump()
    SQLiteGraphMaterializationStore.upgrade_schema(workflow.db_path)
    runtime.enable_graph_materialization(SQLiteGraphMaterializationStore(workflow.db_path))
    mat = runtime.materialize_graph_revision(graph.commit_id, idempotency_key="mat")
    assert mat.status == "MATERIALIZED_INACTIVE", mat.model_dump()
    SQLiteGraphActivationStore.upgrade_schema(workflow.db_path)
    journal = SQLiteGraphActivationStore(workflow.db_path)
    runtime.enable_graph_activation(journal)
    result = runtime.prepare_graph_activation(mat.materialization_id, idempotency_key="act")
    assert result.status == "REJECTED" and "unsettled" in result.reason, result.model_dump()
    assert journal.head(run_id) is None and workflow.get_run(run_id).acg_blueprint["version"] == 1


def _recover_child(folder, definition, run_id, results):
    try:
        runtime, workflow, agent = _reopen(folder, definition)
        before = workflow.get_run(run_id).model_dump(mode="json", by_alias=True)
        def forbidden(*a, **kw): raise AssertionError("recovery invoked planning or binding")
        runtime.runtime_planning_coordinator.planner_for_run = forbidden
        runtime.runtime_binding_service.prepare = forbidden
        runtime.semantic_revision_service.prepare = forbidden
        asyncio.run(runtime._recover_pending_planning_transitions(limit=10))
        asyncio.run(runtime.close_orphaned_runs(limit=10))
        with pytest.raises(ValueError, match="execution permit"):
            asyncio.run(runtime.execute_prepared_run(run_id))
        assert workflow.get_run(run_id).model_dump(mode="json", by_alias=True) == before
        assert agent.calls == []
        results.put({"pid": os.getpid(), "ok": True})
    except BaseException as exc:
        results.put({"error": repr(exc), "pid": os.getpid()})


def test_real_completed_A_pending_BC_activation_and_process_recovery(tmp_path, monkeypatch):
    # Reuse the independently accepted S03-01 complete initial communication
    # fixture; it executes A through the real NodeRunner and persists its receipt.
    import test_react_loop
    from test_graph_materialization_audit import test_real_executed_A_pending_BC_materialized_D_survives_process_restart
    from test_planning_commit_runtime import dump_databases
    captured = []
    original = test_react_loop.runtime_at
    def capture(path):
        value = original(path)
        captured.append(value)
        return value
    monkeypatch.setattr(test_react_loop, "runtime_at", capture)
    test_real_executed_A_pending_BC_materialized_D_survives_process_restart(tmp_path, True)
    runtime, workflow, agent = captured[0]
    run = workflow.list_all_runs(limit=10)[0]
    before = run.model_copy(deep=True)
    outside = {k:v for k,v in dump_databases(workflow, include_ledger=True).items()
               if k != workflow.db_path.name}
    SQLiteGraphActivationStore.upgrade_schema(workflow.db_path)
    journal = SQLiteGraphActivationStore(workflow.db_path)
    runtime.enable_graph_activation(journal)
    with journal.connection() as conn:
        mat_id = conn.execute("SELECT materialization_id FROM graph_materializations").fetchone()[0]
    assert runtime.prepare_graph_activation(mat_id, idempotency_key="act").status == "ACTIVATION_PREPARED"
    original_upsert = SQLiteWorkflowStore._upsert_run
    def traced_upsert(conn, run):
        try:
            return original_upsert(conn, run)
        except ValueError as exc:
            print("real prefix activation write rejected:", str(exc))
            raise
    monkeypatch.setattr(SQLiteWorkflowStore, "_upsert_run", staticmethod(traced_upsert))
    receipt = runtime.commit_graph_activation(mat_id, idempotency_key="act")
    assert receipt.status == "ACTIVATED_PAUSED", receipt.model_dump()
    current = workflow.get_run(run.run_id)
    assert current.run_id == before.run_id and current.get_step("A") == before.get_step("A")
    assert all(current.get_step(k).status == StepStatus.PENDING for k in "BCD")
    assert current.completed_step_ids == before.completed_step_ids == ["A"]
    assert current.execution_state["checkpointId"] is None
    assert current.execution_state["graphActivation"]["supersededCheckpointId"] == before.execution_state["checkpointId"]
    assert {k:v for k,v in dump_databases(workflow, include_ledger=True).items()
            if k != workflow.db_path.name} == outside
    current.lifecycle_message = "paused diagnostic after real completion"
    workflow.save_run(current)
    definition = runtime._workflow_for_run(current).model_dump(mode="json", by_alias=True)
    ctx = multiprocessing.get_context("spawn")
    results = ctx.Queue()
    worker = ctx.Process(target=_recover_child, args=(str(workflow.db_path.parent), definition, current.run_id, results))
    worker.start()
    try:
        result = results.get(timeout=90)
    finally:
        worker.join(10)
        if worker.is_alive(): worker.terminate(); worker.join(10)
    assert worker.exitcode == 0 and result.get("ok") is True, result
    assert result["pid"] != os.getpid() and agent.calls == ["A"]
    assert {k:v for k,v in dump_databases(workflow, include_ledger=True).items()
            if k != workflow.db_path.name} == outside

"""Settlement events use full-snapshot CAS without weakening terminal guards."""
from types import SimpleNamespace

import pytest

from components.executor.graph import ACGExecutionState
from contracts.workflow import RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus
from runtime.state_persistence import ACGStatePersistenceService
from support.stores.memory_workflow_store import MemoryWorkflowStore
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore


@pytest.fixture(params=['memory', 'sqlite'])
def store(request, tmp_path):
    return MemoryWorkflowStore() if request.param == 'memory' else SQLiteWorkflowStore(tmp_path / 'settlement.db')


def record(store):
    mission = RuntimeMissionRecord(title='settlement')
    store.save_mission(mission)
    run = RuntimeRunRecord(runId='execution', missionId=mission.mission_id, workflowId='workflow', domain='general',
                           runtimeEngine='workflow', status=WorkflowStatus.RUNNING)
    store.save_run(run)
    return run


def event():
    return {'eventId': 'step.cancelled:execution', 'eventType': 'step.cancelled', 'aggregateId': 'step',
            'payload': {'runId': 'execution', 'reason': 'operator_cancel'}}


def test_stale_event_snapshot_cas_preserves_run_mission_and_outbox(store):
    stale = record(store)
    current = stale.model_copy(deep=True)
    current.execution_state['newEvidence'] = 'must survive even at same runtimeRevision'
    store.save_run(current)
    before_run = store.get_run(current.run_id)
    before_mission = store.get_mission(current.mission_id)
    before_events = store.list_outbox()
    with pytest.raises(ValueError, match='Run changed'):
        store.save_run_with_events(stale, [event()], expected_snapshot=stale)
    assert store.get_run(current.run_id) == before_run
    assert store.get_mission(current.mission_id) == before_mission
    assert store.list_outbox() == before_events


def test_cancelled_terminal_accepts_exact_once_event_without_losing_trace_or_state(store):
    run = record(store)
    run.status = WorkflowStatus.CANCELLED
    run.execution_state['preservedOutput'] = 'output-ref'
    store.save_run(run)
    current = store.get_run(run.run_id)
    store.save_run_with_events(current, [event()], expected_snapshot=current)
    once = store.list_outbox()
    store.save_run_with_events(current, [event()], expected_snapshot=current)
    assert store.list_outbox() == once
    assert store.get_run(run.run_id) == current


def test_stale_acg_projection_cannot_mutate_cancelled_snapshot(store):
    run = record(store)
    cancelled = run.model_copy(deep=True)
    cancelled.status = WorkflowStatus.CANCELLED
    cancelled.execution_state['committedCancellation'] = True
    store.save_run(cancelled)
    before = store.get_run(run.run_id)
    persistence = ACGStatePersistenceService(collaborators=SimpleNamespace(workflow_store=store))
    persistence.persist(run, ACGExecutionState(runId=run.run_id, activeStepIds=['late-node']))
    assert store.get_run(run.run_id) == before

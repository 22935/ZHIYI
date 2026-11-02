"""Shared Memory/SQLite contracts: Mission is a summary of independent Runs."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest

from components.mission_manager.service import MissionManager
from components.mission_manager.state_machine import InvalidStateTransition, StateMachine
from components.mission_manager.store import WorkflowRegistry
from contracts.workflow import RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus, WorkflowStep, StepStatus
from support.stores.memory_workflow_store import MemoryWorkflowStore
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore


@pytest.fixture(params=['memory', 'sqlite'])
def store(request, tmp_path):
    return MemoryWorkflowStore() if request.param == 'memory' else SQLiteWorkflowStore(tmp_path / 'branches.db')


def branch(store, mission, key, status):
    run = RuntimeRunRecord(runId=key, missionId=mission.mission_id, workflowId='w', domain='general',
        runtimeEngine='workflow', status=WorkflowStatus(status))
    if status == 'waiting_review':
        run.steps = [WorkflowStep(stepId='A', name='A', agentName='a', status=StepStatus.WAITING_REVIEW)]
    store.save_run(run)
    return store.get_run(key)


@pytest.mark.parametrize('a,b,expected', [
    ('pending', 'completed', 'pending'), ('running', 'completed', 'running'),
    ('cancelled', 'waiting_review', 'waiting_review'), ('failed', 'running', 'running'),
    ('completed', 'failed', 'failed'), ('failed', 'completed', 'failed'),
    ('waiting_review', 'completed', 'waiting_review'), ('running', 'waiting_review', 'running'),
    ('superseded', 'pending', 'pending'), ('cancelled', 'completed', 'cancelled'),
])
def test_aggregate_is_order_independent_and_keeps_complete_run_records(store, a, b, expected):
    mission = RuntimeMissionRecord(title='branches')
    store.save_mission(mission)
    records = [branch(store, mission, 'a', a), branch(store, mission, 'b', b)]
    assert store.get_mission(mission.mission_id).status.value == expected
    for run in records:
        assert store.get_run(run.run_id).model_dump(mode='json') == run.model_dump(mode='json')


@pytest.mark.parametrize('callback', ['mark_running', 'mark_waiting_review', 'mark_completed', 'mark_cancelled',
    'mark_failed', 'mark_running_for_new_run', 'mark_failed_for_run'])
def test_stale_callbacks_never_write_old_mission_fields_or_override_other_branches(store, callback):
    mission = RuntimeMissionRecord(title='original')
    store.save_mission(mission)
    stale = store.get_mission(mission.mission_id)
    a = branch(store, mission, 'a', 'completed')
    b = branch(store, mission, 'b', 'running')
    current = store.get_mission(mission.mission_id)
    current.title = 'new title'
    store.save_mission(current)
    before = store.get_mission(mission.mission_id).model_dump(mode='json')
    manager = MissionManager(workflow_store=store, workflow_registry=WorkflowRegistry())
    kwargs = {'run_id': a.run_id} if callback in {'mark_running_for_new_run', 'mark_failed_for_run'} else {}
    getattr(manager, callback)(stale, **kwargs)
    assert store.get_mission(mission.mission_id).model_dump(mode='json') == before
    assert store.get_run(a.run_id) == a
    assert store.get_run(b.run_id) == b
    # Even a legacy stale save cannot overwrite the derived lifecycle status.
    store.save_mission(stale)
    assert store.get_mission(mission.mission_id).status == WorkflowStatus.RUNNING


def test_runless_mission_still_obeys_the_original_terminal_state_machine(store):
    mission = RuntimeMissionRecord(title='runless')
    store.save_mission(mission)
    manager = MissionManager(workflow_store=store, workflow_registry=WorkflowRegistry())
    manager.mark_running(mission)
    manager.mark_completed(mission)
    with pytest.raises(InvalidStateTransition):
        manager.mark_cancelled(mission)
    assert not StateMachine().can_transition(WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED)


def test_full_snapshot_compare_and_swap_rolls_back_run_mission_and_outbox(store):
    mission = RuntimeMissionRecord(title='CAS')
    store.save_mission(mission)
    old = branch(store, mission, 'a', 'running')
    changed = old.model_copy(deep=True)
    changed.lifecycle_message = 'progress at the same runtimeRevision'
    store.save_run(changed)
    candidate = old.model_copy(deep=True)
    candidate.status = WorkflowStatus.CANCELLED
    before = store.get_mission(mission.mission_id)
    outbox = store.list_outbox(limit=10000)
    with pytest.raises(ValueError, match='Run changed'):
        store.save_run(candidate, expected_snapshot=old)
    assert store.get_run('a') == changed
    assert store.get_mission(mission.mission_id) == before
    assert store.list_outbox(limit=10000) == outbox


def test_projection_can_be_resaved_without_false_outbox_conflicts(store):
    mission = RuntimeMissionRecord(title='outbox serialization')
    store.save_mission(mission)
    run = branch(store, mission, 'a', 'running')
    projected = store.get_mission(mission.mission_id)
    events = store.list_outbox(limit=10000)
    store.save_mission(projected)
    assert store.get_mission(mission.mission_id) == projected
    assert store.get_run(run.run_id) == run
    assert store.list_outbox(limit=10000) == events


def test_run_outbox_failure_rolls_back_mission_projection_too(store):
    mission = RuntimeMissionRecord(title='rollback')
    store.save_mission(mission)
    run = branch(store, mission, 'a', 'running')
    event = {'eventId': 'same-event', 'eventType': 'test', 'payload': {'version': 1}}
    store.save_run_with_events(run, [event])
    before = store.get_mission(mission.mission_id)
    outbox = store.list_outbox(limit=10000)
    candidate = run.model_copy(deep=True)
    candidate.status = WorkflowStatus.COMPLETED
    with pytest.raises(ValueError, match='conflict'):
        store.save_run_with_events(candidate, [{**event, 'payload': {'version': 2}}])
    assert store.get_run('a') == run
    assert store.get_mission(mission.mission_id) == before
    assert store.list_outbox(limit=10000) == outbox


def test_memory_readers_cannot_observe_an_uncommitted_mission_summary(monkeypatch):
    store = MemoryWorkflowStore()
    mission = RuntimeMissionRecord(title='atomic read')
    store.save_mission(mission)
    run = branch(store, mission, 'a', 'running')
    run.status = WorkflowStatus.COMPLETED
    entered, release = Event(), Event()
    original = store.project_mission_status
    def held(mission_id):
        entered.set()
        assert release.wait(timeout=5)
        return original(mission_id)
    monkeypatch.setattr(store, 'project_mission_status', held)
    def read():
        return store.get_run('a').status, store.get_mission(mission.mission_id).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(store.save_run, run)
        assert entered.wait(timeout=5)
        reader = pool.submit(read)
        try:
            # A reader must block at the transaction boundary, rather than
            # returning COMPLETED / RUNNING from a partially applied write.
            with pytest.raises(TimeoutError):
                reader.result(timeout=.2)
        finally:
            release.set()
        writer.result(timeout=5)
        assert reader.result(timeout=5) == (WorkflowStatus.COMPLETED, WorkflowStatus.COMPLETED)


def test_independent_sqlite_writers_and_process_restart_keep_one_consistent_summary(tmp_path):
    path = tmp_path / 'concurrent.db'
    store = SQLiteWorkflowStore(path)
    mission = RuntimeMissionRecord(title='concurrent')
    store.save_mission(mission)
    a, b = [branch(store, mission, key, 'running') for key in ('a', 'b')]
    barrier = Barrier(2)
    def finish(pair):
        run, status = pair
        writer = SQLiteWorkflowStore(path)
        run.status = WorkflowStatus(status)
        run.runtime_revision += 1
        barrier.wait(timeout=10)
        writer.save_run(run)
        return run
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(finish, [(a, 'completed'), (b, 'failed')]))
    accepted = branch(store, mission, 'c', 'pending')
    cancelled = accepted.model_copy(deep=True)
    cancelled.status = WorkflowStatus.CANCELLED
    store.save_run(cancelled, expected_snapshot=accepted)
    records.append(cancelled)
    reopened = SQLiteWorkflowStore(path)
    assert reopened.get_mission(mission.mission_id).status.value == 'failed'
    for run in records:
        assert reopened.get_run(run.run_id).model_dump(mode='json') == run.model_dump(mode='json')
    root = Path(__file__).resolve().parents[4]
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(root / 'apps/agentOS/src'), str(root / 'apps/agentOS')])}
    code = """import json,sys
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
s=SQLiteWorkflowStore(sys.argv[1])
print(json.dumps({'mission':s.get_mission(sys.argv[2]).model_dump(mode='json'),'runs':[s.get_run(k).model_dump(mode='json') for k in ('a','b','c')]}))
"""
    result = subprocess.run([sys.executable, '-c', code, str(path), mission.mission_id], env=env,
        capture_output=True, text=True, check=True, timeout=30)
    saved = json.loads(result.stdout)
    assert saved['mission'] == reopened.get_mission(mission.mission_id).model_dump(mode='json')
    assert saved['runs'] == [run.model_dump(mode='json') for run in records]

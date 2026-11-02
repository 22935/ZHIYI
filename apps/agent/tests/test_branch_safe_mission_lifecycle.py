"""Real HTTP/SQLite regression for independent Runs sharing one Mission."""
import asyncio
import json
import os
from contextlib import contextmanager

import pytest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_mission_semantic_commands import api, create


def completed_source(client, runtime, coordinator):
    source = create(client)
    async def wait():
        await asyncio.shield(coordinator._tasks[source['runId']])
    client.portal.call(wait)
    run = runtime.workflow_store.get_run(source['runId'])
    assert run.status.value == 'completed'
    assert runtime.workflow_store.get_mission(run.mission_id).status.value == 'completed'
    return run


def pending_branches(client, source):
    def submit(key):
        response = client.post(f'/agentos/v2/missions/{source.mission_id}/runs', json={
            'sourceRunId': source.run_id, 'clientRequestId': key, 'input': {}, 'rerunReason': 'branch_safe'})
        assert response.status_code == 202, response.text
        return response.json()['runId']
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(submit, ['branch-left', 'branch-right']))


def test_pending_successor_cancel_is_independent_of_completed_mission(api, monkeypatch, tmp_path):
    client, runtime, coordinator, _ = api
    source = completed_source(client, runtime, coordinator)
    source_before = source.model_dump(mode='json')
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    branches = pending_branches(client, source)
    store = runtime.workflow_store
    before = {key: store.get_run(key).model_dump(mode='json') for key in branches}
    caps = {key: client.get(f'/agentos/v2/runs/{key}').json()['actionCapabilities'] for key in branches}
    assert all(record['status'] == 'pending' for record in before.values())
    assert all(offer['canCancel'] for offer in caps.values())
    evidence = {'missionBefore': store.get_mission(source.mission_id).model_dump(mode='json'),
        'sourceBefore': source_before, 'runsBefore': before, 'capabilitiesBefore': caps,
        'signalsBefore': {key: runtime._run_cancellation_requested(key) for key in branches}}
    response = client.post(f'/agentos/v2/runs/{branches[0]}/cancel',
        json={'expectedRuntimeRevision': caps[branches[0]]['runtimeRevision']})
    evidence.update(responseStatus=response.status_code, response=response.json(),
        missionAfter=store.get_mission(source.mission_id).model_dump(mode='json'),
        runsAfter={key: store.get_run(key).model_dump(mode='json') for key in branches},
        signalsAfter={key: runtime._run_cancellation_requested(key) for key in branches})
    directory = Path(os.environ.get('PR_UI_041_EVIDENCE', str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'pending-cancel-snapshot.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    assert response.status_code == 200, response.text
    assert store.get_run(branches[0]).status.value == 'cancelled'
    assert store.get_run(branches[1]).model_dump(mode='json') == before[branches[1]]
    assert store.get_run(source.run_id).model_dump(mode='json') == source_before
    assert client.get(f'/agentos/v2/runs/{branches[1]}').json()['actionCapabilities']['canCancel'] is True
    cancelled = store.get_run(branches[0]).model_dump(mode='json')
    assert runtime.cancel(branches[0]).model_dump(mode='json') == cancelled
    assert not runtime._run_cancellation_requested(branches[1])
    other = client.post(f'/agentos/v2/runs/{branches[1]}/cancel',
        json={'expectedRuntimeRevision': caps[branches[1]]['runtimeRevision']})
    assert other.status_code == 200, other.text
    assert store.get_run(branches[0]).model_dump(mode='json') == cancelled


@contextmanager
def executing_branches(api, monkeypatch, modes=('complete', 'complete')):
    client, runtime, coordinator, agent = api
    source = completed_source(client, runtime, coordinator)
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    branches = pending_branches(client, source)
    gates = {key: asyncio.Event() for key in branches}
    arrived = {key: asyncio.Event() for key in branches}
    original_agent = agent.run
    original_build = runtime._build_acg_blueprint
    async def gated(context):
        key = context.run.run_id
        if key in gates:
            arrived[key].set()
            await gates[key].wait()
            if modes[branches.index(key)] == 'fail':
                raise RuntimeError('deterministic branch failure')
        return await original_agent(context)
    def build(task, run, workflow):
        blueprint, plan, bindings = original_build(task, run, workflow)
        if run.run_id in branches and modes[branches.index(run.run_id)] == 'review':
            blueprint = blueprint.model_copy(update={'nodes': [node.model_copy(update={'review_required': True})
                if node.node_id == 'A' else node for node in blueprint.nodes]})
        return blueprint, plan, bindings
    from test_planning_loop import Planner
    from contracts.runtime_planning import RuntimePlanningDecision
    def decide(observation, _plan):
        return RuntimePlanningDecision(observationId=observation.fingerprint(),
            action='abort' if observation.wake_reason == 'failure' else 'complete' if not observation.remaining_step_ids else 'continue',
            reason='deterministic branch failure recorded' if observation.wake_reason == 'failure' else 'persisted branch facts')
    monkeypatch.setattr(runtime.runtime_planning_coordinator, 'planner_for_run', lambda _: Planner(decide))
    monkeypatch.setattr(agent, 'run', gated)
    monkeypatch.setattr(runtime, '_build_acg_blueprint', build)
    async def execute(key):
        from app.security.internal_auth import TrustedUserContext, _trusted_user_context
        token = _trusted_user_context.set(TrustedUserContext('owner', 'owner', 'user', 'tenant'))
        try:
            return await runtime.execute_prepared_run(key)
        finally:
            _trusted_user_context.reset(token)
    tasks = {key: client.portal.start_task_soon(execute, key) for key in branches}
    async def started():
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in arrived.values())), timeout=10)
    try:
        client.portal.call(started)
        assert all(runtime.workflow_store.get_run(key).status.value == 'running' for key in branches)
        yield source, branches, gates, tasks
    finally:
        for gate in gates.values():
            client.portal.call(gate.set)
        for task in tasks.values():
            try:
                task.result(timeout=15)
            except RuntimeError:
                pass  # The explicit failure scenario asserts the full durable record below.


def release_branch(client, runtime, key, gates, tasks, expected):
    client.portal.call(gates[key].set)
    if expected == 'failed':
        from components.executor.graph import ACGSuperstepError
        with pytest.raises(ACGSuperstepError):
            tasks[key].result(timeout=15)
    else:
        tasks[key].result(timeout=15)
    record = runtime.workflow_store.get_run(key)
    assert record.status.value == expected, record.model_dump_json()
    if expected == 'failed':
        assert 'deterministic branch failure' in str(record.error)
    return record.model_dump(mode='json')


def test_completed_branch_does_not_block_cancelling_another_running_branch(api, monkeypatch):
    client, runtime, _, _ = api
    with executing_branches(api, monkeypatch) as (source, branches, gates, tasks):
        a, b = branches
        source_before = runtime.workflow_store.get_run(source.run_id).model_dump(mode='json')
        completed = release_branch(client, runtime, a, gates, tasks, 'completed')
        b_before = runtime.workflow_store.get_run(b).model_dump(mode='json')
        assert b_before['status'] == 'running'
        assert runtime.workflow_store.get_mission(source.mission_id).status.value == 'running'
        cap = client.get(f'/agentos/v2/runs/{b}').json()['actionCapabilities']
        assert cap['canCancel'] is True
        payload = {'expectedRuntimeRevision': cap['runtimeRevision']}
        assert client.post(f'/agentos/v2/runs/{b}/cancel', json=payload).status_code == 200
        cancelled = release_branch(client, runtime, b, gates, tasks, 'cancelled')
        assert cancelled['trace'][:len(b_before['trace'])] == b_before['trace']
        # Lost response: replay exactly the same request, then reconcile facts.
        assert client.post(f'/agentos/v2/runs/{b}/cancel', json=payload).status_code == 409
        assert runtime.workflow_store.get_run(b).model_dump(mode='json') == cancelled
        assert runtime.workflow_store.get_run(a).model_dump(mode='json') == completed
        assert runtime.workflow_store.get_run(source.run_id).model_dump(mode='json') == source_before


@pytest.mark.parametrize('modes,order', [
    (('complete', 'fail'), (0, 1)), (('fail', 'complete'), (0, 1)),
    (('review', 'complete'), (0, 1)), (('complete', 'review'), (0, 1)),
])
def test_branch_completion_failure_and_review_do_not_overwrite_each_other(api, monkeypatch, modes, order):
    client, runtime, _, _ = api
    with executing_branches(api, monkeypatch, modes) as (source, branches, gates, tasks):
        snapshots = {}
        for index in order:
            key = branches[index]
            expected = {'complete': 'completed', 'fail': 'failed', 'review': 'waiting_review'}[modes[index]]
            snapshots[key] = release_branch(client, runtime, key, gates, tasks, expected)
            for previous, record in snapshots.items():
                assert runtime.workflow_store.get_run(previous).model_dump(mode='json') == record
        statuses = {record['status'] for record in snapshots.values()}
        expected_mission = 'waiting_review' if 'waiting_review' in statuses else 'failed'
        assert runtime.workflow_store.get_mission(source.mission_id).status.value == expected_mission
        assert runtime.workflow_store.get_run(source.run_id).model_dump(mode='json') == source.model_dump(mode='json')


def test_cancelled_branch_cannot_block_another_branch_review(api, monkeypatch):
    client, runtime, _, _ = api
    with executing_branches(api, monkeypatch, ('complete', 'review')) as (source, branches, gates, tasks):
        a, b = branches
        cap = client.get(f'/agentos/v2/runs/{a}').json()['actionCapabilities']
        assert client.post(f'/agentos/v2/runs/{a}/cancel', json={'expectedRuntimeRevision': cap['runtimeRevision']}).status_code == 200
        cancelled = release_branch(client, runtime, a, gates, tasks, 'cancelled')
        paused = release_branch(client, runtime, b, gates, tasks, 'waiting_review')
        assert runtime.workflow_store.get_mission(source.mission_id).status.value == 'waiting_review'
        assert client.get(f'/agentos/v2/runs/{b}').json()['actionCapabilities']['canReview'] is True
        response = client.post(f'/agentos/v2/runs/{b}/reviews', json={'stepId': 'A', 'decision': 'approved',
            'operationId': 'independent-review', 'expectedRunUpdatedAt': paused['updated_at'],
            'expectedStepStatus': 'waiting_review'})
        assert response.status_code == 200, response.text
        assert runtime.workflow_store.get_run(a).model_dump(mode='json') == cancelled
        assert runtime.workflow_store.get_run(b).status.value == 'completed'


@pytest.mark.parametrize('fault', ['persist', 'snapshot_conflict', 'stale_revision', 'notification'])
def test_cancel_failures_never_leave_a_partial_signal_or_lose_progress(api, monkeypatch, fault):
    client, runtime, coordinator, _ = api
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    created = create(client)
    run_id = created['runId']
    store = runtime.workflow_store
    before = store.get_run(run_id).model_dump(mode='json')
    mission_before = store.get_mission(created['missionId']).model_dump(mode='json')
    save = store.save_run
    competitor = None
    def interrupted(run, **kwargs):
        nonlocal competitor
        if kwargs.get('expected_snapshot') is not None:
            if fault == 'persist':
                raise ValueError('injected persistence failure')
            if fault == 'snapshot_conflict':
                current = store.get_run(run_id)
                current.lifecycle_message = 'concurrently committed progress'
                current.runtime_revision += 1
                save(current)
                competitor = current.model_dump(mode='json')
        return save(run, **kwargs)
    monkeypatch.setattr(store, 'save_run', interrupted)
    if fault == 'notification':
        def unavailable(**_):
            raise RuntimeError('identity projection unavailable')
        monkeypatch.setattr(runtime, '_flush_identity_outbox', unavailable)
    response = client.post(f'/agentos/v2/runs/{run_id}/cancel', json={
        'expectedRuntimeRevision': before['runtime_revision'] + (1 if fault == 'stale_revision' else 0)})
    if fault == 'notification':
        assert response.status_code == 200
        assert store.get_run(run_id).status.value == 'cancelled'
        assert runtime._run_cancellation_requested(run_id)
    else:
        assert response.status_code == 409
        assert not runtime._run_cancellation_requested(run_id)
        assert store.get_run(run_id).model_dump(mode='json') == (competitor or before)
        assert store.get_mission(created['missionId']).model_dump(mode='json') == mission_before


def test_superseded_delete_offer_matches_command_and_persistent_soft_delete(api, monkeypatch):
    client, runtime, coordinator, _ = api
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    created = create(client)
    store = runtime.workflow_store
    run = store.get_run(created['runId'])
    from contracts.workflow import WorkflowStatus
    run.status = WorkflowStatus.SUPERSEDED
    run.execution_state['supersededByRunId'] = 'replacement'
    store.save_run(run)
    url = f'/agentos/v2/runs/{run.run_id}'
    cap = client.get(url).json()['actionCapabilities']
    assert cap['canDelete'] is True
    assert not cap['canCancel'] and not cap['canRerunSuccessor'] and not cap['canReview']
    before = store.get_run(run.run_id).model_dump(mode='json')
    authorize = runtime.mission_semantic_service.authorize
    monkeypatch.setattr(runtime.mission_semantic_service, 'authorize', lambda principal, mission, action: action == 'read')
    assert client.get(url).json()['actionCapabilities']['canDelete'] is False
    assert client.delete(url).status_code == 403
    assert store.get_run(run.run_id).model_dump(mode='json') == before
    monkeypatch.setattr(runtime.mission_semantic_service, 'authorize', authorize)
    response = client.delete(url)
    assert response.status_code == 200, response.text
    deleted = store.get_run(run.run_id).model_dump(mode='json')
    assert deleted['record_state'] == 'deleted'
    for key in ('status', 'steps', 'trace', 'execution_state', 'runtime_revision'):
        assert deleted[key] == before[key]
    assert client.get(url).status_code == 404

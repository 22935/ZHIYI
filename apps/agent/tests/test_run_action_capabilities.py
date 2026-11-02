"""Run authority adversaries through trusted HTTP and real temporary SQLite."""
import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_mission_semantic_commands import api, create
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
from test_mission_semantic_commands import BODY


def test_same_source_has_multiple_active_branches_and_stable_replay(api, monkeypatch):
    client, runtime, coordinator, _ = api
    source = create(client)
    async def completed():
        task = coordinator._tasks.get(source['runId'])
        if task is not None:
            await asyncio.shield(task)
    client.portal.call(completed)
    original = runtime.workflow_store.get_run(source['runId'])
    assert original.status.value == 'completed'
    before = original.model_dump(mode='json')

    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    url = f"/agentos/v2/missions/{source['missionId']}/runs"
    def submit(key):
        response = client.post(url, json={'sourceRunId': original.run_id,
            'clientRequestId': key, 'input': {}, 'rerunReason': 'branch_test'})
        assert response.status_code == 202, response.text
        return response.json()['runId']

    with ThreadPoolExecutor(max_workers=2) as pool:
        replay = list(pool.map(submit, ['same-branch', 'same-branch']))
        children = list(pool.map(submit, ['branch-left', 'branch-right']))
    assert replay[0] == replay[1]
    assert len(set(children + replay)) == 3
    for run_id in children:
        run = runtime.workflow_store.get_run(run_id)
        assert run.status.value == 'pending'
        assert run.execution_state['sourceRunId'] == original.run_id
        assert run.execution_state['parentRunId'] == original.run_id
        assert not run.execution_state.get('supersedesRunId')
    assert runtime.workflow_store.get_run(original.run_id).model_dump(mode='json') == before

    reopened = SQLiteWorkflowStore(runtime.workflow_store.db_path)
    assert all(reopened.get_run(run_id).status.value == 'pending' for run_id in children)
    root = Path(__file__).resolve().parents[3]
    environment = {**os.environ, 'PYTHONPATH': os.pathsep.join([
        str(root / 'apps' / 'agentOS' / 'src'), str(root / 'apps' / 'agentOS'), str(root)])}
    program = """import json,sys
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
s=SQLiteWorkflowStore(sys.argv[1])
print(json.dumps([(s.get_run(i).run_id,s.get_run(i).execution_state.get('sourceRunId')) for i in sys.argv[2:]]))
"""
    result = subprocess.run([sys.executable, '-c', program, str(runtime.workflow_store.db_path), *children],
        env=environment, capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(result.stdout) == [[run_id, original.run_id] for run_id in children]
    workspace = client.get(f"/agentos/v2/missions/{original.mission_id}/workspace",
        params={'runId': children[0]}).json()
    offers = {row['runId']: row['actionCapabilities'] for row in workspace['runs']}
    for run_id in children:
        assert offers[run_id]['canCancel'] is True
        assert offers[run_id]['canRerunSuccessor'] is False
        assert offers[run_id]['isExecutionActive'] is True
    assert offers[original.run_id]['canCancel'] is False
    assert offers[original.run_id]['canRerunSuccessor'] is True
    assert 'currentRunId' not in workspace


def test_client_offers_cannot_grant_owner_state_or_revision_permissions(api, monkeypatch):
    client, runtime, coordinator, _ = api
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    source = create(client)
    url = f"/agentos/v2/runs/{source['runId']}"
    snapshot = client.get(url).json()
    caps = snapshot['actionCapabilities']
    assert caps['canCancel'] is True
    assert caps['canExecuteFormalAction'] is False
    assert caps['canReview'] is False
    for override in [{'x-authenticated-user-id': 'intruder'}, {'x-authenticated-tenant-id': 'foreign'}]:
        assert client.post(url + '/cancel', headers=override, json={}).status_code in {403, 404}
        assert client.get(url, headers=override).status_code in {403, 404}
    # No review/checkpoint exists. Forged capability bits do not become evidence.
    assert client.post(url + '/reviews', json={'stepId': 'A', 'decision': 'approved',
        'operationId': 'forged-review', 'canReview': True}).status_code in {409, 422}
    assert client.post(url + '/steps/A/retry', json={'mode': 'current_run',
        'clientRequestId': 'forged-in-place', 'expectedRuntimeRevision': caps['runtimeRevision']}).status_code == 409
    assert client.post(url + '/cancel', json={'canCancel': True}).status_code == 422
    changed = runtime.workflow_store.get_run(source['runId'])
    changed.lifecycle_message = 'new persisted progress'
    changed.runtime_revision += 1
    runtime.workflow_store.save_run(changed)
    assert client.post(url + '/cancel', json={'expectedRuntimeRevision': caps['runtimeRevision']}).status_code == 409
    latest = client.get(url).json()['actionCapabilities']
    assert client.post(url + '/cancel', json={'expectedRuntimeRevision': latest['runtimeRevision']}).status_code == 200
    terminal = client.get(url).json()['actionCapabilities']
    assert terminal['canCancel'] is False
    before = runtime.workflow_store.get_run(source['runId']).model_dump(mode='json')
    assert client.post(url + '/cancel', json={}).status_code == 409
    assert runtime.workflow_store.get_run(source['runId']).model_dump(mode='json') == before
    # Runtime remains the command authority even if a client replays the old offer.
    assert runtime.workflow_store.get_run(source['runId']).status.value == 'cancelled'


def test_projection_lag_does_not_turn_source_edges_into_supersession(api, monkeypatch):
    client, runtime, coordinator, _ = api
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    first = create(client)
    run = runtime.workflow_store.get_run(first['runId'])
    # A source relationship alone must not revoke an independent active branch.
    run.execution_state['sourceRunId'] = 'older-source'
    runtime.workflow_store.save_run(run)
    url = f"/agentos/v2/runs/{run.run_id}"
    assert client.get(url).json()['actionCapabilities']['canCancel'] is True
    run = runtime.workflow_store.get_run(run.run_id)
    run.execution_state['supersededByRunId'] = 'replacement'
    runtime.workflow_store.save_run(run)
    result = client.get(url).json()['actionCapabilities']
    assert result['isSuperseded'] is True
    assert result['canInspect'] is True and result['canDiscuss'] is True
    assert not any(value for key, value in result.items() if key.startswith('can') and key not in {'canInspect', 'canDiscuss'})
    assert client.post(url + '/cancel', json={}).status_code == 409
    assert client.post(url + '/copilot/permission', json={'permission': 'task_collaboration'}).status_code == 409


def test_trusted_unscoped_namespace_requires_the_existing_semantic_authority(api, monkeypatch):
    client, runtime, coordinator, _ = api
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    unscoped = {'x-authenticated-tenant-id': ''}
    created = client.post('/agentos/v2/missions', json={**BODY, 'clientRequestId': 'unscoped-source'}, headers=unscoped)
    assert created.status_code == 202, created.text
    url = '/agentos/v2/runs/' + created.json()['runId']
    cap = client.get(url, headers=unscoped).json()['actionCapabilities']
    assert cap['canCancel'] is True and cap['canInspect'] is True
    # Same user in a different tenant cannot reinterpret the unscoped Mission.
    assert client.get(url).status_code == 403
    assert client.post(url + '/cancel', json={}).status_code == 403


def test_read_grant_does_not_imply_write_offers_or_allow_a_forged_command(api, monkeypatch):
    client, runtime, coordinator, _ = api
    async def hold(_):
        return False
    monkeypatch.setattr(coordinator, 'submit', hold)
    first = create(client)
    source = runtime.workflow_store.get_run(first['runId']).model_dump(mode='json')
    monkeypatch.setattr(runtime.mission_semantic_service, 'authorize', lambda principal, mission, action: action == 'read')
    url = '/agentos/v2/runs/' + first['runId']
    observed = client.get(url)
    assert observed.status_code == 200
    cap = observed.json()['actionCapabilities']
    assert cap['canInspect'] is True and cap['canDiscuss'] is True
    assert not any(value for key, value in cap.items() if key.startswith('can') and key not in {'canInspect', 'canDiscuss'})
    assert client.post(url + '/cancel', json={'expectedRuntimeRevision': cap['runtimeRevision']}).status_code == 403
    assert runtime.workflow_store.get_run(first['runId']).model_dump(mode='json') == source

"""Independent capability tests with real C2 authorities, databases and Review."""
from test_agentos_c2_http import (server, create, accepted, materialize, base, PREFIX, facts, activation_body)
from test_agentos_c2_dispatch_http import database, wait_run
from test_agentos_c2_final_delivery import final_delivery_setup
from test_agentos_c2_human_review import create_review_run, dispatch_review_run
from test_agentos_c2_permit_http import handoff, issue, trusted_call, ready_resource
from test_agentos_c2_dispatch_http import endpoint


def test_formal_offers_follow_existing_sources_and_semantic_revision_revokes_old_offer(tmp_path):
    database(tmp_path)
    with server(tmp_path, dispatch=True, setup=final_delivery_setup) as (client, runtime, _):
        created, _ = create(client)
        control = accepted(client, created)
        url = PREFIX + '/runs/' + created['runId']
        before = facts(runtime)
        cap = client.get(url).json()['actionCapabilities']
        assert cap['canCancel'] is True
        assert cap['canExecuteFormalAction'] is True
        assert cap['formalActions'] == ['materialize']
        assert cap['canReview'] is False
        assert facts(runtime) == before  # Reading offers cannot create control facts.
        changed = client.post(f"{PREFIX}/missions/{created['missionId']}/semantics", json={
            'operationId': 'change-authority-basis', 'expectedMissionRevision': 1,
            'objective': 'Changed requirements', 'constraints': [], 'sourceRefs': []})
        assert changed.status_code == 200, changed.text
        cap = client.get(url).json()['actionCapabilities']
        assert cap['canExecuteFormalAction'] is False
        assert cap['canCancel'] is True  # Stop is independent from permission to execute an old plan.
        assert client.post(base(created) + '/materializations', json={'operationId': 'old-offer',
            'commitId': control['commitId'], 'expectedCommitmentRevision': control['commitmentRevision']}).status_code == 409


def test_review_offer_requires_real_checkpoint_and_current_write_authority(tmp_path):
    database(tmp_path)
    with server(tmp_path, dispatch=True, setup=final_delivery_setup) as (client, runtime, agent):
        created = create_review_run(client)
        dispatch_review_run(client, runtime, created)
        paused = wait_run(client, created)
        assert paused['status'] == 'waiting_review'
        cap = paused['actionCapabilities']
        assert cap['canReview'] is True
        assert cap['canCancel'] is True
        assert cap['canExecuteFormalAction'] is False
        url = PREFIX + '/runs/' + created['runId']
        body = {'stepId': 'A', 'decision': 'approved', 'operationId': 'capability-review',
            'expectedRunUpdatedAt': paused['updatedAt'], 'expectedStepStatus': 'waiting_review'}
        assert client.post(url + '/reviews', json=body, headers={'X-Authenticated-Tenant-Id': 'foreign'}).status_code in {403, 404}
        assert agent.calls == ['A']
        result = client.post(url + '/reviews', json=body)
        assert result.status_code == 200, result.text
        next_barrier = wait_run(client, created)
        assert next_barrier['currentStepId'] != 'A'
        assert client.post(url + '/reviews', json={**body, 'operationId': 'stale-other-operation'}).status_code == 409


def test_each_formal_stage_has_its_own_offer_and_queries_create_no_authority_facts(tmp_path):
    database(tmp_path)
    with server(tmp_path, dispatch=True, setup=final_delivery_setup) as (client, runtime, agent):
        created, _ = create(client)
        control = accepted(client, created)
        url = PREFIX + '/runs/' + created['runId']
        def offered(action):
            before = facts(runtime)
            run = client.get(url).json()
            assert run['actionCapabilities']['formalActions'] == [action], run['actionCapabilities']
            assert run['actionCapabilities']['canExecuteFormalAction'] is True
            assert facts(runtime) == before
            assert 'actionCapabilities' not in runtime.workflow_store.get_run(created['runId']).execution_state
            return run
        offered('materialize')
        mat, _ = materialize(client, created, control)
        offered('activate')
        activation = client.post(base(created) + '/activation', json=activation_body(mat))
        assert activation.status_code == 200, activation.text
        offered('handoff')
        prepared, _ = handoff(client, created, mat, activation.json())
        offered('permit')
        permit, _ = issue(client, created, mat, prepared)
        trusted_call(client, ready_resource, runtime, created['runId'])
        run = offered('dispatch')
        response = client.post(endpoint(created), json={'operationId': 'stale-ui-offer',
            'expectedPermitId': permit['permitId'], 'expectedGraphId': mat['graphId'],
            'expectedGraphVersion': mat['graphVersion'], 'expectedRuntimeRevision': run['runtimeRevision'] + 1})
        assert response.status_code == 409
        assert not agent.calls

"""Memory and real SQLite status/ownership contracts for UI capability facts."""
from types import SimpleNamespace
import asyncio
import pytest
from app.execution.run_capabilities import project_run_capabilities
from app.security.internal_auth import TrustedUserContext, _trusted_user_context
from contracts.workflow import RuntimeMissionRecord, RuntimeRunRecord, WorkflowStatus, WorkflowStep, StepStatus
from support.stores.memory_workflow_store import MemoryWorkflowStore
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore


@pytest.fixture(params=['memory', 'sqlite'])
def authority(request, tmp_path):
    store = MemoryWorkflowStore() if request.param == 'memory' else SQLiteWorkflowStore(tmp_path / 'authority.db')
    owner = {'authenticatedUserId': 'owner', 'authenticatedTenantId': 'tenant'}
    mission = RuntimeMissionRecord(title='Authority', input=owner)
    store.save_mission(mission)
    run = RuntimeRunRecord(missionId=mission.mission_id, workflowId='w', domain='general', runtimeEngine='acg', input=owner)
    store.save_run(run)
    token = _trusted_user_context.set(TrustedUserContext('owner', 'owner', 'user', 'tenant'))
    try:
        yield SimpleNamespace(workflow_store=store), store.get_run(run.run_id)
    finally:
        _trusted_user_context.reset(token)


@pytest.mark.parametrize('status', list(WorkflowStatus))
def test_each_status_has_independent_offers_and_no_fabricated_current(authority, status):
    runtime, run = authority
    run.status = status
    if status == WorkflowStatus.WAITING_REVIEW:
        run.steps = [WorkflowStep(stepId='s', name='S', agentName='a', status=StepStatus.WAITING_REVIEW)]
        run.current_step_id = 's'
        run.execution_state.update(checkpointId='missing-checkpoint',
            reviewPayload={'subjectType': 'step', 'subjectId': 's', 'stepId': 's'})
    runtime.workflow_store.save_run(run)
    run = runtime.workflow_store.get_run(run.run_id)
    before = run.model_dump(mode='json')
    caps = project_run_capabilities(runtime, run)
    assert caps['canInspect'] and caps['canDiscuss']
    assert caps['canCancel'] == (status.value in {'pending', 'planning', 'running', 'retrying', 'waiting_review'})
    assert caps['canRerunSuccessor'] == (status.value in {'completed', 'failed', 'cancelled'})
    assert caps['canDelete'] == (status.value in {'completed', 'failed', 'cancelled', 'superseded'})
    assert not caps['canReview']  # no authoritative checkpoint
    assert not caps['canExecuteFormalAction']  # no C2 authority
    assert not caps['canRetrySuccessor']  # no persisted compiled recovery evidence
    assert 'currentRunId' not in caps
    assert runtime.workflow_store.get_run(run.run_id).model_dump(mode='json') == before


@pytest.mark.parametrize('owner,tenant', [('foreign', 'tenant'), ('owner', 'foreign'), ('', 'tenant')])
def test_scope_incomplete_or_mismatched_is_closed(authority, owner, tenant):
    runtime, run = authority
    run.input.update(authenticatedUserId=owner, authenticatedTenantId=tenant)
    runtime.workflow_store.save_run(run)
    caps = project_run_capabilities(runtime, runtime.workflow_store.get_run(run.run_id))
    assert not any(value for key, value in caps.items() if key.startswith('can'))


def test_stale_snapshot_and_missing_trusted_actor_do_not_offer_mutations(authority):
    runtime, run = authority
    next_run = run.model_copy(deep=True)
    next_run.status = WorkflowStatus.CANCELLED
    runtime.workflow_store.save_run(next_run)
    caps = project_run_capabilities(runtime, run)
    assert not caps['canCancel']
    assert {'action': 'canCancel', 'code': 'SNAPSHOT_CHANGED'} in caps['unavailableReasons']
    token = _trusted_user_context.set(None)
    try:
        caps = project_run_capabilities(runtime, runtime.workflow_store.get_run(run.run_id))
        assert not caps['canInspect'] and not caps['canCancel']
    finally:
        _trusted_user_context.reset(token)


def test_late_active_snapshot_cannot_resurrect_a_terminal_store_record(authority):
    runtime, old = authority
    terminal = old.model_copy(deep=True)
    terminal.status = WorkflowStatus.CANCELLED
    runtime.workflow_store.save_run(terminal)
    old.status = WorkflowStatus.RUNNING
    runtime.workflow_store.save_run(old)
    persisted = runtime.workflow_store.get_run(old.run_id)
    assert persisted.status == WorkflowStatus.CANCELLED
    assert project_run_capabilities(runtime, persisted)['canCancel'] is False


def test_unknown_state_is_not_an_actionable_pending_state(authority):
    runtime, run = authority
    invalid = run.model_copy(update={'status': SimpleNamespace(value='unknown_future_status')})
    caps = project_run_capabilities(runtime, invalid)
    assert caps['status'] == 'unknown_future_status'
    assert not caps['isExecutionActive']
    assert not any(value for key, value in caps.items() if key.startswith('can') and key not in {'canInspect', 'canDiscuss'})


def test_real_failed_node_offer_reuses_existing_recovery_validator_without_mutating_source(tmp_path):
    from test_single_step_retry import _RetryAgent, _retry_runtime
    from contracts.planning import TaskPlan, PlannedTask, TaskPlanRelation, TaskImplementationBinding
    runtime, blueprint = _retry_runtime(tmp_path, _RetryAgent())
    owner = {'authenticatedUserId': 'owner', 'authenticatedTenantId': 'tenant'}
    mission = runtime.create_mission('Capability recovery', workflow_id='single-step-retry', input=owner)
    plan = TaskPlan(missionId=mission.mission_id, nodes=tuple(PlannedTask(
        key=f'step:{node.node_id}', title=node.name or node.node_id, objective=node.goal or node.node_id,
        capabilityRequirements=(node.capability,) if node.capability else (), logicalRole=node.logical_role,
    ) for node in blueprint.step_nodes()), relations=(TaskPlanRelation(
        sourceKey='step:source', targetKey='step:final', relationType='depends_on'),))
    mission.input.update(acgBlueprint=blueprint.model_dump(by_alias=True, mode='json'),
        taskPlan=plan.model_dump(by_alias=True, mode='json'), taskBindings=[TaskImplementationBinding(
            planNodeKey=f'step:{node.node_id}', acgNodeId=node.node_id).model_dump(by_alias=True, mode='json')
            for node in blueprint.step_nodes()])
    runtime.workflow_store.save_mission(mission)
    _, source = runtime.prepare_run(mission.mission_id)
    token = _trusted_user_context.set(TrustedUserContext('owner', 'owner', 'user', 'tenant'))
    try:
        with pytest.raises(RuntimeError, match='ACG superstep failed'):
            asyncio.run(runtime.execute_prepared_run(source.run_id))
        failed = runtime.workflow_store.get_run(source.run_id)
        before = failed.model_dump(mode='json')
        cap = project_run_capabilities(runtime, failed)
        assert cap['canRetrySuccessor'] is True and cap['retryStepId'] == 'final'
        assert runtime.workflow_store.list_runs(owner_user_id='owner', owner_tenant_id='tenant').total == 1
        assert runtime.workflow_store.get_run(source.run_id).model_dump(mode='json') == before
        with pytest.raises(ValueError, match='changed'):
            runtime.prepare_single_step_retry(source.run_id, 'final', expected_runtime_revision=failed.runtime_revision + 1)
        children = [runtime.prepare_single_step_retry(source.run_id, 'final', expected_runtime_revision=failed.runtime_revision,
            idempotency_key=key, idempotency_fingerprint=key) for key in ['left', 'right', 'left']]
        assert children[0].run_id != children[1].run_id
        assert children[0].run_id == children[2].run_id
        assert project_run_capabilities(runtime, children[0])['canCancel'] is True
        assert runtime.workflow_store.get_run(source.run_id).model_dump(mode='json') == before
    finally:
        _trusted_user_context.reset(token)
        runtime.content_manifest_store.close()

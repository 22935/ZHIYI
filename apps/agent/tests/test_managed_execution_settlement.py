"""Cancellation must settle real Coordinator -> ACG owned execution tasks."""
import asyncio
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest

from test_mission_semantic_commands import api, create
from components.resource.scheduler.binder import LeaseKeepAlive


@pytest.fixture(autouse=True)
def no_abandoned_execution_tasks_or_unhandled_exceptions(api):
    client, _, _, _ = api
    errors = []
    async def install():
        loop = asyncio.get_running_loop()
        previous = loop.get_exception_handler()
        def handler(loop, context):
            errors.append(context)
            (previous or (lambda loop, context: loop.default_exception_handler(context)))(loop, context)
        loop.set_exception_handler(handler)
        return previous
    previous = client.portal.call(install)
    try:
        yield
        async def inspect():
            return [task.get_name() for task in asyncio.all_tasks() if not task.done() and
                    task.get_name().startswith(('acg:', 'acg-runner:', 'acg-renewal:', 'acg-cleanup:',
                                               'acg-stream-close:', 'acg-stream-error-close:', 'lease-renewal:',
                                               'hands-', 'owned-blocking-call'))]
        assert client.portal.call(inspect) == []
        assert errors == []
    finally:
        async def restore():
            asyncio.get_running_loop().set_exception_handler(previous)
        client.portal.call(restore)


def step_events(runtime, run_id):
    with sqlite3.connect(runtime.workflow_store.db_path) as conn:
        return [(kind, json.loads(payload)) for kind, payload in conn.execute(
            "SELECT event_type, payload FROM lifecycle_outbox WHERE event_type LIKE 'step.%'")
            if json.loads(payload).get('runId') == run_id]


def test_api_cancel_settles_acg_children_before_releasing_lease(api, monkeypatch, tmp_path):
    client, runtime, coordinator, agent = api
    started, cancelled, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    owned, releases = {}, []
    original_wait = LeaseKeepAlive.wait_failed
    original_release = runtime.resource_binder.release

    async def blocked(context):
        owned['runner'] = asyncio.current_task()
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await finish.wait()
            raise

    async def wait_failed(self):
        owned['waiter'] = asyncio.current_task()
        owned['keep_alive'] = self
        return await original_wait(self)

    def release(lease_id):
        releases.append({'leaseId': lease_id, 'runnerDone': owned['runner'].done()})
        return original_release(lease_id)

    monkeypatch.setattr(agent, 'run', blocked)
    monkeypatch.setattr(LeaseKeepAlive, 'wait_failed', wait_failed)
    monkeypatch.setattr(runtime.resource_binder, 'release', release)
    run_id = create(client)['runId']

    async def wait_started():
        await asyncio.wait_for(started.wait(), 10)
        owned['parent'] = coordinator._tasks[run_id]

    async def drain():
        finish.set()
        for key in ('runner', 'waiter'):
            task = owned.get(key)
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(value for value in owned.values() if isinstance(value, asyncio.Task)), return_exceptions=True)

    client.portal.call(wait_started)
    try:
        response = client.post(f'/agentos/v2/runs/{run_id}/cancel')
        assert response.status_code == 200, response.text

        async def observe():
            # Parent completion OR a real runner cancellation signal determines
            # the observation point; no timing sleep substitutes for settlement.
            signal = asyncio.create_task(cancelled.wait())
            await asyncio.wait_for(asyncio.wait({owned['parent'], signal}, return_when=asyncio.FIRST_COMPLETED), 10)
            signal.cancel()
            await asyncio.gather(signal, return_exceptions=True)
            return {key: owned[key].done() for key in ('parent', 'runner', 'waiter')}

        tasks = client.portal.call(observe)
        evidence = {'tasks': tasks, 'runnerReceivedCancel': cancelled.is_set(), 'releases': list(releases),
            'run': runtime.workflow_store.get_run(run_id).model_dump(mode='json')}
        directory = Path(os.environ.get('PR_UI_042_EVIDENCE', str(tmp_path)))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'managed-cancel.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        assert cancelled.is_set(), evidence
        assert not tasks['parent'], evidence
        assert not releases, evidence
        client.portal.call(finish.set)

        async def settled():
            await asyncio.wait_for(asyncio.shield(owned['parent']), 10)
        client.portal.call(settled)
        assert all(owned[key].done() for key in ('parent', 'runner', 'waiter'))
        assert owned['keep_alive']._task.done()
        assert len(releases) == 1 and releases[0]['runnerDone']
        assert not coordinator.is_active(run_id)
        assert runtime.workflow_store.get_run(run_id).status.value == 'cancelled'
        events = step_events(runtime, run_id)
        assert [kind for kind, _ in events].count('step.cancelled') == 1
        assert next(payload for kind, payload in events if kind == 'step.cancelled')['reason'] == 'operator_cancel'
        assert not any(kind == 'step.succeeded' for kind, _ in events)
        with sqlite3.connect(runtime.workflow_store.db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM lifecycle_outbox WHERE event_type='run.finished' AND aggregate_id=?",
                                (run_id,)).fetchone()[0] == 1
    finally:
        client.portal.call(drain)


@contextmanager
def managed_branches(api, monkeypatch, *, suppress=False, cleanup_error=False):
    from test_branch_safe_mission_lifecycle import completed_source, pending_branches
    client, runtime, coordinator, agent = api
    source = completed_source(client, runtime, coordinator)
    original = agent.run
    owned, releases = {}, []
    release = runtime.resource_binder.release
    async def blocked(context):
        key = context.run.run_id
        entry = owned.setdefault(key, {'started': asyncio.Event(), 'cancelled': asyncio.Event(), 'finish': asyncio.Event()})
        entry['runner'] = asyncio.current_task()
        entry['started'].set()
        try:
            await entry['finish'].wait()
        except asyncio.CancelledError as exc:
            entry['reason'] = str(exc)
            entry['cancelled'].set()
            await entry['finish'].wait()
            if cleanup_error:
                raise RuntimeError('injected runner cancellation cleanup failure')
            if not suppress:
                raise
        return await original(context)
    def tracked_release(lease_id):
        key = next(key for key in owned if key in lease_id)
        releases.append((key, owned[key]['runner'].done()))
        return release(lease_id)
    monkeypatch.setattr(agent, 'run', blocked)
    monkeypatch.setattr(runtime.resource_binder, 'release', tracked_release)
    branches = pending_branches(client, source)
    async def wait_started():
        # Entries are created inside the real Agent invocation. No runtime
        # execute method is called directly by this integration fixture.
        for key in branches:
            owned.setdefault(key, {'started': asyncio.Event(), 'cancelled': asyncio.Event(), 'finish': asyncio.Event()})
        await asyncio.wait_for(asyncio.gather(*(owned[key]['started'].wait() for key in branches)), 15)
        for key in branches:
            owned[key]['parent'] = coordinator._tasks[key]
    client.portal.call(wait_started)
    try:
        yield source, branches, owned, releases
    finally:
        async def drain():
            for entry in owned.values():
                entry['finish'].set()
            await asyncio.wait_for(asyncio.gather(*(entry['parent'] for entry in owned.values()), return_exceptions=True), 15)
        client.portal.call(drain)


def wait_event(client, event):
    async def wait():
        await asyncio.wait_for(event.wait(), 10)
    client.portal.call(wait)


def settle(client, entry):
    async def wait():
        entry['finish'].set()
        await asyncio.wait_for(asyncio.gather(entry['parent'], return_exceptions=True), 15)
    client.portal.call(wait)


@pytest.mark.parametrize('suppress', [False, True])
def test_two_managed_branches_cancel_and_late_success_are_isolated(api, monkeypatch, suppress):
    client, runtime, coordinator, _ = api
    with managed_branches(api, monkeypatch, suppress=suppress) as (source, branches, owned, releases):
        a, b = branches
        source_before = runtime.workflow_store.get_run(source.run_id).model_dump(mode='json')
        b_before = runtime.workflow_store.get_run(b).model_dump(mode='json')
        assert client.post(f'/agentos/v2/runs/{a}/cancel').status_code == 200
        wait_event(client, owned[a]['cancelled'])
        assert coordinator.is_active(a) and coordinator.is_active(b)
        assert not releases
        assert runtime.workflow_store.get_run(b).model_dump(mode='json') == b_before
        assert client.post(f'/agentos/v2/runs/{a}/cancel').status_code == 409
        settle(client, owned[a])
        assert runtime.workflow_store.get_run(a).status.value == 'cancelled'
        assert coordinator.is_active(b)
        assert releases == [(a, True)]
        assert not any(kind == 'step.succeeded' for kind, _ in step_events(runtime, a))
        settle(client, owned[b])
        assert runtime.workflow_store.get_run(b).status.value == 'completed'
        assert runtime.workflow_store.get_run(source.run_id).model_dump(mode='json') == source_before
        assert releases == [(a, True), (b, True)]
        assert not coordinator._tasks


def test_repeated_cancel_and_shutdown_cannot_interrupt_runner_cleanup(api, monkeypatch):
    client, runtime, coordinator, _ = api
    with managed_branches(api, monkeypatch) as (_, branches, owned, releases):
        a, b = branches
        assert client.post(f'/agentos/v2/runs/{a}/cancel').status_code == 200
        wait_event(client, owned[a]['cancelled'])
        async def shutdown():
            await coordinator.shutdown()
        shutdown_future = client.portal.start_task_soon(shutdown)
        wait_event(client, owned[b]['cancelled'])
        assert owned[a]['reason'] == 'operator_cancel'
        assert owned[b]['reason'] == 'worker_shutdown'
        assert not shutdown_future.done() and not releases
        # A second external cancellation of the parent must not abandon children.
        client.portal.call(owned[a]['parent'].cancel, 'repeated_cancel')
        settle(client, owned[a])
        settle(client, owned[b])
        shutdown_future.result(timeout=15)
        assert len(releases) == 2 and all(done for _, done in releases)
        assert not coordinator._tasks
        assert runtime.workflow_store.get_run(a).status.value == 'cancelled'
        assert runtime.workflow_store.get_run(b).status.value == 'failed'
        assert next(payload for kind, payload in step_events(runtime, b) if kind == 'step.cancelled')['reason'] == 'worker_shutdown'


@pytest.mark.parametrize('fault', ['terminal_commit', 'cancel_outbox', 'release', 'runner_cleanup', 'renewal_stop'])
def test_managed_cancel_failure_injection_keeps_ownership_and_durable_truth(api, monkeypatch, fault, caplog):
    client, runtime, coordinator, _ = api
    with managed_branches(api, monkeypatch, cleanup_error=fault == 'runner_cleanup') as (_, branches, owned, releases):
        a, b = branches
        before = runtime.workflow_store.get_run(a).model_dump(mode='json')
        if fault == 'terminal_commit':
            save = runtime.workflow_store.save_run
            def fail(run, **kwargs):
                if run.run_id == a and run.status.value == 'cancelled':
                    raise ValueError('injected terminal transaction failure')
                return save(run, **kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(runtime.workflow_store, 'save_run', fail)
                assert client.post(f'/agentos/v2/runs/{a}/cancel').status_code == 409
            assert runtime.workflow_store.get_run(a).model_dump(mode='json') == before
            assert not runtime._run_cancellation_requested(a)
            assert not owned[a]['cancelled'].is_set()
            assert coordinator.is_active(a) and not releases
        else:
            if fault == 'cancel_outbox':
                save = runtime.workflow_store.save_run_with_events
                def fail(run, events, **kwargs):
                    if run.run_id == a and any(event['eventType'] == 'step.cancelled' for event in events):
                        raise ValueError('injected cancellation outbox failure')
                    return save(run, events, **kwargs)
                monkeypatch.setattr(runtime.workflow_store, 'save_run_with_events', fail)
            if fault == 'release':
                release = runtime.resource_binder.release
                def fail(lease_id):
                    if a in lease_id:
                        raise RuntimeError('injected resource release failure')
                    return release(lease_id)
                monkeypatch.setattr(runtime.resource_binder, 'release', fail)
            if fault == 'renewal_stop':
                stop = LeaseKeepAlive.stop
                async def fail(self):
                    await stop(self)
                    if self.lease.run_id == a:
                        raise RuntimeError('injected keepalive stop failure')
                monkeypatch.setattr(LeaseKeepAlive, 'stop', fail)
            assert client.post(f'/agentos/v2/runs/{a}/cancel').status_code == 200
            wait_event(client, owned[a]['cancelled'])
            assert not releases
            settle(client, owned[a])
            record = runtime.workflow_store.get_run(a)
            assert record.status.value == 'cancelled'
            assert sum(event.event_type.value == 'run_cancelled' for event in record.trace) == 1
            assert not coordinator.is_active(a)
            settlement = next(iter(record.execution_state['taskSettlement'].values()))
            assert settlement['leaseState'] == ('release_failed' if fault == 'release' else 'released')
            assert 'injected' in caplog.text
        assert coordinator.is_active(b)


def test_concurrent_api_cancels_commit_one_terminal_trace_and_one_release(api, monkeypatch):
    client, runtime, coordinator, _ = api
    with managed_branches(api, monkeypatch) as (_, branches, owned, releases):
        a, b = branches
        revision = runtime.workflow_store.get_run(a).runtime_revision
        def cancel(_):
            return client.post(f'/agentos/v2/runs/{a}/cancel', json={'expectedRuntimeRevision': revision}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(cancel, range(2))) == [200, 409]
        wait_event(client, owned[a]['cancelled'])
        settle(client, owned[a])
        record = runtime.workflow_store.get_run(a)
        assert record.status.value == 'cancelled'
        assert sum(event.event_type.value == 'run_cancelled' for event in record.trace) == 1
        assert releases == [(a, True)]
        assert coordinator.is_active(b)


def test_api_cancel_before_actual_runtime_entry_does_not_start_agent(api, monkeypatch):
    client, runtime, coordinator, agent = api
    entered, blocked = asyncio.Event(), asyncio.Event()
    async def pause(run_id):
        entered.set()
        await blocked.wait()
        pytest.fail('cancelled prepared run was executed')
    monkeypatch.setattr(runtime, 'execute_prepared_run', pause)
    run_id = create(client)['runId']
    wait_event(client, entered)
    parent = coordinator._tasks[run_id]
    assert client.post(f'/agentos/v2/runs/{run_id}/cancel').status_code == 200
    async def wait():
        await asyncio.wait_for(asyncio.gather(parent, return_exceptions=True), 5)
    client.portal.call(wait)
    assert not agent.calls and not coordinator._tasks
    assert runtime.workflow_store.get_run(run_id).status.value == 'cancelled'
    assert not step_events(runtime, run_id)


@pytest.mark.parametrize('operator_cancel', [False, True])
def test_lease_renewal_failure_settles_runner_before_release_even_during_cancel(api, monkeypatch, operator_cancel):
    from components.resource.scheduler.leases import LeaseRenewalFailedError
    renewers = {}
    wait_failed = LeaseKeepAlive.wait_failed
    async def capture(self):
        renewers[self.lease.run_id] = self
        return await wait_failed(self)
    monkeypatch.setattr(LeaseKeepAlive, 'wait_failed', capture)
    client, runtime, coordinator, _ = api
    with managed_branches(api, monkeypatch) as (_, branches, owned, releases):
        # Existing renewers are already running. Drive one real failure waiter
        # through its owning LeaseKeepAlive without elapsed-time assumptions.
        a, b = branches
        async def fail_waiter():
            keepalive = renewers[a]
            keepalive.failure = LeaseRenewalFailedError('injected lease renewal failure')
            keepalive._failed.set()
        client.portal.call(fail_waiter)
        wait_event(client, owned[a]['cancelled'])
        assert owned[a]['reason'] == 'lease_renewal_failure'
        assert not releases and coordinator.is_active(a)
        if operator_cancel:
            assert client.post(f'/agentos/v2/runs/{a}/cancel').status_code == 200
        settle(client, owned[a])
        record = runtime.workflow_store.get_run(a)
        assert record.status.value == ('cancelled' if operator_cancel else 'waiting_review')
        assert releases == [(a, True)]
        assert coordinator.is_active(b)


def test_cancel_preserves_completed_prefix_and_never_starts_next_node(api, monkeypatch):
    from contracts.workflow import WorkflowDefinition, WorkflowStepDefinition
    from contracts.planning import PlannedTask, TaskPlanRelation
    from test_mission_semantic_commands import BODY
    client, runtime, coordinator, agent = api
    runtime.workflow_registry.register(WorkflowDefinition(workflowId='semantic-test', name='progress', domain='general',
        runtimeEngine='acg', planningNodes=[PlannedTask(key=f'step:{key}', title=key, objective=f'do {key}') for key in 'ABC'],
        planningRelations=[TaskPlanRelation(sourceKey=f'step:{a}', targetKey=f'step:{b}', relationType='depends_on')
                           for a, b in [('A', 'B'), ('B', 'C')]],
        steps=[WorkflowStepDefinition(stepId=key, name=key, agentName='runner', nextStepId=next_key)
               for key, next_key in [('A', 'B'), ('B', 'C'), ('C', None)]]))
    started, received = asyncio.Event(), asyncio.Event()
    calls = []
    original = agent.run
    async def execute(context):
        key = context.step.step_id
        calls.append(key)
        if key == 'B':
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                received.set()
                raise
        return await original(context)
    monkeypatch.setattr(agent, 'run', execute)
    run_id = create(client, BODY)['runId']
    try:
        wait_event(client, started)
    except TimeoutError:
        pytest.fail('Expected node B to start: ' + runtime.workflow_store.get_run(run_id).model_dump_json(by_alias=True))
    before = runtime.workflow_store.get_run(run_id)
    assert before.completed_step_ids == ['A']
    completed_step = before.get_step('A').model_dump(mode='json')
    parent = coordinator._tasks[run_id]
    assert client.post(f'/agentos/v2/runs/{run_id}/cancel').status_code == 200
    async def settle_parent():
        await asyncio.wait_for(asyncio.gather(parent, return_exceptions=True), 10)
    client.portal.call(settle_parent)
    after = runtime.workflow_store.get_run(run_id)
    assert received.is_set() and calls == ['A', 'B']
    assert after.status.value == 'cancelled'
    assert after.completed_step_ids == ['A']
    assert after.get_step('A').model_dump(mode='json') == completed_step
    assert after.get_step('B').status.value != 'completed'
    assert set(event.event_id for event in before.trace) <= set(event.event_id for event in after.trace)
    assert after.execution_state['outputRefs']['A'] == before.execution_state['outputRefs']['A']


def test_natural_completion_racing_api_cancel_has_one_explainable_terminal(api, monkeypatch):
    client, runtime, coordinator, _ = api
    with managed_branches(api, monkeypatch) as (_, branches, owned, releases):
        a, _ = branches
        with ThreadPoolExecutor(max_workers=2) as pool:
            release = pool.submit(client.portal.call, owned[a]['finish'].set)
            cancel = pool.submit(client.post, f'/agentos/v2/runs/{a}/cancel')
            release.result(timeout=10)
            response = cancel.result(timeout=15)
        settle(client, owned[a])
        record = runtime.workflow_store.get_run(a)
        assert response.status_code in (200, 409)
        assert record.status.value == ('cancelled' if response.status_code == 200 else 'completed')
        assert sum(event.event_type.value == 'run_cancelled' for event in record.trace) == (response.status_code == 200)
        assert releases == [(a, True)]


def test_cancel_during_deferred_planning_keeps_thread_and_signal_owned_until_it_stops(api, monkeypatch):
    from threading import Event
    client, runtime, coordinator, agent = api
    started, finish, ended = asyncio.Event(), Event(), Event()
    observed = []
    submit = coordinator.submit
    async def defer(run_id):
        run = runtime.workflow_store.get_run(run_id)
        run.execution_state['planningDeferred'] = True
        runtime.workflow_store.save_run(run)
        return await submit(run_id)
    loop = client.portal.call(asyncio.get_running_loop)
    def planning(run_id):
        loop.call_soon_threadsafe(started.set)
        assert finish.wait(10)
        observed.append(runtime._run_cancellation_requested(run_id))
        ended.set()
        return runtime.workflow_store.get_run(run_id)
    monkeypatch.setattr(coordinator, 'submit', defer)
    monkeypatch.setattr(runtime, '_materialize_deferred_acg_run', planning)
    run_id = create(client)['runId']
    try:
        wait_event(client, started)
        parent = coordinator._tasks[run_id]
        assert client.post(f'/agentos/v2/runs/{run_id}/cancel').status_code == 200
        assert not ended.is_set() and not parent.done()
        assert runtime._run_cancellation_requested(run_id)
        finish.set()
        async def settled():
            await asyncio.wait_for(asyncio.gather(parent, return_exceptions=True), 10)
        client.portal.call(settled)
        assert ended.is_set() and observed == [True]
        assert not agent.calls
        assert runtime.workflow_store.get_run(run_id).status.value == 'cancelled'
        assert not coordinator.is_active(run_id)
    finally:
        finish.set()

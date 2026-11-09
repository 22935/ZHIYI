"""External work must really settle before its owning coroutine can finish."""
import asyncio
from threading import Event
from types import SimpleNamespace

import httpx
import pytest

from support.async_tasks import cancel_and_wait


@pytest.mark.asyncio
async def test_repeated_parent_cancellation_waits_for_child_cleanup():
    started, cancelling, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def child():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelling.set()
            await finish.wait()
            raise
    task = asyncio.create_task(child())
    await started.wait()
    parent = asyncio.create_task(cancel_and_wait([task], reason='operator_cancel'))
    await cancelling.wait()
    parent.cancel()
    parent.cancel()
    assert not parent.done() and not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await parent
    assert task.done()


@pytest.mark.asyncio
async def test_gateway_cancellation_waits_for_actual_pool_thread(monkeypatch):
    from app.execution.model_runtime import GatewayStructuredGenerationRuntime
    loop = asyncio.get_running_loop()
    started, finish, ended = asyncio.Event(), Event(), Event()
    def generate(*args, **kwargs):
        loop.call_soon_threadsafe(started.set)
        try:
            assert finish.wait(10)
            return {'data': {'answer': 'late'}, 'provider': 'test', 'model': 'test'}
        finally:
            ended.set()
    gateway = SimpleNamespace(provider_name='test', model='test', generate_json=generate)
    monkeypatch.setattr('app.execution.model_runtime.get_llm_gateway', lambda: gateway)
    runtime = GatewayStructuredGenerationRuntime()
    task = asyncio.create_task(runtime.generate_json(prompt='test', schema={}))
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel('operator_cancel')
        assert not ended.is_set() and not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert ended.is_set()
    finally:
        finish.set()
        await asyncio.gather(task, return_exceptions=True)
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream_open', [False, True])
async def test_http_thread_cancellation_drains_and_closes_acquired_response(monkeypatch, stream_open):
    from adapters.http_transport import HttpJsonTransport
    loop = asyncio.get_running_loop()
    started, finish, closed, ended = asyncio.Event(), Event(), Event(), Event()
    response = SimpleNamespace(close=closed.set)
    def blocked(**kwargs):
        loop.call_soon_threadsafe(started.set)
        assert finish.wait(10)
        ended.set()
        return response if stream_open else {}
    transport = HttpJsonTransport(base_url='https://example.test')
    monkeypatch.setattr(transport, '_open_stream_sync' if stream_open else '_post_json_sync', blocked)
    stream = transport.stream_json(path='/chat', payload={}) if stream_open else None
    task = asyncio.create_task(anext(stream) if stream_open else transport.post_json(path='/chat', payload={}))
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        assert not task.done() and not ended.is_set()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert ended.is_set()
        assert closed.is_set() is stream_open
    finally:
        finish.set()
        await asyncio.gather(task, return_exceptions=True)
        if stream is not None:
            await stream.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 202, 503])
async def test_remote_cancel_waits_for_response_or_reports_unknown(status):
    from adapters.resource_execution import HttpResourceExecutionAdapter, ResourceExecutionError
    context = SimpleNamespace(task=SimpleNamespace(mission_id='mission'), run=SimpleNamespace(run_id='run'),
        step=SimpleNamespace(step_id='A', agent_name='agent', capability=None, goal='test'),
        context_pack=SimpleNamespace(data={}, evidence_refs=[], attempt_id='attempt'), commit_id='commit')
    credentials = SimpleNamespace(current_signing_credential=lambda _: ('credential', 'secret'))
    started, finish = asyncio.Event(), asyncio.Event()
    async def handler(request):
        started.set()
        await finish.wait()
        return httpx.Response(status, json={'output': {}, 'summary': 'done'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = HttpResourceExecutionAdapter(resource_id='edge', address='http://edge', credential_provider=credentials, client=client)
        task = asyncio.create_task(adapter.run(context))
        await started.wait()
        task.cancel('operator_cancel')
        assert not task.done()
        finish.set()
        if status != 200:
            with pytest.raises(ResourceExecutionError) as error:
                await task
            assert error.value.outcome_unknown
        else:
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
@pytest.mark.parametrize('repeated', [False, True])
@pytest.mark.parametrize('admission_blocked,unknown', [(False, False), (True, False), (False, True)])
async def test_hands_cancel_ack_is_not_a_terminal_receipt(monkeypatch, admission_blocked, unknown, repeated):
    from adapters.hands_http import HandsHttpTransport, HandsExecutionCancelled, HandsOutcomeUnknown, receipt_checksum
    from contracts.local_runtime import LocalRuntimeExecutionRequest
    request = LocalRuntimeExecutionRequest(protocolVersion='1', requestId='request', invocationId='invocation', resourceId='hands',
        capabilityId='shell.exec', authorization={'workspaceId': 'workspace', 'grantId': 'grant'},
        input={'command': 'managed test'}, idempotencyKey='operation',
        limits={'timeoutSeconds': 5, 'maxStdoutBytes': 100, 'maxStderrBytes': 100})
    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    started, admitted, cancel_ack, finish = (asyncio.Event() for _ in range(4))
    wire, calls = {}, []
    async def call(method, suffix='', payload=None, key=None):
        calls.append((method, suffix))
        if method == 'POST' and not suffix:
            wire.update(payload)
            started.set()
            if admission_blocked:
                await admitted.wait()
            return {'executionId': 'execution', 'state': 'RUNNING'}
        if suffix.endswith('/cancel'):
            cancel_ack.set()
            return {'state': 'CANCELLING'}
        await finish.wait()
        if unknown:
            return {'executionId': 'execution', 'state': 'UNKNOWN'}
        receipt = {key: wire[key] for key in ('requestId', 'invocationId', 'capabilityId', 'idempotencyKey')}
        receipt.update(identity={}, grantId='grant', status='cancelled', output={},
                       startedAt='2026-11-01T00:00:00Z', completedAt='2026-11-01T00:00:01Z')
        receipt['checksum'] = receipt_checksum(receipt)
        return {'executionId': 'execution', 'state': 'CANCELLED', 'receipt': receipt}
    monkeypatch.setattr(transport, '_call', call)
    task = asyncio.create_task(transport.execute_with_identity(request, {}))
    try:
        await started.wait()
        task.cancel('worker_shutdown')
        admitted.set()
        await asyncio.wait_for(cancel_ack.wait(), 5)
        assert not task.done()  # An acknowledged cancel still owns the external work.
        if repeated:
            task.cancel('repeated_cancel')
        finish.set()
        if unknown:
            with pytest.raises(HandsOutcomeUnknown):
                await asyncio.wait_for(task, 5)
        else:
            with pytest.raises(HandsExecutionCancelled) as error:
                await asyncio.wait_for(task, 5)
            assert error.value.result.output['handsReceipt']['status'] == 'cancelled'
            assert str(error.value) == 'worker_shutdown'
        assert calls.count(('POST', '/execution/cancel')) == 1
    finally:
        admitted.set()
        finish.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_closing_graph_stream_settles_siblings_and_preserves_completed_output():
    from components.executor.graph import ACGExecutionGraph, ACGExecutionState
    graph = ACGExecutionGraph(nodes=('fast', 'slow'))
    state = ACGExecutionState(runId='owned-graph')
    entered, cancelled = asyncio.Event(), asyncio.Event()
    children = []
    async def execute(key, state):
        children.append(asyncio.current_task())
        if key == 'slow':
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        await entered.wait()
        return {'outputSummary': 'preserved'}
    stream = graph.astream(state, execute)
    async for event in stream:
        if event['type'] == 'node_completed':
            break
    await stream.aclose()
    assert cancelled.is_set() and all(task.done() for task in children)
    assert state.completed_step_ids == ['fast']
    assert state.active_step_ids == []
    assert state.output_summaries == {'fast': 'preserved'}


@pytest.mark.asyncio
@pytest.mark.parametrize('unknown', [False, True])
async def test_formal_tool_keeps_nested_lease_until_receipt_or_quarantines_unknown(tmp_path, monkeypatch, unknown):
    import app.tools.formal_workspace as module
    from adapters.hands_http import HandsExecutionCancelled, HandsOutcomeUnknown, receipt_checksum
    from components.executor.value_store import SQLiteExecutionValueStore
    from components.resource.scheduler.leases import InMemoryLeaseCoordinator
    from contracts.local_runtime import LocalRuntimeExecutionResult, LocalRuntimeExecutionError, LocalRuntimeAuthorizationRef
    from datetime import datetime, timedelta, timezone
    started, cancelling, finish, external_ended = (asyncio.Event() for _ in range(4))
    leases = InMemoryLeaseCoordinator()
    lease = leases.acquire(lease_id='nested-lease', resource_id='hands', capacity=1, run_id='run',
        step_id='A', attempt_id='attempt', slot_count=1, ttl=timedelta(seconds=90), now=datetime.now(timezone.utc))
    releases, quarantine, events = [], [], []
    values = SQLiteExecutionValueStore(db_path=tmp_path/'formal-values.sqlite3')
    async def allow(**kwargs):
        return None
    async def healthy(transport):
        return True
    async def publish(run_id, event):
        events.append(event)
    monkeypatch.setattr(module, 'runtime_event_broker', SimpleNamespace(publish=publish))
    async def execute(request, identity, event_sink):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as cancellation:
            cancelling.set()
            await finish.wait()
            external_ended.set()
            if unknown:
                raise HandsOutcomeUnknown('injected uncertain external operation')
            receipt = dict(requestId=request.request_id, invocationId=request.invocation_id,
                capabilityId='fs.read', idempotencyKey=request.idempotency_key, identity=identity,
                grantId='grant', status='cancelled', output={}, startedAt='2026-11-01T00:00:00Z',
                completedAt='2026-11-01T00:00:01Z')
            receipt['checksum'] = receipt_checksum(receipt)
            result = LocalRuntimeExecutionResult(requestId=request.request_id, invocationId=request.invocation_id,
                status='failed', output={'executionId':'execution','handsReceipt':receipt},
                error=LocalRuntimeExecutionError(code='HANDS_CANCELLED', retryable=False, message='cancelled'),
                startedAt=receipt['startedAt'], completedAt=receipt['completedAt'])
            raise HandsExecutionCancelled(result, str(cancellation))
    def release(lease_id):
        releases.append((lease_id, external_ended.is_set()))
        return leases.release(lease_id)
    runtime = SimpleNamespace(
        local_runtime_authorization=LocalRuntimeAuthorizationRef(grantId='grant', workspaceId='workspace'),
        local_runtime_health_projector=SimpleNamespace(refresh=healthy),
        local_runtime_transport=SimpleNamespace(execute_with_identity=execute),
        local_runtime_resource=SimpleNamespace(profile=SimpleNamespace(runtime_id='hands')),
        resource_binder=SimpleNamespace(coordinator=leases, release=release,
            bind_ready=lambda **kwargs: SimpleNamespace(binding=SimpleNamespace(resource_id='hands', binding_id='binding'),lease=lease)),
        resource_plane=SimpleNamespace(
            set_runtime_health=lambda resource_id, **kwargs: quarantine.append(('health',resource_id,kwargs)),
            set_runtime_enabled=lambda resource_id, **kwargs: quarantine.append(('enabled',resource_id,kwargs))),
        execution_value_store=values, formal_tool_pending={})
    tools = module.FormalWorkspaceTools.__new__(module.FormalWorkspaceTools)
    tools.runtime, tools.guard = runtime, lambda: None
    tools.context = SimpleNamespace(run=SimpleNamespace(run_id='run'), step=SimpleNamespace(step_id='A'),
                                    attempt_id='attempt', commit_id='commit')
    tools.permissions = SimpleNamespace(authorize=allow)
    task = asyncio.create_task(tools.execute('read_file', {'path':'file.txt'}, operation_key='operation'))
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel('operator_cancel')
        await asyncio.wait_for(cancelling.wait(), 5)
        assert not task.done() and not releases and leases.active_slots('hands') == 1
        finish.set()
        with pytest.raises(HandsOutcomeUnknown if unknown else asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert external_ended.is_set()
        assert values.get_tool_value(run_id='run', key='operation:request') is not None
        if unknown:
            assert releases == [] and leases.active_slots('hands') == 1
            assert ('enabled','hands',{'enabled':False}) in quarantine
            assert values.get_tool_value(run_id='run', key='operation:receipt') is None
            assert values.get_tool_value(run_id='run', key='operation:unsettled')['reason'] == 'external_outcome_unknown'
        else:
            assert releases == [('nested-lease', True)] and leases.active_slots('hands') == 0
            receipt = values.get_tool_value(run_id='run', key='operation:receipt')
            assert receipt['checksum'] == receipt_checksum(receipt)
            assert quarantine == []
        assert sum(event.event_type == 'tool.execution_completed' for event in events) == (not unknown)
        assert not any(item.get_name() == 'lease-renewal:nested-lease' for item in asyncio.all_tasks() if not item.done())
    finally:
        finish.set()
        if not task.done() and not task.cancelling():
            task.cancel('test_cleanup')
        await asyncio.gather(task, return_exceptions=True)
        values.close()

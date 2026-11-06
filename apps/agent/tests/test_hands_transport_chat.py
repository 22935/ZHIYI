"""HandsHttpTransport 的 chat 工具链适配合同。

chat 的文件/命令工具经 LocalRuntimeClient 打到 hands 时，传输层必须完成三件事：
把 hands 事件流翻译成 LocalRuntime 事件契约（含终态 exitCode 富化）、把取消语义
对齐（已终态不算错）、并把 chat 工具输入字段 remap 成 hands 引擎认识的字段。
"""
import asyncio

import pytest


def _hands_transport(monkeypatch, call):
    from adapters.hands_http import HandsHttpTransport
    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    monkeypatch.setattr(transport, '_call', call)
    return transport


def _receipt(wire, status='completed', output=None, error=None):
    from adapters.hands_http import receipt_checksum
    receipt = {key: wire[key] for key in ('requestId', 'invocationId', 'capabilityId', 'idempotencyKey')}
    receipt.update(identity={}, grantId='grant', status=status,
                   startedAt='2026-11-01T00:00:00Z', completedAt='2026-11-01T00:00:01Z',
                   output=output or {})
    if error is not None:
        receipt['error'] = error
    receipt['checksum'] = receipt_checksum(receipt)
    return receipt


def _request(capability, payload):
    from contracts.local_runtime import LocalRuntimeExecutionRequest
    return LocalRuntimeExecutionRequest(
        protocolVersion='1', requestId='request', invocationId='invocation', resourceId='hands',
        capabilityId=capability, authorization={'workspaceId': 'workspace', 'grantId': 'grant'},
        input=payload, idempotencyKey='operation',
        limits={'timeoutSeconds': 5, 'maxStdoutBytes': 100, 'maxStderrBytes': 100})


@pytest.mark.asyncio
async def test_events_translate_hands_wire_to_local_runtime_contract(monkeypatch):
    from contracts.local_runtime import LocalRuntimeExecutionEvent
    calls = []

    async def call(method, suffix='', payload=None, key=None):
        calls.append((method, suffix))
        if suffix == '/execution/events?afterSequence=-1':
            return {'executionId': 'execution', 'events': [
                {'executionId': 'execution', 'seq': 0, 'type': 'execution.accepted', 'timestamp': 't'},
                {'executionId': 'execution', 'seq': 1, 'type': 'execution.started', 'timestamp': 't'},
                {'executionId': 'execution', 'seq': 2, 'type': 'stdout.delta', 'timestamp': 't',
                 'payload': {'text': 'hello'}},
                {'executionId': 'execution', 'seq': 3, 'type': 'stderr.delta', 'timestamp': 't',
                 'payload': {'text': 'oops'}},
                {'executionId': 'execution', 'seq': 4, 'type': 'execution.completed', 'timestamp': 't',
                 'payload': {'checksum': 'abc'}},
            ], 'nextSeq': 5, 'truncated': False, 'state': 'COMPLETED', 'terminal': True}
        if suffix == '/execution':
            return {'executionId': 'execution', 'state': 'COMPLETED',
                    'receipt': {'output': {'exitCode': 0, 'stdout': {'text': 'hello', 'truncated': False}}}}
        raise AssertionError('unexpected call: ' + suffix)

    transport = _hands_transport(monkeypatch, call)
    events, terminal, state = await transport.events(
        execution_id='execution', request_id='request', invocation_id='invocation')

    assert terminal is True and state == 'COMPLETED'
    assert [(event.event_type, event.sequence) for event in events] == [
        ('started', 1), ('stdout_delta', 2), ('stderr_delta', 3), ('completed', 4)]
    by_type = {event.event_type: event for event in events}
    assert by_type['stdout_delta'].data == {'delta': 'hello'}
    assert by_type['stderr_delta'].data == {'delta': 'oops'}
    # 终态事件从收据富化 exitCode，run_command 的 terminal 才有退出码。
    assert by_type['completed'].data['exitCode'] == 0
    for event in events:
        assert isinstance(event, LocalRuntimeExecutionEvent)
        assert event.protocol_version == '1'
        assert event.request_id == 'request'
        assert event.invocation_id == 'invocation'
        assert event.execution_id == 'execution'
    # accepted 没有对应契约类型，跳过；终态富化只查一次执行记录。
    assert calls == [('GET', '/execution/events?afterSequence=-1'), ('GET', '/execution')]


@pytest.mark.asyncio
async def test_events_require_correlation_ids(monkeypatch):
    async def call(method, suffix='', payload=None, key=None):
        raise AssertionError('unexpected call: ' + suffix)

    transport = _hands_transport(monkeypatch, call)
    with pytest.raises(ValueError):
        await transport.events(execution_id='execution')


@pytest.mark.asyncio
async def test_stream_events_via_client_correlation(monkeypatch):
    from adapters.hands_http import HandsHttpTransport
    from adapters.local_runtime import LocalRuntimeClient
    from contracts.local_runtime import LocalRuntimeExecutionEvent

    def _event(seq, event_type, data):
        return LocalRuntimeExecutionEvent(protocolVersion='1', requestId='request', invocationId='invocation',
                                          executionId='execution', eventType=event_type, sequence=seq, data=data)

    rounds = [
        ([_event(2, 'stdout_delta', {'delta': 'hi'})], False, 'RUNNING'),
        ([_event(3, 'completed', {'exitCode': 0})], True, 'COMPLETED'),
    ]

    async def fake_events(**kwargs):
        events, terminal, state = rounds.pop(0)
        assert kwargs['after_sequence'] == (-1 if len(rounds) == 1 else 2)
        return events, terminal, state

    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    monkeypatch.setattr(transport, 'events', fake_events)
    client = LocalRuntimeClient(transport)
    collected = []
    async for event in client.stream_events(
            execution_id='execution', request_id='request', invocation_id='invocation'):
        collected.append(event.event_type)
    assert collected == ['stdout_delta', 'completed']


@pytest.mark.asyncio
@pytest.mark.parametrize('settled', [False, True])
async def test_cancel_returns_state_and_treats_settled_as_state(monkeypatch, settled):
    calls = []

    async def call(method, suffix='', payload=None, key=None):
        calls.append((method, suffix))
        if suffix == '/execution/cancel':
            if settled:
                from adapters.hands_http import HandsAdmissionRejected
                raise HandsAdmissionRejected(409, 'EXECUTION_ALREADY_SETTLED')
            return {'executionId': 'execution', 'cancelRequested': True, 'state': 'CANCELLING'}
        if suffix == '/execution':
            return {'executionId': 'execution', 'state': 'COMPLETED'}
        raise AssertionError('unexpected call: ' + suffix)

    transport = _hands_transport(monkeypatch, call)
    state = await transport.cancel(execution_id='execution', request_id='request', invocation_id='invocation')
    assert state == ('COMPLETED' if settled else 'CANCELLING')
    if settled:
        assert ('GET', '/execution') in calls


@pytest.mark.asyncio
async def test_cancel_reraises_other_conflicts(monkeypatch):
    from adapters.hands_http import HandsAdmissionRejected

    async def call(method, suffix='', payload=None, key=None):
        raise HandsAdmissionRejected(409, 'REPLAY_REJECTED')

    transport = _hands_transport(monkeypatch, call)
    with pytest.raises(HandsAdmissionRejected):
        await transport.cancel(execution_id='execution', request_id='request', invocation_id='invocation')


@pytest.mark.asyncio
@pytest.mark.parametrize('capability,payload,expect_absent,expect_present', [
    ('fs.write', {'path': 'a.txt', 'content': 'x', 'overwrite': False}, ['overwrite'], {'createIfAbsent': True}),
    ('fs.write', {'path': 'a.txt', 'content': 'x', 'overwrite': True}, ['overwrite'], {}),
    ('shell.exec', {'command': 'dir', 'cwd': 'sub'}, ['cwd'], {'workdir': 'sub'}),
])
async def test_execute_remaps_chat_input_fields(monkeypatch, capability, payload, expect_absent, expect_present):
    from adapters.hands_http import HandsHttpTransport
    request = _request(capability, payload)
    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    wire_seen = {}

    async def call(method, suffix='', payload=None, key=None):
        if method == 'POST' and not suffix:
            wire_seen.update(payload)
            record = {'executionId': 'execution', 'state': 'COMPLETED',
                      'receipt': _receipt(wire_seen, output={'path': payload['input'].get('path')})}
            return record
        if suffix == '/execution':
            return {'executionId': 'execution', 'state': 'COMPLETED',
                    'receipt': _receipt(wire_seen, output={'path': wire_seen['input'].get('path')})}
        raise AssertionError('unexpected call: ' + suffix)

    monkeypatch.setattr(transport, '_call', call)
    result = await transport.execute(request)
    assert result.status == 'completed'
    sent = wire_seen['input']
    for absent in expect_absent:
        assert absent not in sent, sent
    for key, value in expect_present.items():
        assert sent.get(key) == value, sent


@pytest.mark.asyncio
async def test_chat_patch_diff_runs_as_read_modify_write(monkeypatch):
    """chat 的 unified diff 在 hands 上按 读->内存应用->写 两张收据执行。"""
    from adapters.hands_http import HandsHttpTransport, HandsAdmissionRejected
    request = _request('fs.patch', {
        'path': 'hello.txt',
        'patch': '@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n',
        'encoding': 'utf-8',
    })
    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    source = 'alpha\nbeta\n'
    written = {}
    steps = []

    async def call(method, suffix='', payload=None, key=None):
        if method == 'POST' and not suffix:
            steps.append((payload['capabilityId'], dict(payload['input']), payload['idempotencyKey']))
            if payload['capabilityId'] == 'fs.read':
                output = {'path': payload['input']['path'], 'text': source}
            else:
                written.update(payload['input'])
                output = {'path': payload['input']['path']}
            return {'executionId': 'execution', 'state': 'COMPLETED',
                    'receipt': _receipt(payload, output=output)}
        if suffix == '/execution':
            if written:
                output = {'path': written['path']}
            else:
                output = {'path': steps[0][1]['path'], 'text': source}
            return {'executionId': 'execution', 'state': 'COMPLETED',
                    'receipt': _receipt({**steps[-1][1], 'capabilityId': steps[-1][0],
                                         'requestId': 'wire', 'invocationId': 'wire', 'idempotencyKey': 'wire'},
                                        output=output)}
        raise AssertionError('unexpected call: ' + suffix)

    monkeypatch.setattr(transport, '_call', call)
    result = await transport.execute(request)
    assert result.status == 'completed'
    assert result.request_id == 'request' and result.invocation_id == 'invocation'
    # 两步执行：读拿旧文、写落新文；idempotency 派生键保证各自独立收据。
    assert [step[0] for step in steps] == ['fs.read', 'fs.write']
    assert steps[0][2] == 'operation:patch-read' and steps[1][2] == 'operation:patch-write'
    assert written == {'path': 'hello.txt', 'content': 'alpha\ngamma\n'}


@pytest.mark.asyncio
async def test_chat_patch_conflict_is_definite_rejection(monkeypatch):
    from adapters.hands_http import HandsHttpTransport, HandsAdmissionRejected
    request = _request('fs.patch', {'path': 'hello.txt', 'patch': '@@ -9,1 +9,1 @@\n-missing\n+nope\n'})
    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    executed = []

    async def call(method, suffix='', payload=None, key=None):
        if method == 'POST' and not suffix:
            executed.append(payload['capabilityId'])
            if payload['capabilityId'] == 'fs.read':
                return {'executionId': 'execution', 'state': 'COMPLETED',
                        'receipt': _receipt(payload, output={'path': 'hello.txt', 'text': 'alpha\nbeta\n'})}
            raise AssertionError('write must not run on conflict')
        if suffix == '/execution':
            return {'executionId': 'execution', 'state': 'COMPLETED',
                    'receipt': _receipt(payload, output={'path': 'hello.txt', 'text': 'alpha\nbeta\n'})}
        raise AssertionError('unexpected call: ' + suffix)

    monkeypatch.setattr(transport, '_call', call)
    with pytest.raises(HandsAdmissionRejected) as error:
        await transport.execute(request)
    assert error.value.code == 'PATCH_CONFLICT'
    assert executed == ['fs.read']


@pytest.mark.asyncio
async def test_shell_exec_returns_accepted_at_admission(monkeypatch):
    """chat run_command 依赖「admission 即返回 + 事件流推进终态」模型。"""
    from adapters.hands_http import HandsHttpTransport
    request = _request('shell.exec', {'command': 'echo hi'})
    transport = HandsHttpTransport.__new__(HandsHttpTransport)
    calls = []

    async def call(method, suffix='', payload=None, key=None):
        calls.append((method, suffix))
        if method == 'POST' and not suffix:
            return {'executionId': 'execution', 'state': 'RECEIVED', 'createdAt': '2026-11-05T00:00:00Z'}
        raise AssertionError('no polling must happen after accepted return: ' + suffix)

    monkeypatch.setattr(transport, '_call', call)
    result = await transport.execute(request)
    assert result.status == 'accepted'
    assert result.request_id == 'request' and result.invocation_id == 'invocation'
    assert result.output == {'executionId': 'execution'}
    assert calls == [('POST', '')]  # 不阻塞轮询，终态交给 stream_events


@pytest.mark.asyncio
async def test_list_entries_are_mapped_to_runtime_shape(monkeypatch):
    from adapters.hands_http import HandsHttpTransport
    request = _request('fs.list', {'path': '.'})
    transport = HandsHttpTransport.__new__(HandsHttpTransport)

    async def call(method, suffix='', payload=None, key=None):
        if method == 'POST' and not suffix:
            output = {'path': '.', 'entries': [
                {'name': 'hello.txt', 'type': 'file',
                 'target': {'targetKey': 'k', 'displayPath': 'hello.txt'}, 'size': 11},
                {'name': 'sub', 'type': 'directory', 'target': {'targetKey': 'k2', 'displayPath': 'sub'}},
            ]}
            return {'executionId': 'execution', 'state': 'COMPLETED', 'receipt': _receipt(payload, output=output)}
        if suffix == '/execution':
            raise AssertionError('unexpected polling')
        raise AssertionError('unexpected call: ' + suffix)

    monkeypatch.setattr(transport, '_call', call)
    result = await transport.execute(request)
    assert result.status == 'completed'
    assert result.output['entries'] == [
        {'path': 'hello.txt', 'name': 'hello.txt', 'type': 'file', 'size': 11},
        {'path': 'sub', 'name': 'sub', 'type': 'directory'},
    ]\n
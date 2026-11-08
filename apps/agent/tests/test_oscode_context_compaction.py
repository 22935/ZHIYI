"""Real Node bridge + SDK/API seams; no replacement Compaction Runtime in Python."""
import asyncio
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from agents import Agent, ModelSettings, Runner
from agents.models.interface import Model, ModelResponse
from agents.run import CallModelData, ModelInputData
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText, ResponseFunctionToolCall

from app.context_compaction.runtime import TypeScriptInputFilter, CompactionBridgeError, build_input_filter
from app.config import settings
from app.api import chat
from app.tools.runtime import AgentsToolRuntime


FIELDS = ('goals', 'facts', 'constraints', 'completed', 'decisions', 'unresolved', 'references', 'tool_results')


def history(context='alpha', rounds=8):
    return [message for i in range(rounds) for message in (
        {'role': 'user', 'content': f'{context} goal {i}: src/main.ts ' + 'x' * 1800},
        {'role': 'assistant', 'content': f'{context} decision: preserve API ' + 'y' * 1800})]


async def fake_summary(**kwargs):
    assert kwargs['reasoning_effort'] == 'disabled'
    assert kwargs['parameters']['max_tokens'] > 0
    assert 'tools' not in kwargs
    assert 'UNTRUSTED' in kwargs['context'][0]['content']
    values = {name: [] for name in FIELDS}
    values['facts'] = ['alpha' if 'alpha' in kwargs['text'] else 'beta']
    values['decisions'] = ['preserve API']
    values['references'] = ['src/main.ts']
    return {'text': json.dumps(values), 'total_tokens': 100}


def bridge(owner='ctx-a', invoke=fake_summary):
    return TypeScriptInputFilter(context_id=owner, model='mock', base_url='https://mock.test', api_key='never-to-node',
                                 budget={'contextWindow': 16000, 'outputReserve': 1000, 'safetyMargin': 500},
                                 config={'retainTurns': 1, 'retainRatio': 0}, tools=[], invoke=invoke)


def call(messages):
    return SimpleNamespace(model_data=ModelInputData(input=messages, instructions='immutable SYSTEM'))


async def test_short_input_does_not_start_node_or_call_summary():
    projection = bridge()
    data = call([{'role': 'user', 'content': 'hello'}])
    assert await projection(data) is data.model_data
    assert projection.process is None


async def test_real_node_projection_keeps_source_and_memo_across_tool_steps():
    invokes = []
    async def summarize(**kwargs):
        invokes.append(kwargs)
        return await fake_summary(**kwargs)
    projection = bridge(invoke=summarize)
    source = history() + [{'role': 'user', 'content': 'current'}]
    original = copy.deepcopy(source)
    try:
        first = await projection(call(source))
        process = projection.process
        count = len(invokes)
        second = await projection(call(source))
        assert count > 0 and len(invokes) == count
        assert first == second
        assert len(first.input) < len(source)
        assert first.input[-1] == source[-1]
        assert first.instructions == 'immutable SYSTEM'
        assert source == original
        assert process.returncode is None
    finally:
        await projection.close()
    assert process.returncode is not None


async def test_concurrent_sessions_use_distinct_workers_and_summaries():
    a, b = bridge('ctx-a'), bridge('ctx-b')
    try:
        x, y = await asyncio.gather(a(call(history('alpha') + [{'role': 'user', 'content': 'A'}])),
                                    b(call(history('beta') + [{'role': 'user', 'content': 'B'}])))
        assert 'alpha' in x.input[0]['content'] and 'beta' not in x.input[0]['content']
        assert 'beta' in y.input[0]['content'] and 'alpha' not in y.input[0]['content']
        assert a.process.pid != b.process.pid
    finally:
        await asyncio.gather(a.close(), b.close())


async def test_cancelled_summary_terminates_owned_worker_without_changing_history():
    entered = asyncio.Event()
    async def waiting(**_):
        entered.set()
        await asyncio.Future()
    projection = bridge(invoke=waiting)
    source = history() + [{'role': 'user', 'content': 'current'}]
    original = copy.deepcopy(source)
    task = asyncio.create_task(projection(call(source)))
    await asyncio.wait_for(entered.wait(), 10)
    process = projection.process
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode is not None and projection.process is None
    assert source == original


async def test_summary_failure_blocks_overflow_and_releases_worker():
    async def fail(**_):
        raise RuntimeError('provider offline')
    projection = bridge(invoke=fail)
    source = history() + [{'role': 'user', 'content': 'current'}]
    original = copy.deepcopy(source)
    with pytest.raises(CompactionBridgeError):
        await projection(call(source))
    assert source == original and projection.process is None


async def test_unsupported_window_fails_only_when_enabled_and_sets_real_output_cap():
    agent = Agent(name='test', model='mock', model_settings=ModelSettings())
    with pytest.raises(CompactionBridgeError):
        build_input_filter(agent=agent, context_id='ctx', model='unknown', base_url='https://mock.test', api_key='unused')
    hook = build_input_filter(agent=agent, context_id='ctx', model='mock', base_url='https://mock.test', api_key='unused',
                              model_policies={'https://mock.test::mock': {'context_window': 10000, 'output_reserve': 1500}})
    assert agent.model_settings.max_tokens == 1500
    await hook.close()


class MockModel(Model):
    def __init__(self, with_tool=False):
        self.inputs = []
        self.with_tool = with_tool

    async def get_response(self, system_instructions, input, model_settings, *args, **kwargs):
        self.inputs.append((system_instructions, copy.deepcopy(input), model_settings.max_tokens))
        if self.with_tool and len(self.inputs) == 1:
            return ModelResponse(output=[ResponseFunctionToolCall(id='tool-item', type='function_call', call_id='clock-call',
                name='current_datetime', arguments='{}')], usage=Usage(requests=1, input_tokens=100, output_tokens=10, total_tokens=110), response_id='tool-response')
        return ModelResponse(output=[ResponseOutputMessage(id='answer', type='message', role='assistant', status='completed',
            content=[ResponseOutputText(type='output_text', text='resumed: preserve API in src/main.ts', annotations=[])])],
            usage=Usage(requests=1, input_tokens=100, output_tokens=10, total_tokens=110), response_id='response-mock')

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield


@pytest.mark.parametrize('enabled', [False, True])
async def test_python_chat_api_to_actual_sdk_runner_to_model_projection(enabled, monkeypatch):
    from app.ai_engine import model_runtime
    monkeypatch.setattr(model_runtime, 'generate_with_runtime_model', fake_summary)
    monkeypatch.setattr(settings, 'OSCODE_CONTEXT_COMPACTION_ENABLED', enabled)
    monkeypatch.setattr(settings, 'OSCODE_CONTEXT_COMPACTION_MODELS', {
        'https://mock.test::mock': {'context_window': 16000, 'output_reserve': 1000, 'safety_margin': 500,
                                   'retain_turns': 1, 'retain_ratio': 0}})
    model = MockModel()
    runtime = AgentsToolRuntime(allowed_tools=[])
    closed = []
    class Client:
        async def close(self): closed.append(True)
    monkeypatch.setattr(runtime, '_build_agent', lambda *a, **k: (
        Agent(name='OScode', model=model, instructions='SYSTEM', model_settings=ModelSettings()), Client(), {'effectiveModel': 'mock'}))
    monkeypatch.setattr(chat, 'get_chat_tool_runtime', lambda: runtime)
    source = history()
    original = copy.deepcopy(source)
    response = await chat.chat_text(chat.ChatRequest(text='current', context=source, context_id='ctx-test',
                                                    model='mock', base_url='https://mock.test', api_key='test'))
    assert response.text == 'resumed: preserve API in src/main.ts'
    instructions, actual, cap = model.inputs[0]
    assert actual[-1] == {'role': 'user', 'content': 'current'}
    assert sum(item.get('content') == 'current' for item in actual) == 1
    assert instructions == 'SYSTEM' and source == original and closed
    if enabled:
        assert len(actual) < len(source) and cap == 1000
        assert 'checkpoint' in actual[0]['content']
    else:
        assert actual == source + [{'role': 'user', 'content': 'current'}]
        assert cap is None


async def test_actual_sdk_multiple_tool_steps_keep_call_ids_and_resume_after_compaction(monkeypatch):
    from app.ai_engine import model_runtime
    from app.tools.runtime import SDK_TOOLS
    monkeypatch.setattr(model_runtime, 'generate_with_runtime_model', fake_summary)
    monkeypatch.setattr(settings, 'OSCODE_CONTEXT_COMPACTION_MODELS', {
        'https://mock.test::mock': {'context_window': 16000, 'output_reserve': 1000, 'safety_margin': 500,
                                   'retain_turns': 1, 'retain_ratio': 0}})
    model = MockModel(with_tool=True)
    runtime = AgentsToolRuntime(allowed_tools=['current_datetime'])
    class Client:
        async def close(self): pass
    monkeypatch.setattr(runtime, '_build_agent', lambda *a, **k: (
        Agent(name='OScode', model=model, instructions='SYSTEM', tools=[SDK_TOOLS['current_datetime']]), Client(), {'effectiveModel': 'mock'}))
    result = await runtime.run('current', history=history(), session_id='ctx-tools', model='mock', base_url='https://mock.test',
                               api_key='test', oscode_context_compaction=True)
    assert result.text.startswith('resumed') and len(model.inputs) == 2
    second = model.inputs[1][1]
    calls = [item for item in second if item.get('type') == 'function_call']
    outputs = [item for item in second if item.get('type') == 'function_call_output']
    assert calls[0]['call_id'] == outputs[0]['call_id'] == 'clock-call'


async def test_http_chat_stream_uses_real_sdk_filter_and_preserves_sse_contract(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from openai import AsyncOpenAI
    from app.tools import runtime as runtime_module
    from app.ai_engine import model_runtime
    inputs = []
    def provider(request):
        body = json.loads(request.content)
        inputs.append(body)
        base = {'id': 'chat-mock', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'mock'}
        chunks = [{**base, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'stream resumed'}, 'finish_reason': None}]},
                  {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}]
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                              content=''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n')
    def client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(provider)))
    monkeypatch.setattr(runtime_module, 'AsyncOpenAI', client)
    monkeypatch.setattr(model_runtime, 'generate_with_runtime_model', fake_summary)
    monkeypatch.setattr(settings, 'OSCODE_CONTEXT_COMPACTION_ENABLED', True)
    monkeypatch.setattr(settings, 'OSCODE_CONTEXT_COMPACTION_MODELS', {
        'https://mock.test::mock': {'context_window': 16000, 'output_reserve': 1000, 'safety_margin': 500,
                                   'retain_turns': 1, 'retain_ratio': 0}})
    monkeypatch.setattr(chat, 'get_chat_tool_runtime', lambda: AgentsToolRuntime(allowed_tools=[]))
    app = FastAPI()
    app.include_router(chat.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as session:
        response = await session.post('/chat/text/stream', json={'text': 'current', 'context': history(), 'context_id': 'ctx-http',
                                    'model': 'mock', 'base_url': 'https://mock.test', 'api_key': 'test'})
    assert response.status_code == 200
    assert 'stream resumed' in response.text and '"event": "done"' in response.text
    assert len(inputs) == 1
    assert any('checkpoint' in str(m.get('content')) for m in inputs[0]['messages'])
    assert inputs[0]['max_tokens'] == 1000
    assert sum(m.get('role') == 'user' and m.get('content') == 'current' for m in inputs[0]['messages']) == 1
    usage = next(json.loads(line[6:])['data'] for line in response.text.splitlines()
                 if line.startswith('data: ') and json.loads(line[6:]).get('event') == 'usage')
    assert usage['contextFixedTokens'] > 0
    assert usage['contextTokenMethod'] == 'utf8-upper-bound'


@pytest.mark.skipif(os.environ.get('OSCODE_COMPACTION_LIVE_TEST') != '1', reason='explicit opt-in for limited real Provider calls')
async def test_real_provider_summary_and_post_compaction_fact_recovery():
    from app.ai_engine.model_runtime import resolve_system_runtime_config, generate_with_runtime_model
    model, base_url, api_key = resolve_system_runtime_config()
    facts = 'Confirmed: keep REST; file path is src/context.ts; unfinished task is add race tests; budget limit is 1500.'
    source = [{'role': 'user', 'content': facts}]
    for i in range(6):
        source.extend([{'role': 'assistant', 'content': f'observation {i} ' + 'x' * 1650},
                       {'role': 'user', 'content': f'review {i} ' + 'y' * 1650}])
    source.append({'role': 'user', 'content': 'Return JSON with decision, path, todo, budget from confirmed facts. No prose.'})
    projection = TypeScriptInputFilter(context_id='synthetic-live-compaction', model=model, base_url=base_url, api_key=api_key,
        budget={'contextWindow': 25000, 'outputReserve': 1000, 'safetyMargin': 500},
        config={'retainTurns': 1, 'retainRatio': 0, 'summaryMaxTokens': 1800}, tools=[])
    original = copy.deepcopy(source)
    try:
        # Same Provider helper before and after, no production history/database.
        before = await generate_with_runtime_model(text=source[-1]['content'], context=source[:-1], model=model,
            base_url=base_url, api_key=api_key, reasoning_effort='disabled', parameters={'max_tokens': 300})
        compacted = await projection(call(source))
        assert len(compacted.input) < len(source), 'live fixture must actually trigger compaction'
        after = await generate_with_runtime_model(text=source[-1]['content'], context=compacted.input[:-1], model=model,
            base_url=base_url, api_key=api_key, reasoning_effort='disabled', parameters={'max_tokens': 300})
        for response in [before, after]:
            output = response['text'].lower()
            assert 'rest' in output and 'src/context.ts' in output and 'race' in output and '1500' in output
        assert source == original
        out = Path(__file__).resolve().parents[3] / '.tmp-tests/pr-ctx-01/live-quality.json'
        out.write_text(json.dumps({'model': model, 'before': before['text'], 'after': after['text'],
            'beforeTokens': before.get('total_tokens'), 'afterTokens': after.get('total_tokens'),
            'beforeInputTokens': before.get('input_tokens'), 'afterInputTokens': after.get('input_tokens'),
            'beforeOutputTokens': before.get('output_tokens'), 'afterOutputTokens': after.get('output_tokens'),
            'criticalFacts': 4, 'retainedBefore': 4, 'retainedAfter': 4,
            'sourceMessages': len(source), 'projectedMessages': len(compacted.input),
            'compaction': projection.last_metrics}, ensure_ascii=False, indent=2), encoding='utf8')
    finally:
        await projection.close()

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import uvicorn
import pytest
from fastapi import FastAPI

import app.api.agentos_v2 as agentos_v2
import components.executor.node_runner as node_runner
import runtime.live_events as live_events
from adapters.model_compatibility import ModelCompatibilityRegistry
from adapters.model_runtime import RegisteredModelRuntime
from app.api.agentos_v2 import create_router
from app.execution.coordinator import RunExecutionCoordinator
from components.executor import InMemoryExecutionValueStore
from components.mission_manager.store import WorkflowRegistry
from components.recovery.checkpoint import ACGCheckpointStore
from contracts.planning import PlannedTask
from contracts.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionType,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from runtime import ExecutionRuntime
from runtime.app_setup import ApplicationSetup
from runtime.live_events import RuntimeEventBroker
from service.agents import AgentRegistry
from adapters.model.native import NativeGeneralAgent
from support.stores.memory_workflow_store import MemoryWorkflowStore


def _without_public_provenance(value):
    """Validate safe provenance metadata before applying the body-leak checks.

    Hash/version fields are part of the existing public event contract. Their
    names contain 'prompt', but they must never carry prompt bodies.
    """
    if isinstance(value, list):
        return [_without_public_provenance(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in {'promptTemplateHash', 'promptInstanceHash'}:
            assert isinstance(item, str) and re.fullmatch(r'(?:[a-f0-9]{64})?', item)
        elif key in {'promptVersion', 'promptRendererVersion'}:
            assert item is None or isinstance(item, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{0,160}', item)
        elif key in {'reasoningEffort', 'effectiveReasoningEffort', 'requestedReasoningEffort'}:
            assert item in {None, 'disabled', 'off', 'minimal', 'low', 'medium', 'standard', 'high', 'deep', 'xhigh', 'max', 'ultra'}
        elif key in {'reasoning_tokens', 'reasoningTokens'}:
            assert isinstance(item, int) and item >= 0
        else:
            result[key] = _without_public_provenance(item)
    return result


def _assert_no_request_bodies(payloads):
    def strings(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, str):
            yield value
    for payload in payloads:
        text_values = list(strings(payload))
        for request in _StreamingProviderHandler.requests:
            for message in request.get('messages', []):
                content = message.get('content')
                if isinstance(content, str) and content:
                    assert all(content not in value for value in text_values)


@pytest.mark.parametrize('content', ['private message', '{"private":"quoted\\nrequest"}'])
def test_stream_security_checks_detect_quoted_request_bodies(monkeypatch, content):
    monkeypatch.setattr(_StreamingProviderHandler, 'requests', [{'messages':[{'content':content}]}])
    with pytest.raises(AssertionError):
        _assert_no_request_bodies([{'payload':{'nested':['prefix '+content+' suffix']}}])


@pytest.mark.parametrize('payload', [
    {'promptTemplateHash': 'raw prompt body'}, {'promptVersion': 'raw prompt body'},
    {'nested': {'prompt': 'secret'}}, {'reasoning_content': 'private reasoning'},
])
def test_stream_security_checks_reject_bodies_including_provenance_fields(payload):
    with pytest.raises(AssertionError):
        cleaned = _without_public_provenance(payload)
        assert not any(word in json.dumps(cleaned).lower() for word in ('prompt', 'reasoning'))


class _StreamingProviderHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    first_delta_ack: threading.Event | None = None
    native_response_chunks = (
        '{"task_summary":"streamed',
        ' native task","constraints":[],"success_criteria":["visible"],'
        '"assumptions":[],"open_questions":[]}',
    )

    @classmethod
    def response_chunks(cls, payload: dict) -> tuple[str, ...]:
        schema = (
            payload.get("response_format", {})
            .get("json_schema", {})
            .get("schema", {})
        )
        required = set(schema.get("required") or [])
        if {'observationId', 'action', 'reason'} <= required:
            request = json.loads(payload['messages'][-1]['content'])
            observation = request['observation']
            value = {
                'observationId': request['observationId'],
                'action': 'wait' if observation['completionBlockers'] else 'continue' if observation['remainingStepIds'] else 'complete',
                'reason': 'Decision from the current persisted execution facts',
            }
        elif "primaryGoal" in required:
            value = {
                "primaryGoal": "Understand the streamed task",
                "keyConstraints": [],
                "requiredCapabilities": ["task_understanding"],
                "expectedArtifacts": [],
                "verificationRequirements": [],
                "estimatedComplexity": "simple",
                "domainHint": "general",
                "taskTypeHint": "general",
                "implicitRequirements": [],
                "riskLevel": "normal",
            }
        elif "tasks" in required:
            value = {
                "tasks": [{
                    "key": "understand",
                    "title": "Understand streamed task",
                    "objective": "consume the streamed task understanding result",
                    "capabilityId": "task_understanding",
                    "acceptanceCriteria": ["the streamed result is visible"],
                    "sourceRefs": [],
                    "decompositionRationale": "production streaming E2E",
                    "logicalRole": "task",
                }],
                "relations": [],
            }
        else:
            return cls.native_response_chunks
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        midpoint = max(1, len(serialized) // 2)
        return serialized[:midpoint], serialized[midpoint:]

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size).decode("utf-8"))
        self.requests.append(payload)
        if not payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            body = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for index, chunk in enumerate(self.response_chunks(payload)):
            event = {"choices": [{"delta": {"content": chunk}}]}
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()
            if index == 0:
                assert self.first_delta_ack is not None and self.first_delta_ack.wait(10), "SSE prefix was not delivered before completion"
        self.wfile.write(
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, _format: str, *_args) -> None:
        return None


def _subscriber_ready(broker, run_id):
    """Signal after the actual server subscriber has installed its queue."""
    ready = asyncio.Event()
    client_loop = asyncio.get_running_loop()
    class Subscribers(set):
        def add(self, queue):
            super().add(queue)
            # The next server-loop turn follows subscribe() entering queue.get.
            asyncio.get_running_loop().call_soon(client_loop.call_soon_threadsafe, ready.set)
    broker._queues[run_id] = Subscribers()
    return ready


def _model_environment(base_url: str) -> dict[str, str]:
    return {
        "AGENTOS_MODELS": json.dumps([
            {
                "capabilityId": "model.runtime.streaming.e2e",
                "provider": "openai_compatible",
                "models": ["local-streaming-model"],
                "baseUrl": base_url,
                "apiKeyEnv": "LOCAL_STREAMING_KEY",
                "allowInsecure": True,
                "priority": 100,
            }
        ]),
        "LOCAL_STREAMING_KEY": "test-only-key",
    }


def _runtime(tmp_path, model_registry: ModelCompatibilityRegistry) -> ExecutionRuntime:
    native = NativeGeneralAgent()
    agents = AgentRegistry()
    agents.register(native)
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="native-http-streaming-e2e",
            name="Native HTTP streaming E2E",
            domain="general",
            runtimeEngine="acg",
            planningNodes=[PlannedTask(
                key="understand",
                title="Understand streamed task",
                objective="consume the native streaming model",
            )],
            steps=[WorkflowStepDefinition(
                stepId="understand",
                name="Understand streamed task",
                agentName=native.profile.agent_name,
                capability="task_understanding",
            )],
        )
    )
    return ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "native-http-checkpoints.sqlite3"),
        execution_value_store=InMemoryExecutionValueStore(),
        model_registry=model_registry,
    )


def _planner_runtime(tmp_path, model_registry: ModelCompatibilityRegistry) -> ExecutionRuntime:
    native = NativeGeneralAgent()
    agents = AgentRegistry()
    agents.register(native)
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="planner-http-streaming-e2e",
        name="Planner HTTP streaming E2E",
        domain="general",
        runtimeEngine="acg",
        definitionType=WorkflowDefinitionType.NATIVE_BOOTSTRAP,
        steps=[],
    ))
    return ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "planner-http-checkpoints.sqlite3"),
        execution_value_store=InMemoryExecutionValueStore(),
        model_registry=model_registry,
    )


def _start_http_app(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "uvicorn did not start"
    socket = server.servers[0].sockets[0]
    port = socket.getsockname()[1]
    return server, thread, f"http://127.0.0.1:{port}"


def test_native_http_provider_to_fastapi_sse_streams_before_node_completion(
    tmp_path, monkeypatch
) -> None:
    asyncio.run(_test_native_http_provider_to_fastapi_sse_streams_before_node_completion(tmp_path, monkeypatch))


async def _test_native_http_provider_to_fastapi_sse_streams_before_node_completion(
    tmp_path, monkeypatch
) -> None:
    provider = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingProviderHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    _StreamingProviderHandler.requests = []
    _StreamingProviderHandler.first_delta_ack = threading.Event()

    registry = ModelCompatibilityRegistry()
    setup = ApplicationSetup.from_environment(
        _model_environment(f"http://127.0.0.1:{provider.server_port}/v1"),
        model_registry=registry,
    )
    await setup.start()
    runtime = _runtime(tmp_path, registry)
    runtime.default_model_binding = setup.default_model_binding

    broker = RuntimeEventBroker()
    monkeypatch.setattr(live_events, "runtime_event_broker", broker)
    monkeypatch.setattr(node_runner, "runtime_event_broker", broker)
    monkeypatch.setattr(agentos_v2, "runtime_event_broker", broker)
    import adapters.model.native as native_module

    monkeypatch.setattr(native_module, "runtime_event_broker", broker)

    task = runtime.create_mission(
        "Native HTTP streaming acceptance",
        workflow_id="native-http-streaming-e2e",
        input={"userIntent": "understand this streamed task"},
    )
    _, run = runtime.prepare_run(task.mission_id, workflow_id="native-http-streaming-e2e")
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    server, server_thread, base_url = _start_http_app(app)
    subscriber_ready = _subscriber_ready(broker, run.run_id)
    execution = None
    event_types: list[str] = []
    payloads: list[dict] = []
    saw_delta_before_completion = False

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            async with client.stream(
                "GET", f"{base_url}/agentos/v2/runs/{run.run_id}/events"
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                await asyncio.wait_for(subscriber_ready.wait(), timeout=5)
                execution = asyncio.create_task(runtime.execute_prepared_run(run.run_id))
                event_type = ""
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        event_types.append(event_type)
                    elif line.startswith("data:"):
                        payload = json.loads(line.split(":", 1)[1].strip())
                        payloads.append(payload)
                        if event_type == "model.output.delta":
                            status = runtime.get_status(run.run_id)
                            saw_delta_before_completion = saw_delta_before_completion or status.status is not WorkflowStatus.COMPLETED
                            _StreamingProviderHandler.first_delta_ack.set()
                        if event_type == "run.completed":
                            break
        result = await asyncio.wait_for(execution, timeout=10)
        assert result.status is WorkflowStatus.COMPLETED
    finally:
        _StreamingProviderHandler.first_delta_ack.set()
        if execution is not None:
            if not execution.done():
                execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
        server.should_exit = True
        server_thread.join(timeout=5)
        await setup.close()
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=2)

    assert _StreamingProviderHandler.requests
    assert _StreamingProviderHandler.requests[0]["stream"] is True
    assert "model.output.delta" in event_types
    assert event_types.index("model.output.delta") < event_types.index("node.completed")
    assert event_types[-1] == "run.completed"
    assert saw_delta_before_completion
    deltas = [
        payload.get("payload", {}).get("delta", "")
        for payload in payloads
        if payload.get("eventType") == "model.output.delta"
    ]
    assert deltas and "task_summary" in "".join(deltas)
    assert all("prompt" not in json.dumps(_without_public_provenance(payload), ensure_ascii=False).lower() for payload in payloads)
    _assert_no_request_bodies(payloads)
    assert run.run_id not in broker._queues


def test_planner_http_provider_to_fastapi_sse_precedes_planner_completion(tmp_path, monkeypatch) -> None:
    asyncio.run(_test_planner_http_provider_to_fastapi_sse_precedes_planner_completion(tmp_path, monkeypatch))


async def _test_planner_http_provider_to_fastapi_sse_precedes_planner_completion(
    tmp_path, monkeypatch
) -> None:
    provider = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingProviderHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    _StreamingProviderHandler.requests = []
    _StreamingProviderHandler.first_delta_ack = threading.Event()
    registry = ModelCompatibilityRegistry()
    setup = ApplicationSetup.from_environment(
        _model_environment(f"http://127.0.0.1:{provider.server_port}/v1"),
        model_registry=registry,
    )
    await setup.start()
    runtime = _planner_runtime(tmp_path, registry)
    runtime.default_model_binding = setup.default_model_binding
    runtime.set_intent_llm(RegisteredModelRuntime(
        registry=registry,
        provider="openai_compatible",
        model="local-streaming-model",
    ))

    broker = RuntimeEventBroker()
    monkeypatch.setattr(live_events, "runtime_event_broker", broker)
    monkeypatch.setattr(node_runner, "runtime_event_broker", broker)
    monkeypatch.setattr(agentos_v2, "runtime_event_broker", broker)
    import adapters.model.native as native_module

    monkeypatch.setattr(native_module, "runtime_event_broker", broker)
    task = runtime.create_mission(
        "Planner HTTP streaming acceptance",
        workflow_id="planner-http-streaming-e2e",
        input={
            "userIntent": "understand this task through the planner",
            "usePlanner": True,
            "deterministicIntent": False,
        },
    )
    _, run = runtime.prepare_run(
        task.mission_id,
        workflow_id="planner-http-streaming-e2e",
        defer_acg_planning=True,
    )
    app = FastAPI()
    app.include_router(create_router(runtime, RunExecutionCoordinator(runtime)))
    server, server_thread, base_url = _start_http_app(app)
    subscriber_ready = _subscriber_ready(broker, run.run_id)
    execution = None
    event_types: list[str] = []
    payloads: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "GET", f"{base_url}/agentos/v2/runs/{run.run_id}/events"
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                await asyncio.wait_for(subscriber_ready.wait(), timeout=5)
                execution = asyncio.create_task(runtime.execute_prepared_run(run.run_id))
                event_type = ""
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        event_types.append(event_type)
                    elif line.startswith("data:"):
                        payload = json.loads(line.split(":", 1)[1].strip())
                        payloads.append(payload)
                        if event_type == 'planner.model.output.delta':
                            _StreamingProviderHandler.first_delta_ack.set()
                        if event_type == "run.completed":
                            break
        result = await asyncio.wait_for(execution, timeout=15)
        assert result.status is WorkflowStatus.COMPLETED
    finally:
        _StreamingProviderHandler.first_delta_ack.set()
        if execution is not None:
            if not execution.done():
                execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
        server.should_exit = True
        server_thread.join(timeout=5)
        await setup.close()
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=2)

    assert 'planner.started' in event_types
    assert event_types.count("planner.model.started") >= 1
    assert "planner.model.first_token" in event_types
    assert "planner.model.completed" in event_types
    assert "planner.completed" in event_types
    assert event_types.index("planner.model.first_token") < event_types.index("planner.completed")
    assert event_types.index("planner.completed") < event_types.index("node.started")
    assert "planner.model.output.delta" in event_types
    assert all(
        not any(key in json.dumps(_without_public_provenance(payload), ensure_ascii=False).lower() for key in ("prompt", "reasoning", '"data"'))
        for payload in payloads
        if payload.get("eventType", "").startswith("planner.")
    )
    _assert_no_request_bodies(payloads)
    assert len(_StreamingProviderHandler.requests) >= 3
    assert all(request.get("stream") is True for request in _StreamingProviderHandler.requests)
    assert run.run_id not in broker._queues

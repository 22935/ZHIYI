"""Cross-process Runtime Streaming acceptance for the TypeScript -> Python SSE chain.

This script is intentionally outside the production runtime and is not a second
streaming implementation. It starts the existing Python router and the current
compiled Node backend, then drives its real HTTP gateway with an isolated LocalIdentity.
The model provider is a deterministic local HTTP fixture; no external model is claimed.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
for import_root in (
    PROJECT_ROOT,
    PROJECT_ROOT / "apps" / "agent",
    PROJECT_ROOT / "apps" / "agentOS",
    PROJECT_ROOT / "apps" / "agentOS" / "src",
    PROJECT_ROOT / "apps" / "agent" / "tests",
):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.security.internal_auth import InternalServiceAuthMiddleware
from app.api.agentos_v2 import create_router
from app.execution.coordinator import RunExecutionCoordinator
from app.execution.wiring import aclose_runtime
from contracts.planning import PlannedTask, TaskImplementationBinding, TaskPlan
from runtime.live_events import RuntimeEventBroker
from support.acg.models import ACGBlueprint, StepNode
from support.acg.planning import ACGResourcePlan, AgentBindingSpec

import app.api.agentos_v2 as agentos_v2
import components.executor.node_runner as node_runner
import runtime.live_events as live_events
import adapters.model.native as native_module

production_e2e = importlib.import_module("test_runtime_streaming_production_e2e")
_StreamingProviderHandler = production_e2e._StreamingProviderHandler
_model_environment = production_e2e._model_environment
_planner_runtime = production_e2e._planner_runtime
_runtime = production_e2e._runtime
ApplicationSetup = production_e2e.ApplicationSetup
ModelCompatibilityRegistry = production_e2e.ModelCompatibilityRegistry
RegisteredModelRuntime = production_e2e.RegisteredModelRuntime


INTERNAL_TOKEN = "combined-runtime-streaming-acceptance-token-20260903"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"


class TrackingBroker(RuntimeEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.subscription_ready = asyncio.Event()
        self.subscription_closed = asyncio.Event()

    async def subscribe(self, run_id: str):
        # The parent generator registers its queue synchronously before the
        # first await. Setting this immediately before entering it lets the
        # orchestration task start Runtime only after TypeScript has reached Python.
        self.subscription_ready.set()
        try:
            async for event in super().subscribe(run_id):
                yield event
        finally:
            self.subscription_closed.set()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_backend_gateway(python_base_url: str, directory: Path) -> tuple[subprocess.Popen[str], str, list[str]]:
    entry = PROJECT_ROOT / "apps/backend-ts/dist/main.js"
    if not entry.is_file():
        raise RuntimeError("Build apps/backend-ts first: npm run build")
    port = _free_port()
    identity = directory / "gateway-identity.json"
    identity.write_text(json.dumps({"format": "zhiyi-local-identity-v1", "version": 1,
        "actorId": ACTOR_ID, "legacyUserId": ACTOR_ID, "wireTenantId": None,
        "homeBinding": "isolated-streaming-acceptance"}), encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "ZHIYI_BACKEND_TS_PORT": str(port),
        "ZHIYI_BACKEND_TS_IDENTITY_FILE": str(identity),
        "ZHIYI_BACKEND_TS_EXPECTED_USER_ID": ACTOR_ID,
        "ZHIYI_BACKEND_TS_HOME_BINDING": "isolated-streaming-acceptance",
        "AI_SERVICE_URL": python_base_url, "AI_INTERNAL_TOKEN": INTERNAL_TOKEN,
    })
    process = subprocess.Popen(
        [shutil.which("node"), str(entry)], cwd=directory, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    output: list[str] = []

    def collect() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output.append(line.rstrip())

    threading.Thread(target=collect, daemon=True).start()
    return process, f"http://127.0.0.1:{port}", output


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


async def _wait_backend_ready(base_url: str, process: subprocess.Popen[str], logs: list[str]) -> None:
    deadline = time.monotonic() + 45
    async with httpx.AsyncClient(timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                tail = "\n".join(logs[-30:])
                raise RuntimeError(f"TypeScript gateway exited with {process.returncode}\n{tail}")
            try:
                response = await client.get(f"{base_url}/health/live")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    tail = "\n".join(logs[-30:])
    raise TimeoutError(f"TypeScript gateway did not become ready\n{tail}")


async def _start_http_app_async(app: FastAPI) -> tuple[uvicorn.Server, asyncio.Task[None], str]:
    """Run uvicorn on this event loop so Runtime SQLite stores stay thread-local."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    if not server.started:
        raise RuntimeError("uvicorn did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, task, f"http://127.0.0.1:{port}"


def _event_payload(event_type: str, data: str) -> dict[str, Any]:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise AssertionError(f"SSE event {event_type} was not an object")
    return payload


def _bind_native_plan(runtime, mission) -> None:
    """Supply the explicit plan package required by the current Runtime contract.

    WorkflowStepDefinition is a registration hint; Runtime deliberately no longer
    promotes it into an executable plan. This isolated acceptance supplies its own
    one-node TaskPlan, Blueprint and bindings without changing execution policy.
    """
    agent = next(iter(runtime.agent_registry.all()))
    blueprint = ACGBlueprint(
        graphId="combined-native-streaming-graph",
        nodes=[StepNode(nodeId="understand", name="Understand streamed task",
                        goal="consume the native streaming model", capability="task_understanding")],
        edges=[],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(
            stepId="understand", plannedAgentId=agent.profile.agent_name),)),
    )
    plan = TaskPlan(missionId=mission.mission_id, nodes=(PlannedTask(
        key="step:understand", title="Understand streamed task", objective="consume the native streaming model",
        capabilityRequirements=("task_understanding",), logicalRole="task"),))
    binding = TaskImplementationBinding(planNodeKey="step:understand", acgNodeId="understand")
    mission.input.update(acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
                         taskPlan=plan.model_dump(by_alias=True, mode="json"),
                         taskBindings=[binding.model_dump(by_alias=True, mode="json")])
    runtime.workflow_store.save_mission(mission)


async def _read_backend_events(
    client: httpx.AsyncClient,
    url: str,
    *,
    disconnect_after_first: bool = False,
) -> tuple[list[str], list[dict[str, Any]], float | None, float | None]:
    event_types: list[str] = []
    payloads: list[dict[str, Any]] = []
    first_delta_at: float | None = None
    node_completed_at: float | None = None
    async with client.stream(
        "GET",
        url,
        headers={"Origin": "kinlin-app://shell"},
    ) as response:
        if response.status_code != 200:
            raise AssertionError(f"TypeScript SSE status={response.status_code}: {await response.aread()}")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("text/event-stream"):
            raise AssertionError(f"TypeScript SSE content-type={content_type!r}")
        current_type = ""
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                current_type = line.split(":", 1)[1].strip()
                event_types.append(current_type)
            elif line.startswith("data:"):
                payload = _event_payload(current_type, line.split(":", 1)[1].strip())
                payloads.append(payload)
                now = time.monotonic()
                if current_type == "model.output.delta" and first_delta_at is None:
                    first_delta_at = now
                if current_type in {"model.output.delta", "planner.model.output.delta"}:
                    # The local provider withholds its remaining chunks until a
                    # real delta crossed Python -> Node -> this HTTP consumer.
                    _StreamingProviderHandler.first_delta_ack.set()
                if current_type == "node.completed" and node_completed_at is None:
                    node_completed_at = now
                if disconnect_after_first and len(event_types) >= 1:
                    # An observer must not control execution. Release the test
                    # provider gate before deliberately closing this observer.
                    _StreamingProviderHandler.first_delta_ack.set()
                    return event_types, payloads, first_delta_at, node_completed_at
                if current_type == "run.completed":
                    break
    return event_types, payloads, first_delta_at, node_completed_at


async def _run_case(kind: str, *, disconnect: bool = False) -> dict[str, Any]:
    provider = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingProviderHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    _StreamingProviderHandler.requests = []
    _StreamingProviderHandler.first_delta_ack = threading.Event()
    setup = None
    python_server = None
    python_task = None
    backend_process = None
    temp_dir = None
    stream_task = None
    execution = None
    runtime = None
    previous_environment: dict[str, str | None] = {}
    try:
        registry = ModelCompatibilityRegistry()
        setup = ApplicationSetup.from_environment(
            _model_environment(f"http://127.0.0.1:{provider.server_port}/v1"),
            model_registry=registry,
        )
        await setup.start()
        temp_dir = Path(tempfile.mkdtemp(prefix=f"runtime-streaming-{kind}-"))
        for key in ("CONTENT_MANIFEST", "EXECUTION_MEMORY", "PROVENANCE", "AUDIT", "COMMUNICATION", "EVOLUTION"):
            variable = f"AGENTOS_{key}_DB"
            previous_environment[variable] = os.environ.get(variable)
            os.environ[variable] = str(temp_dir / f"{key.lower()}.sqlite3")
        runtime = _planner_runtime(temp_dir, registry) if kind == "planner" else _runtime(temp_dir, registry)
        runtime.default_model_binding = setup.default_model_binding
        if kind == "planner":
            runtime.set_intent_llm(RegisteredModelRuntime(
                registry=registry,
                provider="openai_compatible",
                model="local-streaming-model",
            ))

        broker = TrackingBroker()
        live_events.runtime_event_broker = broker
        agentos_v2.runtime_event_broker = broker
        node_runner.runtime_event_broker = broker
        native_module.runtime_event_broker = broker
        app = FastAPI()
        coordinator = RunExecutionCoordinator(runtime)
        app.include_router(create_router(runtime, coordinator), prefix="/ai")
        app.add_middleware(InternalServiceAuthMiddleware, token=INTERNAL_TOKEN)
        python_server, python_task, python_base_url = await _start_http_app_async(app)
        backend_process, backend_base_url, backend_logs = _start_backend_gateway(python_base_url, temp_dir)
        await _wait_backend_ready(backend_base_url, backend_process, backend_logs)

        async with httpx.AsyncClient(timeout=20) as client:
            task_record = runtime.create_mission(
                f"Combined {kind} streaming acceptance",
                workflow_id=f"{kind}-http-streaming-e2e",
                input={
                    "authenticatedUserId": ACTOR_ID,
                    "userIntent": f"run the {kind} combined streaming acceptance",
                    "usePlanner": kind == "planner",
                    "deterministicIntent": False,
                },
            )
            if kind == "native":
                _bind_native_plan(runtime, task_record)
            _, prepared_run = runtime.prepare_run(
                task_record.mission_id,
                workflow_id=f"{kind}-http-streaming-e2e",
                review_mode="auto",
                defer_acg_planning=kind == "planner",
            )
            run_id = prepared_run.run_id
            stream_task = asyncio.create_task(_read_backend_events(
                client,
                f"{backend_base_url}/api/agentos/v2/runs/{run_id}/events",
                disconnect_after_first=disconnect,
            ))
            await asyncio.wait_for(broker.subscription_ready.wait(), timeout=10)
            await asyncio.sleep(0)
            execution = asyncio.create_task(runtime.execute_prepared_run(run_id))
            event_types, payloads, first_delta_at, node_completed_at = await stream_task

            if disconnect:
                await asyncio.wait_for(broker.subscription_closed.wait(), timeout=10)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if runtime.get_status(run_id).status.value in {"completed", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(0.1)
                status = runtime.get_status(run_id).status.value
                if status != "completed":
                    raise AssertionError(f"observer disconnect changed workflow status: {status}")
            else:
                if "run.completed" not in event_types:
                    raise AssertionError(f"combined {kind} stream did not reach run.completed: {event_types}")
                result = await asyncio.wait_for(execution, timeout=10)
                if result.status.value != "completed":
                    raise AssertionError(f"combined {kind} workflow status={result.status.value}")

        if kind == "native":
            if not disconnect:
                expected = [
                    "node.started", "model.started", "model.first_token",
                    "model.output.delta", "model.completed", "node.completed",
                ]
                missing = [name for name in expected if name not in event_types]
                if missing:
                    raise AssertionError(f"combined Native stream missing {missing}: {event_types}")
                if event_types.index("model.output.delta") > event_types.index("node.completed"):
                    raise AssertionError(f"first delta was after node completion: {event_types}")
                if first_delta_at is None or node_completed_at is None or first_delta_at >= node_completed_at:
                    raise AssertionError("first_delta < node_completed was not observed")
        else:
            expected = [
                "planner.started", "planner.model.started",
                "planner.model.first_token", "planner.model.activity",
            ]
            missing = [name for name in expected if name not in event_types]
            if missing:
                raise AssertionError(f"combined Planner stream missing {missing}: {event_types}")
            planner_payloads = [
                json.dumps(production_e2e._without_public_provenance(payload), ensure_ascii=False)
                for payload in payloads
                if payload.get("eventType", "").startswith("planner.")
            ]
            for marker in ("prompt", "reasoning_content", '"data"'):
                if any(marker in payload for payload in planner_payloads):
                    raise AssertionError(f"planner SSE leaked {marker}")

        return {
            "kind": kind,
            "runId": run_id,
            "events": event_types,
            "disconnectIsolation": disconnect,
            "firstDeltaBeforeNodeCompleted": (
                first_delta_at is not None
                and node_completed_at is not None
                and first_delta_at < node_completed_at
            ) if kind == "native" else None,
        }
    finally:
        _StreamingProviderHandler.first_delta_ack.set()
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)
        if execution is not None:
            if not execution.done():
                execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
        if backend_process is not None:
            _stop_process(backend_process)
        if python_server is not None:
            python_server.should_exit = True
        if python_task is not None:
            try:
                await asyncio.wait_for(python_task, timeout=5)
            except asyncio.TimeoutError:
                python_task.cancel()
                await asyncio.gather(python_task, return_exceptions=True)
        if setup is not None:
            await setup.close()
        if runtime is not None:
            await aclose_runtime(runtime)
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=3)
        if temp_dir is not None:
            resolved = temp_dir.resolve()
            if resolved.parent != Path(tempfile.gettempdir()).resolve() or not resolved.name.startswith(f"runtime-streaming-{kind}-"):
                raise RuntimeError("Refusing to clean a directory outside this acceptance case")
            shutil.rmtree(resolved)
        for variable, value in previous_environment.items():
            if value is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = value


async def main() -> None:
    native = await _run_case("native", disconnect=False)
    planner = await _run_case("planner", disconnect=False)
    disconnect = await _run_case("native", disconnect=True)
    print(json.dumps({"native": native, "planner": planner, "disconnect": disconnect}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

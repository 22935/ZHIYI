from __future__ import annotations

import json
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from adapters.resource_execution import (
    HttpResourceExecutionAdapter,
    ResourceExecutionError,
    build_resource_execution_adapter,
    normalize_execution_endpoint,
)
from adapters.resource_execution import ResourceCredentialProvider
from contracts.resource import ResourceEndpoint, RuntimeKind, RuntimeProfile
from contracts.resource_signing import build_resource_signature
from service.agents.base import AgentOutput


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        task=SimpleNamespace(mission_id="mission-1"),
        run=SimpleNamespace(run_id="run-1"),
        step=SimpleNamespace(step_id="step-1", agent_name="edge-vision", capability="vision.infer", goal="classify"),
        context_pack=SimpleNamespace(
            data={"imageRef": "artifact://image-1"},
            evidence_refs=["evidence-1"],
            attempt_id="attempt-1",
        ),
        commit_id="commit-1",
    )


@pytest.mark.asyncio
async def test_http_adapter_sends_controlled_context_and_returns_agent_output() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["headers"] = dict(request.headers)
        received["json"] = json.loads(request.content)
        return httpx.Response(200, json={"output": {"label": "cat"}, "summary": "classified"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://edge")
    adapter = HttpResourceExecutionAdapter(
        resource_id="edge-01",
        address="http://edge",
        credential_provider=_Credentials(),
        client=client,
    )

    result = await adapter.run(_context())

    assert isinstance(result, AgentOutput)
    assert result.output == {"label": "cat"}
    assert received["headers"]["idempotency-key"] == "commit-1"
    assert received["json"] == {
        "runId": "run-1",
        "missionId": "mission-1",
        "stepId": "step-1",
        "attemptId": "attempt-1",
        "commitId": "commit-1",
        "agentName": "edge-vision",
        "capability": "vision.infer",
        "goal": "classify",
        "input": {"imageRef": "artifact://image-1"},
        "evidenceRefs": ["evidence-1"],
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_http_adapter_reports_remote_failure_without_returning_fake_output() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "edge unavailable"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://edge")
    adapter = HttpResourceExecutionAdapter(
        resource_id="edge-01",
        address="http://edge",
        credential_provider=_Credentials(),
        client=client,
    )

    with pytest.raises(ResourceExecutionError, match="REMOTE_EXECUTION_FAILED"):
        await adapter.run(_context())

    await client.aclose()


class _Credentials:
    def __init__(self, credential_id: str = "credential-1", secret: str = "secret-1") -> None:
        self.credential_id = credential_id
        self.secret = secret

    def current_signing_credential(self, resource_id: str) -> tuple[str, str]:
        assert resource_id == "edge-01"
        return self.credential_id, self.secret


def test_normalize_execution_endpoint_does_not_duplicate_execute_path() -> None:
    assert normalize_execution_endpoint("https://edge.example.test") == "https://edge.example.test/execute"
    assert normalize_execution_endpoint("https://edge.example.test/execute") == "https://edge.example.test/execute"
    assert normalize_execution_endpoint("https://edge.example.test/api/execute/") == "https://edge.example.test/api/execute"


@pytest.mark.asyncio
async def test_http_adapter_signs_exact_json_body_with_current_resource_credential() -> None:
    received: dict[str, object] = {}
    credentials = _Credentials()

    async def handler(request: httpx.Request) -> httpx.Response:
        received["request"] = request
        return httpx.Response(200, json={"output": {"ok": True}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://edge")
    adapter = HttpResourceExecutionAdapter(
        resource_id="edge-01",
        address="http://edge/execute",
        credential_provider=credentials,
        client=client,
    )

    await adapter.run(_context())

    request = received["request"]
    assert isinstance(request, httpx.Request)
    timestamp = int(request.headers["x-resource-timestamp"])
    nonce = request.headers["x-resource-nonce"]
    expected = build_resource_signature(
        credentials.secret,
        method="POST",
        path="/execute",
        timestamp=timestamp,
        nonce=nonce,
        body=request.content,
    )
    assert request.headers["x-resource-credential"] == "credential-1"
    assert request.headers["x-resource-signature"] == expected
    assert request.url.path == "/execute"
    await client.aclose()


@pytest.mark.asyncio
async def test_http_adapter_reads_rotated_credential_for_next_request() -> None:
    credentials = _Credentials()
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["x-resource-credential"])
        return httpx.Response(200, json={"output": {"ok": True}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://edge")
    adapter = HttpResourceExecutionAdapter(
        resource_id="edge-01",
        address="http://edge",
        credential_provider=credentials,
        client=client,
    )
    await adapter.run(_context())
    credentials.credential_id = "credential-2"
    credentials.secret = "secret-2"
    await adapter.run(_context())

    assert seen == ["credential-1", "credential-2"]
    await client.aclose()


def test_build_resource_execution_adapter_uses_remote_profile_endpoint() -> None:
    profile = RuntimeProfile(
        runtimeId="edge-01",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-1",
        capabilities=["analysis"],
        endpoint=ResourceEndpoint(protocol="https", address="https://edge.example.test/execute"),
    )
    adapter = build_resource_execution_adapter(
        profile,
        credential_provider=_Credentials(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )
    assert isinstance(adapter, HttpResourceExecutionAdapter)
    assert adapter.address == "https://edge.example.test/execute"


def test_build_resource_execution_adapter_rejects_declared_but_unsupported_protocol():
    profile = RuntimeProfile(runtimeId="grpc-runtime", nodeId="node:edge", capabilities=["analysis"],
        adapter="grpc-vendor", endpoint=ResourceEndpoint(protocol="grpc", address="grpc://edge.example.test"))
    with pytest.raises(ResourceExecutionError, match="unsupported adapter/protocol"):
        build_resource_execution_adapter(profile, credential_provider=_Credentials())


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload", [
    (202, {"output": {"accepted": True}}),
    (200, {"status": "RUNNING"}),
    (200, {"status": "RUNNING", "output": {}}),
    (200, {}),
    (204, None),
    (503, {"error": "failed after side effect"}),
    (409, {"status": "RUNNING"}),
])
async def test_unconfirmed_remote_response_is_unknown(status, payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json=payload)
    )) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        with pytest.raises(ResourceExecutionError) as caught:
            await adapter.run(_context())
        assert caught.value.outcome_unknown is True


@pytest.mark.asyncio
@pytest.mark.parametrize("exception,unknown", [
    (httpx.ConnectError, False), (httpx.ConnectTimeout, False),
    (httpx.PoolTimeout, False), (httpx.ReadTimeout, True),
    (httpx.WriteTimeout, True), (httpx.WriteError, True),
    (httpx.RemoteProtocolError, True),
])
async def test_transport_failure_preserves_execution_uncertainty(exception, unknown):
    calls = []
    async def handler(request):
        calls.append(request)
        raise exception("transport failed", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        with pytest.raises(ResourceExecutionError) as caught:
            await adapter.run(_context())
        assert caught.value.outcome_unknown is unknown
        assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 415, 422])
async def test_explicit_request_rejection_is_not_unknown(status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": "request rejected"})
    )) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        with pytest.raises(ResourceExecutionError) as caught:
            await adapter.run(_context())
        assert caught.value.outcome_unknown is False


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_connect", [True, False])
async def test_write_timeout_uses_actual_httpcore_transmission_stage(fail_connect):
    import httpcore
    writes = []
    class Stream:
        async def write(self, buffer, timeout=None):
            writes.append(buffer)
            raise httpcore.WriteTimeout("partial header write")
        async def aclose(self):
            pass
        def get_extra_info(self, name):
            return None
    class Backend:
        async def connect_tcp(self, *args, **kwargs):
            if fail_connect:
                raise httpcore.WriteTimeout("connect failed before HTTP bytes")
            return Stream()
    transport = httpx.AsyncHTTPTransport(retries=0)
    transport._pool._network_backend = Backend()
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        with pytest.raises(ResourceExecutionError) as caught:
            await adapter.run(_context())
        assert caught.value.outcome_unknown is (not fail_connect)
        assert bool(writes) is (not fail_connect)


@pytest.mark.asyncio
async def test_connect_retry_does_not_hide_later_sent_request_uncertainty():
    import httpcore
    connects = []
    class Stream:
        async def write(self, buffer, timeout=None):
            pass
        async def read(self, max_bytes, timeout=None):
            raise httpcore.ReadTimeout("response lost after successful send")
        async def aclose(self):
            pass
        def get_extra_info(self, name):
            return None
    class Backend:
        async def connect_tcp(self, *args, **kwargs):
            connects.append(True)
            if len(connects) == 1:
                raise httpcore.ConnectError("first connection unavailable")
            return Stream()
        async def sleep(self, seconds):
            pass
    transport = httpx.AsyncHTTPTransport(retries=1)
    transport._pool._network_backend = Backend()
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        with pytest.raises(ResourceExecutionError) as caught:
            await adapter.run(_context())
        assert len(connects) == 2
        assert caught.value.outcome_unknown is True


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"state": "RUNNING", "output": {}},
    {"success": False, "output": {}},
    {"status": "RUNNING", "output": {}},
    {"state": "COMPLETED", "output": {}},
    {"executionStatus": "COMPLETED", "output": {}},
    {"progress": 1, "output": {}},
    {"admission": "accepted", "output": {}},
    {"metadata": {"serverVersion": "1"}, "output": {}},
    {"status": "COMPLETED", "state": "RUNNING", "success": False, "output": {"result": "ok"}},
    {}, [], None, "done",
    {"summary": "done"}, {"output": None}, {"output": []},
    {"output": {}, "summary": []},
])
async def test_terminal_response_rejects_undefined_envelopes_and_invalid_output(payload):
    calls = []
    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        with pytest.raises(ResourceExecutionError) as caught:
            await adapter.run(_context())
        assert caught.value.outcome_unknown is True
        assert caught.value.__cause__ is not None
        assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("names", ["aliases", "python", "mixed"])
async def test_terminal_response_preserves_all_defined_fields_and_names(names):
    expected = AgentOutput(
        output={"result": "ok", "state": "RUNNING", "success": False,
                "status": "business-status", "progress": 0, "admission": "business-data"},
        summary="execution completed", risk_level="normal", sources=[{"state": "source-state"}],
        tool_executions=[{"tool": "search", "success": True}], evidence_refs=["evidence-1"],
        model_invocations=[{"model": "test", "status": "completed"}],
        runtime_events=[{"eventType": "output", "progress": 1}],
    )
    payload = expected.model_dump(by_alias=names != "python", mode="json")
    if names == "mixed":
        payload["risk_level"] = payload.pop("riskLevel")
        payload["runtime_events"] = payload.pop("runtimeEvents")
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        assert await adapter.run(_context()) == expected


@pytest.mark.asyncio
async def test_explicit_empty_output_is_a_valid_synchronous_terminal_response():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"output": {}})
    )) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        assert await adapter.run(_context()) == AgentOutput(output={})


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,unknown", [
    ({"state": "RUNNING", "output": {}}, True),
    ({"success": False, "output": {}}, True),
    ({"status": "RUNNING", "output": {}}, True),
    ({"state": "COMPLETED", "output": {}}, True),
    ({"output": {}}, False),
    ({"output": {"state": "RUNNING"}, "summary": "execution completed"}, False),
])
async def test_cancel_settlement_uses_the_same_terminal_response_contract(payload, unknown):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def handler(request):
        calls.append(request)
        started.set()
        await release.wait()
        return httpx.Response(200, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = HttpResourceExecutionAdapter(resource_id="edge-01", address="http://edge",
            credential_provider=_Credentials(), client=client)
        task = asyncio.create_task(adapter.run(_context()))
        try:
            await asyncio.wait_for(started.wait(), 1)
            task.cancel("operator_cancel")
            assert not task.done()
            release.set()
            if unknown:
                with pytest.raises(ResourceExecutionError) as caught:
                    await task
                assert caught.value.outcome_unknown is True
                assert isinstance(caught.value.__cause__, TypeError)
            else:
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert len(calls) == 1
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

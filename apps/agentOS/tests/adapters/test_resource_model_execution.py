"""资源绑定模型端点的实际推理调用合同。"""

from __future__ import annotations

import asyncio
import json

import httpx

from adapters.resource_model_execution import ResourceModelProviderAdapter, normalize_model_endpoint
from contracts.capability import ModelInvocationRequest
from contracts.resource import ModelEndpointProfile, ResourceEndpoint, RuntimeKind, RuntimeProfile
from contracts.resource_signing import build_resource_signature


class _Credentials:
    def __init__(self) -> None:
        self.observations: list[tuple[str, bool, float]] = []

    def current_signing_credential(self, resource_id: str) -> tuple[str, str]:
        assert resource_id == "runtime:edge:model"
        return "credential-1", "secret-1"

    def observe_execution(self, runtime_id: str, *, success: bool, latency_ms: float) -> None:
        self.observations.append((runtime_id, success, latency_ms))


def _runtime() -> RuntimeProfile:
    return RuntimeProfile(
        runtimeId="runtime:edge:model",
        kind=RuntimeKind.MODEL_SERVER,
        nodeId="node:edge:model",
        capabilities=["model.generate"],
        provider="Acme",
        adapter="agentos_model_http",
        endpoint=ResourceEndpoint(protocol="https", address="https://edge.example.test"),
        modelIds=["chat-v1"],
    )


def _endpoint() -> ModelEndpointProfile:
    return ModelEndpointProfile(
        endpointId="model:runtime:edge:model:chat-v1",
        runtimeId="runtime:edge:model",
        provider="Acme",
        adapter="agentos_model_http",
        model="chat-v1",
    )


def test_normalize_model_endpoint_accepts_an_openai_compatible_v1_base_url():
    assert normalize_model_endpoint("https://edge.example.test/v1") == "https://edge.example.test"
    assert normalize_model_endpoint("https://edge.example.test/v1/chat/completions") == "https://edge.example.test"


def test_model_observation_failure_is_audited_without_sensitive_error():
    from components.resource.application.resource_plane import ResourcePlane
    from time import monotonic
    class Observer:
        def observe_execution(self, *args, **kwargs):
            raise OSError("secret-business-body")
    plane = ResourcePlane()
    client = httpx.AsyncClient()
    adapter = ResourceModelProviderAdapter(endpoint=_endpoint(), runtime=_runtime(), credential_provider=_Credentials(), execution_observer=Observer(), audit_reporter=plane, client=client)
    adapter._observe_execution(success=True, started=monotonic())
    events = plane.audit_events()
    assert events[0].kind == "execution_observation_write_failed"
    assert events[0].metadata == {"reason": "OSError"}
    assert "secret-business-body" not in repr(events)
    assert plane.audit_counts() == {"execution_observation_write_failed": 1}
    asyncio.run(client.aclose())


def test_resource_model_adapter_calls_the_bound_runtime_with_signed_openai_request():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"answer":"edge"}'}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 2},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    credentials = _Credentials()
    adapter = ResourceModelProviderAdapter(
        endpoint=_endpoint(), runtime=_runtime(), credential_provider=credentials,
        execution_observer=credentials, client=client
    )
    result = asyncio.run(adapter.invoke(ModelInvocationRequest(
        requestId="commit-1", model="chat-v1", messages=[{"role": "user", "content": "hello"}],
        responseSchema={"type": "object"}, commitId="commit-1",
    )))

    request = seen["request"]
    assert isinstance(request, httpx.Request)
    assert request.url == httpx.URL("https://edge.example.test/v1/chat/completions")
    payload = json.loads(request.content)
    assert payload["model"] == "chat-v1"
    assert payload["response_format"]["type"] == "json_schema"
    assert result.content == {"answer": "edge"}
    expected = build_resource_signature(
        "secret-1", method="POST", path="/v1/chat/completions",
        timestamp=int(request.headers["x-resource-timestamp"]),
        nonce=request.headers["x-resource-nonce"], body=request.content,
    )
    assert request.headers["x-resource-credential"] == "credential-1"
    assert request.headers["x-resource-signature"] == expected
    assert len(credentials.observations) == 1
    runtime_id, success, latency_ms = credentials.observations[0]
    assert runtime_id == "runtime:edge:model" and success is True and latency_ms >= 0
    asyncio.run(client.aclose())


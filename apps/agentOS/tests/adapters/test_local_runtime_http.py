from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest

from adapters.local_runtime_http import (
    HttpLocalRuntimeTransport,
    LocalRuntimeTransportError,
)
from components.resource.auth import build_resource_signature
from contracts.local_runtime import (
    LocalRuntimeAuthorizationRef,
    LocalRuntimeCapability,
    LocalRuntimeExecutionLimits,
    LocalRuntimeExecutionRequest,
)


class CredentialProvider:
    def current_signing_credential(self, resource_id: str) -> tuple[str, str]:
        assert resource_id == "zhiyi-local-runtime"
        return "credential-1", "secret-1"


def _request() -> LocalRuntimeExecutionRequest:
    return LocalRuntimeExecutionRequest(
        protocolVersion="1",
        requestId="request-1",
        invocationId="invocation-1",
        resourceId="zhiyi-local-runtime",
        capabilityId=LocalRuntimeCapability.FS_READ,
        authorization=LocalRuntimeAuthorizationRef(grantId="grant-1", workspaceId="workspace-1"),
        input={"path": "README.md"},
        limits=LocalRuntimeExecutionLimits(timeoutSeconds=5, maxStdoutBytes=1024, maxStderrBytes=1024),
        idempotencyKey="idempotency-1",
    )


def _result(request: LocalRuntimeExecutionRequest, *, request_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "requestId": request_id or request.request_id,
        "invocationId": request.invocation_id,
        "status": "completed",
        "output": {"content": "ok"},
        "startedAt": now,
        "completedAt": now,
    }


@pytest.mark.asyncio
async def test_http_transport_signs_request_and_validates_correlation():
    request = _request()
    captured: dict[str, object] = {}

    async def handler(incoming: httpx.Request) -> httpx.Response:
        captured["path"] = incoming.url.path
        captured["body"] = incoming.content
        captured["headers"] = dict(incoming.headers)
        headers = incoming.headers
        expected = build_resource_signature(
            "secret-1",
            method="POST",
            path=incoming.url.path,
            timestamp=int(headers["x-resource-timestamp"]),
            nonce=headers["x-resource-nonce"],
            body=incoming.content,
        )
        assert headers["x-resource-signature"] == expected
        assert headers["idempotency-key"] == request.idempotency_key
        return httpx.Response(200, json=_result(request), request=incoming)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://runtime.test",
    )
    transport = HttpLocalRuntimeTransport(
        resource_id="zhiyi-local-runtime",
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )
    try:
        result = await transport.execute(request)
    finally:
        await client.aclose()
    assert result.request_id == request.request_id
    assert result.invocation_id == request.invocation_id
    assert captured["path"] == "/v1/executions"


@pytest.mark.asyncio
async def test_http_transport_distinguishes_auth_failure_and_unavailable():
    request = _request()

    async def unauthorized(incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": "AUTHENTICATION_FAILED", "message": "authentication failed"}},
            request=incoming,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(unauthorized), base_url="http://runtime.test")
    transport = HttpLocalRuntimeTransport(
        resource_id=request.resource_id,
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )
    with pytest.raises(LocalRuntimeTransportError) as unauthorized_error:
        await transport.execute(request)
    assert unauthorized_error.value.code == "AUTHENTICATION_FAILED"

    async def unavailable(incoming: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=incoming)

    unavailable_client = httpx.AsyncClient(
        transport=httpx.MockTransport(unavailable), base_url="http://runtime.test"
    )
    unavailable_transport = HttpLocalRuntimeTransport(
        resource_id=request.resource_id,
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=unavailable_client,
    )
    with pytest.raises(LocalRuntimeTransportError) as unavailable_error:
        await unavailable_transport.execute(request)
    assert unavailable_error.value.code == "TRANSPORT_UNAVAILABLE"
    assert unavailable_error.value.retryable is True
    await client.aclose()
    await unavailable_client.aclose()


@pytest.mark.asyncio
async def test_http_transport_rejects_malformed_response_and_correlation_mismatch():
    request = _request()

    async def malformed(incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", request=incoming)

    client = httpx.AsyncClient(transport=httpx.MockTransport(malformed), base_url="http://runtime.test")
    transport = HttpLocalRuntimeTransport(
        resource_id=request.resource_id,
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )
    with pytest.raises(LocalRuntimeTransportError) as malformed_error:
        await transport.execute(request)
    assert malformed_error.value.code == "TRANSPORT_RESPONSE_INVALID"
    await client.aclose()

    async def mismatch(incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_result(request, request_id="other"), request=incoming)

    mismatch_client = httpx.AsyncClient(
        transport=httpx.MockTransport(mismatch), base_url="http://runtime.test"
    )
    mismatch_transport = HttpLocalRuntimeTransport(
        resource_id=request.resource_id,
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=mismatch_client,
    )
    with pytest.raises(LocalRuntimeTransportError) as mismatch_error:
        await mismatch_transport.execute(request)
    assert mismatch_error.value.code == "TRANSPORT_CORRELATION_MISMATCH"
    await mismatch_client.aclose()


@pytest.mark.asyncio
async def test_health_probe_is_separate_from_signed_execution():
    async def handler(incoming: httpx.Request) -> httpx.Response:
        assert incoming.method == "GET"
        assert incoming.url.path == "/health"
        return httpx.Response(
            200,
            json={"resourceId": "zhiyi-local-runtime", "protocolVersion": "1", "status": "online"},
            request=incoming,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime.test")
    transport = HttpLocalRuntimeTransport(
        resource_id="zhiyi-local-runtime",
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )
    assert (await transport.health())["status"] == "online"
    await client.aclose()


@pytest.mark.asyncio
async def test_workspace_root_uses_signed_grant_reference_and_checks_response_identity():
    authorization = LocalRuntimeAuthorizationRef(grantId="grant-1", workspaceId="workspace-1")
    captured: list[str] = []

    async def handler(incoming: httpx.Request) -> httpx.Response:
        raw_path = incoming.url.raw_path.decode("ascii")
        captured.append(raw_path)
        headers = incoming.headers
        expected = build_resource_signature(
            "secret-1",
            method="GET",
            path=raw_path,
            timestamp=int(headers["x-resource-timestamp"]),
            nonce=headers["x-resource-nonce"],
            body=b"",
        )
        assert headers["x-resource-signature"] == expected
        return httpx.Response(
            200,
            json={"workspaceId": "workspace-1", "workspaceRoot": "C:/work/project"},
            request=incoming,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime.test")
    transport = HttpLocalRuntimeTransport(
        resource_id="zhiyi-local-runtime",
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )
    try:
        assert await transport.workspace_root(authorization) == "C:/work/project"
    finally:
        await client.aclose()
    assert captured == ["/v1/workspace?grantId=grant-1&workspaceId=workspace-1"]


@pytest.mark.asyncio
async def test_http_transport_authenticates_events_and_cancel_on_same_runtime_boundary():
    execution_id = "execution-1"
    request_id = "request-1"
    invocation_id = "invocation-1"
    captured: list[tuple[str, str]] = []

    async def handler(incoming: httpx.Request) -> httpx.Response:
        path = incoming.url.raw_path.decode("ascii")
        captured.append((incoming.method, path))
        headers = incoming.headers
        expected = build_resource_signature(
            "secret-1",
            method=incoming.method,
            path=path,
            timestamp=int(headers["x-resource-timestamp"]),
            nonce=headers["x-resource-nonce"],
            body=incoming.content,
        )
        assert headers["x-resource-signature"] == expected
        if incoming.method == "GET":
            return httpx.Response(
                200,
                json={
                    "executionId": execution_id,
                    "events": [{
                        "protocolVersion": "1",
                        "requestId": request_id,
                        "invocationId": invocation_id,
                        "executionId": execution_id,
                        "eventType": "started",
                        "sequence": 0,
                        "data": {},
                    }],
                    "terminal": False,
                    "state": "running",
                },
                request=incoming,
            )
        assert incoming.url.path == f"/v1/executions/{execution_id}/cancel"
        return httpx.Response(
            200,
            json={
                "protocolVersion": "1",
                "executionId": execution_id,
                "requestId": request_id,
                "invocationId": invocation_id,
                "state": "cancelling",
            },
            request=incoming,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://runtime.test")
    transport = HttpLocalRuntimeTransport(
        resource_id="zhiyi-local-runtime",
        address="http://runtime.test/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )
    events, terminal, state = await transport.events(
        execution_id=execution_id,
        after_sequence=-1,
        wait_seconds=0.1,
        request_id=request_id,
        invocation_id=invocation_id,
    )
    cancel_state = await transport.cancel(
        execution_id=execution_id,
        request_id=request_id,
        invocation_id=invocation_id,
    )
    await client.aclose()

    assert events[0].execution_id == execution_id
    assert terminal is False
    assert state == "running"
    assert cancel_state == "cancelling"
    assert captured[0][0] == "GET"
    assert captured[0][1].startswith(f"/v1/executions/{execution_id}/events?")
    assert captured[1] == ("POST", f"/v1/executions/{execution_id}/cancel")


def test_default_client_ignores_environment_proxy(monkeypatch: pytest.MonkeyPatch):
    """设备侧 Runtime 端点不得被 HTTP_PROXY 接管。

    走环境代理时请求行会变成绝对 URI：代理把 "POST /v1/executions" 转发为
    "POST http://host/v1/executions"，对端按原始 req.url 验签就会 401；凭据
    也会被送往代理。因此默认客户端必须 trust_env=False（显式传入的 client
    仍然是调用方的责任）。
    """
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")

    transport = HttpLocalRuntimeTransport(
        resource_id="zhiyi-local-runtime",
        address="http://127.0.0.1:18765/v1/executions",
        credential_provider=CredentialProvider(),
    )

    assert transport._client.trust_env is False


def test_explicit_client_is_used_as_given():
    client = httpx.AsyncClient(trust_env=True)
    transport = HttpLocalRuntimeTransport(
        resource_id="zhiyi-local-runtime",
        address="http://127.0.0.1:18765/v1/executions",
        credential_provider=CredentialProvider(),
        client=client,
    )

    assert transport._client is client

from __future__ import annotations

import json
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
from contracts.resource import ResourceEndpoint, ResourceProfile, ResourceType, DeploymentTier
from components.resource.auth import build_resource_signature
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
    profile = ResourceProfile(
        resourceId="edge-01",
        resourceType=ResourceType.WORKER,
        deploymentTier=DeploymentTier.EDGE,
        capabilities=["analysis"],
        executionEndpoint=ResourceEndpoint(protocol="https", address="https://edge.example.test/execute"),
    )
    adapter = build_resource_execution_adapter(
        profile,
        credential_provider=_Credentials(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )
    assert isinstance(adapter, HttpResourceExecutionAdapter)
    assert adapter.address == "https://edge.example.test/execute"

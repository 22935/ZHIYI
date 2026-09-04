"""Execution adapters for local and remote AgentOS resources."""

from __future__ import annotations

import json
from time import time
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
import secrets

import httpx

from components.resource.auth import build_resource_signature
from contracts.resource import ResourceProfile
from service.agents.base import AgentOutput, AgentRunContext, BaseAgent


class ResourceExecutionError(RuntimeError):
    """A bound resource could not execute a step safely."""


class ResourceExecutionAdapter(Protocol):
    async def run(self, context: AgentRunContext) -> AgentOutput:
        """Execute one already-bound step using the target resource."""


class ResourceCredentialProvider(Protocol):
    """Read the current resource credential at the moment of an execution."""

    def current_signing_credential(self, resource_id: str) -> tuple[str, str]:
        """Return ``(credential_id, secret)`` without caching a previous rotation."""


class LocalResourceExecutionAdapter:
    """Keep existing in-process Agent execution behind the resource seam."""

    def __init__(self, agent: BaseAgent) -> None:
        self.agent = agent

    async def run(self, context: AgentRunContext) -> AgentOutput:
        return await self.agent.run(context)


class ResourceAgentProxy(BaseAgent):
    """Expose a remote resource as a profile-bearing target for the node runner."""

    def __init__(self, *, profile, adapter: ResourceExecutionAdapter) -> None:
        super().__init__(profile)
        self.adapter = adapter

    async def run(self, context: AgentRunContext) -> AgentOutput:
        return await self.adapter.run(context)


class HttpResourceExecutionAdapter:
    """Call a terminal, edge or cloud execution endpoint with a safe context subset."""

    def __init__(
        self,
        *,
        resource_id: str,
        address: str,
        credential_provider: ResourceCredentialProvider,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not resource_id.strip():
            raise ValueError("remote execution resource_id is required")
        if not address.strip():
            raise ValueError("remote execution address is required")
        if timeout_seconds <= 0:
            raise ValueError("remote execution timeout must be positive")
        if credential_provider is None:
            raise ValueError("remote execution credential provider is required")
        self.resource_id = resource_id
        self.address = normalize_execution_endpoint(address)
        self.credential_provider = credential_provider
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def run(self, context: AgentRunContext) -> AgentOutput:
        payload = build_remote_execution_payload(context)
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        credential_id, secret = self.credential_provider.current_signing_credential(
            self.resource_id
        )
        timestamp = int(time())
        nonce = secrets.token_urlsafe(24)
        path = urlsplit(self.address).path or "/"
        headers = {
            "Idempotency-Key": str(context.commit_id or payload["attemptId"]),
            "X-AgentOS-Run-Id": str(payload["runId"]),
            "X-AgentOS-Step-Id": str(payload["stepId"]),
            "Content-Type": "application/json",
            "X-Resource-Credential": credential_id,
            "X-Resource-Timestamp": str(timestamp),
            "X-Resource-Nonce": nonce,
            "X-Resource-Signature": build_resource_signature(
                secret,
                method="POST",
                path=path,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            ),
        }
        try:
            response = await self._client.post(
                self.address,
                content=body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: timeout") from exc
        except httpx.HTTPError as exc:
            raise ResourceExecutionError(f"REMOTE_EXECUTION_FAILED: {exc}") from exc
        if response.is_error:
            detail = response.text[:500]
            raise ResourceExecutionError(
                f"REMOTE_EXECUTION_FAILED: HTTP {response.status_code}: {detail}"
            )
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("response JSON must be an object")
            return AgentOutput.model_validate(body)
        except Exception as exc:
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: invalid AgentOutput") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def normalize_execution_endpoint(address: str) -> str:
    """Normalize a resource endpoint to exactly one ``/execute`` suffix."""
    value = address.strip()
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("remote execution address must be an absolute URL")
    path = parsed.path.rstrip("/")
    if not path.endswith("/execute"):
        path = f"{path}/execute" if path else "/execute"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def build_resource_execution_adapter(
    profile: ResourceProfile,
    *,
    credential_provider: ResourceCredentialProvider,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 120.0,
) -> ResourceExecutionAdapter:
    """Construct the only supported remote execution adapter from a profile."""
    endpoint = profile.execution_endpoint
    if endpoint is None:
        raise ResourceExecutionError(
            f"REMOTE_EXECUTION_CONFIG_INVALID: {profile.resource_id} has no endpoint"
        )
    if endpoint.protocol not in {"http", "https"}:
        raise ResourceExecutionError(
            f"REMOTE_EXECUTION_CONFIG_INVALID: unsupported protocol {endpoint.protocol}"
        )
    parsed = urlsplit(endpoint.address)
    if parsed.scheme != endpoint.protocol:
        raise ResourceExecutionError(
            f"REMOTE_EXECUTION_CONFIG_INVALID: endpoint scheme does not match protocol for {profile.resource_id}"
        )
    return HttpResourceExecutionAdapter(
        resource_id=profile.resource_id,
        address=endpoint.address,
        credential_provider=credential_provider,
        client=client,
        timeout_seconds=timeout_seconds,
    )


def build_remote_execution_payload(context: AgentRunContext) -> dict[str, Any]:
    """Serialize only the step contract, never the full Runtime or Agent context."""
    pack = context.context_pack
    return {
        "runId": context.run.run_id,
        "missionId": context.task.mission_id,
        "stepId": context.step.step_id,
        "attemptId": str(getattr(pack, "attempt_id", "") or context.commit_id or ""),
        "commitId": str(context.commit_id or ""),
        "agentName": context.step.agent_name,
        "capability": context.step.capability,
        "goal": context.step.goal,
        "input": dict(getattr(pack, "data", {}) or {}),
        "evidenceRefs": list(getattr(pack, "evidence_refs", []) or []),
    }


__all__ = [
    "HttpResourceExecutionAdapter",
    "LocalResourceExecutionAdapter",
    "ResourceAgentProxy",
    "ResourceExecutionAdapter",
    "ResourceExecutionError",
    "ResourceCredentialProvider",
    "build_resource_execution_adapter",
    "build_remote_execution_payload",
    "normalize_execution_endpoint",
]

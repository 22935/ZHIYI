"""Execution adapters for local and remote AgentOS resources."""

from __future__ import annotations

import json
import asyncio
from support.async_tasks import await_owned, await_settled
from time import time
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
import secrets

import httpx

from components.resource.auth import build_resource_signature
from contracts.resource import ResourceEndpoint, RuntimeProfile
from service.agents.base import AgentOutput, AgentRunContext, BaseAgent


class ResourceExecutionError(RuntimeError):
    """A bound resource could not execute a step safely."""

    outcome_unknown = False

    def __init__(self, message: str, *, outcome_unknown: bool = False) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


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
        pre_send_failed = False
        send_started = False

        async def trace(event: str, info: dict[str, Any]) -> None:
            nonlocal pre_send_failed, send_started
            if event in {"http11.send_request_headers.started", "http2.send_request_headers.started"}:
                send_started = True
            if not send_started and event in {
                "connection.connect_tcp.failed", "connection.connect_unix_socket.failed", "connection.start_tls.failed",
            }:
                pre_send_failed = True

        def unknown_transport_outcome(exc: BaseException) -> bool:
            if send_started:
                return True
            return not (pre_send_failed or isinstance(exc, (
                httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.UnsupportedProtocol,
            )))

        request_task = asyncio.create_task(self._client.post(
                self.address,
                content=body,
                headers=headers,
                timeout=self.timeout_seconds,
                extensions={"trace": trace},
            ), name=f"resource-request:{context.run.run_id}:{context.step.step_id}")
        try:
            try:
                response = await await_owned(request_task)
            except asyncio.CancelledError:
                # A disconnected HTTP client is not evidence of remote stop.
                # Retain ownership until the admitted request settles.
                results = await await_settled(asyncio.gather(request_task, return_exceptions=True), propagate_cancel=False)
                result = results[0]
                settled = False
                if not isinstance(result, BaseException):
                    try:
                        self._terminal_output(result)
                        settled = True
                    except ResourceExecutionError as exc:
                        settled = not exc.outcome_unknown
                if not settled:
                    # A failed cancellation wait can still prove that nothing
                    # was sent (e.g. pool/connect failure).
                    if isinstance(result, httpx.HTTPError) and not unknown_transport_outcome(result):
                        raise
                    raise ResourceExecutionError("REMOTE_EXECUTION_OUTCOME_UNKNOWN: cancellation requires reconciliation",
                                                 outcome_unknown=True)
                raise
        except httpx.HTTPError as exc:
            # In particular WriteTimeout/WriteError may follow a partial write;
            # httpx supplies no byte-delivery proof. Idempotency-Key is only a
            # request hint, not a verified server deduplication contract.
            unknown = unknown_transport_outcome(exc)
            stage = "outcome unknown" if unknown else "request not sent"
            raise ResourceExecutionError(f"REMOTE_EXECUTION_FAILED: transport {stage}: {exc}",
                                         outcome_unknown=unknown) from exc
        except ResourceExecutionError:
            raise
        except Exception as exc:
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: unclassified transport outcome",
                                         outcome_unknown=True) from exc
        return self._terminal_output(response)

    @staticmethod
    def _terminal_output(response: httpx.Response) -> AgentOutput:
        # The existing /execute contract is synchronous HTTP 200 + AgentOutput.
        # Admission, progress, empty and malformed replies cannot prove completion.
        if response.status_code != 200:
            detail = response.text[:500]
            raise ResourceExecutionError(
                f"REMOTE_EXECUTION_FAILED: HTTP {response.status_code}: {detail}",
                # These statuses reject the request before execution admission.
                # Conflict, server/proxy errors and all other replies provide no
                # terminal receipt and must remain unknown.
                outcome_unknown=response.status_code not in {400, 401, 403, 404, 405, 413, 415, 422},
            )
        try:
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("output"), dict):
                raise TypeError("terminal AgentOutput must explicitly include output")
            if "status" in body:
                # No status envelope is defined by this synchronous protocol.
                # Do not let AgentOutput(extra='ignore') hide progress/errors.
                raise TypeError("status envelope is not a terminal AgentOutput")
            return AgentOutput.model_validate(body)
        except Exception as exc:
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: unconfirmed AgentOutput", outcome_unknown=True) from exc

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
    profile: RuntimeProfile,
    *,
    credential_provider: ResourceCredentialProvider,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 120.0,
) -> ResourceExecutionAdapter:
    """Construct the only supported remote execution adapter from a runtime profile."""
    endpoint = profile.endpoint
    if endpoint is None:
        raise ResourceExecutionError(
            f"REMOTE_EXECUTION_CONFIG_INVALID: {profile.runtime_id} has no endpoint"
        )
    if endpoint.protocol not in {"http", "https"}:
        raise ResourceExecutionError(
            f"REMOTE_EXECUTION_CONFIG_INVALID: unsupported protocol {endpoint.protocol}"
        )
    parsed = urlsplit(endpoint.address)
    if parsed.scheme != endpoint.protocol:
        raise ResourceExecutionError(
            f"REMOTE_EXECUTION_CONFIG_INVALID: endpoint scheme does not match protocol for {profile.runtime_id}"
        )
    return HttpResourceExecutionAdapter(
        resource_id=profile.runtime_id,
        address=endpoint.address,
        credential_provider=credential_provider,
        client=client,
        timeout_seconds=timeout_seconds,
    )


def build_remote_execution_payload(context: AgentRunContext) -> dict[str, Any]:
    """Serialize only the step contract, never the full Runtime or Agent context."""
    pack = context.context_pack
    basis = getattr(context, "mission_intent_basis", None)
    return {
        "runId": context.run.run_id,
        "missionId": context.task.mission_id,
        **({"missionIntentBasis": basis.model_dump(by_alias=True, mode="json")} if basis is not None else {}),
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

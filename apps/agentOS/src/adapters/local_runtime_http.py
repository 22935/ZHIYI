"""HTTP transport for the low-level Local Runtime execution contract.

This adapter is intentionally separate from the existing high-level remote
execution adapter: it carries the Local Runtime request/result contract only.
"""

from __future__ import annotations

import json
import secrets
from time import time
from typing import Any, AsyncIterator, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from contracts.local_runtime import (
    LOCAL_RUNTIME_PROTOCOL_VERSION,
    LocalRuntimeAuthorizationRef,
    LocalRuntimeExecutionCancelRequest,
    LocalRuntimeExecutionEvent,
    LocalRuntimeExecutionRequest,
    LocalRuntimeExecutionResult,
)
from contracts.resource_signing import build_resource_signature


class LocalRuntimeCredentialProvider(Protocol):
    def current_signing_credential(self, resource_id: str) -> tuple[str, str]: ...


class LocalRuntimeTransportError(RuntimeError):
    """A transport/protocol failure, distinct from a runtime domain result."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class HttpLocalRuntimeTransport:
    """Sign and send Local Runtime envelopes over the selected HTTP endpoint."""

    def __init__(
        self,
        *,
        resource_id: str,
        address: str,
        credential_provider: LocalRuntimeCredentialProvider,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not resource_id.strip():
            raise ValueError("local runtime resource_id is required")
        parsed = urlsplit(address.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("local runtime address must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("local runtime address must not contain inline credentials")
        if timeout_seconds <= 0:
            raise ValueError("local runtime timeout must be positive")
        if credential_provider is None:
            raise ValueError("local runtime credential provider is required")
        self.resource_id = resource_id.strip()
        self.address = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path or "/v1/executions", parsed.query, parsed.fragment)
        )
        self._path = urlsplit(self.address).path or "/"
        self._health_address = urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))
        self.credential_provider = credential_provider
        self.timeout_seconds = timeout_seconds
        # 本机/设备侧 Runtime 端点绝不能被环境代理接管（HTTP_PROXY/ALL_PROXY）：
        # 走代理会把回环流量外发，且代理转发时请求行变成绝对 URI，签名路径
        # 与规范化路径不一致 -> 对端 401。凭据也只应抵达该设备本身。
        self._client = client or httpx.AsyncClient(trust_env=False)
        self._owns_client = client is None

    async def execute(self, request: LocalRuntimeExecutionRequest) -> LocalRuntimeExecutionResult:
        if request.resource_id != self.resource_id:
            raise LocalRuntimeTransportError("RESOURCE_MISMATCH", "request resource does not match transport")
        body = json.dumps(
            request.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = self._signed_headers(
            method="POST",
            path=self._path,
            body=body,
            idempotency_key=request.idempotency_key,
        )
        try:
            response = await self._client.post(
                self.address,
                content=body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime request timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime is unavailable", retryable=True
            ) from exc
        payload = self._decode_response(response)
        if response.status_code < 200 or response.status_code >= 300:
            error = payload.get("error") if isinstance(payload, dict) else None
            code = str(error.get("code") or "TRANSPORT_HTTP_ERROR") if isinstance(error, dict) else "TRANSPORT_HTTP_ERROR"
            raise LocalRuntimeTransportError(
                code,
                "local runtime rejected the request",
                retryable=response.status_code >= 500,
            )
        try:
            result = LocalRuntimeExecutionResult.model_validate(payload)
        except Exception as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_RESPONSE_INVALID", "local runtime response is invalid"
            ) from exc
        if (
            result.protocol_version != LOCAL_RUNTIME_PROTOCOL_VERSION
            or result.request_id != request.request_id
            or result.invocation_id != request.invocation_id
        ):
            raise LocalRuntimeTransportError(
                "TRANSPORT_CORRELATION_MISMATCH", "local runtime response correlation mismatch"
            )
        return result

    async def events(
        self,
        *,
        execution_id: str,
        after_sequence: int = -1,
        wait_seconds: float = 0.0,
        request_id: str | None = None,
        invocation_id: str | None = None,
    ) -> tuple[list[LocalRuntimeExecutionEvent], bool, str]:
        if not execution_id.strip():
            raise ValueError("execution_id is required")
        if after_sequence < -1:
            raise ValueError("after_sequence must not be below -1")
        path = f"{self._path}/{quote(execution_id, safe='')}/events"
        query = f"afterSequence={after_sequence}&waitSeconds={max(0.0, min(wait_seconds, 5.0)):.3f}"
        signed_path = f"{path}?{query}"
        address = self._address_for_path(signed_path)
        try:
            response = await self._client.get(
                address,
                headers=self._signed_headers(method="GET", path=signed_path, body=b""),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime event polling timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime is unavailable", retryable=True
            ) from exc
        payload = self._decode_response(response)
        if response.status_code < 200 or response.status_code >= 300:
            self._raise_http_error(payload, response.status_code)
        try:
            events = [LocalRuntimeExecutionEvent.model_validate(item) for item in payload.get("events", [])]
            terminal = bool(payload["terminal"])
            state = str(payload["state"])
            if str(payload["executionId"]) != execution_id:
                raise ValueError("execution correlation mismatch")
            for event in events:
                if event.execution_id != execution_id:
                    raise ValueError("event execution correlation mismatch")
                if request_id is not None and event.request_id != request_id:
                    raise ValueError("event request correlation mismatch")
                if invocation_id is not None and event.invocation_id != invocation_id:
                    raise ValueError("event invocation correlation mismatch")
        except Exception as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_RESPONSE_INVALID", "local runtime event response is invalid"
            ) from exc
        return events, terminal, state

    async def stream_events(
        self,
        *,
        execution_id: str,
        request_id: str,
        invocation_id: str,
        poll_seconds: float = 0.05,
    ) -> AsyncIterator[LocalRuntimeExecutionEvent]:
        cursor = -1
        while True:
            events, terminal, _state = await self.events(
                execution_id=execution_id,
                after_sequence=cursor,
                wait_seconds=max(poll_seconds, 0.05),
                request_id=request_id,
                invocation_id=invocation_id,
            )
            for event in events:
                cursor = max(cursor, event.sequence)
                yield event
            if terminal:
                return

    async def cancel(
        self,
        *,
        execution_id: str,
        request_id: str,
        invocation_id: str,
    ) -> str:
        cancellation = LocalRuntimeExecutionCancelRequest(
            requestId=request_id,
            invocationId=invocation_id,
            resourceId=self.resource_id,
            executionId=execution_id,
        )
        body = json.dumps(
            cancellation.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        path = f"{self._path}/{quote(execution_id, safe='')}/cancel"
        try:
            response = await self._client.post(
                self._address_for_path(path),
                content=body,
                headers=self._signed_headers(method="POST", path=path, body=body),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime cancellation timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime is unavailable", retryable=True
            ) from exc
        payload = self._decode_response(response)
        if response.status_code < 200 or response.status_code >= 300:
            self._raise_http_error(payload, response.status_code)
        if (
            payload.get("executionId") != execution_id
            or payload.get("requestId") != request_id
            or payload.get("invocationId") != invocation_id
        ):
            raise LocalRuntimeTransportError(
                "TRANSPORT_CORRELATION_MISMATCH", "local runtime cancellation correlation mismatch"
            )
        return str(payload.get("state") or "")

    async def health(self) -> dict[str, Any]:
        """Probe the non-sensitive health endpoint for ResourcePlane projection."""
        try:
            response = await self._client.get(self._health_address, timeout=self.timeout_seconds)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime health is unavailable", retryable=True
            ) from exc
        payload = self._decode_response(response)
        if response.status_code < 200 or response.status_code >= 300:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime health is unavailable", retryable=True
            )
        if not isinstance(payload, dict):
            raise LocalRuntimeTransportError(
                "TRANSPORT_RESPONSE_INVALID", "local runtime health response is invalid"
            )
        return payload

    async def workspace_root(self, authorization: LocalRuntimeAuthorizationRef) -> str:
        """Fetch the canonical root over the signed, grant-checked runtime boundary."""
        path = (
            "/v1/workspace?"
            f"grantId={quote(authorization.grant_id, safe='')}"
            f"&workspaceId={quote(authorization.workspace_id, safe='')}"
        )
        try:
            response = await self._client.get(
                self._address_for_path(path),
                headers=self._signed_headers(method="GET", path=path, body=b""),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime request timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_UNAVAILABLE", "local runtime is unavailable", retryable=True
            ) from exc
        payload = self._decode_response(response)
        if response.status_code < 200 or response.status_code >= 300:
            self._raise_http_error(payload, response.status_code)
        workspace_root = payload.get("workspaceRoot") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("workspaceId") != authorization.workspace_id
            or not isinstance(workspace_root, str)
            or not workspace_root.strip()
        ):
            raise LocalRuntimeTransportError(
                "TRANSPORT_RESPONSE_INVALID", "local runtime workspace response is invalid"
            )
        return workspace_root

    def _signed_headers(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        try:
            credential_id, secret = self.credential_provider.current_signing_credential(self.resource_id)
        except Exception as exc:
            raise LocalRuntimeTransportError(
                "AUTHENTICATION_FAILED", "local runtime credential is unavailable"
            ) from exc
        if not str(credential_id).strip() or not str(secret).strip():
            raise LocalRuntimeTransportError(
                "AUTHENTICATION_FAILED", "local runtime credential is unavailable"
            )
        timestamp = int(time())
        nonce = secrets.token_urlsafe(24)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Resource-Credential": credential_id,
            "X-Resource-Timestamp": str(timestamp),
            "X-Resource-Nonce": nonce,
            "X-Resource-Signature": build_resource_signature(
                secret,
                method=method,
                path=path,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            ),
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _address_for_path(self, path: str) -> str:
        parsed = urlsplit(self.address)
        return urlunsplit((parsed.scheme, parsed.netloc, path.split("?", 1)[0], path.split("?", 1)[1] if "?" in path else "", ""))

    @staticmethod
    def _raise_http_error(payload: Any, status_code: int) -> None:
        error = payload.get("error") if isinstance(payload, dict) else None
        code = str(error.get("code") or "TRANSPORT_HTTP_ERROR") if isinstance(error, dict) else "TRANSPORT_HTTP_ERROR"
        raise LocalRuntimeTransportError(
            code,
            "local runtime rejected the request",
            retryable=status_code >= 500,
        )

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LocalRuntimeTransportError(
                "TRANSPORT_RESPONSE_INVALID", "local runtime response is not valid JSON"
            ) from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = [
    "HttpLocalRuntimeTransport",
    "LocalRuntimeCredentialProvider",
    "LocalRuntimeTransportError",
]

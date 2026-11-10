"""将冻结的资源模型端点映射为实际的 AgentOS 模型调用。"""

from __future__ import annotations

import json
import logging
import secrets
from time import monotonic, time
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from adapters.model_compatibility import ModelCompatibilityRegistry
from adapters.model_runtime import RegisteredModelRuntime
from adapters.openai_runtime import ModelInvocationError, OpenAICompatibleRuntime
from contracts.capability import (
    CapabilityKind,
    CapabilityManifest,
    ModelCapabilityEnvelope,
    ModelCapabilitySource,
    ModelInvocationRequest,
)
from contracts.resource import ModelEndpointProfile, RuntimeProfile
from contracts.resource.resource_signing import build_resource_signature


_MODEL_ADAPTER = "agentos_model_http"
_OPENAI_COMPATIBLE_PATH = "/chat/completions"
_MODEL_PATH = "/v1/chat/completions"


class ResourceModelCredentialProvider:
    """资源模型 transport 所需的最小凭据读取端口。"""

    def current_signing_credential(self, resource_id: str) -> tuple[str, str]:
        raise NotImplementedError


class ResourceModelExecutionObserver(Protocol):
    """模型调用完成后接收无敏感内容运行观测的端口。"""

    def observe_execution(self, runtime_id: str, *, success: bool, latency_ms: float) -> object:
        """记录 Runtime 的成功状态与调用时延。"""


class ResourceModelAuditReporter(Protocol):
    def record_audit_event(self, kind: str, resource_id: str, **metadata: str) -> None: ...


def normalize_model_endpoint(address: str) -> str:
    """归一化模型服务基地址，禁止请求参数改变协议或主机。"""
    parsed = urlsplit(address.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("resource model endpoint must be an absolute HTTP(S) URL")
    path = parsed.path.rstrip("/")
    if path.endswith("/execute"):
        path = path[: -len("/execute")]
    if path.endswith(_MODEL_PATH):
        path = path[: -len(_MODEL_PATH)]
    # OpenAI Compatible 服务常被登记为 /v1 基地址；transport 会统一补全模型路径。
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


class _SignedResourceModelTransport:
    """只向已绑定 Runtime 的固定模型路径发送 HMAC 签名 JSON 请求。"""

    def __init__(
        self,
        *,
        runtime_id: str,
        address: str,
        credential_provider: ResourceModelCredentialProvider,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("resource model timeout must be positive")
        self.runtime_id = runtime_id
        self.address = normalize_model_endpoint(address)
        self.credential_provider = credential_provider
        self.client = client or httpx.AsyncClient()
        self.timeout_seconds = timeout_seconds

    async def post_json(
        self, *, path: str, payload: dict[str, Any], idempotency_key: str | None = None
    ) -> dict[str, Any]:
        if path != _OPENAI_COMPATIBLE_PATH:
            raise ModelInvocationError("MODEL_PATH_INVALID", "resource model path is not supported")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        credential_id, secret = self.credential_provider.current_signing_credential(self.runtime_id)
        timestamp = int(time())
        nonce = secrets.token_urlsafe(24)
        headers = {
            "Content-Type": "application/json",
            "X-Resource-Credential": credential_id,
            "X-Resource-Timestamp": str(timestamp),
            "X-Resource-Nonce": nonce,
            "X-Resource-Signature": build_resource_signature(
                secret, method="POST", path=_MODEL_PATH, timestamp=timestamp, nonce=nonce, body=body
            ),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = await self.client.post(
                f"{self.address}{_MODEL_PATH}", content=body, headers=headers, timeout=self.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise ModelInvocationError("MODEL_TIMEOUT", "resource model request timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelInvocationError("MODEL_TEMPORARY_UNAVAILABLE", "resource model request failed") from exc
        if response.status_code == 429:
            raise ModelInvocationError("MODEL_RATE_LIMITED", "resource model rejected the request")
        if response.status_code >= 500:
            raise ModelInvocationError("MODEL_TEMPORARY_UNAVAILABLE", "resource model is unavailable")
        if response.status_code < 200 or response.status_code >= 300:
            raise ModelInvocationError("MODEL_PROVIDER_FAILED", "resource model rejected the request")
        try:
            result = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelInvocationError("MODEL_RESPONSE_INVALID", "resource model response is not JSON") from exc
        if not isinstance(result, dict):
            raise ModelInvocationError("MODEL_RESPONSE_INVALID", "resource model response is not an object")
        return result


class ResourceModelProviderAdapter:
    """一个 Runtime 承载的 ``agentos_model_http`` 模型端点适配器。"""

    def __init__(
        self,
        *,
        endpoint: ModelEndpointProfile,
        runtime: RuntimeProfile,
        credential_provider: ResourceModelCredentialProvider,
        execution_observer: ResourceModelExecutionObserver | None = None,
        audit_reporter: ResourceModelAuditReporter | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if endpoint.runtime_id != runtime.runtime_id:
            raise ValueError("resource model endpoint must belong to its runtime")
        if runtime.endpoint is None or runtime.endpoint.protocol not in {"http", "https"}:
            raise ValueError("resource model runtime requires an HTTP(S) endpoint")
        if endpoint.adapter != _MODEL_ADAPTER or runtime.adapter != _MODEL_ADAPTER:
            raise ValueError("resource model endpoint requires the agentos_model_http adapter")
        self.endpoint = endpoint
        self.runtime = runtime
        self._execution_observer = execution_observer
        self._audit_reporter = audit_reporter
        self._manifest = CapabilityManifest(
            capabilityId=f"resource-model.{runtime.runtime_id}.{endpoint.endpoint_id}",
            kind=CapabilityKind.MODEL,
            displayName=endpoint.endpoint_id,
            provider=endpoint.provider,
            capabilities=[endpoint.model],
            version="1.0.0",
        )
        self._delegate = OpenAICompatibleRuntime(
            manifest=self._manifest,
            transport=_SignedResourceModelTransport(
                runtime_id=runtime.runtime_id,
                address=runtime.endpoint.address,
                credential_provider=credential_provider,
                client=client,
                timeout_seconds=timeout_seconds,
            ),
        )

    @property
    def manifest(self) -> CapabilityManifest:
        return self._manifest

    def is_available(self) -> bool:
        return True

    def describe_model(self, model: str) -> ModelCapabilityEnvelope:
        if model.strip() != self.endpoint.model:
            raise ModelInvocationError("MODEL_NOT_SUPPORTED", "requested model is not declared by this resource")
        return ModelCapabilityEnvelope(
            provider=self.endpoint.provider,
            model=self.endpoint.model,
            version=self.endpoint.model_version,
            source=ModelCapabilitySource.RUNTIME_OBSERVED,
            contextWindowTokens=self.endpoint.context_window_tokens,
            maxOutputTokens=self.endpoint.max_output_tokens,
            features=self.endpoint.features,
        )

    async def invoke(self, request: ModelInvocationRequest):
        started = monotonic()
        try:
            result = await self._delegate.invoke(request)
        except BaseException:
            self._observe_execution(success=False, started=started)
            raise
        self._observe_execution(success=True, started=started)
        return result

    def _observe_execution(self, *, success: bool, started: float) -> None:
        """观测为旁路，不能因健康存储短暂故障中断模型响应。"""
        if self._execution_observer is None:
            return
        try:
            self._execution_observer.observe_execution(
                self.runtime.runtime_id,
                success=success,
                latency_ms=(monotonic() - started) * 1000,
            )
        except Exception as error:
            # 只记录异常类型，避免存储错误正文夹带提示词或响应内容。
            if self._audit_reporter is not None:
                try:
                    self._audit_reporter.record_audit_event("execution_observation_write_failed", self.runtime.runtime_id, reason=type(error).__name__)
                except Exception:
                    logging.getLogger(__name__).warning("resource model audit write failed")
            else:
                logging.getLogger(__name__).warning("resource model observation write failed", extra={"runtime_id": self.runtime.runtime_id, "reason": type(error).__name__})


def build_resource_model_runtime(
    endpoint: ModelEndpointProfile,
    runtime: RuntimeProfile,
    *,
    credential_provider: ResourceModelCredentialProvider,
    execution_observer: ResourceModelExecutionObserver | None = None,
    audit_reporter: ResourceModelAuditReporter | None = None,
) -> RegisteredModelRuntime:
    """为已经绑定的端点构造隔离的模型运行时，不改写全局模型注册表。"""
    registry = ModelCompatibilityRegistry()
    registry.register(ResourceModelProviderAdapter(
        endpoint=endpoint,
        runtime=runtime,
        credential_provider=credential_provider,
        execution_observer=execution_observer,
        audit_reporter=audit_reporter,
    ))
    return RegisteredModelRuntime(registry=registry, provider=endpoint.provider, model=endpoint.model)


__all__ = [
    "ResourceModelProviderAdapter",
    "ResourceModelExecutionObserver",
    "ResourceModelAuditReporter",
    "build_resource_model_runtime",
    "normalize_model_endpoint",
]

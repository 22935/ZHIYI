"""通过注入 JSON 传输接入 OpenAI Chat Completions 兼容端点。"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from time import monotonic
from typing import Any, AsyncIterator, Protocol

from adapters.http_transport import HttpTransportError
from contracts.capability import (
    CapabilityKind,
    CapabilityManifest,
    ModelCapabilityEnvelope,
    ModelCapabilitySource,
    ModelFeatureSet,
    ModelInvocationRequest,
    ModelInvocationResponse,
    ModelStreamEvent,
)


logger = logging.getLogger(__name__)


def _usage_diagnostics_enabled() -> bool:
    configured = os.getenv("AGENTOS_PROVIDER_USAGE_DIAGNOSTICS")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_mapping_keys(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    return sorted(str(key) for key in value.keys())[:64]


def _log_provider_usage_shape(
    *,
    provider: str,
    model: str,
    response_mode: str,
    response: object,
    finish_reason_present: bool,
    stream_options_present: bool = False,
    stream_options_include_usage: bool = False,
    stream_usage_present: bool | None = None,
) -> None:
    """Log only provider response shape; never log prompt, output, or values."""
    if not _usage_diagnostics_enabled():
        return
    top_level_keys = _safe_mapping_keys(response)
    usage_present = isinstance(response, Mapping) and "usage" in response
    usage_value = response.get("usage") if isinstance(response, Mapping) else None
    logger.info(
        "provider_usage_diagnostic provider=%s model=%s response_mode=%s "
        "provider_response_type=%s top_level_keys=%s usage_present=%s "
        "usage_type=%s usage_keys=%s stream_usage_present=%s "
        "finish_reason_present=%s stream_options_present=%s "
        "stream_options_include_usage=%s",
        provider,
        model,
        response_mode,
        type(response).__name__,
        top_level_keys,
        usage_present,
        type(usage_value).__name__ if usage_present else None,
        _safe_mapping_keys(usage_value),
        stream_usage_present,
        finish_reason_present,
        stream_options_present,
        stream_options_include_usage,
    )


class JsonTransport(Protocol):
    """定义由应用层实现的无 SDK JSON 传输边界。

    传输实现负责基地址、认证密钥、HTTP 客户端、连接池与网络重试。适配器只提供
    已规范化的相对路径和 JSON 请求，不保存密钥，也不接触任何供应商 SDK 对象。
    """

    async def post_json(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """提交 JSON 并可将提交标识映射为 HTTP 幂等键，返回已解析对象。"""
        ...

    def stream_json(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式返回已解析 JSON；关闭迭代器时必须释放底层网络响应。"""
        ...


class ModelInvocationError(RuntimeError):
    """表示调用或响应不满足统一模型合同的稳定错误。

    ``code`` 可供应用层映射到审计和重试策略；异常文本不包含提示词、工具参数或
    模型响应正文，避免调用方把敏感内容经 Trace 或日志带出执行边界。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        usage: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.usage = dict(usage or {})
        self.metadata = dict(metadata or {})


def decode_json_object(content: object) -> dict[str, Any]:
    """Decode a provider JSON object while tolerating harmless text wrappers."""
    if isinstance(content, Mapping):
        return dict(content)
    if not isinstance(content, str):
        raise ModelInvocationError("MODEL_RESPONSE_INVALID", "provider content is not a JSON object")

    stripped = content.strip().lstrip("\ufeff")
    candidates = [stripped]
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())
    first_object = stripped.find("{")
    last_object = stripped.rfind("}")
    if first_object >= 0 and last_object > first_object:
        candidates.append(stripped[first_object:last_object + 1])

    for candidate in dict.fromkeys(candidates):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            # Markdown strings sometimes contain literal newlines/tabs. This
            # changes escaping only, never invents syntax or edits field values.
            # Other control bytes, broken quotes and truncated objects still fail.
            if exc.msg.startswith("Invalid control character") and not any(
                ord(char) < 32 and char not in "\n\r\t" for char in candidate
            ):
                try:
                    parsed = json.loads(candidate, strict=False)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
            continue
        except TypeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ModelInvocationError("MODEL_RESPONSE_INVALID", "provider content is not valid JSON")


class OpenAICompatibleRuntime:
    """把 AgentOS 模型信封映射为 OpenAI 兼容的 Chat Completions 请求。

    此实现同时适用于 OpenAI、DeepSeek、通义兼容模式、Ollama 和 vLLM 等端点，
    前提是应用层注入符合 ``JsonTransport`` 的传输实现。它不发起隐式网络连接，
    不实现 Agent 编排，也不把请求正文写入运行状态、检查点或审计元数据。
    """

    _PATH = "/chat/completions"
    _RESERVED_OPTIONS = frozenset({"model", "messages", "response_format", "stream", "schemaMessageIndex", "schema_message_index"})

    def __init__(self, *, manifest: CapabilityManifest, transport: JsonTransport) -> None:
        """保存模型声明和应用层传输，并在启动期验证声明边界。"""
        if manifest.kind is not CapabilityKind.MODEL:
            raise ValueError(
                f"CAPABILITY_KIND_INVALID: expected model, got {manifest.kind.value}"
            )
        if not manifest.provider.strip():
            raise ValueError("MODEL_PROVIDER_INVALID: provider is required")
        if not manifest.capabilities or any(not item.strip() for item in manifest.capabilities):
            raise ValueError(
                "MODEL_CAPABILITIES_INVALID: manifest.capabilities must declare models"
            )
        self._manifest = manifest
        self._transport = transport
        self._models = frozenset(item.strip() for item in manifest.capabilities)

    @property
    def manifest(self) -> CapabilityManifest:
        """返回运行时的不可变模型能力声明，供兼容注册表建立路由。"""
        return self._manifest

    def is_available(self) -> bool:
        """表明运行时已被装配；真实连通性检查由应用层生命周期管理。"""
        return True

    def describe_model(self, model: str) -> ModelCapabilityEnvelope:
        """从应用层 Manifest 读取精确声明；未声明容量时保持 unknown。"""

        normalized = model.strip()
        if normalized not in self._models:
            raise ModelInvocationError("MODEL_NOT_SUPPORTED", "requested model is not declared by this adapter")
        raw_all = self._manifest.metadata.get("modelCapabilities")
        raw = raw_all.get(normalized) if isinstance(raw_all, Mapping) else None
        if not isinstance(raw, Mapping):
            return ModelCapabilityEnvelope.unknown(
                provider=self._manifest.provider,
                model=normalized,
                version=self._manifest.version,
            )
        features = raw.get("features") if isinstance(raw.get("features"), Mapping) else {}
        source_value = str(raw.get("source") or ModelCapabilitySource.ADAPTER_DECLARED.value)
        try:
            source = ModelCapabilitySource(source_value)
        except ValueError:
            source = ModelCapabilitySource.ADAPTER_DECLARED
        return ModelCapabilityEnvelope(
            provider=self._manifest.provider,
            model=normalized,
            version=self._manifest.version,
            revision=str(raw.get("revision")) if raw.get("revision") else None,
            source=source,
            contextWindowTokens=raw.get("contextWindowTokens"),
            maxOutputTokens=raw.get("maxOutputTokens"),
            maxTokensField=str(raw.get("maxTokensField")) if raw.get("maxTokensField") else None,
            maxTokensRequired=bool(raw.get("maxTokensRequired", False)),
            features=ModelFeatureSet.model_validate(features),
        )

    async def invoke(self, request: ModelInvocationRequest) -> ModelInvocationResponse:
        """调用兼容端点并将首个 JSON 响应选择映射回稳定模型信封。"""
        model = request.model.strip()
        if model not in self._models:
            raise ModelInvocationError(
                "MODEL_NOT_SUPPORTED",
                "requested model is not declared by this adapter",
            )
        payload = self._build_payload(request, model)
        try:
            response = await self._transport.post_json(
                path=self._PATH,
                payload=payload,
                idempotency_key=request.commit_id,
            )
        except ModelInvocationError:
            raise
        except HttpTransportError as exc:
            raise ModelInvocationError(exc.code, "OpenAI compatible provider request failed") from exc
        except Exception as exc:
            raise ModelInvocationError(
                "MODEL_PROVIDER_FAILED",
                "OpenAI compatible provider request failed",
            ) from exc
        return self._parse_response(request=request, response=response, model=model)

    async def astream(self, request: ModelInvocationRequest) -> AsyncIterator[ModelStreamEvent]:
        """将 OpenAI 兼容流投影为会话内增量事件，不向运行状态写入正文。"""
        model = request.model.strip()
        if model not in self._models:
            raise ModelInvocationError("MODEL_NOT_SUPPORTED", "requested model is not declared by this adapter")
        streamer = getattr(self._transport, "stream_json", None)
        if not callable(streamer):
            raise ModelInvocationError("MODEL_STREAM_UNSUPPORTED", "transport does not support streaming")
        payload = self._build_payload(request, model)
        payload["stream"] = True
        stream_usage_present = False
        stream_usage_type: str | None = None
        stream_usage_keys: list[str] = []
        stream_usage: dict[str, Any] = {}
        last_chunk: Mapping[str, Any] | None = None
        stream_started = False
        first_token_observed = False
        output_delta_observed = False
        delta_count = 0
        completion_observed = False
        stream_started_at = monotonic()

        def stream_diagnostics(reason: str) -> dict[str, Any]:
            return {
                "streamStarted": stream_started,
                "firstTokenObserved": first_token_observed,
                "outputDeltaObserved": output_delta_observed,
                "deltaCount": delta_count,
                "completionObserved": completion_observed,
                "streamTerminationReason": reason,
                "elapsedMs": max(0, round((monotonic() - stream_started_at) * 1000)),
            }

        stream_options = payload.get("stream_options")
        stream_options_include_usage = (
            isinstance(stream_options, Mapping)
            and stream_options.get("include_usage") is True
        )
        completed = False
        finish_reason: str | None = None
        try:
            stream_started = True
            async for chunk in streamer(path=self._PATH, payload=payload, idempotency_key=request.commit_id):
                if not isinstance(chunk, Mapping):
                    raise ModelInvocationError("MODEL_RESPONSE_INVALID", "stream chunk is not an object")
                last_chunk = chunk
                if "usage" in chunk:
                    stream_usage_present = True
                    raw_usage = chunk.get("usage")
                    stream_usage_type = type(raw_usage).__name__
                    stream_usage_keys = _safe_mapping_keys(raw_usage)
                    if isinstance(raw_usage, Mapping):
                        stream_usage = dict(raw_usage)
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
                    continue
                choice = choices[0]
                delta_data = choice.get("delta")
                delta = delta_data.get("content") if isinstance(delta_data, Mapping) else None
                reasoning = delta_data.get("reasoning_content") if isinstance(delta_data, Mapping) else None
                if isinstance(reasoning, str) and reasoning:
                    # Never expose private reasoning, but preserve provider
                    # liveness so long thinking is not misclassified as TTFT.
                    yield ModelStreamEvent(requestId=request.request_id, eventType="activity", provider=self._manifest.provider, model=model)
                if isinstance(delta, str) and delta:
                    first_token_observed = True
                    output_delta_observed = True
                    delta_count += 1
                    yield ModelStreamEvent(requestId=request.request_id, eventType="delta", delta=delta, provider=self._manifest.provider, model=model)
                if isinstance(delta_data, Mapping):
                    tool_calls = delta_data.get("tool_calls")
                    if isinstance(tool_calls, list):
                        for tool_call in tool_calls:
                            if not isinstance(tool_call, Mapping):
                                continue
                            function = tool_call.get("function")
                            if not isinstance(function, Mapping):
                                continue
                            arguments = function.get("arguments", "")
                            if not isinstance(arguments, str):
                                continue
                            call_id = tool_call.get("id")
                            name = function.get("name")
                            yield ModelStreamEvent(
                                requestId=request.request_id,
                                eventType="tool_call",
                                provider=self._manifest.provider,
                                model=model,
                                toolCallId=call_id if isinstance(call_id, str) else None,
                                toolName=name if isinstance(name, str) else None,
                                toolArguments=arguments,
                            )
                if isinstance(choice.get("finish_reason"), str):
                    completed = True
                    completion_observed = True
                    finish_reason = choice["finish_reason"]
                    # Some OpenAI-compatible providers send usage in a final
                    # choices=[] chunk after the finish chunk. Keep consuming
                    # the stream so the shape diagnostic can observe it.
                    continue
        except HttpTransportError as exc:
            raise ModelInvocationError(
                exc.code,
                "OpenAI compatible provider stream failed",
                metadata={"streamDiagnostics": stream_diagnostics("provider_transport_error")},
            ) from exc
        except ModelInvocationError as exc:
            metadata = dict(exc.metadata)
            metadata.setdefault("streamDiagnostics", stream_diagnostics("provider_error"))
            raise ModelInvocationError(
                exc.code,
                str(exc),
                usage=exc.usage,
                metadata=metadata,
            ) from exc
        except Exception as exc:
            raise ModelInvocationError(
                "MODEL_PROVIDER_FAILED",
                "OpenAI compatible provider stream failed",
                metadata={"streamDiagnostics": stream_diagnostics("provider_exception")},
            ) from exc
        _log_provider_usage_shape(
            provider=self._manifest.provider,
            model=model,
            response=last_chunk or {},
            response_mode="stream",
            finish_reason_present=finish_reason is not None,
            stream_options_present=isinstance(stream_options, Mapping),
            stream_options_include_usage=stream_options_include_usage,
            stream_usage_present=stream_usage_present,
        )
        if _usage_diagnostics_enabled():
            logger.info(
                "provider_usage_diagnostic_stream_detail provider=%s model=%s "
                "usage_type=%s usage_keys=%s",
                self._manifest.provider,
                model,
                stream_usage_type,
                stream_usage_keys,
            )
        if not completed:
            raise ModelInvocationError(
                "MODEL_STREAM_INCOMPLETE",
                "provider stream ended without completion",
                metadata={"streamDiagnostics": stream_diagnostics("eof_before_completion")},
            )
        metadata: dict[str, Any] = {}
        if finish_reason is not None:
            metadata["finishReason"] = finish_reason
        if stream_usage:
            metadata["usage"] = dict(stream_usage)
        metadata["streamDiagnostics"] = stream_diagnostics("completed")
        yield ModelStreamEvent(
            requestId=request.request_id,
            eventType="completed",
            provider=self._manifest.provider,
            model=model,
            metadata=metadata,
        )

    def _build_payload(
        self,
        request: ModelInvocationRequest,
        model: str,
    ) -> dict[str, Any]:
        """构造请求并禁止选项覆盖受合同保护的模型、消息和 JSON Schema。"""
        reserved = self._RESERVED_OPTIONS.intersection(request.options)
        if reserved:
            raise ModelInvocationError(
                "MODEL_OPTIONS_INVALID",
                "options must not override protected OpenAI request fields",
            )
        payload: dict[str, Any] = dict(request.options)
        payload["model"] = model
        payload["messages"] = [dict(message) for message in request.messages]
        if request.response_schema is not None:
            # 思考档位只对声明该能力的供应商（GLM/DeepSeek）外发，其余端点剥离
            # 该选项，避免未知参数破坏严格兼容端点的 wire format。判定依据是
            # 供应商标识而非模型名，官方上新/改名模型自动适用。
            reasoning_effort = payload.pop("reasoning_effort", None)
            provider = self._manifest.provider.strip().lower()
            thinking_provider = provider in {"glm", "zhipu", "deepseek"}
            if thinking_provider:
                if isinstance(reasoning_effort, str) and reasoning_effort.strip():
                    # 显式档位意味着用户选择让思考参与本次输出；此时关闭思考
                    # 会静默吞掉档位语义，等价于档位永远无效。
                    if provider == "deepseek":
                        effort = reasoning_effort.strip()
                        payload["reasoning_effort"] = "high" if effort == "medium" else effort
                    else:
                        payload["reasoning_effort"] = reasoning_effort.strip()
                    payload["thinking"] = {"type": "enabled"}
                else:
                    # 无显式档位时保持直出：GLM 5 系/DeepSeek 思考模型默认长思
                    # 考，私有推理与 JSON 答案争夺同一输出预算，可能在对象闭合
                    # 前耗尽响应；规划器已提供显式校验与修复兜底。
                    payload["thinking"] = {"type": "disabled"}
                payload["response_format"] = {"type": "json_object"}
                schema_instruction = (
                    "Return exactly one JSON object that strictly validates against this JSON Schema. "
                    "Do not omit required fields, add undeclared fields, or change required array sizes.\n"
                    + json.dumps(
                        request.prefix_response_schema if request.prefix_response_schema is not None else request.response_schema,
                        ensure_ascii=False, separators=(",", ":"),
                    )
                )
                schema_index = request.schema_message_index if request.schema_message_index is not None else 0
                if request.schema_message_index is not None and (
                    schema_index >= len(payload["messages"]) or payload["messages"][schema_index].get("role") != "system"
                ):
                    raise ModelInvocationError("MODEL_REQUEST_INVALID", "schema target must be an existing system message")
                if payload["messages"] and payload["messages"][schema_index].get("role") == "system":
                    payload["messages"][schema_index]["content"] = (
                        str(payload["messages"][schema_index].get("content") or "")
                        + "\n\nTRANSPORT OUTPUT CONTRACT:\n"
                        + schema_instruction
                    )
                else:
                    payload["messages"] = [
                        {"role": "system", "content": schema_instruction},
                        *payload["messages"],
                    ]
                if request.prefix_response_schema is not None:
                    payload["messages"].insert(len(payload["messages"]) - 1, {
                        "role": "system",
                        "content": "CURRENT CONTINUATION OUTPUT CONTRACT: This replaces only the earlier output schema, "
                        "not the evidence or authority rules. Return exactly the JSON object matching this schema:\n"
                        + json.dumps(request.response_schema, ensure_ascii=False, separators=(",", ":")),
                    })
            else:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agentos_response",
                        "strict": True,
                        "schema": dict(request.response_schema),
                    },
                }
        return payload

    def _parse_response(
        self,
        *,
        request: ModelInvocationRequest,
        response: object,
        model: str,
    ) -> ModelInvocationResponse:
        """解析首个 choice 的 JSON 对象，拒绝空、非对象和无效 JSON 响应。"""
        if not isinstance(response, Mapping):
            raise ModelInvocationError("MODEL_RESPONSE_INVALID", "provider response is not an object")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ModelInvocationError("MODEL_RESPONSE_INVALID", "provider response has no usable choice")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, Mapping):
            raise ModelInvocationError("MODEL_RESPONSE_INVALID", "provider response has no message")
        usage = response.get("usage")
        finish_reason = choice.get("finish_reason")
        safe_usage = dict(usage) if isinstance(usage, Mapping) else {}
        _log_provider_usage_shape(
            provider=self._manifest.provider,
            model=model,
            response_mode="non_stream",
            response=response,
            finish_reason_present=isinstance(finish_reason, str),
        )
        safe_metadata = {"finishReason": finish_reason} if isinstance(finish_reason, str) else {}
        if finish_reason in {"length", "max_tokens", "max_output_tokens"}:
            raise ModelInvocationError(
                "MODEL_OUTPUT_EXHAUSTED",
                "model provider exhausted its output capacity before completing JSON",
                usage=safe_usage,
                metadata=safe_metadata,
            )
        try:
            content = self._content_object(message.get("content"))
        except ModelInvocationError as exc:
            # Keep model source/prompt text out of logs while retaining enough
            # syntax evidence to diagnose code-bearing structured responses.
            raw = message.get("content")
            diagnostics = {"length": len(raw) if isinstance(raw, str) else 0}
            if isinstance(raw, str):
                try:
                    json.loads(raw)
                except json.JSONDecodeError as syntax:
                    diagnostics.update(reason=syntax.msg, line=syntax.lineno, column=syntax.colno)
            logger.warning("model_json_decode_failed provider=%s model=%s diagnostics=%s",
                           self._manifest.provider, model, diagnostics)
            exc.usage.update(safe_usage)
            exc.metadata.update(safe_metadata, responseDiagnostics=diagnostics)
            raise
        return ModelInvocationResponse(
            requestId=request.request_id,
            content=content,
            provider=self._manifest.provider,
            model=model,
            usage=safe_usage,
            metadata=safe_metadata,
        )

    @staticmethod
    def _content_object(content: object) -> dict[str, Any]:
        """把供应商内容规范为 JSON 对象，不把原始响应嵌入错误信息。"""
        return decode_json_object(content)


__all__ = ["JsonTransport", "ModelInvocationError", "OpenAICompatibleRuntime"]

"""将统一模型适配器桥接为原生 Agent 所需的结构化生成运行时。"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any
from uuid import uuid4

from adapters.model_adapter import (
    StructuredGenerationError,
    StructuredGenerationResult,
)
from adapters.model_compatibility import ModelCompatibilityRegistry
from adapters.openai_runtime import ModelInvocationError, decode_json_object
from adapters.prompt_runtime import canonical_hash, prompt_instance_metadata, trust_summary
from adapters.execution_prefix import execution_messages
from contracts.capability import (
    ModelCapabilityEnvelope,
    ModelOutputPolicy,
    ModelInvocationRequest,
)
from contracts.runtime_events import RuntimeEvent


# 允许透传的思考档位：GLM 5.3 low/high/max 与 OpenAI 系 low/medium/high 的并集。
_REASONING_EFFORT_VALUES = frozenset({"low", "medium", "high", "max"})


def _validated_reasoning_effort(value: Any) -> str | None:
    """只放行受支持的档位，防止任务输入把任意键值注入供应商请求体。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _REASONING_EFFORT_VALUES:
            return normalized
    return None


class RegisteredModelRuntime:
    """按已冻结的提供商和模型名解析统一适配器的无 SDK 生成运行时。

    本类不缓存供应商客户端、不持有密钥，也不改变注册表。每次调用都经注册表重新
    解析健康适配器，因此应用层撤销或替换失效实现后不会继续调用旧对象。超时、重试
    和限流由外层 ``GuardedModelRuntime`` 统一控制；此桥接层仅负责合同转换。
    """

    supports_continuation = True

    def __init__(
        self,
        *,
        registry: ModelCompatibilityRegistry,
        provider: str,
        model: str,
        version: str | None = None,
        clock: Callable[[], float] = monotonic,
        wait_for: Callable[[Awaitable[Any], float], Awaitable[Any]] | None = None,
    ) -> None:
        """保存只读路由键；空键在构造期失败，避免节点开始后才发现配置不完整。"""
        self._registry = registry
        self.provider = provider.strip()
        self.model = model.strip()
        self.version = version.strip() if version is not None else None
        self._clock = clock
        self._wait_for = wait_for or _wait_for
        if not self.provider:
            raise ValueError("MODEL_PROVIDER_REQUIRED: Agent profile must set modelProvider")
        if not self.model:
            raise ValueError("MODEL_NAME_REQUIRED: Agent profile must set modelName")

    def is_available(self) -> bool:
        """返回当前路由是否能解析到健康适配器，不执行网络连通性探测。"""
        try:
            self._registry.resolve(self.provider, self.model, version=self.version)
        except LookupError:
            return False
        return True

    def describe_model(self) -> ModelCapabilityEnvelope:
        """读取当前首选模型路由的能力，不触发远端探测。"""
        return self._registry.describe_model(
            self.provider,
            self.model,
            version=self.version,
        )

    _FAILOVER_CODES = frozenset(
        {
            "MODEL_TIMEOUT",
            "MODEL_RATE_LIMITED",
            "MODEL_TEMPORARY_UNAVAILABLE",
            "MODEL_PROVIDER_FAILED",
        }
    )

    async def generate_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
        thinking_mode: str = "disabled",
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        timeout_seconds: float = 120.0,
        max_output_tokens: int | None = None,
        prompt_version: str = "native-capability.v3",
        commit_id: str | None = None,
        prompt_metadata: dict[str, Any] | None = None,
        continuation: list[dict[str, str]] | None = None,
        prefix_schema: dict[str, Any] | None = None,
    ) -> StructuredGenerationResult:
        """把原生 JSON 生成请求转换为统一模型调用，并返回安全审计投影。"""
        # thinking_mode 的供应商映射发生在适配器层；本桥接只转发显式声明的
        # reasoning_effort（OpenAI 兼容参数），是否外发由适配器按提供方裁决。
        del thinking_mode
        reasoning_effort = _validated_reasoning_effort(reasoning_effort)
        if temperature is not None and (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(float(temperature))
            or not 0 <= float(temperature) <= 2
        ):
            raise StructuredGenerationError(
                "MODEL_TEMPERATURE_INVALID", "temperature must be between 0 and 2"
            )
        if timeout_seconds <= 0:
            raise StructuredGenerationError(
                "MODEL_TIMEOUT_INVALID",
                "timeout_seconds must be greater than zero",
            )
        if max_output_tokens is not None and max_output_tokens <= 0:
            raise StructuredGenerationError(
                "MODEL_OUTPUT_BUDGET_INVALID",
                "max_output_tokens must be greater than zero",
            )
        request_id = commit_id or f"model:{uuid4().hex}"
        started = self._clock()
        try:
            candidates = self._registry.resolve_candidates(
                self.provider,
                self.model,
                version=self.version,
            )
        except LookupError as exc:
            raise StructuredGenerationError(
                "MODEL_NOT_CONFIGURED",
                "requested model adapter is not registered or healthy",
            ) from exc
        response = None
        last_error: ModelInvocationError | asyncio.TimeoutError | None = None
        selected_capability: ModelCapabilityEnvelope | None = None
        selected_policy = ModelOutputPolicy.API_CONTROLLED
        selected_effective_tokens: int | None = None
        selected_reason = "provider_default"
        selected_prompt_identity: dict[str, str] = {}
        last_prompt_audit: dict[str, Any] = {}
        messages, schema_message_index = execution_messages(
            prompt=prompt, system_prompt=system_prompt, provider=self.provider, prompt_metadata=prompt_metadata,
        )
        if continuation is not None:
            if not isinstance(continuation, list) or not continuation or any(
                not isinstance(item, dict) or set(item) != {"role", "content"} or item["role"] not in {"assistant", "user"}
                or not isinstance(item["content"], str) for item in continuation
            ) or continuation[-1]["role"] != "user":
                raise StructuredGenerationError("MODEL_CONTINUATION_INVALID", "continuation must end in user data")
            messages.extend(dict(item) for item in continuation)
        if prefix_schema is not None and not continuation:
            raise StructuredGenerationError("MODEL_CONTINUATION_INVALID", "a prefix contract requires continuation messages")
        safe_prompt_metadata = self._prompt_metadata(
            prompt_metadata=prompt_metadata,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
        )
        if schema_message_index is not None:
            safe_prompt_metadata["stablePrefixHash"] = canonical_hash(messages[:schema_message_index])
        for index, adapter in enumerate(candidates):
            # ``timeout_seconds`` 是整个模型选择动作的上限，而不是每个候选各自的
            # 上限。剩余时间在尚未尝试的候选之间均分：主实现慢超时时备实现仍有机会
            # 返回，同时候选数增加也不会线性放大用户等待时间。
            remaining = timeout_seconds - (self._clock() - started)
            if remaining <= 0:
                raise StructuredGenerationError(
                    "MODEL_TIMEOUT",
                    "model invocation timed out",
                )
            candidate_timeout = remaining / (len(candidates) - index)
            describer = getattr(adapter, "describe_model", None)
            capability = (
                describer(self.model)
                if callable(describer)
                else ModelCapabilityEnvelope.unknown(
                    provider=self.provider,
                    model=self.model,
                    version=self.version,
                )
            )
            options: dict[str, Any] = {}
            policy = ModelOutputPolicy.API_CONTROLLED
            effective_tokens: int | None = None
            effective_reason = "provider_default"
            if max_output_tokens is not None:
                field = capability.max_tokens_field or "max_tokens"
                options[field] = max_output_tokens
                policy = ModelOutputPolicy.EXPLICIT
                effective_tokens = max_output_tokens
                effective_reason = "explicit_request"
            elif capability.max_tokens_required:
                if capability.max_output_tokens is None:
                    raise StructuredGenerationError(
                        "MODEL_CAPABILITY_INVALID",
                        "provider requires an output token field but declares no value",
                    )
                field = capability.max_tokens_field or "max_tokens"
                options[field] = capability.max_output_tokens
                policy = ModelOutputPolicy.PROVIDER_REQUIRED
                effective_tokens = capability.max_output_tokens
                effective_reason = "provider_required"
            elif capability.max_output_tokens is not None:
                # 调用方未指定时，能力目录登记的输出上限必须显式随请求发送：
                # "未指定"不得等价于供应商服务端默认额度（结构化 JSON 会被静默截断）。
                field = capability.max_tokens_field or "max_tokens"
                options[field] = capability.max_output_tokens
                policy = ModelOutputPolicy.CATALOG_DEFAULT
                effective_tokens = capability.max_output_tokens
                effective_reason = "catalog_default"
            if reasoning_effort:
                options["reasoning_effort"] = reasoning_effort
            if temperature is not None:
                options["temperature"] = float(temperature)
            invocation_identity = prompt_instance_metadata(
                messages=messages,
                response_schema=dict(schema),
                provider_family=capability.provider or self.provider,
                model=capability.model or self.model,
                model_version=capability.version or self.version,
                behavior_options={**options, **({"prefixResponseSchemaHash": canonical_hash(prefix_schema)}
                                               if prefix_schema is not None else {})},
            )
            candidate_prompt_audit = {
                **safe_prompt_metadata,
                **invocation_identity,
                "promptVersion": prompt_version,
                "requestType": self._request_type(prompt),
                "providerFamily": capability.provider or self.provider,
                "modelVersion": capability.version or self.version,
                "streaming": False,
                "trustSummary": trust_summary(prompt),
            }
            last_prompt_audit = candidate_prompt_audit
            request = ModelInvocationRequest(
                requestId=request_id,
                model=self.model,
                messages=messages,
                responseSchema=dict(schema),
                prefixResponseSchema=prefix_schema,
                schemaMessageIndex=schema_message_index,
                options=options,
                commitId=commit_id,
            )
            try:
                response = await self._wait_for(
                    adapter.invoke(request),
                    candidate_timeout,
                )
                selected_capability = capability
                selected_policy = policy
                selected_effective_tokens = effective_tokens
                selected_reason = effective_reason
                selected_prompt_identity = invocation_identity
                break
            except asyncio.TimeoutError as exc:
                last_error = exc
                if index + 1 < len(candidates):
                    continue
                raise StructuredGenerationError(
                    "MODEL_TIMEOUT",
                    "model invocation timed out",
                    audit=candidate_prompt_audit,
                ) from exc
            except ModelInvocationError as exc:
                last_error = exc
                if exc.code in self._FAILOVER_CODES and index + 1 < len(candidates):
                    continue
                raise StructuredGenerationError(
                    exc.code,
                    str(exc),
                    # 容量耗尽需进入分解/分片恢复，普通重试同一语义单元
                    # 只会重复失败并放大费用。
                    retryable=exc.code in self._FAILOVER_CODES,
                    audit={
                        **candidate_prompt_audit,
                        "provider": capability.provider,
                        "model": capability.model,
                        "usage": dict(getattr(exc, "usage", {}) or {}),
                        "finishReason": (getattr(exc, "metadata", {}) or {}).get("finishReason"),
                        "capability": capability.model_dump(by_alias=True, mode="json", exclude_none=True),
                        "outputPolicy": policy.value,
                        "requestedOutputTokens": max_output_tokens,
                        "effectiveOutputTokens": effective_tokens,
                        "effectiveReason": effective_reason,
                        "outputExhausted": exc.code == "MODEL_OUTPUT_EXHAUSTED",
                    },
                ) from exc
            except Exception as exc:
                raise StructuredGenerationError(
                    "MODEL_PROVIDER_FAILED",
                    "model provider invocation failed",
                    audit=candidate_prompt_audit,
                ) from exc
        if response is None:
            if isinstance(last_error, ModelInvocationError):
                raise StructuredGenerationError(
                    last_error.code,
                    str(last_error),
                    audit=last_prompt_audit,
                ) from last_error
            raise StructuredGenerationError(
                "MODEL_PROVIDER_FAILED",
                "model provider invocation failed",
                audit=last_prompt_audit,
            )
        finish_reason = str(response.metadata.get("finishReason") or "") or None
        output_exhausted = finish_reason in {"length", "max_tokens", "max_output_tokens"}
        if output_exhausted:
            raise StructuredGenerationError(
                "MODEL_OUTPUT_EXHAUSTED",
                "model provider exhausted its output capacity before completing the response",
                retryable=False,
                audit={
                    **safe_prompt_metadata,
                    **selected_prompt_identity,
                    "promptVersion": prompt_version,
                    "requestType": self._request_type(prompt),
                    "providerFamily": selected_capability.provider or self.provider,
                    "modelVersion": selected_capability.version or self.version,
                    "streaming": False,
                    "trustSummary": trust_summary(prompt),
                    "provider": selected_capability.provider,
                    "model": selected_capability.model,
                    "usage": dict(response.usage),
                    "finishReason": finish_reason,
                    "capability": selected_capability.model_dump(
                        by_alias=True, mode="json", exclude_none=True
                    ),
                    "outputPolicy": selected_policy.value,
                    "requestedOutputTokens": max_output_tokens,
                    "effectiveOutputTokens": selected_effective_tokens,
                    "effectiveReason": selected_reason,
                    "outputExhausted": True,
                },
            )
        return StructuredGenerationResult(
            data=dict(response.content),
            provider=response.provider,
            model=response.model,
            latencyMs=round((self._clock() - started) * 1000),
            promptVersion=prompt_version,
            promptTemplateHash=safe_prompt_metadata["promptTemplateHash"],
            promptInstanceHash=selected_prompt_identity["promptInstanceHash"],
            stablePrefixHash=safe_prompt_metadata["stablePrefixHash"],
            schemaHash=selected_prompt_identity["schemaHash"],
            kernelVersion=safe_prompt_metadata.get("kernelVersion"),
            preset=safe_prompt_metadata.get("preset"),
            presetVersion=safe_prompt_metadata.get("presetVersion"),
            capabilityId=safe_prompt_metadata.get("capabilityId"),
            capabilityPolicyVersion=safe_prompt_metadata.get("capabilityPolicyVersion"),
            requestProtocolVersion=safe_prompt_metadata.get("requestProtocolVersion"),
            outputProtocolVersion=safe_prompt_metadata.get("outputProtocolVersion"),
            promptRendererVersion=safe_prompt_metadata.get("promptRendererVersion"),
            requestType=self._request_type(prompt),
            providerFamily=(selected_capability.provider or self.provider),
            modelVersion=(selected_capability.version or self.version),
            streaming=False,
            trustSummary=trust_summary(prompt),
            usage=dict(response.usage),
            finishReason=finish_reason,
            capability=selected_capability,
            outputPolicy=selected_policy,
            requestedOutputTokens=max_output_tokens,
            effectiveOutputTokens=selected_effective_tokens,
            effectiveReason=selected_reason,
            outputExhausted=False,
        )

    async def stream_generate_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
        run_id: str,
        node_id: str | None = None,
        attempt_id: str | None = None,
        ttft_timeout: float = 30.0,
        idle_timeout: float = 60.0,
        total_timeout: float = 300.0,
        thinking_mode: str = "disabled",
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        prompt_version: str = "native-capability.v3",
        commit_id: str | None = None,
        emit_output_deltas: bool = True,
        prompt_metadata: dict[str, Any] | None = None,
    ):
        """Consume a provider stream while keeping structured output private when requested."""
        del thinking_mode
        reasoning_effort = _validated_reasoning_effort(reasoning_effort)
        if temperature is not None and (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(float(temperature))
            or not 0 <= float(temperature) <= 2
        ):
            raise StructuredGenerationError(
                "MODEL_TEMPERATURE_INVALID", "temperature must be between 0 and 2"
            )
        if min(ttft_timeout, idle_timeout, total_timeout) <= 0:
            raise StructuredGenerationError("MODEL_TIMEOUT_INVALID", "stream timeouts must be positive")
        try:
            candidates = self._registry.resolve_candidates(self.provider, self.model, version=self.version)
        except LookupError as exc:
            raise StructuredGenerationError("MODEL_NOT_CONFIGURED", "requested model adapter is not registered") from exc
        adapter = candidates[0]
        streamer = getattr(adapter, "astream", None)
        if not callable(streamer):
            raise StructuredGenerationError("MODEL_STREAM_UNSUPPORTED", "model adapter does not support streaming")
        try:
            capability = adapter.describe_model(self.model)
        except Exception:
            capability = ModelCapabilityEnvelope.unknown(
                provider=self.provider, model=self.model, version=self.version
            )
        options: dict[str, Any] = {}
        if max_output_tokens is not None:
            options[capability.max_tokens_field or "max_tokens"] = max_output_tokens
        elif capability.max_tokens_required and capability.max_output_tokens is not None:
            options[capability.max_tokens_field or "max_tokens"] = capability.max_output_tokens
        elif capability.max_output_tokens is not None:
            options[capability.max_tokens_field or "max_tokens"] = capability.max_output_tokens
        if reasoning_effort:
            options["reasoning_effort"] = reasoning_effort
        if temperature is not None:
            options["temperature"] = float(temperature)
        request_id = commit_id or f"model:{uuid4().hex}"
        messages, schema_message_index = execution_messages(
            prompt=prompt, system_prompt=system_prompt, provider=self.provider, prompt_metadata=prompt_metadata,
        )
        safe_prompt_metadata = self._prompt_metadata(
            prompt_metadata=prompt_metadata,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
        )
        if schema_message_index is not None:
            safe_prompt_metadata["stablePrefixHash"] = canonical_hash(messages[:schema_message_index])
        invocation_identity = prompt_instance_metadata(
            messages=messages,
            response_schema=dict(schema),
            provider_family=capability.provider or self.provider,
            model=capability.model or self.model,
            model_version=capability.version or self.version,
            behavior_options=options,
        )
        safe_audit = {
            **safe_prompt_metadata,
            **invocation_identity,
            "promptVersion": prompt_version,
            "requestType": self._request_type(prompt),
            "providerFamily": capability.provider or self.provider,
            "modelVersion": capability.version or self.version,
            "streaming": True,
            "trustSummary": trust_summary(prompt),
        }
        request = ModelInvocationRequest(
            requestId=request_id,
            model=self.model,
            messages=messages,
            responseSchema=dict(schema),
            schemaMessageIndex=schema_message_index,
            options=options,
            commitId=commit_id,
        )
        seq = 0
        started = self._clock()
        last_activity = started
        last_activity_event = started
        first = False
        provider_active = False
        received_chunks = 0
        public_activity_pending = False
        buffer: list[str] = []
        finish_reason: str | None = None
        stream_usage: dict[str, Any] = {}
        stream_diagnostics: dict[str, Any] = {}
        iterator = streamer(request)

        def emit(kind: str, payload: dict[str, Any] | None = None) -> RuntimeEvent:
            nonlocal seq
            seq += 1
            return RuntimeEvent(
                eventType=kind,
                runId=run_id,
                nodeId=node_id,
                attemptId=attempt_id,
                sequence=seq,
                payload=payload or {},
            )

        def activity_payload(idle_ms: float) -> dict[str, Any]:
            return {
                "elapsedMs": round((self._clock() - started) * 1000),
                "idleMs": round(max(0.0, idle_ms) * 1000),
                "receivedChunks": received_chunks,
                "receivedLength": sum(map(len, buffer)),
            }

        yield emit("model.started", {
            "requestId": request_id,
            "provider": self.provider,
            "model": self.model,
            "streamingCapability": True,
            **safe_audit,
        })
        completed = False
        try:
            while True:
                total_left = total_timeout - (self._clock() - started)
                if total_left <= 0:
                    raise StructuredGenerationError("MODEL_TOTAL_TIMEOUT", "model stream total timeout exceeded")
                window = ttft_timeout if not provider_active else idle_timeout
                activity_left = window - (self._clock() - (started if not provider_active else last_activity))
                if activity_left <= 0:
                    code = "MODEL_TTFT_TIMEOUT" if not first else "MODEL_IDLE_TIMEOUT"
                    raise StructuredGenerationError(code, "model stream activity deadline exceeded", retryable=True)
                try:
                    item = await self._wait_for(anext(iterator), min(total_left, activity_left))
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    code = "MODEL_TTFT_TIMEOUT" if not first else "MODEL_IDLE_TIMEOUT"
                    raise StructuredGenerationError(code, "model stream activity deadline exceeded", retryable=True) from exc
                except ModelInvocationError as exc:
                    audit = {
                        "provider": self.provider,
                        "model": self.model,
                        "usage": dict(getattr(exc, "usage", {}) or {}),
                        "finishReason": (getattr(exc, "metadata", {}) or {}).get("finishReason"),
                    }
                    raw_diagnostics = (getattr(exc, "metadata", {}) or {}).get("streamDiagnostics")
                    if isinstance(raw_diagnostics, dict):
                        stream_diagnostics = {
                            key: value
                            for key, value in raw_diagnostics.items()
                            if key in {
                                "streamStarted", "firstTokenObserved", "outputDeltaObserved",
                                "deltaCount", "completionObserved", "streamTerminationReason", "elapsedMs",
                            }
                            and isinstance(value, (bool, int, float, str))
                        }
                        audit["streamDiagnostics"] = dict(stream_diagnostics)
                    raise StructuredGenerationError(
                        exc.code,
                        "model provider stream failed",
                        retryable=exc.code in self._FAILOVER_CODES,
                        audit=audit,
                    ) from exc
                now = self._clock()
                if item.event_type == "activity":
                    provider_active = True
                    idle_ms = now - last_activity
                    last_activity = now
                    if now - last_activity_event >= 0.35:
                        last_activity_event = now
                        yield emit("model.activity", activity_payload(idle_ms))
                elif item.event_type == "delta" and item.delta:
                    provider_active = True
                    received_chunks += 1
                    buffer.append(item.delta)
                    public_activity_pending = True
                    idle_ms = now - last_activity
                    last_activity = now
                    if not first:
                        first = True
                        yield emit("model.first_token", activity_payload(idle_ms))
                    if emit_output_deltas:
                        yield emit("model.output.delta", {"delta": item.delta})
                    if received_chunks == 1 or now - last_activity_event >= 0.35:
                        last_activity_event = now
                        public_activity_pending = False
                        yield emit("model.activity", activity_payload(idle_ms))
                elif item.event_type == "completed":
                    raw_finish_reason = item.metadata.get("finishReason")
                    finish_reason = str(raw_finish_reason or "") or None
                    raw_usage = item.metadata.get("usage")
                    if isinstance(raw_usage, dict):
                        stream_usage = dict(raw_usage)
                    raw_diagnostics = item.metadata.get("streamDiagnostics")
                    if isinstance(raw_diagnostics, dict):
                        stream_diagnostics = dict(raw_diagnostics)
                    completed = True
                    break
        except asyncio.CancelledError:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
            raise
        except Exception as exc:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
            if isinstance(exc, StructuredGenerationError):
                exc.audit = {**safe_audit, **exc.audit}
            raise
        if not first:
            raise StructuredGenerationError(
                "MODEL_TTFT_TIMEOUT",
                "model stream completed without output",
                audit=safe_audit,
            )
        if not completed:
            # A provider adapter normally emits completed; treating a clean end
            # as parseable keeps compatible fake streams useful without relaxing
            # TTFT/idle/total ownership.
            completed = True
        # Usage is reported before JSON decoding. A malformed answer still
        # consumed provider tokens and must remain measurable when repaired.
        completed_audit = {
            **safe_audit,
            "provider": capability.provider or self.provider,
            "model": capability.model or self.model,
            "usage": dict(stream_usage),
            "finishReason": finish_reason,
            "latencyMs": round((self._clock() - started) * 1000),
        }
        if finish_reason in {"length", "max_tokens", "max_output_tokens"}:
            raise StructuredGenerationError(
                "MODEL_OUTPUT_EXHAUSTED",
                "model provider exhausted its output capacity before completing the response",
                retryable=False,
                audit=completed_audit,
            )
        if public_activity_pending:
            yield emit("model.activity", activity_payload(0.0))
        try:
            data = decode_json_object("".join(buffer))
        except ModelInvocationError as exc:
            raise StructuredGenerationError(
                "MODEL_OUTPUT_INVALID_JSON",
                "streamed model output is not valid JSON",
                audit=completed_audit,
            ) from exc
        yield emit("model.completed", {
            "receivedLength": sum(map(len, buffer)),
            "data": data,
            "provider": self.provider,
            "model": self.model,
            "usage": dict(stream_usage),
            "finishReason": finish_reason,
            "latencyMs": round((self._clock() - started) * 1000),
            "streamDiagnostics": dict(stream_diagnostics),
            **safe_audit,
        })

    @staticmethod
    def _prompt_metadata(
        *,
        prompt_metadata: dict[str, Any] | None,
        system_prompt: str | None,
        prompt_version: str,
    ) -> dict[str, Any]:
        allowed = {
            "promptTemplateHash", "stablePrefixHash", "kernelVersion", "preset",
            "presetVersion", "capabilityId", "capabilityPolicyVersion",
            "requestProtocolVersion", "outputProtocolVersion", "promptRendererVersion",
        }
        metadata = {
            key: value for key, value in dict(prompt_metadata or {}).items() if key in allowed
        }
        if "stablePrefixHash" not in metadata:
            metadata["stablePrefixHash"] = canonical_hash(
                ([{"role": "system", "content": system_prompt}] if system_prompt else [])
            )
        if "promptTemplateHash" not in metadata:
            metadata["promptTemplateHash"] = canonical_hash({
                "legacyPromptVersion": prompt_version,
                "systemPrompt": system_prompt or "",
            })
        return metadata

    @staticmethod
    def _request_type(prompt: str) -> str | None:
        try:
            payload = json.loads(prompt)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        request_type = payload.get("requestType")
        if not isinstance(request_type, str):
            nested = payload.get("executionRequest")
            request_type = nested.get("requestType") if isinstance(nested, dict) else None
        return request_type if isinstance(request_type, str) and request_type else None


async def _wait_for(awaitable: Awaitable[Any], timeout: float) -> Any:
    """Keep asyncio behind an injectable deadline boundary for deterministic tests."""
    return await asyncio.wait_for(awaitable, timeout=timeout)


__all__ = ["RegisteredModelRuntime"]

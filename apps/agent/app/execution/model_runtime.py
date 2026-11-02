"""Application adapter for bounded, asynchronous ACG structured generation."""

from __future__ import annotations

import asyncio
from support.async_tasks import await_owned, await_settled
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Any, Dict

from adapters.model_adapter import (
    StructuredGenerationError,
    StructuredGenerationResult,
)
from contracts.capability import (
    ModelCapabilityEnvelope,
    ModelCapabilitySource,
    ModelFeatureSet,
    ModelOutputPolicy,
)

from app.llm.gateway import get_llm_gateway
from app.llm.capabilities import provider_model_capabilities


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int((os.getenv(name) or str(default)).strip()))
    except ValueError:
        return default


class GatewayStructuredGenerationRuntime:
    """Run synchronous gateway calls outside the event loop with bounded concurrency."""

    production_stream_required = True

    def __init__(self, *, max_concurrency: int | None = None) -> None:
        workers = max_concurrency or _positive_int("AGENTOS_ACG_MODEL_MAX_CONCURRENCY", 2)
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="agentos-acg-model",
        )

    def is_available(self) -> bool:
        return get_llm_gateway().provider_name not in {"", "mock", "unavailable"}

    def describe_model(self) -> ModelCapabilityEnvelope:
        gateway = get_llm_gateway()
        if gateway.provider_name in {"", "mock", "unavailable"}:
            return ModelCapabilityEnvelope.unknown(
                provider=gateway.provider_name or "unavailable",
                model=gateway.model or "unknown",
            )
        declared = provider_model_capabilities(
            gateway.model,
            str(getattr(getattr(gateway, "provider", None), "base_url", "") or ""),
        )
        return ModelCapabilityEnvelope(
            provider=gateway.provider_name or "unavailable",
            model=gateway.model or "unknown",
            version=declared.version,
            source=ModelCapabilitySource.ADAPTER_DECLARED,
            contextWindowTokens=declared.context_window_tokens,
            maxOutputTokens=declared.max_output_tokens,
            maxTokensField=declared.max_tokens_field,
            features=ModelFeatureSet(
                jsonSchema=declared.supports_json_schema,
                streaming=declared.supports_stream_usage,
                tools=declared.supports_tools,
                thinking=declared.supports_thinking,
                promptCaching=None,
            ),
        )

    def close(self) -> None:
        """Release application-owned worker threads during service shutdown."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def generate_json(
        self,
        *,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: str | None = None,
        thinking_mode: str = "disabled",
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        timeout_seconds: float = 120.0,
        max_output_tokens: int | None = None,
        prompt_version: str = "native-capability.v3",
        commit_id: str | None = None,
        prompt_metadata: Dict[str, Any] | None = None,
    ) -> StructuredGenerationResult:
        gateway = get_llm_gateway()
        if gateway.provider_name in {"", "mock", "unavailable"}:
            raise StructuredGenerationError(
                "MODEL_UNAVAILABLE",
                "No production model is configured for native ACG execution.",
            )

        loop = asyncio.get_running_loop()

        def invoke() -> Dict[str, Any]:
            kwargs: Dict[str, Any] = {
                "system_prompt": system_prompt,
                "prompt_metadata": prompt_metadata,
                "prompt_version": prompt_version,
                "thinking_mode": thinking_mode,
                "commit_id": commit_id,
                # 档位守护预算必须下探到 provider 连接层，否则客户端构造期
                # 固定的读超时会先掐线，外层守护形同虚设。留 5 秒余量让
                # provider 侧以干净的 MODEL_TIMEOUT 先触发，保住在途调用的
                # 用量对账，而不是被 wait_for 取消后照常计费。
                "timeout_seconds": max(1.0, float(timeout_seconds) - 5.0),
            }
            if reasoning_effort is not None:
                kwargs["reasoning_effort"] = reasoning_effort
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_output_tokens is not None:
                kwargs["max_tokens"] = max_output_tokens
            return gateway.generate_json(prompt, schema, **kwargs)

        work = loop.run_in_executor(self._executor, invoke)
        try:
            try:
                raw = await asyncio.wait_for(
                    await_owned(work), timeout=max(1.0, timeout_seconds),
                )
            except (asyncio.CancelledError, TimeoutError):
                # Cancelling an asyncio Future cannot stop an active pool thread.
                # Keep ownership (and the enclosing execution lease) until the
                # provider call actually returns, then preserve the original error.
                await await_settled(asyncio.gather(work, return_exceptions=True), propagate_cancel=False)
                raise
        except asyncio.TimeoutError as exc:
            raise StructuredGenerationError(
                "MODEL_TIMEOUT",
                f"Structured model generation exceeded {timeout_seconds:g} seconds.",
            ) from exc
        except StructuredGenerationError:
            raise
        except Exception as exc:
            explicit_code = str(getattr(exc, "code", "") or "")
            message = str(exc)
            lowered = message.lower()
            if explicit_code:
                code = explicit_code
            elif (
                "invalid json returned" in lowered
                or "json response must be an object" in lowered
                or "unterminated string" in lowered
            ):
                code = "MODEL_OUTPUT_INVALID_JSON"
            elif "empty json content" in lowered or "empty content" in lowered:
                code = "MODEL_EMPTY_RESPONSE"
            elif "rate limit" in lowered or "429" in lowered:
                code = "MODEL_RATE_LIMITED"
            elif "timeout" in lowered or "timed out" in lowered:
                code = "MODEL_TIMEOUT"
            else:
                code = "MODEL_TRANSPORT_ERROR"
            raise StructuredGenerationError(
                code,
                message or code,
                retryable=code in {"MODEL_RATE_LIMITED", "MODEL_TIMEOUT"},
                audit={
                    "provider": gateway.provider_name,
                    "model": gateway.model,
                    "usage": dict(getattr(exc, "usage", {}) or {}),
                    "finishReason": getattr(exc, "finish_reason", None),
                    "capability": self.describe_model().model_dump(
                        by_alias=True, mode="json", exclude_none=True
                    ),
                    "outputPolicy": (
                        ModelOutputPolicy.EXPLICIT.value
                        if max_output_tokens is not None
                        else ModelOutputPolicy.API_CONTROLLED.value
                    ),
                    "requestedOutputTokens": max_output_tokens,
                    "effectiveOutputTokens": max_output_tokens,
                    "effectiveReason": (
                        "explicit_request" if max_output_tokens is not None else "provider_default"
                    ),
                    "outputExhausted": code == "MODEL_OUTPUT_EXHAUSTED",
                },
            ) from exc

        data = raw.get("data")
        if not isinstance(data, dict) or not data:
            raise StructuredGenerationError(
                "MODEL_EMPTY_RESPONSE",
                "Structured model generation returned no JSON object.",
            )
        return StructuredGenerationResult(
            data=data,
            provider=str(raw.get("provider") or gateway.provider_name),
            model=str(raw.get("model") or gateway.model),
            latencyMs=int(raw.get("latency_ms") or 0),
            promptVersion=prompt_version,
            usage=dict(raw.get("usage") or {}),
            finishReason=str(raw.get("finish_reason") or "") or None,
            capability=self.describe_model(),
            outputPolicy=(
                ModelOutputPolicy.EXPLICIT
                if max_output_tokens is not None
                else ModelOutputPolicy.API_CONTROLLED
            ),
            requestedOutputTokens=max_output_tokens,
            effectiveOutputTokens=max_output_tokens,
            effectiveReason=("explicit_request" if max_output_tokens is not None else "provider_default"),
        )


__all__ = ["GatewayStructuredGenerationRuntime"]

"""Per-request OpenAI-compatible model execution."""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from openai import AsyncOpenAI

from app.llm.capabilities import (
    adapt_chat_completion_parameters,
    normalize_deepseek_model,
    normalize_model_request,
    normalize_thinking_mode,
    provider_model_capabilities,
)
from app.llm.contracts import (
    ProviderProtocolMessage,
    ProviderRawResult,
    ProviderToolCall,
    ThinkingMode,
)
from app.llm.chat_stream import ChatStreamEvent, ChatStreamEventType
from app.llm.provider_conversation import (
    ProviderConversationManager,
    configured_provider_conversation_manager,
)


REASONING_INSTRUCTIONS = {
    ThinkingMode.STANDARD: "先分析关键条件并核验结论，再给出结构清晰的回答。",
    ThinkingMode.DEEP: "进行深入、全面的分析，检查边界条件和潜在反例后再回答。",
}


def resolve_system_runtime_config(model: str = "") -> tuple[str, str, str]:
    """Resolve a request-level model override against server-managed credentials."""
    from app.config import settings

    deepseek_key = (settings.DEEPSEEK_API_KEY or "").strip()
    if deepseek_key:
        return (
            normalize_deepseek_model(model.strip() or settings.DEEPSEEK_MODEL),
            settings.DEEPSEEK_BASE_URL,
            deepseek_key,
        )

    qwen_key = (settings.DASHSCOPE_API_KEY or settings.QWEN_API_KEY or "").strip()
    if qwen_key:
        return (
            model.strip() or settings.QWEN_MODEL_BALANCED,
            settings.QWEN_BASE_URL,
            qwen_key,
        )

    raise ValueError("服务端尚未配置可用的模型 API Key")


async def list_system_runtime_models() -> Dict[str, object]:
    """Read the real model catalog without exposing the server API key."""
    default_model, base_url, api_key = resolve_system_runtime_config()
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    try:
        page = await client.models.list()
        models = sorted(
            {
                normalize_deepseek_model(item.id)
                for item in page.data
                if getattr(item, "id", "")
            }
        )
    except Exception:
        # Some OpenAI-compatible providers do not implement GET /models.
        models = [default_model]
    finally:
        await client.close()

    if default_model not in models:
        models.insert(0, default_model)
    return {"models": models, "default_model": default_model}


def validate_runtime_config(model: str, base_url: str, api_key: str) -> None:
    if not model.strip() or not base_url.strip() or not api_key.strip():
        raise ValueError("模型、API 地址和 API Key 均不能为空")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("API 地址必须是有效的 http:// 或 https:// 地址")
    if parsed.username or parsed.password:
        raise ValueError("API 地址不能包含用户名或密码")


def apply_reasoning_instruction(messages: List[Dict[str, str]], effort: str) -> List[Dict[str, str]]:
    instruction = REASONING_INSTRUCTIONS.get(normalize_thinking_mode(effort))
    if not instruction:
        return messages
    result = [dict(message) for message in messages]
    for message in result:
        if message.get("role") == "system":
            message["content"] = f"{message.get('content', '')}\n\n回答策略：{instruction}".strip()
            return result
    return [{"role": "system", "content": f"回答策略：{instruction}"}, *result]


def build_messages(
    text: str,
    context: Optional[List[Dict[str, str]]],
    reasoning_effort: str,
) -> List[Dict[str, str]]:
    messages = [
        {"role": item["role"], "content": item["content"]}
        for item in (context or [])
        if item.get("role") in {"system", "user", "assistant"} and item.get("content")
    ]
    if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != text:
        messages.append({"role": "user", "content": text})
    return apply_reasoning_instruction(messages, reasoning_effort)


def completion_options(model: str, base_url: str, reasoning_effort: str) -> Dict:
    return adapt_chat_completion_parameters(
        model=model,
        base_url=base_url,
        thinking_mode=reasoning_effort,
    ).parameters


async def generate_with_runtime_model(
    *,
    text: str,
    context: Optional[List[Dict[str, str]]],
    model: str,
    base_url: str,
    api_key: str,
    reasoning_effort: str = "off",
) -> Dict:
    validate_runtime_config(model, base_url, api_key)
    started = time.perf_counter()
    normalized = normalize_model_request(model, reasoning_effort)
    adapted = adapt_chat_completion_parameters(
        model=normalized.effective_model,
        base_url=base_url,
        thinking_mode=normalized.effective_thinking_mode,
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    try:
        response = await client.chat.completions.create(
            model=normalized.effective_model,
            messages=build_messages(text, context, normalized.effective_thinking_mode.value),
            **adapted.parameters,
        )
        content = response.choices[0].message.content if response.choices else ""
        usage = _usage_values(getattr(response, "usage", None))
        return {
            "text": content or "",
            "confidence": 0.95,
            "tokens_used": usage["total_tokens"] or 0,
            "input_tokens": usage["input_tokens"],
            "reasoning_tokens": usage["reasoning_tokens"],
            "output_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": normalized.effective_model,
            "requested_model": normalized.requested_model,
            "requested_thinking_mode": normalized.requested_thinking_mode.value,
            "thinking_mode": adapted.effective_thinking_mode.value,
            "reasoning_effort": adapted.effective_reasoning_effort,
            "resolution_reasons": [
                *normalized.resolution_reasons,
                *adapted.resolution_reasons,
            ],
        }
    finally:
        await client.close()


async def generate_tool_conversation_with_runtime_model(
    *,
    text: str,
    context: Optional[List[Dict[str, str]]],
    conversation_id: str,
    tools: Sequence[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Any],
    model: str,
    base_url: str,
    api_key: str,
    reasoning_effort: str = "off",
    provider: str = "openai-compatible",
    context_revision: Optional[str] = None,
    conversation_manager: Optional[ProviderConversationManager] = None,
) -> Dict[str, Any]:
    """Execute one complete Provider tool branch without exposing raw protocol state."""
    validate_runtime_config(model, base_url, api_key)
    if not conversation_id.strip():
        raise ValueError("conversation_id is required for Provider tool continuation")
    if not tools:
        raise ValueError("tools are required for Provider tool continuation")
    capabilities = provider_model_capabilities(model, base_url)
    if not capabilities.supports_tools:
        raise ValueError(f"Model {model} does not support tools")
    manager = conversation_manager or configured_provider_conversation_manager()
    if manager is None:
        raise RuntimeError("Provider conversation state is disabled")

    started = time.perf_counter()
    normalized = normalize_model_request(model, reasoning_effort)
    adapted = adapt_chat_completion_parameters(
        model=normalized.effective_model,
        base_url=base_url,
        thinking_mode=normalized.effective_thinking_mode,
    )
    business_messages = [
        ProviderProtocolMessage(role=message["role"], content=message.get("content"))
        for message in build_messages(text, context, normalized.effective_thinking_mode.value)
    ]
    prepared = await manager.prepare(
        conversation_id=conversation_id,
        provider=provider,
        model=normalized.effective_model,
        business_messages=business_messages,
        requested_context_revision=context_revision,
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    usage_totals = {
        "input_tokens": 0,
        "reasoning_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    async def invoke(messages: list[dict]) -> ProviderRawResult:
        completion = await client.chat.completions.create(
            model=normalized.effective_model,
            messages=messages,
            tools=list(tools),
            **adapted.parameters,
        )
        raw_result = _extract_provider_raw_result(completion)
        values = _usage_values(getattr(completion, "usage", None))
        for key in usage_totals:
            usage_totals[key] += values[key] or 0
        return raw_result

    try:
        round_result = await manager.execute_tool_round(prepared, invoke, tool_executor)
    finally:
        await client.close()
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "text": round_result.raw_result.content,
        "confidence": 0.95,
        "tokens_used": usage_totals["total_tokens"],
        **usage_totals,
        "latency_ms": latency_ms,
        "model": normalized.effective_model,
        "requested_model": normalized.requested_model,
        "requested_thinking_mode": normalized.requested_thinking_mode.value,
        "thinking_mode": adapted.effective_thinking_mode.value,
        "reasoning_effort": adapted.effective_reasoning_effort,
        "context_revision": round_result.context_revision,
        "context_reset_reason": round_result.context_reset_reason,
        "tool_names": round_result.tool_names,
        "resolution_reasons": [
            *normalized.resolution_reasons,
            *adapted.resolution_reasons,
        ],
    }


async def stream_with_runtime_model(
    *,
    text: str,
    context: Optional[List[Dict[str, str]]],
    model: str,
    base_url: str,
    api_key: str,
    reasoning_effort: str = "off",
    request_id: str = "anonymous",
) -> AsyncIterator[ChatStreamEvent]:
    validate_runtime_config(model, base_url, api_key)
    started = time.perf_counter()
    normalized = normalize_model_request(model, reasoning_effort)
    adapted = adapt_chat_completion_parameters(
        model=normalized.effective_model,
        base_url=base_url,
        thinking_mode=normalized.effective_thinking_mode,
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    sequence = 0
    reasoning_started_at: Optional[float] = None
    reasoning_ended = False
    usage = {"input_tokens": None, "reasoning_tokens": None, "output_tokens": None, "total_tokens": None}

    def event(event_type: ChatStreamEventType, data: Optional[Dict[str, Any]] = None) -> ChatStreamEvent:
        nonlocal sequence
        sequence += 1
        return ChatStreamEvent(
            event=event_type,
            request_id=request_id,
            sequence=sequence,
            data=data or {},
        )

    try:
        stream_parameters = dict(adapted.parameters)
        if provider_model_capabilities(normalized.effective_model, base_url).supports_stream_usage:
            stream_parameters.setdefault("stream_options", {"include_usage": True})
        stream = await client.chat.completions.create(
            model=normalized.effective_model,
            messages=build_messages(text, context, normalized.effective_thinking_mode.value),
            stream=True,
            **stream_parameters,
        )
        if adapted.effective_thinking_mode != ThinkingMode.DISABLED:
            reasoning_started_at = time.perf_counter()
            yield event(
                ChatStreamEventType.REASONING_START,
                {
                    "requestedThinkingMode": normalized.requested_thinking_mode.value,
                    "effectiveThinkingMode": adapted.effective_thinking_mode.value,
                    "effectiveReasoningEffort": adapted.effective_reasoning_effort,
                },
            )
        async for chunk in stream:
            chunk_usage = _usage_values(getattr(chunk, "usage", None))
            for key, value in chunk_usage.items():
                if value is not None:
                    usage[key] = value
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            reasoning_delta = getattr(delta, "reasoning_content", None)
            if reasoning_delta:
                yield event(ChatStreamEventType.REASONING_DELTA, {"delta": reasoning_delta})
            content_delta = getattr(delta, "content", None)
            if content_delta:
                if reasoning_started_at is not None and not reasoning_ended:
                    reasoning_ended = True
                    yield event(
                        ChatStreamEventType.REASONING_END,
                        {"reasoningPhaseMs": int((time.perf_counter() - reasoning_started_at) * 1000)},
                    )
                yield event(ChatStreamEventType.CONTENT_DELTA, {"delta": content_delta})
        if reasoning_started_at is not None and not reasoning_ended:
            reasoning_ended = True
            yield event(
                ChatStreamEventType.REASONING_END,
                {"reasoningPhaseMs": int((time.perf_counter() - reasoning_started_at) * 1000)},
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        yield event(
            ChatStreamEventType.USAGE,
            {
                "inputTokens": usage["input_tokens"],
                "reasoningTokens": usage["reasoning_tokens"],
                "outputTokens": usage["output_tokens"],
                "totalTokens": usage["total_tokens"],
                "latencyMs": latency_ms,
                "requestedModel": normalized.requested_model,
                "effectiveModel": normalized.effective_model,
                "requestedThinkingMode": normalized.requested_thinking_mode.value,
                "effectiveThinkingMode": adapted.effective_thinking_mode.value,
                "effectiveReasoningEffort": adapted.effective_reasoning_effort,
                "resolutionReasons": [
                    *normalized.resolution_reasons,
                    *adapted.resolution_reasons,
                ],
            },
        )
        yield event(
            ChatStreamEventType.DONE,
            {
                "status": "completed",
                "latencyMs": latency_ms,
                "requestedModel": normalized.requested_model,
                "effectiveModel": normalized.effective_model,
                "requestedThinkingMode": normalized.requested_thinking_mode.value,
                "effectiveThinkingMode": adapted.effective_thinking_mode.value,
                "effectiveReasoningEffort": adapted.effective_reasoning_effort,
            },
        )
    finally:
        await client.close()


def _usage_values(usage: Any) -> Dict[str, Optional[int]]:
    if usage is None:
        return {
            "input_tokens": None,
            "reasoning_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(usage, "reasoning_tokens", None)
    if reasoning_tokens is None and details is not None:
        reasoning_tokens = getattr(details, "reasoning_tokens", None)
    return {
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "reasoning_tokens": reasoning_tokens,
        "output_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _extract_provider_raw_result(completion: Any) -> ProviderRawResult:
    choice = completion.choices[0] if getattr(completion, "choices", None) else None
    message = getattr(choice, "message", None)
    tool_calls = []
    for tool_call in getattr(message, "tool_calls", None) or []:
        function = getattr(tool_call, "function", None)
        tool_calls.append(
            ProviderToolCall(
                id=str(getattr(tool_call, "id", "")),
                type=str(getattr(tool_call, "type", "function")),
                function={
                    "name": str(getattr(function, "name", "")),
                    "arguments": str(getattr(function, "arguments", "")),
                },
            )
        )
    usage = getattr(completion, "usage", None)
    raw_usage = usage.model_dump() if hasattr(usage, "model_dump") else {}
    return ProviderRawResult(
        content=str(getattr(message, "content", "") or ""),
        reasoning_content=getattr(message, "reasoning_content", None),
        tool_calls=tool_calls,
        raw_usage=raw_usage,
        raw_response_metadata={
            "finish_reason": getattr(choice, "finish_reason", None),
            "response_id": getattr(completion, "id", None),
        },
    )

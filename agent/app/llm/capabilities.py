from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.llm.contracts import ProviderModelCapabilities, ThinkingMode


DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
DEEPSEEK_LEGACY_MODELS = {
    "deepseek-chat": (DEEPSEEK_DEFAULT_MODEL, ThinkingMode.DISABLED),
    "deepseek-reasoner": (DEEPSEEK_DEFAULT_MODEL, ThinkingMode.STANDARD),
}

_THINKING_MODE_ALIASES = {
    "": ThinkingMode.DISABLED,
    "off": ThinkingMode.DISABLED,
    "none": ThinkingMode.DISABLED,
    "disabled": ThinkingMode.DISABLED,
    "false": ThinkingMode.DISABLED,
    "low": ThinkingMode.STANDARD,
    "medium": ThinkingMode.STANDARD,
    "standard": ThinkingMode.STANDARD,
    "high": ThinkingMode.DEEP,
    "xhigh": ThinkingMode.DEEP,
    "max": ThinkingMode.DEEP,
    "deep": ThinkingMode.DEEP,
}


@dataclass(frozen=True)
class NormalizedModelRequest:
    requested_model: str
    effective_model: str
    requested_thinking_mode: ThinkingMode
    effective_thinking_mode: ThinkingMode
    resolution_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AdaptedProviderRequest:
    parameters: Dict[str, Any]
    effective_thinking_mode: ThinkingMode
    effective_reasoning_effort: Optional[str]
    resolution_reasons: List[str] = field(default_factory=list)


def normalize_thinking_mode(value: str | ThinkingMode | None) -> ThinkingMode:
    if isinstance(value, ThinkingMode):
        return value
    normalized = str(value or "").strip().lower()
    try:
        return _THINKING_MODE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported thinking mode: {value}") from exc


def normalize_deepseek_model(model: str) -> str:
    normalized = (model or "").strip()
    legacy = DEEPSEEK_LEGACY_MODELS.get(normalized.lower())
    return legacy[0] if legacy else normalized


def normalize_model_request(
    model: str,
    thinking_mode: str | ThinkingMode | None = None,
) -> NormalizedModelRequest:
    requested_model = (model or "").strip()
    legacy = DEEPSEEK_LEGACY_MODELS.get(requested_model.lower())
    reasons: List[str] = []

    if legacy:
        effective_model, legacy_mode = legacy
        reasons.append(f"legacy_model_migrated:{requested_model}->{effective_model}")
        requested_mode = normalize_thinking_mode(thinking_mode) if thinking_mode is not None else legacy_mode
        if thinking_mode is None:
            reasons.append(f"legacy_thinking_mode_migrated:{legacy_mode.value}")
    else:
        effective_model = requested_model
        requested_mode = normalize_thinking_mode(thinking_mode)

    return NormalizedModelRequest(
        requested_model=requested_model,
        effective_model=effective_model,
        requested_thinking_mode=requested_mode,
        effective_thinking_mode=requested_mode,
        resolution_reasons=reasons,
    )


def provider_model_capabilities(model: str, base_url: str = "") -> ProviderModelCapabilities:
    normalized_model = normalize_deepseek_model(model).lower()
    normalized_url = (base_url or "").lower()

    if normalized_model.startswith("deepseek-v4") or "api.deepseek.com" in normalized_url:
        return ProviderModelCapabilities(
            supports_thinking=True,
            supported_thinking_modes={
                ThinkingMode.DISABLED,
                ThinkingMode.STANDARD,
                ThinkingMode.DEEP,
            },
            supports_reasoning_effort=True,
            supports_tools=True,
            supports_tool_choice_in_thinking=False,
            requires_reasoning_content_for_tool_calls=True,
            requires_non_null_assistant_content_for_tool_calls=True,
            supports_json_object=True,
            supports_json_schema=False,
            supports_developer_role=False,
            supports_stream_usage=True,
            max_tokens_field="max_tokens",
        )

    if "dashscope.aliyuncs.com" in normalized_url and "qwen3" in normalized_model:
        return ProviderModelCapabilities(
            supports_thinking=True,
            supported_thinking_modes={
                ThinkingMode.DISABLED,
                ThinkingMode.STANDARD,
                ThinkingMode.DEEP,
            },
            supports_reasoning_effort=False,
            supports_tools=True,
            supports_json_object=True,
            supports_stream_usage=True,
            max_tokens_field="max_tokens",
        )

    if normalized_model.startswith(("o1", "o3", "o4", "gpt-5")):
        return ProviderModelCapabilities(
            supports_thinking=True,
            supported_thinking_modes={
                ThinkingMode.DISABLED,
                ThinkingMode.STANDARD,
                ThinkingMode.DEEP,
            },
            supports_reasoning_effort=True,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=True,
            supports_developer_role=True,
            supports_stream_usage=True,
            max_tokens_field="max_completion_tokens",
        )

    return ProviderModelCapabilities()


def adapt_chat_completion_parameters(
    *,
    model: str,
    base_url: str,
    thinking_mode: str | ThinkingMode | None,
    parameters: Optional[Dict[str, Any]] = None,
) -> AdaptedProviderRequest:
    mode = normalize_thinking_mode(thinking_mode)
    capabilities = provider_model_capabilities(model, base_url)
    request = dict(parameters or {})
    reasons: List[str] = []

    if mode not in capabilities.supported_thinking_modes:
        if ThinkingMode.STANDARD in capabilities.supported_thinking_modes and mode == ThinkingMode.DEEP:
            reasons.append("thinking_mode_downgraded:deep->standard")
            mode = ThinkingMode.STANDARD
        elif ThinkingMode.DISABLED in capabilities.supported_thinking_modes:
            reasons.append(f"thinking_mode_downgraded:{mode.value}->disabled")
            mode = ThinkingMode.DISABLED
        else:
            raise ValueError(f"Model {model} does not support thinking mode {mode.value}")

    normalized_model = normalize_deepseek_model(model).lower()
    effective_effort: Optional[str] = None
    if normalized_model.startswith("deepseek-v4") or "api.deepseek.com" in base_url.lower():
        extra_body = dict(request.get("extra_body") or {})
        if mode == ThinkingMode.DISABLED:
            extra_body["thinking"] = {"type": "disabled"}
            request.pop("reasoning_effort", None)
        else:
            extra_body["thinking"] = {"type": "enabled"}
            effective_effort = "max" if mode == ThinkingMode.DEEP else "high"
            request["reasoning_effort"] = effective_effort
            for key in (
                "temperature",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
            ):
                request.pop(key, None)
            if not capabilities.supports_tool_choice_in_thinking:
                request.pop("tool_choice", None)
        request["extra_body"] = extra_body
    elif "dashscope.aliyuncs.com" in base_url.lower() and "qwen3" in normalized_model:
        extra_body = dict(request.get("extra_body") or {})
        if mode == ThinkingMode.DISABLED:
            extra_body["enable_thinking"] = False
        else:
            extra_body["enable_thinking"] = True
            extra_body["thinking_budget"] = 8192 if mode == ThinkingMode.DEEP else 4096
        request["extra_body"] = extra_body
    elif normalized_model.startswith(("o1", "o3", "o4", "gpt-5")):
        if mode != ThinkingMode.DISABLED:
            effective_effort = "high" if mode == ThinkingMode.DEEP else "medium"
            request["reasoning_effort"] = effective_effort
        else:
            request.pop("reasoning_effort", None)

    return AdaptedProviderRequest(
        parameters=request,
        effective_thinking_mode=mode,
        effective_reasoning_effort=effective_effort,
        resolution_reasons=reasons,
    )


__all__ = [
    "AdaptedProviderRequest",
    "DEEPSEEK_DEFAULT_MODEL",
    "DEEPSEEK_LEGACY_MODELS",
    "NormalizedModelRequest",
    "adapt_chat_completion_parameters",
    "normalize_deepseek_model",
    "normalize_model_request",
    "normalize_thinking_mode",
    "provider_model_capabilities",
]

from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.llm.capabilities import adapt_chat_completion_parameters, normalize_model_request
from app.llm.contracts import ProviderRawResult, ProviderToolCall


class LLMProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    provider_name = "openai-compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: float = 120.0):
        if not base_url:
            raise LLMProviderError("AGENTOS_LLM_BASE_URL is required for openai-compatible provider")
        if not api_key:
            raise LLMProviderError("AGENTOS_LLM_API_KEY is required for openai-compatible provider")
        if not model:
            raise LLMProviderError("AGENTOS_LLM_MODEL is required for openai-compatible provider")
        from openai import OpenAI

        normalized = normalize_model_request(model)
        self.base_url = base_url
        self.requested_model = normalized.requested_model
        self.model = normalized.effective_model
        self.default_thinking_mode = normalized.effective_thinking_mode
        self.timeout_seconds = timeout_seconds
        # One explicit request budget is easier to reason about than the SDK default
        # of three hidden attempts. Deep reasoning/report generation commonly needs
        # more than 30 seconds, so retries at that boundary only multiply latency.
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def generate_text(self, prompt: str, **kwargs) -> str:
        try:
            adapted = self._adapt_parameters(kwargs)
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a careful assistant. Return only the requested content."},
                    {"role": "user", "content": prompt},
                ],
                **adapted,
            )
            content = self._extract_raw_result(completion).content
            if not content:
                raise LLMProviderError("OpenAI-compatible provider returned empty content")
            return content
        except Exception as exc:
            raise LLMProviderError(f"OpenAI-compatible text generation failed: {exc}") from exc

    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        try:
            adapted = self._adapt_parameters(kwargs)
            adapted["response_format"] = {"type": "json_object"}
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._json_system_prompt(schema),
                    },
                    {"role": "user", "content": prompt},
                ],
                **adapted,
            )
            content = self._extract_raw_result(completion).content
            if not content:
                raise LLMProviderError("OpenAI-compatible provider returned empty JSON content")
            return self._parse_json(content)
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"OpenAI-compatible JSON generation failed: {exc}") from exc

    def _adapt_parameters(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        thinking_mode = kwargs.get("thinking_mode", kwargs.get("reasoning_effort", self.default_thinking_mode))
        parameters = {
            key: value
            for key, value in kwargs.items()
            if key not in {"thinking_mode", "reasoning_effort"} and value is not None
        }
        parameters.setdefault("temperature", 0.1)
        return adapt_chat_completion_parameters(
            model=self.model,
            base_url=self.base_url,
            thinking_mode=thinking_mode,
            parameters=parameters,
        ).parameters

    @staticmethod
    def _json_system_prompt(schema: Dict[str, Any]) -> str:
        schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        return (
            "Return one valid JSON object matching the supplied JSON Schema exactly. "
            "Do not wrap JSON in markdown fences or include explanatory text. "
            f"JSON Schema: {schema_text}"
        )

    @staticmethod
    def _extract_raw_result(completion: Any) -> ProviderRawResult:
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

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned, flags=re.IGNORECASE)
            if match:
                cleaned = match.group(1)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"Invalid JSON returned by provider: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMProviderError("Provider JSON response must be an object")
        return parsed


__all__ = ["LLMProviderError", "OpenAICompatibleProvider"]

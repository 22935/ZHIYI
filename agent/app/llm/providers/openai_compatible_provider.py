from __future__ import annotations

import json
import re
from typing import Any, Dict


class LLMProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    provider_name = "openai-compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0):
        if not base_url:
            raise LLMProviderError("AGENTOS_LLM_BASE_URL is required for openai-compatible provider")
        if not api_key:
            raise LLMProviderError("AGENTOS_LLM_API_KEY is required for openai-compatible provider")
        if not model:
            raise LLMProviderError("AGENTOS_LLM_MODEL is required for openai-compatible provider")
        from openai import OpenAI

        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_seconds)

    def generate_text(self, prompt: str, **kwargs) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a careful assistant. Return only the requested content."},
                    {"role": "user", "content": prompt},
                ],
                temperature=kwargs.get("temperature", 0.1),
            )
            content = completion.choices[0].message.content
            if not content:
                raise LLMProviderError("OpenAI-compatible provider returned empty content")
            return content
        except Exception as exc:
            raise LLMProviderError(f"OpenAI-compatible text generation failed: {exc}") from exc

    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Return only valid JSON. Do not wrap JSON in markdown fences."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=kwargs.get("temperature", 0.1),
            )
            content = completion.choices[0].message.content
            if not content:
                raise LLMProviderError("OpenAI-compatible provider returned empty JSON content")
            return self._parse_json(content)
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"OpenAI-compatible JSON generation failed: {exc}") from exc

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

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Protocol

from app.llm.config import LLMConfig
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.providers.openai_compatible_provider import LLMProviderError, OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    provider_name: str
    model: str

    def generate_text(self, prompt: str, **kwargs) -> str:
        ...

    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        ...


class LLMGateway:
    def __init__(self, config: Optional[LLMConfig] = None, provider: Optional[LLMProvider] = None):
        self.config = config or LLMConfig.from_env()
        self.provider = provider or self._build_provider(self.config)

    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "provider_name", self.config.provider)

    @property
    def model(self) -> str:
        return getattr(self.provider, "model", self.config.model)

    def generate_text(self, prompt: str, **kwargs) -> Dict[str, Any]:
        started = time.perf_counter()
        text = self.provider.generate_text(prompt, **kwargs)
        return {
            "text": text,
            "provider": self.provider_name,
            "model": self.model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        started = time.perf_counter()
        data = self.provider.generate_json(prompt, schema, **kwargs)
        return {
            "data": data,
            "provider": self.provider_name,
            "model": self.model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }

    @staticmethod
    def _build_provider(config: LLMConfig) -> LLMProvider:
        if config.provider == "mock":
            return MockLLMProvider()
        if config.provider in {"openai-compatible", "openai_compatible", "openai"}:
            if not config.api_key or not config.base_url or not config.model:
                logger.warning(
                    "AGENTOS_LLM_PROVIDER=%s is missing base_url/api_key/model; falling back to mock provider.",
                    config.provider,
                )
                return MockLLMProvider()
            try:
                return OpenAICompatibleProvider(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    model=config.model,
                    timeout_seconds=config.timeout_seconds,
                )
            except LLMProviderError as exc:
                logger.warning("Failed to initialize openai-compatible provider; falling back to mock provider. error=%s", exc)
                return MockLLMProvider()

        logger.warning("Unsupported AGENTOS_LLM_PROVIDER=%s; falling back to mock provider.", config.provider)
        return MockLLMProvider()


_default_gateway: Optional[LLMGateway] = None


def get_llm_gateway(*, refresh: bool = False) -> LLMGateway:
    global _default_gateway
    if refresh or _default_gateway is None:
        _default_gateway = LLMGateway()
    return _default_gateway


def set_llm_gateway_for_tests(gateway: Optional[LLMGateway]) -> None:
    global _default_gateway
    _default_gateway = gateway


__all__ = ["LLMGateway", "LLMProvider", "get_llm_gateway", "set_llm_gateway_for_tests"]

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "mock"
    base_url: str = ""
    api_key: str = ""
    model: str = "mock-contract-review"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider = (os.getenv("AGENTOS_LLM_PROVIDER") or "mock").strip().lower() or "mock"
        timeout_raw = (os.getenv("AGENTOS_LLM_TIMEOUT_SECONDS") or "30").strip()
        try:
            timeout_seconds = max(1.0, float(timeout_raw))
        except ValueError:
            timeout_seconds = 30.0
        return cls(
            provider=provider,
            base_url=(os.getenv("AGENTOS_LLM_BASE_URL") or "").strip(),
            api_key=(os.getenv("AGENTOS_LLM_API_KEY") or "").strip(),
            model=(os.getenv("AGENTOS_LLM_MODEL") or "mock-contract-review").strip() or "mock-contract-review",
            timeout_seconds=timeout_seconds,
        )


__all__ = ["LLMConfig"]

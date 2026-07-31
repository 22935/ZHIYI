from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "unavailable"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        timeout_raw = (os.getenv("AGENTOS_LLM_TIMEOUT_SECONDS") or "120").strip()
        try:
            timeout_seconds = max(1.0, float(timeout_raw))
        except ValueError:
            timeout_seconds = 120.0

        # 一级配置：显式的 AGENTOS_LLM_* 始终优先。
        provider = (os.getenv("AGENTOS_LLM_PROVIDER") or "").strip().lower()
        base_url = (os.getenv("AGENTOS_LLM_BASE_URL") or "").strip()
        api_key = _read_secret_setting("AGENTOS_LLM_API_KEY")
        model = (os.getenv("AGENTOS_LLM_MODEL") or "").strip()

        # 二级配置：未显式设置 AGENTOS_LLM_* 时，自动从项目既有的
        # DEEPSEEK_* / DASHSCOPE_* 配置回落映射，让真实模型直接生效，
        # 避免“.env 配了 key 却静默走 mock”的体验陷阱。
        if not provider:
            resolved = _resolve_provider_fallback()
            if resolved:
                provider, base_url, api_key, model = resolved
            else:
                provider = "unavailable"

        return cls(
            provider=provider or "unavailable",
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )


def _resolve_provider_fallback() -> tuple[str, str, str, str] | None:
    """从项目既有的供应商环境变量推断 openai-compatible 配置。

    返回 (provider, base_url, api_key, model)；无可用 key 时返回 None。
    DeepSeek 优先（文本主引擎），其次通义千问。
    """
    deepseek_key = _read_secret_setting("DEEPSEEK_API_KEY")
    deepseek_enabled = (os.getenv("DEEPSEEK_ENABLED") or "true").strip().lower() not in {"false", "0", "off", "no"}
    if deepseek_key and not deepseek_key.startswith("your-") and deepseek_enabled:
        return (
            "openai-compatible",
            (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").strip(),
            deepseek_key,
            (os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip(),
        )

    qwen_key = _read_secret_setting("DASHSCOPE_API_KEY") or _read_secret_setting("QWEN_API_KEY")
    if qwen_key and not qwen_key.startswith("your-"):
        return (
            "openai-compatible",
            (os.getenv("QWEN_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip(),
            qwen_key,
            (os.getenv("QWEN_MODEL_BALANCED") or "qwen-plus").strip(),
        )

    return None


def _read_secret_setting(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if value:
        return value

    file_path = (os.getenv(f"{name}_FILE") or "").strip()
    if not file_path:
        return ""
    try:
        return Path(file_path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


__all__ = ["LLMConfig"]

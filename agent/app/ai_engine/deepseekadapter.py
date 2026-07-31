"""
DeepSeek API适配器
使用OpenAI兼容模式调用DeepSeek大模型
DeepSeek作为文本生成主引擎，响应速度快，成本低
"""
import logging
from typing import Any, Dict, Optional
from openai import OpenAI

from app.llm.capabilities import adapt_chat_completion_parameters, normalize_model_request

logger = logging.getLogger(__name__)


class DeepSeekAdapter:
    """DeepSeek API适配器（OpenAI兼容模式）"""

    def __init__(self, api_key: str, model_name: str = "deepseek-v4-flash",
                 base_url: str = "https://api.deepseek.com/v1"):
        normalized = normalize_model_request(model_name)
        self.api_key = api_key
        self.requested_model_name = normalized.requested_model
        self.model_name = normalized.effective_model
        self.default_thinking_mode = normalized.effective_thinking_mode
        self.base_url = base_url
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        global _deepseek_init_logged
        if not _deepseek_init_logged:
            logger.info(f"DeepSeek adapter initialized: model={self.model_name}, base_url={base_url}")
            _deepseek_init_logged = True

    def chat(self, messages: list, temperature: float = 0.7,
             max_tokens: int = 4096, stream: bool = False,
             thinking_mode: Optional[str] = None, **kwargs):
        """非流式对话"""
        parameters = self._adapt_parameters(
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            thinking_mode=thinking_mode,
            kwargs=kwargs,
        )
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **parameters,
        )
        return response

    def chat_stream(self, messages: list, temperature: float = 0.7,
                    max_tokens: int = 4096,
                    thinking_mode: Optional[str] = None, **kwargs):
        """流式对话生成器"""
        parameters = self._adapt_parameters(
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            thinking_mode=thinking_mode,
            kwargs=kwargs,
        )
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **parameters,
        )
        for chunk in response:
            yield chunk

    def _adapt_parameters(
        self,
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
        thinking_mode: Optional[str],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        parameters = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }
        return adapt_chat_completion_parameters(
            model=self.model_name,
            base_url=self.base_url,
            thinking_mode=thinking_mode or self.default_thinking_mode,
            parameters=parameters,
        ).parameters

    def get_model_name(self) -> str:
        return self.model_name


_deepseek_init_logged = False

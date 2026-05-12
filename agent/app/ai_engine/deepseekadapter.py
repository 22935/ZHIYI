"""
DeepSeek API适配器
使用OpenAI兼容模式调用DeepSeek大模型
DeepSeek作为文本生成主引擎，响应速度快，成本低
"""
import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


class DeepSeekAdapter:
    """DeepSeek API适配器（OpenAI兼容模式）"""

    def __init__(self, api_key: str, model_name: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com/v1"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        global _deepseek_init_logged
        if not _deepseek_init_logged:
            logger.info(f"DeepSeek adapter initialized: model={model_name}, base_url={base_url}")
            _deepseek_init_logged = True

    def chat(self, messages: list, temperature: float = 0.7,
             max_tokens: int = 4096, stream: bool = False, **kwargs):
        """非流式对话"""
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs
        )
        return response

    def chat_stream(self, messages: list, temperature: float = 0.7,
                    max_tokens: int = 4096, **kwargs):
        """流式对话生成器"""
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )
        for chunk in response:
            yield chunk

    def get_model_name(self) -> str:
        return self.model_name


_deepseek_init_logged = False

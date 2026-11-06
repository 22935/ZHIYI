"""
AI服务
封装麒麟AI SDK调用
集成创新功能：情感感知、数字人等
"""
import logging
from typing import Dict, List, Optional
from app.ai_engine.kylin_sdk.client import KylinAIClient
from app.ai_engine.model_runtime import (
    apply_reasoning_instruction,
    generate_with_runtime_model,
    resolve_system_runtime_config,
)

logger = logging.getLogger(__name__)

class AIService:
    """AI服务类"""
    
    def __init__(self):
        """初始化AI服务"""
        self.client = KylinAIClient()
    
    async def generate_text(
        self,
        text: str,
        role_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        thinking_mode: str = "disabled",
    ) -> Dict:
        """
        生成文本回复

        Args:
            text: 用户输入文本
            role_id: 角色ID（可选）
            context: 对话上下文（可选）

        Returns:
            包含text、confidence、tokens_used的字典
        """
        try:
            if model and not base_url and not api_key:
                model, base_url, api_key = resolve_system_runtime_config(model)

            if model or base_url or api_key:
                return await generate_with_runtime_model(
                    text=text,
                    context=context,
                    model=model or "",
                    base_url=base_url or "",
                    api_key=api_key or "",
                    reasoning_effort=thinking_mode,
                )

            if thinking_mode != "disabled":
                prompt_messages = apply_reasoning_instruction(
                    [{"role": "user", "content": text}], thinking_mode
                )
                text = "\n".join(item["content"] for item in prompt_messages)
            response = await self.client.generate_text(
                text=text,
                role_id=role_id,
                context=context
            )

            return {
                "text": response.get("text", ""),
                "confidence": response.get("confidence", 0.85),
                "tokens_used": response.get("tokens_used", 0),
                "emotion_aware": False
            }
        except Exception as e:
            logger.error(f"文本生成失败: {e}", exc_info=True)
            if model or base_url or api_key:
                raise
            # 返回默认回复
            return {
                "text": f"抱歉，我暂时无法处理这个问题。错误: {str(e)}",
                "confidence": 0.5,
                "emotion_aware": False
            }
    
    async def recognize_speech(
        self, 
        audio_data: bytes,
        language: str = "zh-CN",
        format: str = "wav",
        sample_rate: int = 16000
    ) -> Dict:
        """
        语音识别（支持重试机制）
        
        Args:
            audio_data: 音频数据
            language: 语言代码（默认zh-CN）
            format: 音频格式（默认wav）
            sample_rate: 采样率（默认16000）
        
        Returns:
            包含text和confidence的字典
        """
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                response = await self.client.recognize_speech(
                    audio_data,
                    language=language,
                    format=format,
                    sample_rate=sample_rate
                )
                
                # 检查响应是否成功
                if response.get("success", False) or response.get("text"):
                    return {
                        "text": response.get("text", ""),
                        "confidence": response.get("confidence", 0.85),
                        "success": True
                    }
                else:
                    # 如果响应不成功且还有重试机会，继续重试
                    if attempt < max_retries - 1:
                        logger.warning(f"语音识别失败，重试 {attempt + 1}/{max_retries}")
                        import asyncio
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        return {
                            "text": "",
                            "confidence": 0.0,
                            "success": False,
                            "error": "识别失败"
                        }
            except Exception as e:
                logger.error(f"语音识别失败 (尝试 {attempt + 1}/{max_retries}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    return {
                        "text": "",
                        "confidence": 0.0,
                        "success": False,
                        "error": str(e)
                    }
        
        return {
            "text": "",
            "confidence": 0.0,
            "success": False,
            "error": "超过最大重试次数"
        }
    
    async def synthesize_speech(
        self, 
        text: str, 
        voice: str = "default",
        speed: float = 1.0,
        pitch: float = 1.0
    ) -> bytes:
        """
        语音合成（支持重试机制）
        
        Args:
            text: 要合成的文本
            voice: 语音类型（default/female/male/gentle/lively）
            speed: 语速（0.5-2.0，默认1.0）
            pitch: 音调（0.5-2.0，默认1.0）
        
        Returns:
            音频数据（字节流）
        """
        max_retries = 3
        retry_delay = 0.5
        
        # 限制参数范围
        speed = max(0.5, min(2.0, speed))
        pitch = max(0.5, min(2.0, pitch))
        
        for attempt in range(max_retries):
            try:
                audio_data = await self.client.synthesize_speech(
                    text=text, 
                    voice=voice,
                    speed=speed,
                    pitch=pitch
                )
                
                # 检查音频数据是否有效
                if audio_data and len(audio_data) > 0:
                    logger.info(f"语音合成成功: {len(text)} 字符, 音频长度: {len(audio_data)} 字节")
                    return audio_data
                else:
                    # 如果音频数据为空且还有重试机会，继续重试
                    if attempt < max_retries - 1:
                        logger.warning(f"语音合成返回空数据，重试 {attempt + 1}/{max_retries}")
                        import asyncio
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        logger.error("语音合成返回空数据，超过最大重试次数")
                        return b""
            except Exception as e:
                logger.error(f"语音合成失败 (尝试 {attempt + 1}/{max_retries}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error("语音合成失败，超过最大重试次数")
                    return b""
        
        return b""

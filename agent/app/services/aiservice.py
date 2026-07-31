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

# 可选导入创新功能（如果可用）
try:
    from app.services.emotionawareservice import emotion_aware_service
    EMOTION_AWARE_AVAILABLE = True
except ImportError:
    EMOTION_AWARE_AVAILABLE = False
    logger.warning("情感感知服务未加载")

try:
    from app.services.digitalhumanservice import digital_human_service
    DIGITAL_HUMAN_AVAILABLE = True
except ImportError:
    DIGITAL_HUMAN_AVAILABLE = False
    logger.warning("数字人服务未加载")

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
        enable_emotion_aware: bool = False,
        audio_features: Optional[Dict] = None,
        facial_features: Optional[Dict] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        thinking_mode: str = "disabled",
    ) -> Dict:
        """
        生成文本回复（支持情感感知）
        
        Args:
            text: 用户输入文本
            role_id: 角色ID（可选）
            context: 对话上下文（可选）
            enable_emotion_aware: 是否启用情感感知（默认False）
            audio_features: 音频特征（可选，用于情感分析）
            facial_features: 面部特征（可选，用于情感分析）
        
        Returns:
            包含text、confidence、emotion、animation等的字典
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

            # 如果启用情感感知
            if enable_emotion_aware and EMOTION_AWARE_AVAILABLE:
                # 获取角色配置（简化实现）
                base_role = {
                    "role_id": role_id or "default",
                    "personality": "友好、专业",
                    "knowledge_domain": []
                }
                
                # 生成情感感知回复
                emotion_response = emotion_aware_service.generate_emotion_aware_response(
                    question=text,
                    user_emotion=None,  # 自动分析
                    base_role=base_role,
                    text=text,
                    audio_features=audio_features,
                    facial_features=facial_features
                )
                
                # 如果启用数字人，生成动画
                animation = None
                if DIGITAL_HUMAN_AVAILABLE and role_id:
                    try:
                        animation = digital_human_service.active_avatars.get(role_id, {}).get("avatar_data", {}).get("animations", {})
                    except:
                        pass
                
                return {
                    "text": emotion_response.get("text", ""),
                    "confidence": 0.85,
                    "tokens_used": emotion_response.get("tokens_used", 0),
                    "emotion": emotion_response.get("emotion", {}),
                    "user_emotion": emotion_response.get("user_emotion", {}),
                    "animation": emotion_response.get("animation", animation),
                    "emotion_aware": True
                }
            else:
                # 标准文本生成
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

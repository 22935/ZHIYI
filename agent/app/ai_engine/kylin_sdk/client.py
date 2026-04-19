"""
麒麟AI SDK客户端封装
支持麒麟OS原生SDK和通义千问大模型
智能选择：麒麟操作系统使用麒麟SDK，其他系统使用通义千问
"""
import logging
from typing import List, Dict, Optional
import httpx
import platform

logger = logging.getLogger(__name__)

# 全局标志：是否已打印API key警告
_api_key_warning_printed = False
# 全局标志：是否已打印通义千问启用日志
_qwen_enabled_logged = False
# 全局标志：是否已打印麒麟SDK日志
_kylin_sdk_logged = False

class KylinSDKClient:
    """麒麟AI SDK客户端 - 智能选择SDK策略"""
    
    def __init__(self, api_key: str, api_endpoint: str, timeout: int = 30, qwen_api_key: Optional[str] = None, qwen_model: str = "qwen-plus"):
        """
        初始化客户端
        
        Args:
            api_key: 麒麟AI API密钥（兼容旧配置）
            api_endpoint: API端点
            timeout: 超时时间（秒）
            qwen_api_key: 通义千问API密钥（如果提供则使用通义千问）
            qwen_model: 通义千问模型名称
        """
        self.api_key = api_key
        self.api_endpoint = api_endpoint.rstrip('/')
        self.timeout = timeout
        
        # 检测操作系统类型
        self.is_kylin_os = self._detect_kylin_os()
        
        # 智能选择SDK策略
        self.qwen_adapter = None
        self.use_qwen = False
        self.use_kylin_sdk = False
        
        # 策略选择：麒麟OS优先使用麒麟SDK，其他系统使用通义千问
        if self.is_kylin_os and self.api_key:
            # 麒麟OS系统：尝试使用麒麟SDK
            try:
                global _kylin_sdk_logged
                if not _kylin_sdk_logged:
                    logger.info(f"检测到麒麟操作系统，使用麒麟AI SDK")
                    _kylin_sdk_logged = True
                self.use_kylin_sdk = True
            except Exception as e:
                logger.warning(f"麒麟SDK初始化失败: {e}，降级到通义千问")
                self.use_kylin_sdk = False
        
        # 如果不是麒麟OS或麒麟SDK不可用，使用通义千问
        if not self.use_kylin_sdk and qwen_api_key:
            try:
                from app.ai_engine.qwenadapter import QwenAdapter
                # 从配置读取base_url（如果可用）
                qwen_base_url = None
                try:
                    from app.config import settings
                    qwen_base_url = getattr(settings, 'QWEN_BASE_URL', None)
                except:
                    pass
                self.qwen_adapter = QwenAdapter(qwen_api_key, qwen_model, base_url=qwen_base_url)
                self.use_qwen = True
                # 只在第一次启用时打印日志，避免重复
                global _qwen_enabled_logged
                if not _qwen_enabled_logged:
                    logger.info(f"使用通义千问大模型: {qwen_model}")
                    _qwen_enabled_logged = True
            except Exception as e:
                logger.warning(f"初始化通义千问适配器失败: {e}，将使用模拟响应")
        
        # 创建HTTP客户端（用于其他API调用）
        self.client = httpx.AsyncClient(
            base_url=self.api_endpoint,
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json"
            },
            timeout=timeout
        )
        
        if not self.use_qwen and not self.use_kylin_sdk:
            logger.info(f"SDK未配置，将使用模拟响应模式")
    
    def _detect_kylin_os(self) -> bool:
        """
        检测是否为麒麟操作系统
        
        Returns:
            是否为麒麟OS
        """
        try:
            # 检测Windows系统
            if platform.system().lower() == 'windows':
                return False
            
            # 导入麒麟OS集成服务（如果可用）
            try:
                from app.services.kylinosintegration import kylin_os_integration_service
                return kylin_os_integration_service.is_kylin_os
            except ImportError:
                pass
            
            # 回退检测方法
            import os
            
            # 检查麒麟特有文件
            if os.path.exists('/etc/kylin-release'):
                return True
            
            # 检查系统信息
            try:
                system_info = platform.platform().lower()
                if 'kylin' in system_info or 'neokylin' in system_info:
                    return True
            except:
                pass
            
            return False
        except Exception as e:
            logger.debug(f"检测麒麟OS失败: {e}")
            return False
    
    async def generate_text(
        self,
        prompt: str,
        context: Optional[List[Dict[str, str]]] = None,
        role_config: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """
        文本生成
        
        Args:
            prompt: 输入提示
            context: 对话上下文
            role_config: 角色配置
            **kwargs: 其他参数
        
        Returns:
            生成的文本和元数据
        """
        try:
            # 如果启用了通义千问，使用通义千问API
            if self.use_qwen and self.qwen_adapter:
                # 提取系统提示词
                system_prompt = None
                if role_config:
                    system_prompt = role_config.get("system_prompt")
                    if not system_prompt and role_config.get("role_id"):
                        # 尝试从后端获取角色信息并构建提示词
                        try:
                            async with httpx.AsyncClient(timeout=5.0) as client:
                                backend_url = "http://localhost:8080"
                                role_response = await client.get(f"{backend_url}/roles/{role_config.get('role_id')}")
                                if role_response.status_code == 200:
                                    role_data = role_response.json()
                                    system_prompt = self._build_role_system_prompt(role_data)
                                else:
                                    # 如果获取失败，使用默认配置，但也要强调基于麒麟操作系统
                                    system_prompt = f"你是一个专业的AI助手，角色ID: {role_config.get('role_id')}。当用户要求你介绍自己时，你必须说：'我是基于麒麟操作系统而实现的AI助手'，然后介绍你的专业职能、擅长领域和服务能力。绝对不要介绍你是什么AI模型（如Qwen、通义千问等）或底层技术。"
                        except Exception as e:
                            logger.debug(f"无法获取角色信息: {e}")
                            # 如果获取失败，使用默认配置，但也要强调基于麒麟操作系统
                            system_prompt = f"你是一个专业的AI助手，角色ID: {role_config.get('role_id')}。当用户要求你介绍自己时，你必须说：'我是基于麒麟操作系统而实现的AI助手'，然后介绍你的专业职能、擅长领域和服务能力。绝对不要介绍你是什么AI模型（如Qwen、通义千问等）或底层技术。"
                
                # 转换上下文格式（如果需要）
                qwen_context = None
                if context:
                    qwen_context = []
                    for msg in context:
                        if isinstance(msg, dict):
                            # 确保格式正确
                            if "role" in msg and "content" in msg:
                                qwen_context.append({
                                    "role": msg["role"],
                                    "content": msg["content"]
                                })
                            else:
                                # 兼容旧格式
                                qwen_context.append({
                                    "role": "user",
                                    "content": str(msg)
                                })
                        else:
                            qwen_context.append({
                                "role": "user",
                                "content": str(msg)
                            })
                
                # 调用通义千问API
                result = await self.qwen_adapter.generate(
                    prompt=prompt,
                    context=qwen_context,
                    system_prompt=system_prompt,
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 2000),
                    top_p=kwargs.get("top_p", 0.9),
                    request_timeout=kwargs.get("request_timeout", 10),
                )
                
                logger.debug(f"通义千问生成成功: {len(result.get('text', ''))} 字符")
                return result
            
            # 如果配置了麒麟AI API密钥，尝试调用麒麟AI API
            if self.api_key and self.api_endpoint:
                try:
                    # 构建请求体（根据麒麟AI API文档调整）
                    request_body = {
                        "prompt": prompt,
                        "temperature": kwargs.get("temperature", 0.7),
                        "max_tokens": kwargs.get("max_tokens", 2000),
                        "top_p": kwargs.get("top_p", 0.9)
                    }
                    
                    # 如果有上下文，添加到请求中
                    if context:
                        request_body["context"] = context
                    
                    # 如果有角色配置，添加到请求中
                    if role_config:
                        if role_config.get("system_prompt"):
                            request_body["system_prompt"] = role_config.get("system_prompt")
                        if role_config.get("role_id"):
                            request_body["role_id"] = role_config.get("role_id")
                    
                    # 调用麒麟AI API（根据实际API文档调整endpoint路径）
                    # 常见的API路径：/v1/chat/completions, /api/v1/generate, /generate 等
                    api_path = "/v1/chat/completions"  # 可根据实际API文档修改
                    
                    response = await self.client.post(
                        api_path,
                        json=request_body
                    )
                    response.raise_for_status()
                    result_data = response.json()
                    
                    # 解析响应（根据实际API响应格式调整）
                    # 常见的响应格式：
                    # - {"text": "...", "confidence": 0.95}
                    # - {"choices": [{"message": {"content": "..."}}]}
                    # - {"result": {"text": "...", "confidence": 0.95}}
                    
                    text = ""
                    confidence = 0.95
                    tokens_used = 0
                    
                    # 尝试多种响应格式
                    if "text" in result_data:
                        text = result_data["text"]
                        confidence = result_data.get("confidence", 0.95)
                        tokens_used = result_data.get("tokens_used", 0)
                    elif "choices" in result_data and len(result_data["choices"]) > 0:
                        # OpenAI格式
                        choice = result_data["choices"][0]
                        if "message" in choice:
                            text = choice["message"].get("content", "")
                        else:
                            text = choice.get("text", "")
                        tokens_used = result_data.get("usage", {}).get("total_tokens", 0)
                    elif "result" in result_data:
                        # 嵌套结果格式
                        result = result_data["result"]
                        text = result.get("text", "")
                        confidence = result.get("confidence", 0.95)
                        tokens_used = result.get("tokens_used", 0)
                    elif "content" in result_data:
                        # 简单格式
                        text = result_data["content"]
                        confidence = result_data.get("confidence", 0.95)
                    else:
                        # 尝试直接获取第一个字符串值
                        logger.warning(f"未识别的API响应格式: {result_data}")
                        text = str(result_data)
                    
                    logger.info(f"麒麟AI API调用成功: {len(text)} 字符")
                    return {
                        "text": text,
                        "confidence": confidence,
                        "tokens_used": tokens_used
                    }
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"麒麟AI API调用失败 (HTTP {e.response.status_code}): {e.response.text}")
                    # API调用失败，降级到模拟响应
                except Exception as e:
                    logger.error(f"麒麟AI API调用异常: {e}", exc_info=True)
                    # API调用失败，降级到模拟响应
            
            # 否则使用模拟响应（开发模式）
            logger.warning("使用模拟响应模式（未配置API密钥）")
            logger.warning("如需使用真实AI，请配置以下任一选项：")
            logger.warning("1. DASHSCOPE_API_KEY 或 QWEN_API_KEY（推荐，使用通义千问）")
            logger.warning("2. KYLIN_AI_API_KEY 和 KYLIN_AI_ENDPOINT（使用麒麟AI API）")
            return {
                "text": f"这是对'{prompt}'的AI回复（模拟）。如需使用真实AI，请配置API密钥。",
                "confidence": 0.95,
                "tokens_used": 150
            }
            
        except Exception as e:
            logger.error(f"Text generation error: {e}", exc_info=True)
            raise
    
    async def recognize_speech(
        self,
        audio_data: bytes,
        language: str = "zh-CN",
        **kwargs
    ) -> Dict:
        """
        语音识别（使用阿里云ASR API）
        
        Args:
            audio_data: 音频数据
            language: 语言代码
            **kwargs: 其他参数
        
        Returns:
            识别的文本和元数据
        """
        try:
            # 如果启用了通义千问，尝试使用语音适配器
            if self.use_qwen and self.qwen_adapter and self.api_key:
                try:
                    from app.ai_engine.speechadapter import SpeechAdapter
                    speech_adapter = SpeechAdapter(self.api_key)
                    result = await speech_adapter.recognize_speech(
                        audio_data=audio_data,
                        language=language,
                        **kwargs
                    )
                    await speech_adapter.close()
                    return result
                except Exception as e:
                    logger.warning(f"使用语音适配器失败: {e}，尝试其他方式")
            
            # 如果配置了麒麟AI API密钥，尝试调用麒麟AI ASR API
            if self.api_key and self.api_endpoint:
                try:
                    # 构建请求（根据麒麟AI API文档调整）
                    # 通常ASR API需要multipart/form-data格式上传音频文件
                    import base64
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    
                    request_body = {
                        "audio": audio_base64,
                        "language": language,
                        "format": kwargs.get("format", "wav")  # 根据实际API文档调整
                    }
                    
                    # 调用麒麟AI ASR API（根据实际API文档调整endpoint路径）
                    # 常见的API路径：/v1/asr, /api/v1/speech/recognize, /asr 等
                    api_path = "/v1/asr"  # 可根据实际API文档修改
                    
                    response = await self.client.post(
                        api_path,
                        json=request_body
                    )
                    response.raise_for_status()
                    result_data = response.json()
                    
                    # 解析响应（根据实际API响应格式调整）
                    text = ""
                    confidence = 0.92
                    
                    if "text" in result_data:
                        text = result_data["text"]
                        confidence = result_data.get("confidence", 0.92)
                    elif "result" in result_data:
                        result = result_data["result"]
                        text = result.get("text", "")
                        confidence = result.get("confidence", 0.92)
                    elif "transcription" in result_data:
                        text = result_data["transcription"]
                        confidence = result_data.get("confidence", 0.92)
                    else:
                        logger.warning(f"未识别的ASR API响应格式: {result_data}")
                        text = str(result_data)
                    
                    logger.info(f"麒麟AI ASR API调用成功: {len(text)} 字符")
                    return {
                        "text": text,
                        "confidence": confidence,
                        "duration": kwargs.get("duration", 0),
                        "success": True
                    }
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"麒麟AI ASR API调用失败 (HTTP {e.response.status_code}): {e.response.text}")
                except Exception as e:
                    logger.error(f"麒麟AI ASR API调用异常: {e}", exc_info=True)
            
            # 如果没有API密钥或适配器失败，使用模拟响应
            logger.warning("使用模拟响应，请配置以下任一选项以使用真实ASR：")
            logger.warning("1. DASHSCOPE_API_KEY 或 QWEN_API_KEY（推荐，使用通义千问ASR）")
            logger.warning("2. KYLIN_AI_API_KEY 和 KYLIN_AI_ENDPOINT（使用麒麟AI ASR API）")
            return {
                "text": "这是语音识别的结果（模拟）。如需使用真实ASR，请配置API密钥。",
                "confidence": 0.92,
                "duration": 3.5,
                "success": False,
                "note": "模拟响应"
            }
            
        except Exception as e:
            logger.error(f"Speech recognition error: {e}", exc_info=True)
            raise
    
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        pitch: float = 1.0,
        **kwargs
    ) -> bytes:
        """
        语音合成（使用阿里云TTS API）
        
        Args:
            text: 要合成的文本
            voice: 语音类型（default/zhitian_emo/zhitian_tech等）
            speed: 语速（0.5-2.0，默认1.0）
            pitch: 音调（0.5-2.0，默认1.0）
            **kwargs: 其他参数
        
        Returns:
            音频数据
        """
        try:
            # 如果启用了通义千问，尝试使用语音适配器
            if self.use_qwen and self.qwen_adapter and self.api_key:
                try:
                    from app.ai_engine.speechadapter import SpeechAdapter
                    speech_adapter = SpeechAdapter(self.api_key)
                    
                    # 映射默认语音类型
                    voice_map = {
                        "default": "zhitian_emo",  # 默认使用知甜情感语音
                        "zhitian_emo": "zhitian_emo",
                        "zhitian_tech": "zhitian_tech",
                        "zhimiao_emo": "zhimiao_emo"
                    }
                    mapped_voice = voice_map.get(voice, "zhitian_emo")
                    
                    audio_data = await speech_adapter.synthesize_speech(
                        text=text,
                        voice=mapped_voice,
                        speed=speed,
                        pitch=pitch,
                        **kwargs
                    )
                    await speech_adapter.close()
                    return audio_data
                except Exception as e:
                    logger.warning(f"使用语音适配器失败: {e}，尝试其他方式")
            
            # 如果配置了麒麟AI API密钥，尝试调用麒麟AI TTS API
            if self.api_key and self.api_endpoint:
                try:
                    # 构建请求（根据麒麟AI API文档调整）
                    request_body = {
                        "text": text,
                        "voice": voice,
                        "speed": speed,
                        "pitch": pitch,
                        "format": kwargs.get("format", "wav")  # 根据实际API文档调整
                    }
                    
                    # 调用麒麟AI TTS API（根据实际API文档调整endpoint路径）
                    # 常见的API路径：/v1/tts, /api/v1/speech/synthesize, /tts 等
                    api_path = "/v1/tts"  # 可根据实际API文档修改
                    
                    response = await self.client.post(
                        api_path,
                        json=request_body
                    )
                    response.raise_for_status()
                    
                    # 解析响应（根据实际API响应格式调整）
                    # 通常TTS API返回音频数据（base64编码或二进制）
                    audio_data = None
                    
                    if response.headers.get("content-type", "").startswith("audio/"):
                        # 直接返回音频二进制数据
                        audio_data = response.content
                    else:
                        # 尝试解析JSON响应中的音频数据
                        result_data = response.json()
                        if "audio" in result_data:
                            import base64
                            audio_base64 = result_data["audio"]
                            audio_data = base64.b64decode(audio_base64)
                        elif "data" in result_data:
                            import base64
                            audio_base64 = result_data["data"]
                            audio_data = base64.b64decode(audio_base64)
                        elif "result" in result_data:
                            result = result_data["result"]
                            if "audio" in result:
                                import base64
                                audio_base64 = result["audio"]
                                audio_data = base64.b64decode(audio_base64)
                    
                    if audio_data:
                        logger.info(f"麒麟AI TTS API调用成功: {len(audio_data)} 字节")
                        return audio_data
                    else:
                        logger.warning(f"未识别的TTS API响应格式，尝试直接返回内容")
                        return response.content
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"麒麟AI TTS API调用失败 (HTTP {e.response.status_code}): {e.response.text}")
                except Exception as e:
                    logger.error(f"麒麟AI TTS API调用异常: {e}", exc_info=True)
            
            # 如果没有API密钥或适配器失败，返回空音频
            logger.warning("使用模拟响应，请配置以下任一选项以使用真实TTS：")
            logger.warning("1. DASHSCOPE_API_KEY 或 QWEN_API_KEY（推荐，使用通义千问TTS）")
            logger.warning("2. KYLIN_AI_API_KEY 和 KYLIN_AI_ENDPOINT（使用麒麟AI TTS API）")
            
            # 生成简单的音频数据作为占位符（避免返回空数据）
            import wave
            import struct
            import io
            
            # 生成1秒的静音音频
            sample_rate = 16000
            duration = 1
            num_samples = sample_rate * duration
            
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                # 写入静音数据
                for _ in range(num_samples):
                    wav_file.writeframes(struct.pack('<h', 0))
            
            return wav_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Speech synthesis error: {e}", exc_info=True)
            raise
    
    async def close(self):
        """关闭客户端"""
        if self.qwen_adapter:
            await self.qwen_adapter.close()
        await self.client.aclose()


class KylinAIClient:
    """
    麒麟AI客户端包装类
    自动从配置读取参数，提供更便捷的初始化方式
    """
    
    def _build_role_system_prompt(self, role_data: Dict) -> str:
        """
        构建角色系统提示词
        
        Args:
            role_data: 角色数据字典，包含name、description、systemPrompt、personality等
        
        Returns:
            构建好的系统提示词字符串
        """
        name = role_data.get("name", "")
        description = role_data.get("description", "")
        system_prompt = role_data.get("systemPrompt") or role_data.get("system_prompt", "")
        personality = role_data.get("personality", {})
        
        # 构建基础提示词
        prompt_parts = []
        
        # 1. 角色身份
        if name:
            prompt_parts.append(f"你是{name}。")
        
        # 2. 角色描述
        if description:
            prompt_parts.append(f"{description}")
        
        # 3. 系统提示词（如果存在且不是默认的）
        if system_prompt and system_prompt.strip():
            # 如果system_prompt已经包含了完整的角色设定，直接使用
            if "你是" in system_prompt or "你是一位" in system_prompt or "你是一个" in system_prompt:
                prompt_parts.append(system_prompt)
            else:
                # 否则作为补充说明
                prompt_parts.append(f"你的职责和特点：{system_prompt}")
        
        # 4. 性格特点
        if personality:
            if isinstance(personality, dict):
                traits = [k for k, v in personality.items() if v]
                if traits:
                    prompt_parts.append(f"你的性格特点：{', '.join(traits)}。")
            elif isinstance(personality, str):
                if personality.strip():
                    prompt_parts.append(f"你的性格特点：{personality}。")
        
        # 5. 自我介绍指导（重要：必须强调基于麒麟操作系统）
        role_function = name if name else "AI助手"
        prompt_parts.append(f"当用户要求你介绍自己时，你必须这样介绍：'我是基于麒麟操作系统而实现的{role_function}助手'，然后介绍你的专业职能、擅长领域和服务能力。绝对不要介绍你是什么AI模型（如Qwen、通义千问等）或底层技术，只介绍你的角色功能和如何帮助用户。")
        
        # 6. 对话风格指导
        prompt_parts.append("在对话中，始终保持你的角色身份，用符合你角色特点的方式回答问题。")
        
        # 组合所有部分
        full_prompt = " ".join(prompt_parts)
        
        return full_prompt.strip()
    
    def __init__(self, api_key: Optional[str] = None, api_endpoint: Optional[str] = None, timeout: Optional[int] = None):
        """
        初始化客户端
        
        Args:
            api_key: API密钥（可选，默认从配置读取）
            api_endpoint: API端点（可选，默认从配置读取）
            timeout: 超时时间（可选，默认从配置读取）
        """
        # 尝试从配置导入
        try:
            from app.config import settings
            self._api_key = api_key or getattr(settings, 'KYLIN_AI_API_KEY', '')
            self._api_endpoint = api_endpoint or getattr(settings, 'KYLIN_AI_ENDPOINT', 'https://api.kylin.ai')
            self._timeout = timeout or getattr(settings, 'KYLIN_AI_TIMEOUT', 30)
        except Exception as e:
            logger.warning(f"无法从配置读取参数，使用默认值: {e}")
            self._api_key = api_key or ''
            self._api_endpoint = api_endpoint or 'https://api.kylin.ai'
            self._timeout = timeout or 30
        
        # 检查通义千问配置
        # 优先使用 DASHSCOPE_API_KEY（官方推荐），如果没有则使用 QWEN_API_KEY（兼容旧配置）
        # 所有配置都从主目录的.env文件读取（E:\Project\Kinlin_AI\.env），系统全局只保留这一个配置来源
        try:
            from app.config import settings
            dashscope_key = settings.DASHSCOPE_API_KEY or ''
            qwen_key = settings.QWEN_API_KEY or ''
            # 优先使用 DASHSCOPE_API_KEY
            self._qwen_api_key = dashscope_key if dashscope_key else qwen_key
            # 从.env文件读取模型配置
            self._qwen_model = settings.QWEN_MODEL_BALANCED
        except Exception as e:
            logger.warning(f"无法读取通义千问配置: {e}")
            self._qwen_api_key = ''
            self._qwen_model = 'qwen-plus'
        
        # 如果API key为空，记录信息
        global _api_key_warning_printed
        if not self._qwen_api_key and not self._api_key and not _api_key_warning_printed:
            logger.info("未配置API密钥，将使用模拟响应模式")
            logger.info("如需使用通义千问大模型，请在主目录的.env文件中设置:")
            logger.info("DASHSCOPE_API_KEY=sk-your_key")
            logger.info("配置文件路径: E:\\Project\\Kinlin_AI\\.env")
            logger.info("获取API密钥: https://dashscope.aliyuncs.com/")
            _api_key_warning_printed = True
        
        # 创建底层SDK客户端
        self._sdk_client = KylinSDKClient(
            api_key=self._api_key,
            api_endpoint=self._api_endpoint,
            timeout=self._timeout,
            qwen_api_key=self._qwen_api_key,
            qwen_model=self._qwen_model
        )
    
    async def generate_text(
        self,
        text: Optional[str] = None,
        prompt: Optional[str] = None,
        role_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> Dict:
        """
        生成文本回复
        
        Args:
            text: 用户输入文本（与prompt二选一）
            prompt: 输入提示（与text二选一）
            role_id: 角色ID（可选）
            context: 对话上下文（可选）
            **kwargs: 其他参数
        
        Returns:
            包含text、confidence、tokens_used等的字典
        """
        # 支持text和prompt两种参数名
        prompt_text = text or prompt
        if not prompt_text:
            raise ValueError("必须提供text或prompt参数")
        
        # 如果有role_id，尝试获取角色配置
        role_config = None
        if role_id:
            # 尝试从后端API获取角色信息
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # 尝试从后端获取角色信息（假设后端运行在8080端口）
                    backend_url = "http://localhost:8080"
                    role_response = await client.get(f"{backend_url}/roles/{role_id}")
                    if role_response.status_code == 200:
                        role_data = role_response.json()
                        # 构建完善的系统提示词
                        system_prompt = self._build_role_system_prompt(role_data)
                        role_config = {
                            "role_id": role_id,
                            "system_prompt": system_prompt,
                            "name": role_data.get("name", ""),
                            "description": role_data.get("description", ""),
                            "personality": role_data.get("personality", {}),
                            "style": "professional"
                        }
                    else:
                        # 如果获取失败，使用默认配置，但也要强调基于麒麟操作系统
                        role_config = {
                            "role_id": role_id,
                            "system_prompt": f"你是一个专业的AI助手，角色ID: {role_id}。当用户要求你介绍自己时，你必须说：'我是基于麒麟操作系统而实现的AI助手'，然后介绍你的专业职能、擅长领域和服务能力。绝对不要介绍你是什么AI模型（如Qwen、通义千问等）或底层技术。",
                            "style": "professional"
                        }
            except Exception as e:
                logger.debug(f"无法从后端获取角色信息: {e}，使用默认配置")
                # 如果获取失败，使用默认配置，但也要强调基于麒麟操作系统
                role_config = {
                    "role_id": role_id,
                    "system_prompt": f"你是一个专业的AI助手，角色ID: {role_id}。当用户要求你介绍自己时，你必须说：'我是基于麒麟操作系统而实现的AI助手'，然后介绍你的专业职能、擅长领域和服务能力。绝对不要介绍你是什么AI模型（如Qwen、通义千问等）或底层技术。",
                    "style": "professional"
                }
        
        return await self._sdk_client.generate_text(
            prompt=prompt_text,
            context=context,
            role_config=role_config,
            **kwargs
        )
    
    def _build_role_system_prompt(self, role_data: Dict) -> str:
        """
        构建角色系统提示词
        
        Args:
            role_data: 角色数据字典，包含name、description、systemPrompt、personality等
        
        Returns:
            构建好的系统提示词字符串
        """
        name = role_data.get("name", "")
        description = role_data.get("description", "")
        system_prompt = role_data.get("systemPrompt") or role_data.get("system_prompt", "")
        personality = role_data.get("personality", {})
        
        # 构建基础提示词
        prompt_parts = []
        
        # 1. 角色身份
        if name:
            prompt_parts.append(f"你是{name}。")
        
        # 2. 角色描述
        if description:
            prompt_parts.append(f"{description}")
        
        # 3. 系统提示词（如果存在且不是默认的）
        if system_prompt and system_prompt.strip():
            # 如果system_prompt已经包含了完整的角色设定，直接使用
            if "你是" in system_prompt or "你是一位" in system_prompt or "你是一个" in system_prompt:
                prompt_parts.append(system_prompt)
            else:
                # 否则作为补充说明
                prompt_parts.append(f"你的职责和特点：{system_prompt}")
        
        # 4. 性格特点
        if personality:
            if isinstance(personality, dict):
                traits = [k for k, v in personality.items() if v]
                if traits:
                    prompt_parts.append(f"你的性格特点：{', '.join(traits)}。")
            elif isinstance(personality, str):
                if personality.strip():
                    prompt_parts.append(f"你的性格特点：{personality}。")
        
        # 5. 自我介绍指导（重要：必须强调基于麒麟操作系统）
        role_function = name if name else "AI助手"
        prompt_parts.append(f"当用户要求你介绍自己时，你必须这样介绍：'我是基于麒麟操作系统而实现的{role_function}助手'，然后介绍你的专业职能、擅长领域和服务能力。绝对不要介绍你是什么AI模型（如Qwen、通义千问等）或底层技术，只介绍你的角色功能和如何帮助用户。")
        
        # 6. 对话风格指导
        prompt_parts.append("在对话中，始终保持你的角色身份，用符合你角色特点的方式回答问题。")
        
        # 组合所有部分
        full_prompt = " ".join(prompt_parts)
        
        return full_prompt.strip()
    
    async def recognize_speech(self, audio_data: bytes, **kwargs) -> Dict:
        """
        语音识别
        
        Args:
            audio_data: 音频数据
            **kwargs: 其他参数
        
        Returns:
            包含text和confidence的字典
        """
        return await self._sdk_client.recognize_speech(audio_data, **kwargs)
    
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
        pitch: float = 1.0,
        **kwargs
    ) -> bytes:
        """
        语音合成
        
        Args:
            text: 要合成的文本
            voice: 语音类型
            speed: 语速
            pitch: 音调
            **kwargs: 其他参数
        
        Returns:
            音频数据
        """
        return await self._sdk_client.synthesize_speech(
            text=text,
            voice=voice,
            speed=speed,
            pitch=pitch,
            **kwargs
        )
    
    async def close(self):
        """关闭客户端"""
        await self._sdk_client.close()

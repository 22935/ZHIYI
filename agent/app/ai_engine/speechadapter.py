"""
语音服务适配器
支持阿里云语音识别（ASR）和语音合成（TTS）API
使用DashScope SDK，与通义千问共用API密钥
"""
import logging
import base64
import httpx
import os
from typing import Dict, Optional, AsyncIterator
import json

# 尝试导入dashscope SDK
try:
    import dashscope
    from dashscope.audio.qwen_tts import SpeechSynthesizer
    DASHSCOPE_SDK_AVAILABLE = True
except ImportError:
    DASHSCOPE_SDK_AVAILABLE = False
    dashscope = None
    SpeechSynthesizer = None
    logging.warning("dashscope SDK未安装，请运行: pip install dashscope>=1.23.1")

logger = logging.getLogger(__name__)


class SpeechAdapter:
    """语音服务适配器（ASR + TTS）"""
    
    def __init__(self, api_key: str):
        """
        初始化语音服务适配器
        
        Args:
            api_key: DashScope API密钥（与通义千问共用）
        """
        self.api_key = api_key
        self.base_url = "https://dashscope.aliyuncs.com/api/v1"
        self.client = httpx.AsyncClient(timeout=60.0)
        
        # 设置环境变量，供dashscope SDK使用
        if api_key:
            os.environ["DASHSCOPE_API_KEY"] = api_key
        
        logger.info(f"语音服务适配器初始化成功 (SDK可用: {DASHSCOPE_SDK_AVAILABLE})")
    
    async def recognize_speech(
        self,
        audio_data: bytes,
        language: str = "zh-CN",
        format: str = "wav",
        sample_rate: int = 16000,
        **kwargs
    ) -> Dict:
        """
        语音识别（ASR）
        
        Args:
            audio_data: 音频数据（字节流）
            language: 语言代码（zh-CN/en-US等）
            format: 音频格式（wav/pcm/mp3等）
            sample_rate: 采样率（8000/16000等）
            **kwargs: 其他参数
        
        Returns:
            包含text、confidence、duration等的字典
        """
        try:
            # 阿里云DashScope ASR API端点
            # 注意：实际API端点可能不同，需要根据官方文档调整
            asr_url = f"{self.base_url}/services/aigc/asr/transcription"
            
            # 将音频数据编码为base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # 构建请求数据
            request_data = {
                "model": "paraformer-realtime-v2",  # 实时语音识别模型
                "input": {
                    "audio": audio_base64
                },
                "parameters": {
                    "format": format,
                    "sample_rate": sample_rate,
                    "language": language,
                    "enable_punctuation": True,  # 启用标点符号
                    "enable_word_timestamp": False  # 是否返回词级时间戳
                }
            }
            
            # 调用API
            response = await self.client.post(
                asr_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_data
            )
            
            # 检查响应状态
            response.raise_for_status()
            result = response.json()
            
            # 解析响应 - 兼容多种响应格式
            text = ""
            confidence = 0.0
            duration = 0.0
            
            # 尝试多种响应格式解析
            if result.get("output"):
                output = result["output"]
                # 格式1: output.sentence.text
                if isinstance(output, dict):
                    sentence = output.get("sentence", {})
                    if isinstance(sentence, dict):
                        text = sentence.get("text", "")
                        confidence = sentence.get("confidence", 0.0)
                    # 格式2: output.text (直接文本)
                    elif not text:
                        text = output.get("text", "")
                    duration = output.get("duration", 0.0)
            # 格式3: 直接在result中
            elif result.get("text"):
                text = result.get("text", "")
                confidence = result.get("confidence", 0.9)
                duration = result.get("duration", 0.0)
            
            if text:
                logger.info(f"语音识别成功: {len(text)} 字符, 置信度: {confidence:.2f}")
                return {
                    "text": text,
                    "confidence": confidence,
                    "duration": duration,
                    "language": language,
                    "success": True
                }
            else:
                error_msg = result.get("message", result.get("error", "API返回格式错误"))
                logger.error(f"语音识别API返回错误: {result}")
                raise ValueError(f"语音识别API错误: {error_msg}")
                
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_response = e.response.json()
                error_detail = error_response.get("message", error_response.get("error", str(e)))
            except:
                error_detail = str(e)
            
            logger.error(f"语音识别API HTTP错误: {error_detail}")
            raise Exception(f"语音识别API调用失败: {error_detail}")
        except Exception as e:
            logger.error(f"语音识别API调用异常: {e}", exc_info=True)
            raise
    
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "Cherry",
        speed: float = 1.0,
        pitch: float = 1.0,
        format: str = "wav",
        sample_rate: int = 16000,
        **kwargs
    ) -> bytes:
        """
        语音合成（TTS）- 使用通义千问qwen-tts模型
        
        Args:
            text: 要合成的文本
            voice: 语音类型（Cherry/Bella/Bob/Alex等）
            speed: 语速（0.5-2.0，默认1.0）
            pitch: 音调（0.5-2.0，默认1.0）
            format: 音频格式（wav/pcm/mp3）
            sample_rate: 采样率（8000/16000/24000）
            **kwargs: 其他参数
        
        Returns:
            音频数据（字节流）
        """
        try:
            # 限制参数范围
            speed = max(0.5, min(2.0, speed))
            pitch = max(0.5, min(2.0, pitch))
            
            # 映射前端语音类型到qwen-tts支持的voice
            # 通义千问qwen-tts支持的语音类型: Cherry, Serena, Ethan, Chelsie
            voice_mapping = {
                "default": "Cherry",    # 女声，温柔亲切
                "female": "Serena",     # 女声，优雅大方
                "male": "Ethan",        # 男声，稳重成熟
                "gentle": "Cherry",     # 温柔
                "lively": "Chelsie",    # 活泼
                "zhitian_emo": "Cherry", # 兼容旧配置，映射到Cherry
                "zhitian_tech": "Ethan"  # 兼容旧配置，映射到Ethan
            }
            actual_voice = voice_mapping.get(voice, "Cherry")  # 默认使用Cherry
            
            # 优先使用DashScope SDK（如果可用）
            if DASHSCOPE_SDK_AVAILABLE and self.api_key:
                try:
                    logger.info(f"使用qwen-tts SDK合成语音: {len(text)}字符, voice={actual_voice}, speed={speed}, pitch={pitch}")
                    
                    # 使用同步API（在异步函数中调用）
                    import asyncio
                    
                    def call_tts():
                        return SpeechSynthesizer.call(
                            model="qwen-tts",
                            api_key=self.api_key,
                            text=text,
                            voice=actual_voice,
                            format=format,
                            sample_rate=sample_rate,
                            rate=speed,
                            pitch_rate=pitch
                        )
                    
                    # 在线程池中执行同步调用
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, call_tts)
                    
                    logger.info(f"qwen-tts响应: status_code={response.status_code}")
                    
                    # 检查响应状态
                    if response.status_code == 200:
                        # 获取音频数据 - 修复DashScope SDK调用方式
                        try:
                            # 新版本DashScope SDK可能返回不同的数据结构
                            if hasattr(response, 'output') and hasattr(response.output, 'audio'):
                                audio_data = response.output.audio
                            elif hasattr(response, 'get_audio_data'):
                                audio_data = response.get_audio_data()
                            else:
                                # 尝试从响应中提取音频数据
                                audio_data = getattr(response, 'audio', None)
                                if not audio_data:
                                    # 检查响应内容
                                    response_data = response.__dict__
                                    audio_data = response_data.get('audio', None)
                            
                            if audio_data and len(audio_data) > 0:
                                logger.info(f"✅ qwen-tts语音合成成功: 音频长度={len(audio_data)}字节")
                                return audio_data
                            else:
                                logger.warning("qwen-tts返回空音频数据，尝试HTTP API")
                        except Exception as sdk_error:
                            logger.warning(f"DashScope SDK音频数据提取失败: {sdk_error}，尝试HTTP API")
                    else:
                        error_msg = getattr(response, 'message', '未知错误')
                        logger.warning(f"qwen-tts SDK错误 ({response.status_code}): {error_msg}，尝试HTTP API")
                        
                except Exception as sdk_error:
                    logger.warning(f"使用DashScope SDK失败: {sdk_error}，尝试HTTP API", exc_info=True)
            
            # 如果SDK不可用或失败，使用HTTP API（备用方案）
            tts_url = f"{self.base_url}/services/aigc/tts"
            
            # 构建请求数据（使用正确的API格式）
            # 通义千问TTS API需要task参数，使用正确的API格式
            request_data = {
                "model": "qwen-tts",
                "input": {
                    "text": text
                },
                "parameters": {
                    "voice": actual_voice,
                    "format": format,
                    "sample_rate": sample_rate,
                    "rate": speed,
                    "pitch_rate": pitch
                }
            }
            
            # 尝试使用task参数格式（兼容不同版本API）
            request_data_with_task = {
                "task": "text-to-speech",
                "model": "qwen-tts",
                "input": {
                    "text": text
                },
                "parameters": {
                    "voice": actual_voice,
                    "format": format,
                    "sample_rate": sample_rate,
                    "rate": speed,
                    "pitch_rate": pitch
                }
            }
            
            # 使用HTTP API调用，尝试不同的请求格式
            logger.info(f"使用HTTP API调用TTS: {tts_url}")
            
            # 首先尝试带task参数的请求格式
            try:
                response = await self.client.post(
                    tts_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "X-DashScope-Async": "disable"  # 禁用异步，直接返回音频
                    },
                    json=request_data_with_task
                )
                response.raise_for_status()
                logger.info("✅ 使用task参数格式调用成功")
            except Exception as e:
                # 如果带task参数失败，尝试不带task参数的格式
                logger.warning(f"使用task参数格式失败: {e}，尝试不带task参数格式")
                try:
                    response = await self.client.post(
                        tts_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "X-DashScope-Async": "disable"  # 禁用异步，直接返回音频
                        },
                        json=request_data
                    )
                    response.raise_for_status()
                    logger.info("✅ 使用标准格式调用成功")
                except Exception as e2:
                    # 如果两种格式都失败，抛出异常
                    logger.error(f"所有HTTP API格式调用失败: {e2}")
                    raise e2
            
            # TTS API可能直接返回音频流或返回JSON
            content_type = response.headers.get("content-type", "")
            
            if "audio" in content_type or "octet-stream" in content_type:
                # 直接返回音频数据
                audio_data = response.content
                logger.info(f"HTTP API语音合成成功: 音频长度={len(audio_data)}字节")
                return audio_data
            else:
                # 解析JSON响应
                result = response.json()
                
                # 解析响应 - 兼容多种响应格式
                audio_base64 = ""
                
                # 格式1: output.audio
                if result.get("output"):
                    output = result["output"]
                    if isinstance(output, dict):
                        audio_base64 = output.get("audio", "")
                
                # 格式2: 直接在result中
                if not audio_base64:
                    audio_base64 = result.get("audio", "")
                
                if audio_base64:
                    # 解码base64音频数据
                    audio_data = base64.b64decode(audio_base64)
                    logger.info(f"语音合成成功: {len(text)} 字符, 音频长度: {len(audio_data)} 字节")
                    return audio_data
                else:
                    error_msg = result.get("message", result.get("error", "API返回格式错误"))
                    logger.error(f"语音合成API返回错误: {result}")
                    raise ValueError(f"语音合成API错误: {error_msg}")
                
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_response = e.response.json()
                error_detail = error_response.get("message", error_response.get("error", str(e)))
            except:
                error_detail = str(e)
            
            logger.error(f"语音合成API HTTP错误: {error_detail}")
            raise Exception(f"语音合成API调用失败: {error_detail}")
        except Exception as e:
            logger.error(f"语音合成API调用异常: {e}", exc_info=True)
            raise
    
    async def recognize_speech_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        language: str = "zh-CN",
        format: str = "pcm",
        sample_rate: int = 16000,
        **kwargs
    ) -> AsyncIterator[Dict]:
        """
        流式语音识别（实时ASR）
        
        Args:
            audio_stream: 音频流（异步迭代器）
            language: 语言代码
            format: 音频格式
            sample_rate: 采样率
            **kwargs: 其他参数
        
        Yields:
            识别结果字典（包含partial_text和final_text）
        """
        try:
            # 阿里云流式ASR API端点
            stream_asr_url = f"{self.base_url}/services/aigc/asr/transcription-stream"
            
            # 构建请求头
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 流式发送音频数据
            async for audio_chunk in audio_stream:
                # 将音频块编码为base64
                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                
                # 构建请求数据
                request_data = {
                    "model": "paraformer-realtime-v2",
                    "input": {
                        "audio": audio_base64
                    },
                    "parameters": {
                        "format": format,
                        "sample_rate": sample_rate,
                        "language": language,
                        "enable_punctuation": True,
                        "enable_partial_result": True  # 启用部分结果
                    }
                }
                
                # 调用API
                response = await self.client.post(
                    stream_asr_url,
                    headers=headers,
                    json=request_data
                )
                
                response.raise_for_status()
                result = response.json()
                
                # 解析响应
                if result.get("output"):
                    output = result["output"]
                    sentence = output.get("sentence", {})
                    
                    yield {
                        "text": sentence.get("text", ""),
                        "confidence": sentence.get("confidence", 0.0),
                        "is_final": sentence.get("is_final", False),
                        "partial_text": sentence.get("partial_text", ""),
                        "success": True
                    }
                else:
                    error_msg = result.get("message", "API返回格式错误")
                    logger.warning(f"流式识别API返回错误: {error_msg}")
                    yield {
                        "text": "",
                        "confidence": 0.0,
                        "is_final": False,
                        "success": False,
                        "error": error_msg
                    }
                    
        except Exception as e:
            logger.error(f"流式语音识别异常: {e}", exc_info=True)
            yield {
                "text": "",
                "confidence": 0.0,
                "is_final": False,
                "success": False,
                "error": str(e)
            }
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


"""
通义千问API适配器
使用OpenAI兼容模式调用通义千问大模型
支持流式和非流式文本生成
"""
import asyncio
import os
import logging
from typing import List, Dict, Optional, AsyncIterator
from openai import OpenAI

logger = logging.getLogger(__name__)

# 全局标志：是否已打印初始化日志
_qwen_adapter_init_logged = False


class QwenAdapter:
    """通义千问API适配器（OpenAI兼容模式）"""
    
    def __init__(self, api_key: str, model_name: str = "qwen-plus", base_url: Optional[str] = None):
        """
        初始化通义千问适配器
        
        Args:
            api_key: 通义千问API密钥（DASHSCOPE_API_KEY）
            model_name: 模型名称 (qwen-turbo/qwen-plus/qwen-max/qwen3-max等)
            base_url: API基础URL（可选，默认从配置读取）
        """
        self.api_key = api_key
        self.model_name = model_name
        
        # 从配置读取base_url（如果未提供）
        # 所有配置都从主目录的.env文件读取（通过app.config.settings）
        if base_url is None:
            try:
                from app.config import settings
                self.base_url = settings.QWEN_BASE_URL
            except Exception as e:
                logger.warning(f"无法读取QWEN_BASE_URL配置: {e}，使用默认值")
                # 如果无法读取配置，使用默认值
                self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        else:
            self.base_url = base_url
        
        # 初始化OpenAI客户端（兼容模式）
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        
        # 只在第一次初始化时打印日志，避免重复
        global _qwen_adapter_init_logged
        if not _qwen_adapter_init_logged:
            logger.info(f"通义千问适配器初始化成功: 模型={model_name}, base_url={self.base_url}")
            _qwen_adapter_init_logged = True
    
    async def generate(
        self,
        prompt: str,
        context: Optional[List[Dict]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """
        生成文本（非流式）
        
        Args:
            prompt: 用户输入提示
            context: 对话上下文历史 [{"role": "user", "content": "..."}, ...]
            system_prompt: 系统提示词（角色设定等）
            **kwargs: 其他参数
                - temperature: 温度参数 (0-1)
                - max_tokens: 最大生成token数
                - top_p: top_p参数
        
        Returns:
            包含text、tokens_used、confidence的字典
        """
        try:
            messages: List[Dict[str, str]] = []

            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            if context:
                for msg in context:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
                    elif isinstance(msg, str):
                        messages.append({"role": "user", "content": msg})

            messages.append({"role": "user", "content": prompt})

            request_timeout = float(kwargs.get("request_timeout", os.getenv("QWEN_REQUEST_TIMEOUT", "60")))
            completion = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model_name,
                    messages=messages,
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 2000),
                    top_p=kwargs.get("top_p", 0.9),
                    stream=False,
                    timeout=request_timeout,
                ),
                timeout=request_timeout + 1.0,
            )

            text = completion.choices[0].message.content or ""
            tokens_used = completion.usage.total_tokens if completion.usage else 0

            logger.debug(f"通义千问生成成功: {len(text)} 字符, {tokens_used} tokens")

            return {
                "text": text,
                "tokens_used": tokens_used,
                "confidence": 0.95,
                "finish_reason": completion.choices[0].finish_reason or "stop",
            }

        except asyncio.TimeoutError as e:
            logger.warning("通义千问调用超时: %s", e)
            raise Exception("通义千问API调用超时")
        except Exception as e:
            logger.error(f"通义千问API调用异常: {e}", exc_info=True)
            raise Exception(f"通义千问API调用失败: {str(e)}")
    
    async def generate_stream(
        self,
        prompt: str,
        context: Optional[List[Dict]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式生成文本
        
        Args:
            prompt: 用户输入提示
            context: 对话上下文历史
            system_prompt: 系统提示词
            **kwargs: 其他参数
        
        Yields:
            生成的文本片段
        """
        try:
            # 构建消息列表（与generate方法相同）
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            
            if context:
                for msg in context:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                    elif isinstance(msg, str):
                        messages.append({
                            "role": "user",
                            "content": msg
                        })
            
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            # 流式调用OpenAI兼容API
            request_timeout = float(kwargs.get("request_timeout", os.getenv("QWEN_REQUEST_TIMEOUT", "60")))
            # Run the sync OpenAI-compatible client off the event loop so SSE can flush.
            completion = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model_name,
                    messages=messages,
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 2000),
                    top_p=kwargs.get("top_p", 0.9),
                    stream=True,  # 流式输出
                    timeout=request_timeout,
                ),
                timeout=request_timeout + 1.0,
            )
            
            # 流式返回文本片段
            sentinel = object()
            while True:
                chunk = await asyncio.to_thread(next, completion, sentinel)
                if chunk is sentinel:
                    break
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        
        except Exception as e:
            logger.error(f"通义千问流式生成错误: {e}", exc_info=True)
            raise
    
    async def generate_image(
        self,
        prompt: str,
        style: str = "realistic",
        size: str = "1024*1024",
        model: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """
        生成图像（使用通义万相多模态生成API）
        
        Args:
            prompt: 图像描述提示词
            style: 风格（realistic/anime/cartoon/artistic）
            size: 尺寸（1024*1024/1280*1280等，格式：宽*高）
            model: 模型名称（可选，默认从配置读取或使用wan2.6-t2i）
            **kwargs: 其他参数
                - negative_prompt: 负面提示词
                - prompt_extend: 是否扩展提示词（默认true）
                - watermark: 是否添加水印（默认false）
                - n: 生成数量（默认1）
                - seed: 随机种子
        
        Returns:
            包含image_url、image_base64等的字典
        """
        try:
            import httpx
            
            # 从配置读取模型（如果未提供）
            # 所有配置都从主目录的.env文件读取（通过app.config.settings）
            if model is None:
                try:
                    from app.config import settings
                    model = settings.IMAGE_GENERATION_MODEL
                except Exception as e:
                    logger.warning(f"无法读取IMAGE_GENERATION_MODEL配置: {e}，使用默认值")
                    model = 'wan2.6-t2i'  # 默认使用新模型
            
            # 判断使用新API还是旧API
            use_new_api = model.startswith('wan2.') or model.startswith('wanx-v1.5')
            
            if use_new_api:
                # 使用新的多模态生成API（推荐）
                api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
                
                # 解析尺寸（格式：宽*高）
                width, height = 1280, 1280
                if "*" in size:
                    try:
                        width, height = map(int, size.split("*"))
                    except:
                        logger.warning(f"无法解析尺寸格式: {size}，使用默认1280*1280")
                
                # 构建请求数据（新API格式）
                request_data = {
                    "model": model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "text": prompt
                                    }
                                ]
                            }
                        ]
                    },
                    "parameters": {
                        "negative_prompt": kwargs.get("negative_prompt", ""),
                        "prompt_extend": kwargs.get("prompt_extend", True),
                        "watermark": kwargs.get("watermark", False),
                        "n": kwargs.get("n", 1),
                        "size": f"{width}*{height}"
                    }
                }
                
                # 添加随机种子（如果提供）
                if kwargs.get("seed"):
                    request_data["parameters"]["seed"] = kwargs.get("seed")
            else:
                # 使用旧的文本到图像API（兼容旧模型）
                api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
                
                # 解析尺寸（格式：宽*高）
                width, height = 1024, 1024
                if "*" in size:
                    try:
                        width, height = map(int, size.split("*"))
                    except:
                        logger.warning(f"无法解析尺寸格式: {size}，使用默认1024*1024")
                
                # 构建请求数据（旧API格式）
                request_data = {
                    "model": model,
                    "input": {
                        "prompt": prompt
                    },
                    "parameters": {
                        "size": f"{width}*{height}",
                        "n": kwargs.get("n", 1)
                    }
                }
                
                # 添加随机种子（如果提供）
                if kwargs.get("seed"):
                    request_data["parameters"]["seed"] = kwargs.get("seed")
            
            # 创建HTTP客户端
            async with httpx.AsyncClient(timeout=120.0) as client:
                # 调用API
                response = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_data
                )
                
                # 检查响应状态
                response.raise_for_status()
                result = response.json()
                
                # 解析响应（新API和旧API的响应格式可能不同）
                if result.get("output"):
                    output = result["output"]
                    
                    # 新API格式1：choices/message/content格式（多模态生成API）
                    if output.get("choices") and len(output["choices"]) > 0:
                        choices = output["choices"]
                        first_choice = choices[0]
                        message = first_choice.get("message", {})
                        content = message.get("content", [])
                        
                        # 查找image类型的内容
                        image_url = ""
                        image_base64 = ""
                        
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "image":
                                    image_url = item.get("image", "")
                                    break
                        
                        if image_url:
                            logger.info(f"图像生成成功（新API格式）: prompt={prompt[:50]}...")
                            return {
                                "image_url": image_url,
                                "image_base64": image_base64,
                                "prompt": prompt,
                                "style": style,
                                "size": size,
                                "model": model,
                                "task_id": result.get("request_id", ""),
                                "success": True
                            }
                    
                    # 新API格式2：直接返回results数组
                    if output.get("results") and len(output["results"]) > 0:
                        # 处理多个结果（如果n>1）
                        results = output["results"]
                        image_results = []
                        
                        for img_result in results:
                            image_url = img_result.get("url", "")
                            image_base64 = img_result.get("image_base64", "")
                            
                            image_results.append({
                                "image_url": image_url,
                                "image_base64": image_base64
                            })
                        
                        # 返回第一个结果（兼容旧接口）
                        first_result = image_results[0]
                        
                        return {
                            "image_url": first_result["image_url"],
                            "image_base64": first_result["image_base64"],
                            "images": image_results,  # 所有生成的图像
                            "prompt": prompt,
                            "style": style,
                            "size": size,
                            "model": model,
                            "task_id": result.get("request_id", ""),
                            "success": True
                        }
                    
                    # 异步模式：返回任务ID
                    if output.get("task_id"):
                        task_id = output["task_id"]
                        logger.info(f"图像生成任务已提交，任务ID: {task_id}")
                        return {
                            "task_id": task_id,
                            "prompt": prompt,
                            "style": style,
                            "size": size,
                            "model": model,
                            "status": "processing",
                            "message": "图像生成中，请使用task_id查询结果",
                            "success": True
                        }
                    
                    # 如果都没有匹配，记录详细错误信息
                    error_msg = result.get("message", "API返回格式错误：未找到图像数据")
                    logger.error(f"通义万相API返回格式不匹配: {result}")
                    raise ValueError(f"通义万相API错误: {error_msg}")
                else:
                    error_msg = result.get("message", "API返回格式错误：缺少output字段")
                    logger.error(f"通义万相API返回错误: {result}")
                    raise ValueError(f"通义万相API错误: {error_msg}")
                    
        except Exception as e:
            logger.error(f"通义万相API调用异常: {e}", exc_info=True)
            raise Exception(f"通义万相API调用失败: {str(e)}")
    
    async def close(self):
        """
        关闭客户端
        注意：OpenAI客户端不需要显式关闭，但保留此方法以保持接口一致性
        """
        # OpenAI客户端会自动管理连接，无需手动关闭
        pass

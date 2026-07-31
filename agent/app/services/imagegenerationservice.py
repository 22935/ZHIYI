"""
图像生成服务
专门用于生成数字人形象和其他图像内容
支持通义万相（wanx）API
"""
import logging
import httpx
from typing import Dict, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class ImageGenerationService:
    """图像生成服务（使用通义万相wanx API）"""
    
    def __init__(self):
        """初始化图像生成服务"""
        # 获取API密钥（优先使用DASHSCOPE_API_KEY，兼容QWEN_API_KEY）
        # 所有配置都从主目录的.env文件读取（通过app.config.settings）
        try:
            dashscope_key = settings.DASHSCOPE_API_KEY or ''
            qwen_key = settings.QWEN_API_KEY or ''
            self.api_key = dashscope_key if dashscope_key else qwen_key
            self.model = settings.IMAGE_GENERATION_MODEL
        except Exception as e:
            logger.error(f"读取配置失败: {e}")
            self.api_key = ''
            self.model = 'wan2.6-t2i'  # 默认使用图像生成模型
        
        # 验证模型名称：如果是视频模型（t2v），自动改为图像模型（t2i）
        # 必须在设置base_url之前进行，确保使用正确的API
        if self.model and 't2v' in self.model.lower():
            logger.warning(f"检测到视频模型 {self.model}，自动切换为图像模型 wan2.6-t2i")
            self.model = 'wan2.6-t2i'
        
        # 根据模型判断使用新API还是旧API
        # wan2.x系列使用新的多模态生成API，其他使用旧的文本到图像API
        # 注意：必须在模型切换之后判断
        if self.model and (self.model.startswith('wan2.') or self.model.startswith('wanx-v1.5')):
            self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        else:
            self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        
        if not self.api_key:
            logger.warning("未配置图像生成API密钥（DASHSCOPE_API_KEY或QWEN_API_KEY），图像生成功能将不可用")
            logger.info("配置方法：通过对应 Secret 文件设置模型 API Key")
            logger.info("获取API密钥: https://dashscope.aliyuncs.com/")
        else:
            logger.info(f"图像生成服务已初始化，模型: {self.model}, API密钥已配置")
    
    async def generate_image(
        self,
        prompt: str,
        style: str = "realistic",
        size: str = "1280*1280",
        negative_prompt: str = "",
        **kwargs
    ) -> Dict:
        """
        生成图像（使用通义万相wanx API）
        
        Args:
            prompt: 图像描述提示词
            style: 风格（realistic/anime/cartoon/artistic）
            size: 尺寸（1024*1024/1024*768/768*1024等，格式：宽*高）
            **kwargs: 其他参数
                - seed: 随机种子（可选）
        
        Returns:
            包含image_url、image_base64等的字典
        """
        if not self.api_key:
            logger.warning("图像生成API密钥未配置，返回模拟结果")
            return {
                "image_url": "",
                "image_base64": "",
                "prompt": prompt,
                "style": style,
                "size": size,
                "success": False,
                "error": "API密钥未配置，请设置DASHSCOPE_API_KEY或QWEN_API_KEY",
                "note": "这是模拟结果，请配置API密钥以使用真实AI图像生成"
            }
        
        try:
            # 确保模型是图像模型（不是视频模型）
            current_model = self.model
            if current_model and 't2v' in current_model.lower():
                logger.warning(f"检测到视频模型 {current_model}，使用图像模型 wan2.6-t2i")
                current_model = 'wan2.6-t2i'
            
            # 判断使用新API还是旧API（使用当前模型判断）
            use_new_api = current_model and (current_model.startswith('wan2.') or current_model.startswith('wanx-v1.5'))
            
            # 如果使用新API，确保base_url正确
            if use_new_api and not self.base_url.endswith('multimodal-generation/generation'):
                logger.warning(f"检测到模型 {current_model} 应使用新API，但base_url不正确，更新为多模态生成API")
                self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            
            # 解析尺寸（格式：宽*高）- 提升默认尺寸以获得更高质量
            if use_new_api:
                # 新API默认尺寸（提升质量）
                width, height = 1280, 1280
            else:
                # 旧API默认尺寸
                width, height = 1024, 1024
                
            if "*" in size:
                try:
                    width, height = map(int, size.split("*"))
                except:
                    default_size = "1280*1280" if use_new_api else "1024*1024"
                    logger.warning(f"无法解析尺寸格式: {size}，使用默认{default_size}")
            
            # 根据API类型构建不同的请求数据（使用当前模型）
            if current_model and (current_model.startswith('wan2.') or current_model.startswith('wanx-v1.5')):
                # 新API格式（多模态生成）
                request_data = {
                    "model": current_model,
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
                        "negative_prompt": negative_prompt or kwargs.get("negative_prompt", ""),
                        "prompt_extend": kwargs.get("prompt_extend", True),
                        "watermark": kwargs.get("watermark", False),
                        "n": kwargs.get("n", 1),
                        "size": f"{width}*{height}",
                        "seed": kwargs.get("seed")  # 添加随机种子支持
                    }
                }
            else:
                # 旧API格式（文本到图像）
                request_data = {
                    "model": current_model,
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
                    self.base_url,
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
                                "model": current_model,
                                "task_id": result.get("request_id", ""),
                                "success": True
                            }
                    
                    # 新API格式2：直接返回results数组
                    if output.get("results") and len(output["results"]) > 0:
                        # 处理多个结果（如果n>1）
                        results = output["results"]
                        image_result = results[0]  # 取第一个结果
                        image_url = image_result.get("url", "")
                        image_base64 = image_result.get("image_base64", "")
                        
                        if image_url or image_base64:
                            logger.info(f"图像生成成功: prompt={prompt[:50]}...")
                            return {
                                "image_url": image_url,
                                "image_base64": image_base64,
                                "prompt": prompt,
                                "style": style,
                                "size": size,
                                "model": current_model,
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
                            "model": current_model,
                            "status": "processing",
                            "message": "图像生成中，请使用task_id查询结果",
                            "success": True
                        }
                    
                    # 如果都没有匹配，记录详细错误信息
                    error_msg = result.get("message", "API返回格式错误：未找到图像数据")
                    logger.error(f"通义万相API返回格式不匹配: output={output}")
                    raise ValueError(f"通义万相API错误: {error_msg}")
                else:
                    error_msg = result.get("message", "API返回格式错误：缺少output字段")
                    logger.error(f"通义万相API返回错误: {result}")
                    raise ValueError(f"通义万相API错误: {error_msg}")
                    
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_response = e.response.json()
                error_detail = error_response.get("message", str(e))
            except:
                error_detail = str(e)
            
            logger.error(f"通义万相API HTTP错误: {error_detail}")
            return {
                "image_url": "",
                "image_base64": "",
                "prompt": prompt,
                "style": style,
                "size": size,
                "success": False,
                "error": f"API调用失败: {error_detail}"
            }
        except Exception as e:
            logger.error(f"通义万相API调用异常: {e}", exc_info=True)
            return {
                "image_url": "",
                "image_base64": "",
                "prompt": prompt,
                "style": style,
                "size": size,
                "success": False,
                "error": f"图像生成失败: {str(e)}"
            }


# 全局图像生成服务实例
image_generation_service = ImageGenerationService()


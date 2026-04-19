# 麒麟SDK智能切换与增强RAG功能指南

## 📋 概述

本文档介绍Kinlin AI系统中新增的麒麟SDK智能切换功能和增强RAG文档处理功能。这些功能使系统能够根据运行环境智能选择最佳的AI SDK和文档处理工具，提供更好的用户体验和功能兼容性。

## 🎯 核心特性

### 1. 麒麟SDK智能切换

**功能描述**:
- 自动检测当前操作系统类型
- 麒麟OS：优先使用麒麟AI SDK
- 其他系统：自动使用通义千问大模型
- 支持降级策略：SDK不可用时自动切换到备用方案

**技术实现**:
```python
# 系统会自动检测操作系统
if is_kylin_os and kylin_api_key:
    # 使用麒麟SDK
    use_kylin_sdk = True
elif qwen_api_key:
    # 使用通义千问
    use_qwen = True
else:
    # 使用模拟响应
    use_mock = True
```

### 2. 增强文档处理

**支持的文档格式**:
- PDF：使用PyPDF2、pdfplumber、mineru、easydoc
- Word：使用python-docx
- Excel：使用openpyxl
- HTML：使用beautifulsoup4
- Markdown、TXT、JSON、XML：原生支持

**智能处理策略**:
- 自动选择最佳处理工具
- 多层降级保护
- 统一的API接口

### 3. RAG工具集成

**支持的RAG工具**:
- **内置RAG**：ChromaDB + sentence-transformers（默认）
- **RagFlow**：专业RAG框架（可选）
- **QAnything**：问答系统（可选）
- **FastGPT**：API服务（可选）

**智能选择机制**:
```
优先级：RagFlow > QAnything > FastGPT > 内置RAG
```

## 🔧 配置指南

### 1. 基础配置

**在主目录创建 `.env` 文件**:

```env
# ==================== AI SDK配置 ====================

# 麒麟AI SDK配置（麒麟OS用户）
KYLIN_AI_API_KEY=your_kylin_api_key
KYLIN_AI_ENDPOINT=https://api.kylin.ai
KYLIN_AI_TIMEOUT=30

# 通义千问配置（其他系统用户）
DASHSCOPE_API_KEY=sk-your_dashscope_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_BALANCED=qwen-plus
QWEN_MODEL_FAST=qwen-turbo
QWEN_MODEL_ADVANCED=qwen-max
QWEN_MODEL_LATEST=qwen3-max

# ==================== 文档处理配置 ====================

# 文档处理方法：auto/mineru/easydoc/pdfplumber/pypdf2
DOCUMENT_PROCESSOR_METHOD=auto
# 是否使用增强文档处理工具
DOCUMENT_PROCESSOR_USE_ENHANCED=true

# ==================== RAG工具配置 ====================

# RAG工具提供商：auto/ragflow/qanything/fastgpt/builtin
RAG_TOOL_PROVIDER=auto

# FastGPT API配置（可选）
FASTGPT_API_URL=https://your-fastgpt-api.com
FASTGPT_API_KEY=your_fastgpt_key

# RagFlow API配置（可选）
RAGFLOW_API_URL=https://your-ragflow-api.com
RAGFLOW_API_KEY=your_ragflow_key

# QAnything API配置（可选）
QANYTHING_API_URL=https://your-qanything-api.com
QANYTHING_API_KEY=your_qanything_key
```

### 2. 依赖安装

**基础依赖（必需）**:
```bash
cd agent
pip install -r requirements.txt
```

**可选增强工具**:
```bash
# 安装高级文档处理工具
pip install easydoc mineru

# 安装RAG工具
pip install ragflow qanything

# 或单独安装
pip install ragflow  # RagFlow
pip install qanything  # QAnything
```

## 🚀 使用示例

### 1. 智能SDK使用

**自动检测和切换**:
```python
from app.ai_engine.kylin_sdk.client import KylinAIClient

# 初始化客户端（会自动检测OS并选择SDK）
client = KylinAIClient()

# 生成文本（无需关心使用的是哪个SDK）
result = await client.generate_text(
    text="你好，请介绍一下你自己",
    role_id="lawyer"
)

print(result["text"])
# 输出：我是基于麒麟操作系统而实现的律师助手...
```

**检查当前使用的SDK**:
```python
from app.services.kylinosintegration import kylin_os_integration_service

# 检查是否为麒麟OS
if kylin_os_integration_service.is_kylin_os:
    print("当前运行在麒麟操作系统上，使用麒麟SDK")
else:
    print("当前运行在其他系统上，使用通义千问")

# 获取系统信息
system_info = kylin_os_integration_service.get_system_info()
print(system_info)
```

### 2. 文档处理使用

**基础使用**:
```python
from app.services.documentprocessoradvanced import document_processor_advanced

# 提取PDF文本（自动选择最佳工具）
with open("document.pdf", "rb") as f:
    file_data = f.read()

result = document_processor_advanced.extract_text(
    file_data=file_data,
    filename="document.pdf",
    use_enhanced=True
)

if result["success"]:
    print(f"使用工具: {result['method']}")
    print(f"提取的文本: {result['text'][:200]}...")
else:
    print(f"提取失败: {result['error']}")
```

**指定处理方法**:
```python
# 强制使用mineru处理PDF
result = document_processor_advanced.extract_text(
    file_data=file_data,
    filename="document.pdf",
    use_enhanced=True,
    method="mineru"  # 指定使用mineru
)
```

### 3. RAG工具使用

**基础搜索**:
```python
from app.services.ragtoolsintegration import rag_tools_integration

# 搜索相关文档（自动选择最佳RAG工具）
results = await rag_tools_integration.search(
    query="合同纠纷如何处理？",
    top_k=5,
    role_id="lawyer"  # 只搜索律师角色的知识库
)

for result in results:
    print(f"文档: {result['filename']}")
    print(f"相关度: {result['score']}")
    print(f"内容: {result['content'][:100]}...")
    print(f"使用工具: {result['method']}")
    print("---")
```

**指定RAG工具**:
```python
# 强制使用RagFlow
results = await rag_tools_integration.search(
    query="合同纠纷如何处理？",
    top_k=5,
    tool="ragflow"  # 指定使用RagFlow
)

# 强制使用内置RAG
results = await rag_tools_integration.search(
    query="合同纠纷如何处理？",
    top_k=5,
    tool="builtin"  # 指定使用内置RAG
)
```

**上传文档**:
```python
# 上传文档到知识库（自动选择最佳RAG工具）
with open("contract.pdf", "rb") as f:
    file_data = f.read()

doc_id = await rag_tools_integration.upload_document(
    file_data=file_data,
    filename="contract.pdf",
    metadata={"category": "contract", "year": 2024},
    role_id="lawyer"  # 上传到律师知识库
)

print(f"文档已上传，ID: {doc_id}")
```

## 📊 性能对比

### 文档处理性能

| 工具 | PDF解析速度 | 文本准确度 | 资源占用 |
|------|------------|-----------|---------|
| PyPDF2 | 快 | 中 | 低 |
| pdfplumber | 中 | 高 | 中 |
| mineru | 慢 | 很高 | 高 |
| easydoc | 中 | 高 | 中 |

**推荐策略**:
- 快速预览：使用PyPDF2
- 精确提取：使用pdfplumber或mineru
- 自动选择：设置`DOCUMENT_PROCESSOR_METHOD=auto`

### RAG工具性能

| 工具 | 检索速度 | 准确度 | 部署难度 |
|------|---------|-------|---------|
| 内置RAG | 快 | 中 | 易 |
| RagFlow | 中 | 高 | 中 |
| QAnything | 中 | 高 | 中 |
| FastGPT | 依赖网络 | 高 | 易（API） |

**推荐策略**:
- 快速开始：使用内置RAG
- 生产环境：使用RagFlow或QAnything
- 云服务：使用FastGPT API

## 🔍 故障排查

### 1. SDK切换问题

**问题**: 系统未正确检测麒麟OS
```python
# 手动检查检测结果
from app.services.kylinosintegration import kylin_os_integration_service

print(f"是否为麒麟OS: {kylin_os_integration_service.is_kylin_os}")
system_info = kylin_os_integration_service.get_system_info()
print(f"系统信息: {system_info}")
```

**解决方案**:
- 检查是否在麒麟OS上运行
- 检查 `/etc/kylin-release` 文件是否存在
- 查看日志了解检测过程

### 2. 文档处理问题

**问题**: 文档提取失败
```python
# 检查可用工具
from app.services.documentprocessoradvanced import document_processor_advanced

print("可用工具:", document_processor_advanced.available_tools)
```

**解决方案**:
- 安装缺失的依赖：`pip install pdfplumber python-docx openpyxl`
- 检查文件格式是否支持
- 尝试使用不同的处理方法

### 3. RAG工具问题

**问题**: RAG搜索无结果
```python
# 检查可用RAG工具
from app.services.ragtoolsintegration import rag_tools_integration

print("可用工具:", rag_tools_integration.available_tools)
print("当前工具:", rag_tools_integration.selected_tool)
```

**解决方案**:
- 确保已上传文档到知识库
- 检查role_id是否匹配
- 尝试使用不同的RAG工具
- 降级到内置RAG服务

## 📚 API参考

### KylinAIClient

```python
class KylinAIClient:
    async def generate_text(
        self,
        text: str = None,
        prompt: str = None,
        role_id: str = None,
        context: List[Dict] = None,
        **kwargs
    ) -> Dict:
        """
        生成文本回复
        
        Args:
            text: 用户输入文本
            prompt: 输入提示
            role_id: 角色ID
            context: 对话上下文
        
        Returns:
            {
                "text": "生成的文本",
                "confidence": 0.95,
                "tokens_used": 100
            }
        """
```

### DocumentProcessorAdvanced

```python
class DocumentProcessorAdvanced:
    def extract_text(
        self,
        file_data: bytes,
        filename: str,
        use_enhanced: bool = True,
        method: str = None
    ) -> Dict:
        """
        从文件中提取文本
        
        Args:
            file_data: 文件数据
            filename: 文件名
            use_enhanced: 是否使用增强工具
            method: 指定处理方法
        
        Returns:
            {
                "success": True,
                "text": "提取的文本",
                "method": "pdfplumber",
                "metadata": {...}
            }
        """
```

### RAGToolsIntegration

```python
class RAGToolsIntegration:
    async def search(
        self,
        query: str,
        top_k: int = 5,
        tool: str = None,
        role_id: str = None,
        **kwargs
    ) -> List[Dict]:
        """
        使用RAG工具搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            tool: 指定RAG工具
            role_id: 角色ID
        
        Returns:
            [
                {
                    "doc_id": "...",
                    "filename": "...",
                    "score": 0.85,
                    "content": "...",
                    "method": "ragflow"
                }
            ]
        """
    
    async def upload_document(
        self,
        file_data: bytes,
        filename: str,
        metadata: Dict = None,
        role_id: str = None,
        tool: str = None
    ) -> str:
        """
        上传文档到知识库
        
        Args:
            file_data: 文件数据
            filename: 文件名
            metadata: 元数据
            role_id: 角色ID
            tool: 指定RAG工具
        
        Returns:
            文档ID
        """
```

## 🎓 最佳实践

### 1. SDK选择策略

✅ **推荐做法**:
```python
# 让系统自动选择（推荐）
client = KylinAIClient()
result = await client.generate_text(text="...")
```

❌ **不推荐**:
```python
# 硬编码SDK选择（不推荐）
if platform.system() == "Linux":
    # 手动判断...
```

### 2. 文档处理策略

✅ **推荐做法**:
```python
# 使用自动选择
result = document_processor_advanced.extract_text(
    file_data=data,
    filename=filename,
    use_enhanced=True  # 启用增强工具
)

# 检查结果并处理失败
if not result["success"]:
    logger.error(f"文档处理失败: {result['error']}")
```

❌ **不推荐**:
```python
# 直接读取二进制（不推荐）
text = file_data.decode('utf-8')  # 可能失败
```

### 3. RAG工具策略

✅ **推荐做法**:
```python
# 使用try-except处理异常
try:
    results = await rag_tools_integration.search(
        query=query,
        top_k=5,
        role_id=role_id
    )
except Exception as e:
    logger.error(f"RAG搜索失败: {e}")
    results = []  # 使用空结果作为降级
```

❌ **不推荐**:
```python
# 不处理异常（不推荐）
results = await rag_tools_integration.search(...)
# 如果失败会抛出异常
```

## 🔐 安全建议

1. **API密钥管理**:
   - 不要在代码中硬编码API密钥
   - 使用环境变量或.env文件
   - .env文件已加入.gitignore，不会被提交

2. **文件上传**:
   - 验证文件类型和大小
   - 扫描恶意内容
   - 限制上传频率

3. **系统命令执行**:
   - KylinOS集成服务中的命令执行已有白名单限制
   - 不要执行未验证的用户输入

## 📞 技术支持

如遇到问题，请：
1. 查看日志文件：`agent/logs/kinlin_ai.log`
2. 检查配置文件：`.env`
3. 运行诊断命令：
   ```bash
   cd agent
   python -c "from app.services.kylinosintegration import kylin_os_integration_service; print(kylin_os_integration_service.get_system_info())"
   ```
4. 查看相关文档：
   - [项目概述](../README.md)
   - [API文档](./Kinlin-AI技术文档-05-API接口文档.md)
   - [部署指南](./Kinlin-AI技术文档-04-部署和运维指南.md)

---

**最后更新**: 2025-01-03  
**版本**: v1.0.0


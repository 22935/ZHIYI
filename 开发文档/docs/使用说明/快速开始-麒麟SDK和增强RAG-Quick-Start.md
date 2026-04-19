# 快速开始：麒麟SDK智能切换与增强RAG

本指南帮助你快速上手Kinlin AI的麒麟SDK智能切换和增强RAG功能。

## 🚀 5分钟快速开始

### 步骤1：环境准备

```bash
# 克隆项目（如果还没有）
git clone <repository_url>
cd Kinlin_AI

# 安装Python依赖
cd agent
pip install -r requirements.txt
```

### 步骤2：配置API密钥

**在项目主目录创建 `.env` 文件**:

```bash
# 复制模板文件
cp .env.example .env

# 编辑配置文件
# Windows: notepad .env
# Linux/Mac: vim .env
```

**最小配置（选择其一）**:

```env
# 方案1：麒麟操作系统用户
KYLIN_AI_API_KEY=your_kylin_api_key

# 方案2：其他系统用户（推荐）
DASHSCOPE_API_KEY=sk-your_dashscope_key
```

> **提示**: 从 https://dashscope.aliyuncs.com/ 获取通义千问API密钥

### 步骤3：启动服务

```bash
# 启动Python AI服务
cd agent
python app/main.py
```

**看到以下输出表示启动成功**:
```
2025-01-03 10:00:00 - INFO - 使用通义千问大模型: qwen-plus
2025-01-03 10:00:00 - INFO - 文档处理器初始化完成，支持格式: .pdf, .docx, ...
2025-01-03 10:00:00 - INFO - RAG工具集成服务初始化完成
```

### 步骤4：测试功能

**4.1 测试AI对话**:
```bash
# 使用curl测试（新终端）
curl -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好，你是谁？","role_id":"lawyer"}'
```

**4.2 测试文档上传**:
```bash
# 上传PDF文档到知识库
curl -X POST http://localhost:8000/ai/rag/upload \
  -F "file=@your_document.pdf" \
  -F "role_id=lawyer"
```

**4.3 测试RAG检索**:
```bash
# 查询知识库
curl -X POST http://localhost:8000/ai/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query":"合同纠纷如何处理？","role_id":"lawyer","top_k":5}'
```

## 📝 使用示例

### 示例1：智能SDK切换

**Python代码示例**:
```python
from app.ai_engine.kylin_sdk.client import KylinAIClient

async def main():
    # 初始化客户端（自动检测系统并选择SDK）
    client = KylinAIClient()
    
    # 生成文本
    result = await client.generate_text(
        text="请介绍一下合同法的基本原则",
        role_id="lawyer"
    )
    
    print(f"回复: {result['text']}")
    print(f"Token使用: {result['tokens_used']}")

# 运行
import asyncio
asyncio.run(main())
```

### 示例2：文档处理

**Python代码示例**:
```python
from app.services.documentprocessoradvanced import document_processor_advanced

# 读取PDF文件
with open("contract.pdf", "rb") as f:
    file_data = f.read()

# 自动选择最佳工具提取文本
result = document_processor_advanced.extract_text(
    file_data=file_data,
    filename="contract.pdf",
    use_enhanced=True
)

if result["success"]:
    print(f"使用工具: {result['method']}")
    print(f"提取的文本: {result['text'][:500]}...")
    print(f"元数据: {result['metadata']}")
else:
    print(f"提取失败: {result['error']}")
```

### 示例3：RAG搜索

**Python代码示例**:
```python
from app.services.ragtoolsintegration import rag_tools_integration

async def search_example():
    # 搜索知识库
    results = await rag_tools_integration.search(
        query="劳动合同的解除条件有哪些？",
        top_k=3,
        role_id="lawyer"
    )
    
    print(f"找到 {len(results)} 个相关文档：\n")
    for i, result in enumerate(results, 1):
        print(f"结果 {i}:")
        print(f"  文档: {result['filename']}")
        print(f"  相关度: {result['score']:.2f}")
        print(f"  内容预览: {result['content'][:100]}...")
        print(f"  使用工具: {result['method']}\n")

# 运行
import asyncio
asyncio.run(search_example())
```

### 示例4：完整RAG流程

**Python代码示例**:
```python
from app.services.ragtoolsintegration import rag_tools_integration

async def complete_rag_example():
    # 1. 上传文档
    with open("labor_law.pdf", "rb") as f:
        file_data = f.read()
    
    doc_id = await rag_tools_integration.upload_document(
        file_data=file_data,
        filename="labor_law.pdf",
        metadata={
            "category": "labor_law",
            "year": 2024,
            "author": "法律专家"
        },
        role_id="lawyer"
    )
    print(f"文档已上传，ID: {doc_id}\n")
    
    # 2. 搜索相关内容
    results = await rag_tools_integration.search(
        query="劳动合同应该包含哪些内容？",
        top_k=5,
        role_id="lawyer"
    )
    
    # 3. 使用搜索结果生成回答
    from app.ai_engine.kylin_sdk.client import KylinAIClient
    client = KylinAIClient()
    
    # 构建增强上下文
    context_text = "\n\n".join([
        f"相关内容{i+1}:\n{r['content']}"
        for i, r in enumerate(results[:3])
    ])
    
    # 生成最终回答
    prompt = f"""基于以下法律文档内容，请回答问题。

问题：劳动合同应该包含哪些内容？

相关法律文档：
{context_text}

请提供专业的法律意见："""
    
    answer = await client.generate_text(
        text=prompt,
        role_id="lawyer"
    )
    
    print(f"AI回答:\n{answer['text']}")

# 运行
import asyncio
asyncio.run(complete_rag_example())
```

## 🔧 进阶配置

### 配置文档处理优先级

**在 `.env` 文件中**:
```env
# 方案1：自动选择（推荐）
DOCUMENT_PROCESSOR_METHOD=auto

# 方案2：优先使用mineru（高质量）
DOCUMENT_PROCESSOR_METHOD=mineru

# 方案3：优先使用pdfplumber（快速）
DOCUMENT_PROCESSOR_METHOD=pdfplumber
```

### 配置RAG工具优先级

**在 `.env` 文件中**:
```env
# 方案1：自动选择（推荐）
RAG_TOOL_PROVIDER=auto

# 方案2：使用RagFlow
RAG_TOOL_PROVIDER=ragflow

# 方案3：使用FastGPT API
RAG_TOOL_PROVIDER=fastgpt
FASTGPT_API_URL=https://your-api.com
FASTGPT_API_KEY=your_key
```

### 安装可选增强工具

```bash
# 安装高级PDF处理工具
pip install mineru easydoc

# 安装RAG工具
pip install ragflow qanything

# 或只安装其中一个
pip install ragflow  # 只安装RagFlow
```

## 📊 检查系统状态

### 检查SDK状态

**Python脚本**:
```python
from app.services.kylinosintegration import kylin_os_integration_service

# 获取系统信息
system_info = kylin_os_integration_service.get_system_info()

print("系统信息:")
print(f"  操作系统: {system_info['os_name']}")
print(f"  是否为麒麟OS: {system_info['is_kylin_os']}")
print(f"  架构: {system_info['architecture']}")
```

### 检查文档处理工具

**Python脚本**:
```python
from app.services.documentprocessoradvanced import document_processor_advanced

print("可用的文档处理工具:")
for tool, info in document_processor_advanced.available_tools.items():
    status = "✓ 可用" if info else "✗ 不可用"
    print(f"  {tool}: {status}")
```

### 检查RAG工具

**Python脚本**:
```python
from app.services.ragtoolsintegration import rag_tools_integration

print("可用的RAG工具:")
for tool, info in rag_tools_integration.available_tools.items():
    if info.get('available'):
        print(f"  ✓ {tool}: {info.get('note', '可用')}")
    else:
        print(f"  ✗ {tool}: {info.get('install_cmd', '不可用')}")

print(f"\n当前使用: {rag_tools_integration.selected_tool}")
```

## 🐛 常见问题

### Q1: 如何知道系统使用的是哪个SDK？

**A**: 查看启动日志：
```
# 麒麟OS
检测到麒麟操作系统，使用麒麟AI SDK

# 其他系统
使用通义千问大模型: qwen-plus
```

### Q2: PDF文档提取失败怎么办？

**A**: 尝试以下步骤：
1. 检查是否安装了pdfplumber：`pip install pdfplumber`
2. 尝试其他工具：设置`DOCUMENT_PROCESSOR_METHOD=pypdf2`
3. 查看详细错误：检查日志文件`agent/logs/kinlin_ai.log`

### Q3: RAG搜索没有结果？

**A**: 确认以下几点：
1. 是否已上传文档到知识库
2. `role_id` 是否匹配
3. 尝试降低`top_k`值或使用不同的查询词

### Q4: 如何查看日志？

**A**: 日志文件位置：
```bash
# 查看最新日志
tail -f agent/logs/kinlin_ai.log

# Windows
type agent\logs\kinlin_ai.log
```

## 📚 下一步

- 阅读[完整文档](./麒麟SDK智能切换与增强RAG指南.md)
- 查看[API文档](./Kinlin-AI技术文档-05-API接口文档.md)
- 了解[部署指南](./Kinlin-AI技术文档-04-部署和运维指南.md)

## 💡 提示

1. **API密钥安全**: 不要将`.env`文件提交到代码库
2. **性能优化**: 生产环境建议使用RagFlow或QAnything
3. **文档格式**: 推荐使用PDF和Markdown格式以获得最佳提取效果
4. **角色分类**: 为不同角色创建独立的知识库以提高检索精度

---

**最后更新**: 2025-01-03  
**难度等级**: 初级  
**预计完成时间**: 15分钟


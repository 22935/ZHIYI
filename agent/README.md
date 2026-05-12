# 联邦智枢 AI Service

Python AI服务，提供AI能力

## 技术栈

- FastAPI
- 麒麟AI SDK
- Python 3.9+

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

### 创建 `.env` 文件

**重要**：`.env` 文件应该创建在**主目录**下（与 `agent/` 同级），而不是在 `agent/` 目录内。

例如：
```
Kinlin_AI/              # 主目录
├── .env                # ← 配置文件在这里（与agent同级）
├── agent/
│   └── app/
│       └── config.py   # 会自动读取主目录的 .env
├── backend/
└── frontend/
```

在主目录下创建 `.env` 文件，所有配置都统一在这里管理：

```env
# ============================================
# 通义千问大模型配置（推荐使用）⭐
# ============================================
# 方式1：使用官方推荐的环境变量名（推荐）
DASHSCOPE_API_KEY=sk-your_api_key_here

# 方式2：使用兼容的环境变量名（也支持）
# QWEN_API_KEY=sk-your_api_key_here

# API基础URL（通常不需要修改）
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 模型选择（根据需求选择）
QWEN_MODEL_FAST=qwen-turbo          # 快速模型
QWEN_MODEL_BALANCED=qwen-plus       # 平衡模型（推荐）⭐
QWEN_MODEL_ADVANCED=qwen-max         # 高级模型
QWEN_MODEL_LATEST=qwen3-max          # 最新模型

# 是否启用通义千问
QWEN_ENABLED=true

# ============================================
# 麒麟AI SDK配置（兼容旧配置，可选）
# ============================================
KYLIN_AI_API_KEY=your_api_key
KYLIN_AI_ENDPOINT=https://api.kylin.ai
KYLIN_AI_TIMEOUT=30
```

**重要说明**：
- 所有通义千问相关配置都从 `.env` 文件读取
- 系统全局只保留 `config.py` 中的 `settings` 作为唯一配置来源
- 获取API密钥：https://dashscope.aliyuncs.com/

## 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API接口

- `POST /ai/chat/text` - 文本对话
- `POST /ai/chat/voice` - 语音对话
- `POST /ai/tts` - 文本转语音


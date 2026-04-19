# 麒麟AI API 使用说明

## 概述

本项目支持两种AI服务：
1. **通义千问API**（推荐，当前默认使用）
2. **麒麟AI API**（需要配置）

本文档说明如何配置和使用麒麟AI API。

## 配置方法

### 1. 环境变量配置

在主目录的 `.env` 文件中添加以下配置：

```env
# 麒麟AI API配置
KYLIN_AI_API_KEY=your_kylin_api_key_here
KYLIN_AI_ENDPOINT=https://api.kylin.ai
KYLIN_AI_TIMEOUT=30
```

### 2. 配置说明

- **KYLIN_AI_API_KEY**: 麒麟AI API密钥（必需）
  - 从麒麟AI服务提供商获取
  - 格式通常为：`sk-xxxxx` 或类似格式

- **KYLIN_AI_ENDPOINT**: API端点地址（必需）
  - 默认值：`https://api.kylin.ai`
  - 根据实际API文档修改为正确的端点地址

- **KYLIN_AI_TIMEOUT**: 请求超时时间（可选）
  - 默认值：30秒
  - 单位：秒

## API路径配置

代码中预设了常见的API路径，您可能需要根据实际的麒麟AI API文档进行调整：

### 文本生成API
- 默认路径：`/v1/chat/completions`
- 修改位置：`agent/app/ai_engine/kylin_sdk/client.py` 第161行

### 语音识别API (ASR)
- 默认路径：`/v1/asr`
- 修改位置：`agent/app/ai_engine/kylin_sdk/client.py` 第310行

### 语音合成API (TTS)
- 默认路径：`/v1/tts`
- 修改位置：`agent/app/ai_engine/kylin_sdk/client.py` 第380行

## API请求格式

### 文本生成请求格式

代码支持多种常见的API请求格式，会自动适配：

```json
{
  "prompt": "用户输入的问题",
  "temperature": 0.7,
  "max_tokens": 2000,
  "top_p": 0.9,
  "context": [
    {"role": "user", "content": "之前的对话"},
    {"role": "assistant", "content": "AI的回复"}
  ],
  "system_prompt": "系统提示词",
  "role_id": "角色ID"
}
```

### 语音识别请求格式

```json
{
  "audio": "base64编码的音频数据",
  "language": "zh-CN",
  "format": "wav"
}
```

### 语音合成请求格式

```json
{
  "text": "要合成的文本",
  "voice": "default",
  "speed": 1.0,
  "pitch": 1.0,
  "format": "wav"
}
```

## API响应格式

代码支持多种常见的API响应格式，会自动解析：

### 文本生成响应格式

支持以下格式（按优先级）：

1. **简单格式**：
```json
{
  "text": "生成的文本",
  "confidence": 0.95,
  "tokens_used": 150
}
```

2. **OpenAI格式**：
```json
{
  "choices": [
    {
      "message": {
        "content": "生成的文本"
      }
    }
  ],
  "usage": {
    "total_tokens": 150
  }
}
```

3. **嵌套结果格式**：
```json
{
  "result": {
    "text": "生成的文本",
    "confidence": 0.95,
    "tokens_used": 150
  }
}
```

### 语音识别响应格式

支持以下格式：

1. **简单格式**：
```json
{
  "text": "识别的文本",
  "confidence": 0.92
}
```

2. **嵌套结果格式**：
```json
{
  "result": {
    "text": "识别的文本",
    "confidence": 0.92
  }
}
```

3. **转录格式**：
```json
{
  "transcription": "识别的文本",
  "confidence": 0.92
}
```

### 语音合成响应格式

支持以下格式：

1. **直接音频数据**：Content-Type为 `audio/*`，直接返回二进制音频数据

2. **Base64编码**：
```json
{
  "audio": "base64编码的音频数据"
}
```

3. **嵌套格式**：
```json
{
  "result": {
    "audio": "base64编码的音频数据"
  }
}
```

## 自定义API格式

如果您的麒麟AI API使用不同的请求/响应格式，可以修改以下文件：

**文件位置**：`agent/app/ai_engine/kylin_sdk/client.py`

### 修改文本生成API

1. **修改请求格式**（约第145-157行）：
```python
request_body = {
    # 根据实际API文档修改
    "your_custom_field": value
}
```

2. **修改API路径**（约第161行）：
```python
api_path = "/your/custom/path"
```

3. **修改响应解析**（约第176-199行）：
```python
# 根据实际响应格式修改解析逻辑
if "your_custom_field" in result_data:
    text = result_data["your_custom_field"]
```

### 修改语音识别API

1. **修改请求格式**（约第295-301行）
2. **修改API路径**（约第310行）
3. **修改响应解析**（约第315-335行）

### 修改语音合成API

1. **修改请求格式**（约第375-381行）
2. **修改API路径**（约第385行）
3. **修改响应解析**（约第390-420行）

## 使用优先级

系统按以下优先级选择AI服务：

1. **通义千问**（如果配置了 `DASHSCOPE_API_KEY` 或 `QWEN_API_KEY`）
2. **麒麟AI**（如果配置了 `KYLIN_AI_API_KEY` 和 `KYLIN_AI_ENDPOINT`）
3. **模拟响应**（如果都没有配置，用于开发测试）

## 测试配置

### 1. 检查配置是否生效

启动服务后，查看日志输出：

- 如果看到 `"Kylin AI SDK Client initialized: https://api.kylin.ai"`，说明配置已加载
- 如果看到 `"麒麟AI API调用成功"`，说明API调用成功
- 如果看到错误信息，请检查API密钥和端点地址

### 2. 测试文本生成

发送一个对话请求，检查是否使用麒麟AI API：

```bash
curl -X POST http://localhost:8000/ai/chat/text \
  -H "Content-Type: application/json \
  -d '{"text": "你好"}'
```

### 3. 测试语音识别

上传音频文件进行识别：

```bash
curl -X POST http://localhost:8000/ai/voice/recognize \
  -F "audio=@test.wav"
```

### 4. 测试语音合成

发送文本进行语音合成：

```bash
curl -X POST http://localhost:8000/ai/voice/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，这是测试"}'
```

## 常见问题

### Q1: 如何获取麒麟AI API密钥？

A: 请联系麒麟AI服务提供商获取API密钥和文档。

### Q2: API调用失败怎么办？

A: 检查以下几点：
1. API密钥是否正确
2. API端点地址是否正确
3. API路径是否正确（可能需要修改代码中的路径）
4. 网络连接是否正常
5. 查看日志中的详细错误信息

### Q3: 如何修改API请求格式？

A: 修改 `agent/app/ai_engine/kylin_sdk/client.py` 文件中对应的请求构建代码。

### Q4: 如何修改API响应解析？

A: 修改 `agent/app/ai_engine/kylin_sdk/client.py` 文件中对应的响应解析代码。

### Q5: 可以同时使用通义千问和麒麟AI吗？

A: 不可以，系统会优先使用通义千问。如果需要使用麒麟AI，请移除通义千问的配置。

## 注意事项

1. **API密钥安全**：不要将API密钥提交到代码仓库，使用 `.env` 文件并添加到 `.gitignore`
2. **API文档**：请参考实际的麒麟AI API文档，调整代码中的请求格式和路径
3. **错误处理**：如果API调用失败，系统会自动降级到模拟响应，不会中断服务
4. **日志记录**：所有API调用都会记录日志，便于调试和排查问题

## 技术支持

如果遇到问题，请：
1. 查看日志文件获取详细错误信息
2. 检查API配置是否正确
3. 参考实际的麒麟AI API文档
4. 联系技术支持

---

**最后更新**：2025-01-02


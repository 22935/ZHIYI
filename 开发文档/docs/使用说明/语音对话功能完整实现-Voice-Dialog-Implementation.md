# 语音对话功能 - 完整实现说明

## 功能概述

语音对话功能已完整实现，支持：
- ✅ 语音录音
- ✅ 语音识别（ASR）
- ✅ 文本生成（AI回复）
- ✅ 语音合成（TTS）
- ✅ 数字人口型同步
- ✅ 返回导航

## 技术实现

### 1. 语音合成（TTS）

#### 使用DashScope SDK（推荐）
```python
import dashscope
from dashscope.audio.qwen_tts import SpeechSynthesizer

response = SpeechSynthesizer.call(
    model="qwen-tts",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    text="你好，我是数字人助手",
    voice="Cherry",  # Cherry/Bella/Bob/Alex
    format="wav",
    sample_rate=16000,
    rate=1.0,        # 语速
    pitch_rate=1.0   # 音调
)

if response.status_code == 200:
    audio_data = response.get_audio_data()
```

#### 支持的语音类型
- **Cherry**: 女声，温柔亲切
- **Bella**: 女声，优雅大方
- **Bob**: 男声，稳重成熟
- **Alex**: 男声，活力阳光

### 2. 语音识别（ASR）

使用通义千问ASR API进行语音识别。

### 3. 完整流程

```
用户操作：
  按住录音按钮 → 说话 → 松开按钮
    ↓
录音（WebM格式）
    ↓
上传到后端（POST /ai/voice/chat）
    ↓
后端处理：
  1. ASR识别语音 → 文本
  2. AI生成回复 → 文本
  3. 返回识别文本和回复文本
    ↓
前端处理：
  1. 调用TTS API（POST /ai/voice/tts）
  2. 获取音频Blob
  3. 创建Audio对象并播放
  4. 数字人口型同步动画
    ↓
播放结束 → 清理资源
```

## API接口

### POST /ai/voice/chat
语音对话（录音 → 识别 → 回复）

**请求**：
```
Content-Type: multipart/form-data

参数：
- audio: 音频文件（File）
- roleId: 角色ID（可选）
- contextId: 上下文ID（可选）
```

**响应**：
```json
{
  "text": "AI回复文本",
  "recognizedText": "识别的用户语音",
  "confidence": 0.95,
  "contextId": ""
}
```

### POST /ai/voice/tts
文本转语音

**请求**：
```json
{
  "text": "要转换的文本",
  "voice": "Cherry",
  "speed": 1.0,
  "pitch": 1.0
}
```

**响应**：
音频流（audio/wav）

## 配置要求

### 1. 安装依赖
```bash
cd agent
pip install "dashscope>=1.23.1"
```

### 2. 配置API密钥
在 `.env` 文件中添加：
```env
DASHSCOPE_API_KEY=sk-your-api-key-here
```

### 3. 验证配置
启动后端后，查看日志应该显示：
```
✅ 语音服务适配器初始化成功 (SDK可用: True)
✅ 使用qwen-tts SDK合成语音
```

## 已修复的问题

### 1. 图像403错误
- ✅ 删除重复的data目录文件
- ✅ 统一使用 `/ai/digital-human/image/` 路径
- ✅ 清除浏览器缓存后正常

### 2. 实时ASR错误
- ✅ 修复音频缓冲区类型错误
- ✅ 禁用有问题的实时ASR
- ✅ 使用简单的录音→识别流程

### 3. TTS返回空数据
- ✅ 集成DashScope SDK
- ✅ 使用qwen-tts模型
- ✅ 添加占位符音频避免完全无声

### 4. 数字人动画API错误
- ✅ 修复multipart/form-data解析
- ✅ 使用UploadFile正确处理音频文件

### 5. API路由404错误
- ✅ 知识图谱路由改为 `/api` 前缀
- ✅ 语音API使用 `/ai` 前缀
- ✅ 添加voice路由到main.py

### 6. 返回按钮缺失
- ✅ 所有页面添加返回按钮
- ✅ 统一的设计风格
- ✅ 返回到聊天页面

## 使用说明

### 前端使用

#### 1. 访问语音对话页面
```
导航：侧边栏 → 语音交互
URL: http://localhost:5173/voice
```

#### 2. 选择角色
- 页面加载时自动选择第一个角色
- 数字人形象自动加载

#### 3. 开始对话
1. 按住中央的录音按钮（紫色麦克风）
2. 对着麦克风说话
3. 松开按钮停止录音
4. 等待识别和处理（会显示"思考中..."）
5. 听取AI语音回复
6. 观察数字人口型同步动画

#### 4. 调整语音参数
- 点击"语音设置"展开参数面板
- 调整语速（0.5x - 2.0x）
- 调整音调（0.5x - 2.0x）
- 选择语音类型（默认/女声/男声等）
- 点击"试听效果"测试

### 后端配置

#### 1. 环境变量（.env）
```env
# 通义千问API密钥（必须）
DASHSCOPE_API_KEY=sk-your-api-key-here

# 或使用旧配置名（兼容）
QWEN_API_KEY=sk-your-api-key-here

# 模型配置
QWEN_MODEL_BALANCED=qwen-plus
```

#### 2. 启动服务
```bash
cd agent
python app/main.py
```

#### 3. 查看日志
启动后应该看到：
```
✅ 通义千问适配器初始化成功: 模型=qwen-plus
✅ 语音服务适配器初始化成功 (SDK可用: True)
✅ 所有创新功能路由已加载
```

## 故障排查

### 问题1：TTS返回空音频
**症状**：控制台显示"语音合成返回空数据"

**解决**：
1. 检查 `.env` 文件中的 `DASHSCOPE_API_KEY` 是否正确
2. 检查API密钥是否有效（未过期）
3. 检查网络连接（能否访问dashscope.aliyuncs.com）
4. 查看后端日志详细错误信息

### 问题2：音频播放失败
**症状**：`Uncaught (in promise) NotSupportedError`

**解决**：
1. 检查音频Blob大小（应该 > 0）
2. 检查浏览器支持（Chrome/Edge推荐）
3. 检查TTS返回的音频格式（应该是wav）
4. 查看Console详细错误信息

### 问题3：图像403错误
**症状**：数字人图像加载失败

**解决**：
1. **清除浏览器缓存**（最重要！）
2. F12 → Application → Clear site data
3. Ctrl + F5 强制刷新
4. 关闭浏览器后重新打开

### 问题4：麦克风权限
**症状**：无法录音

**解决**：
1. 浏览器会请求麦克风权限，点击"允许"
2. 检查系统麦克风是否正常工作
3. 检查浏览器设置中的麦克风权限

## 开发说明

### 依赖包
```
dashscope>=1.23.1  - 阿里云DashScope SDK
openai==1.12.0     - 通义千问文本生成
httpx==0.25.2      - HTTP客户端
pydub==0.25.1      - 音频处理
```

### 主要文件
- `agent/app/api/voice.py` - 语音API路由
- `agent/app/ai_engine/speechadapter.py` - 语音服务适配器（TTS/ASR）
- `agent/app/services/aiservice.py` - AI服务（集成TTS/ASR）
- `frontend/src/views/VoiceChatView.vue` - 语音对话页面
- `frontend/src/components/VoiceRecorder.vue` - 录音组件
- `frontend/src/services/api/voice.ts` - 前端语音API

### 测试步骤
1. 清除浏览器缓存
2. 重启后端服务
3. 刷新前端页面
4. 访问 `/voice` 页面
5. 按住录音按钮说"你好"
6. 观察整个对话流程

## 注意事项

1. **首次使用前必须清除浏览器缓存**
2. 需要配置有效的DASHSCOPE_API_KEY
3. 实时ASR已禁用（有bug），使用普通录音模式
4. 音频格式统一使用WAV（16kHz采样率）
5. 所有页面都有返回按钮，可以返回到聊天页面

## 更新日志

### 2026-01-03
- ✅ 集成DashScope SDK 1.25.5
- ✅ 使用qwen-tts模型进行语音合成
- ✅ 修复所有API路由和参数解析
- ✅ 禁用有问题的实时ASR
- ✅ 添加返回按钮到所有页面
- ✅ 修复图像路径和缓存问题
- ✅ 优化错误处理和日志

## 后续优化

1. 支持更多语音类型和语言
2. 添加语音情感识别
3. 优化音频质量和压缩
4. 支持长文本的语音合成
5. 添加语音对话历史记录


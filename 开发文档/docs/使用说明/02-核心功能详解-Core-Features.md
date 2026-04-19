# Kinlin AI 技术文档 - 核心功能详解

## 文档版本
- **版本号**: v1.0.0
- **更新日期**: 2025-01-02
- **文档作者**: Kinlin AI 开发团队

---

## 目录

1. [文本对话功能](#1-文本对话功能)
2. [语音对话功能](#2-语音对话功能)
3. [角色管理功能](#3-角色管理功能)
4. [RAG检索增强功能](#4-rag检索增强功能)
5. [数字人交互功能](#5-数字人交互功能)
6. [用户管理功能](#6-用户管理功能)
7. [对话历史管理](#7-对话历史管理)

---

## 1. 文本对话功能

### 1.1 功能概述

文本对话功能是系统的核心功能之一，实现高效准确的自然语言理解，能够理解用户提出的各类问题，并给出合理、有针对性的回答。

### 1.2 核心特性

#### 1.2.1 自然语言理解
- **多轮对话支持**: 支持上下文理解，能够理解多轮对话中的指代和省略
- **意图识别**: 准确识别用户意图，支持问答、咨询、闲聊等多种场景
- **实体抽取**: 自动抽取对话中的关键实体信息

#### 1.2.2 智能回答生成
- **上下文感知**: 根据对话历史生成连贯的回答
- **角色适配**: 根据选择的角色生成符合角色特点的回答
- **RAG增强**: 可选使用RAG检索增强，提供更准确的回答

#### 1.2.3 对话质量评估
- **质量评分**: 自动评估对话质量，提供相关性、准确性、流畅性评分
- **改进建议**: 根据质量评估结果提供改进建议
- **质量趋势**: 跟踪对话质量趋势，识别质量下降

### 1.3 技术实现

#### 1.3.1 后端实现

**核心类**: `ChatService`, `ChatController`

**主要方法**:
```java
// 发送消息并获取回复
public ChatResponse sendMessage(ChatRequest request, UUID userId)

// 构建对话上下文
private List<Map<String, String>> buildContext(List<Message> history)

// 获取或创建对话
private Conversation getOrCreateConversation(String contextId, UUID userId, UUID roleId)
```

**关键流程**:
1. 接收用户消息请求
2. 获取或创建对话会话
3. 保存用户消息到数据库
4. 构建对话上下文（从数据库或请求中获取）
5. 可选：使用RAG增强查询
6. 获取角色上下文（如果指定了角色）
7. 调用AI服务生成回复
8. 保存AI回复到数据库
9. 返回回复给前端

#### 1.3.2 前端实现

**核心组件**: `ChatView.vue`, `MessageBubble.vue`

**主要功能**:
- 消息输入和发送
- 消息列表展示
- 流式响应显示
- 消息操作（复制、删除、导出）
- 对话历史加载

#### 1.3.3 AI服务实现

**核心模块**: `chat.py`, `aiservice.py`

**主要功能**:
- 调用通义千问API生成文本
- 支持流式和非流式生成
- 上下文管理和优化
- 错误处理和重试

### 1.4 API接口

#### 1.4.1 发送消息

**接口**: `POST /api/chat/send`

**请求参数**:
```json
{
  "text": "用户输入的消息",
  "contextId": "对话上下文ID（可选）",
  "roleId": "角色ID（可选）",
  "useRag": true,
  "context": [
    {"role": "user", "content": "历史消息1"},
    {"role": "assistant", "content": "历史回复1"}
  ]
}
```

**响应参数**:
```json
{
  "response": "AI回复内容",
  "contextId": "对话上下文ID",
  "confidence": 0.95,
  "sources": [
    {
      "document": "文档名称",
      "excerpt": "相关片段"
    }
  ]
}
```

#### 1.4.2 流式发送消息

**接口**: `POST /api/chat/stream`

**说明**: 使用Server-Sent Events (SSE) 实现流式响应

### 1.5 使用示例

#### 1.5.1 基础对话

```typescript
// 前端调用示例
const response = await chatApi.sendMessage({
  text: "你好，我想了解一下法律问题",
  contextId: conversationId,
  roleId: lawyerRoleId
});

console.log(response.response); // AI回复
```

#### 1.5.2 多轮对话

```typescript
// 第一轮
const response1 = await chatApi.sendMessage({
  text: "什么是合同？",
  contextId: conversationId
});

// 第二轮（自动使用上下文）
const response2 = await chatApi.sendMessage({
  text: "合同有哪些类型？",
  contextId: conversationId // 使用相同的contextId
});
```

#### 1.5.3 RAG增强对话

```typescript
// 使用RAG增强
const response = await chatApi.sendMessage({
  text: "合同纠纷如何处理？",
  contextId: conversationId,
  useRag: true // 启用RAG检索
});
```

### 1.6 性能优化

- **上下文缓存**: 使用Redis缓存对话上下文，减少数据库查询
- **异步处理**: 使用异步方式处理AI服务调用
- **批量查询**: 批量查询历史消息，减少数据库访问次数
- **流式响应**: 支持流式响应，提升用户体验

---

## 2. 语音对话功能

### 2.1 功能概述

语音对话功能集成高质量的语音识别和语音合成功能，实现实时语音交互。

### 2.2 核心特性

#### 2.2.1 语音识别 (ASR)
- **实时识别**: 支持WebSocket流式语音识别
- **多格式支持**: 支持wav、mp3、m4a等音频格式
- **噪音过滤**: 自动过滤背景噪音，提升识别准确率
- **标点符号**: 自动添加标点符号，提升可读性

#### 2.2.2 语音合成 (TTS)
- **多种语音类型**: 支持default、female、male、gentle、lively等语音类型
- **参数调节**: 支持语速（0.5x-2.0x）、音调（0.5x-2.0x）调节
- **自然流畅**: 使用高质量TTS引擎，生成自然流畅的语音

#### 2.2.3 完整对话流程
- **录音**: 支持实时录音和停止
- **识别**: 自动识别语音并转换为文本
- **生成**: 调用AI服务生成回复
- **合成**: 将回复合成为语音
- **播放**: 自动播放合成的语音

### 2.3 技术实现

#### 2.3.1 后端实现

**核心类**: `VoiceService`, `VoiceController`

**主要方法**:
```java
// 语音转文本
public String speechToText(MultipartFile audioFile)

// 文本转语音
public byte[] textToSpeech(String text, String voiceType, Float speed, Float pitch)
```

**关键流程**:
1. 接收音频文件或音频流
2. 调用AI服务的ASR接口进行识别
3. 返回识别结果
4. 接收文本和语音参数
5. 调用AI服务的TTS接口进行合成
6. 返回音频数据

#### 2.3.2 前端实现

**核心组件**: `VoiceChatView.vue`, `VoiceRecorder.vue`

**主要功能**:
- 语音录制和停止
- 实时识别显示
- 语音参数设置
- 语音播放控制
- 波形可视化

#### 2.3.3 AI服务实现

**核心模块**: `realtimeasr.py`, `tts.py`

**ASR实现**:
- 集成阿里云ASR API
- 支持流式识别（WebSocket）
- 噪音过滤和音频预处理
- 错误处理和重试机制

**TTS实现**:
- 集成阿里云TTS API
- 支持多种语音类型
- 参数映射和验证
- 音频格式转换

### 2.4 API接口

#### 2.4.1 语音转文本

**接口**: `POST /api/voice/speech-to-text`

**请求**: `multipart/form-data`
- `audio`: 音频文件

**响应**:
```json
{
  "text": "识别出的文本",
  "confidence": 0.95
}
```

#### 2.4.2 文本转语音

**接口**: `POST /api/voice/text-to-speech`

**请求参数**:
```json
{
  "text": "要合成的文本",
  "voiceType": "female",
  "speed": 1.0,
  "pitch": 1.0
}
```

**响应**: 音频文件（audio/mpeg）

#### 2.4.3 实时语音识别

**接口**: `WebSocket /api/voice/realtime-asr`

**说明**: 支持WebSocket流式识别

### 2.5 使用示例

#### 2.5.1 基础语音对话

```typescript
// 录音并识别
const audioBlob = await recordAudio();
const text = await voiceApi.speechToText(audioBlob);

// 生成回复
const response = await chatApi.sendMessage({
  text: text,
  contextId: conversationId
});

// 合成语音
const audioData = await voiceApi.textToSpeech({
  text: response.response,
  voiceType: "female",
  speed: 1.0,
  pitch: 1.0
});

// 播放
playAudio(audioData);
```

#### 2.5.2 实时语音识别

```typescript
// 建立WebSocket连接
const ws = new WebSocket('ws://localhost:8090/api/voice/realtime-asr');

// 发送音频数据
ws.send(audioChunk);

// 接收识别结果
ws.onmessage = (event) => {
  const result = JSON.parse(event.data);
  console.log(result.text); // 识别出的文本
};
```

### 2.6 性能优化

- **流式处理**: 支持流式识别和合成，减少延迟
- **音频压缩**: 自动压缩音频数据，减少传输量
- **缓存策略**: 缓存常用语音合成结果
- **并发控制**: 限制并发请求数，保证服务质量

---

## 3. 角色管理功能

### 3.1 功能概述

角色管理功能支持系统内置角色和用户自定义角色，每个角色都有独特的对话风格和专业知识。

### 3.2 核心特性

#### 3.2.1 内置角色
- **律师角色**: 专业法律咨询，严谨、专业、逻辑清晰
- **教师角色**: 知识讲解和学习辅导，耐心、细致、循循善诱
- **程序员角色**: 代码问题排查和编程建议，简洁、技术导向、注重实践
- **作家角色**: 创意写作和文章润色，富有创意、文采斐然

#### 3.2.2 自定义角色
- **角色创建**: 用户可以创建自己的角色
- **角色配置**: 支持配置角色名称、描述、系统提示词、对话风格、性格特点
- **角色编辑**: 支持编辑已有角色
- **角色删除**: 支持删除自定义角色

#### 3.2.3 角色切换
- **快速切换**: 支持快速切换角色
- **上下文保持**: 切换角色时可选择是否保留对话上下文
- **角色缓存**: 使用缓存优化角色切换性能

#### 3.2.4 角色风格学习
- **风格提取**: 从角色描述中提取风格特征
- **示例学习**: 从对话示例中学习对话模式和语言特征
- **风格合并**: 智能合并描述和示例中的风格

### 3.3 技术实现

#### 3.3.1 后端实现

**核心类**: `RoleService`, `RoleController`, `RoleValidationService`

**主要方法**:
```java
// 获取内置角色列表
public List<Role> getBuiltinRoles()

// 获取自定义角色列表
public List<Role> getCustomRoles(UUID userId)

// 创建自定义角色
public Role createRole(RoleCreateRequest request, UUID userId)

// 更新角色
public Optional<Role> updateRole(UUID roleId, RoleCreateRequest request, UUID userId)

// 删除角色
public boolean deleteRole(UUID roleId, UUID userId)
```

**数据模型**:
```java
@Entity
public class Role {
    private UUID id;
    private String name;
    private String description;
    private RoleType roleType; // BUILTIN, CUSTOM
    private UUID userId; // 自定义角色的创建者
    private String systemPrompt;
    private String dialogueStyle;
    private String personality;
    private String avatarConfig;
}
```

#### 3.3.2 前端实现

**核心组件**: `RoleView.vue`, `RoleCard.vue`, `CreateRoleDialog.vue`

**主要功能**:
- 角色列表展示
- 角色创建和编辑
- 角色切换
- 角色收藏

#### 3.3.3 AI服务实现

**核心模块**: `rolestylelearning.py`

**主要功能**:
- 角色描述解析
- 对话风格示例学习
- 风格特征提取
- 风格合并算法

### 3.4 API接口

#### 3.4.1 获取角色列表

**接口**: `GET /api/roles`

**查询参数**:
- `type`: 角色类型（builtin/custom）
- `userId`: 用户ID（获取自定义角色时必需）

**响应**:
```json
[
  {
    "id": "角色ID",
    "name": "角色名称",
    "description": "角色描述",
    "roleType": "BUILTIN",
    "systemPrompt": "系统提示词",
    "dialogueStyle": "对话风格",
    "personality": "性格特点"
  }
]
```

#### 3.4.2 创建角色

**接口**: `POST /api/roles/custom`

**请求参数**:
```json
{
  "name": "角色名称",
  "description": "角色描述",
  "systemPrompt": "系统提示词",
  "dialogueStyle": "对话风格",
  "personality": "性格特点",
  "avatarConfig": "头像配置"
}
```

#### 3.4.3 更新角色

**接口**: `PUT /api/roles/{roleId}`

**请求参数**: 同创建角色

#### 3.4.4 删除角色

**接口**: `DELETE /api/roles/{roleId}`

### 3.5 使用示例

#### 3.5.1 获取角色列表

```typescript
// 获取内置角色
const builtinRoles = await roleApi.getRoles({ type: 'builtin' });

// 获取自定义角色
const customRoles = await roleApi.getRoles({ 
  type: 'custom', 
  userId: currentUserId 
});
```

#### 3.5.2 创建自定义角色

```typescript
const newRole = await roleApi.createRole({
  name: "心理咨询师",
  description: "专业的心理咨询师，擅长倾听和引导",
  systemPrompt: "你是一位专业的心理咨询师...",
  dialogueStyle: "温和、耐心、专业",
  personality: "富有同理心、善于倾听"
});
```

#### 3.5.3 切换角色

```typescript
// 切换角色
await roleStore.setCurrentRole(roleId);

// 开始新对话（可选保留上下文）
await chatStore.startNewConversation(roleId, keepContext);
```

### 3.6 性能优化

- **角色缓存**: 使用Redis缓存角色配置，减少数据库查询
- **预加载**: 应用启动时预加载常用角色
- **批量查询**: 批量查询角色列表，减少数据库访问次数

---

## 4. RAG检索增强功能

### 4.1 功能概述

RAG（Retrieval-Augmented Generation）检索增强功能基于知识库进行检索，将检索结果融入AI生成过程，提供更准确的回答。

### 4.2 核心特性

#### 4.2.1 文档处理
- **多格式支持**: 支持txt、md、pdf、doc、docx等格式
- **智能分块**: 自动将文档分块，保持语义完整性
- **元数据提取**: 自动提取文档标题、作者、创建时间等元数据

#### 4.2.2 知识库构建
- **向量化**: 使用embedding模型将文档向量化
- **索引建立**: 使用ChromaDB建立向量索引
- **增量更新**: 支持增量添加文档，自动更新索引

#### 4.2.3 智能检索
- **向量搜索**: 基于向量相似度搜索相关文档
- **关键词匹配**: 支持关键词匹配和全文搜索
- **重排序**: 使用多策略重排序，提升检索准确性

#### 4.2.4 增强生成
- **上下文融合**: 将检索结果融入AI生成上下文
- **来源标注**: 自动标注回答来源，支持可解释性
- **置信度评估**: 评估检索结果的置信度

### 4.3 技术实现

#### 4.3.1 后端实现

**核心类**: `RagService`, `RagController`

**主要方法**:
```java
// 上传文档
public void uploadDocument(MultipartFile file, UUID userId)

// 查询知识库
public RagResponse query(String query, int topK, String contextId)

// 获取文档列表
public List<DocumentInfo> listDocuments(UUID userId)

// 删除文档
public void deleteDocument(String documentId, UUID userId)
```

#### 4.3.2 前端实现

**核心组件**: `RagView.vue`, `RagQuery.vue`

**主要功能**:
- 文档上传和管理
- 知识库查询
- 检索结果展示
- 来源标注显示

#### 4.3.3 AI服务实现

**核心模块**: `rag.py`, `ragenhanced.py`, `knowledgegraph.py`

**主要功能**:
- 文档解析和分块
- 向量化和索引
- 向量搜索和重排序
- 知识图谱构建和查询

### 4.4 API接口

#### 4.4.1 上传文档

**接口**: `POST /api/rag/documents`

**请求**: `multipart/form-data`
- `file`: 文档文件
- `userId`: 用户ID

#### 4.4.2 查询知识库

**接口**: `POST /api/rag/query`

**请求参数**:
```json
{
  "query": "查询问题",
  "topK": 5,
  "contextId": "上下文ID"
}
```

**响应**:
```json
{
  "answer": "增强后的回答",
  "sources": [
    {
      "document": "文档名称",
      "excerpt": "相关片段",
      "score": 0.95
    }
  ]
}
```

#### 4.4.3 获取文档列表

**接口**: `GET /api/rag/documents`

**查询参数**:
- `userId`: 用户ID

### 4.5 使用示例

#### 4.5.1 上传文档

```typescript
// 上传文档
const formData = new FormData();
formData.append('file', file);
formData.append('userId', userId);

await ragApi.uploadDocument(formData);
```

#### 4.5.2 查询知识库

```typescript
// 查询知识库
const response = await ragApi.query({
  query: "合同纠纷如何处理？",
  topK: 5,
  contextId: conversationId
});

console.log(response.answer); // 增强后的回答
console.log(response.sources); // 来源文档
```

### 4.6 性能优化

- **向量缓存**: 缓存常用查询的向量结果
- **批量处理**: 批量处理文档上传和索引
- **异步索引**: 异步建立索引，不阻塞上传
- **分页查询**: 支持分页查询文档列表

---

## 5. 数字人交互功能

### 5.1 功能概述

数字人交互功能通过AIGC生成数字人形象，实时语音驱动，支持多风格切换，提供沉浸式的交互体验。

### 5.2 核心特性

#### 5.2.1 数字人生成
- **AIGC生成**: 调用通义万相API自动生成数字人形象
- **角色适配**: 根据角色特征智能生成提示词
- **多风格支持**: 支持写实、卡通、二次元三种视觉风格
- **画质调节**: 提供低、中、高三档画质调节

#### 5.2.2 实时语音驱动
- **口型同步**: 根据语音内容实时驱动数字人口型
- **表情生成**: 基于情感和音频特征生成表情
- **手势生成**: 基于音频特征和情感生成手势
- **动画流畅**: 使用Three.js实现流畅的动画效果

#### 5.2.3 交互功能
- **实时对话**: 支持与数字人进行实时对话
- **形象切换**: 支持切换不同的数字人形象
- **风格切换**: 支持切换不同的视觉风格
- **预览功能**: 支持3秒极速预览

### 5.3 技术实现

#### 5.3.1 后端实现

**核心类**: `DigitalHumanService`, `DigitalHumanController`

**主要方法**:
```java
// 生成数字人形象
public DigitalHumanResponse generateDigitalHuman(DigitalHumanRequest request)

// 获取数字人列表
public List<DigitalHumanInfo> listDigitalHumans(UUID userId)

// 删除数字人
public void deleteDigitalHuman(String digitalHumanId, UUID userId)
```

#### 5.3.2 前端实现

**核心组件**: `DigitalHumanChatView.vue`, `DigitalHuman.vue`

**主要功能**:
- 数字人生成和管理
- 3D模型加载和渲染
- 实时语音驱动
- 动画控制

#### 5.3.3 AI服务实现

**核心模块**: `digitalhuman.py`, `imagegenerationservice.py`

**主要功能**:
- 调用通义万相API生成图像
- 音频特征分析
- 口型同步算法
- 表情和手势生成

### 5.4 API接口

#### 5.4.1 生成数字人

**接口**: `POST /api/digital-human/generate`

**请求参数**:
```json
{
  "roleId": "角色ID",
  "style": "realistic",
  "quality": "high"
}
```

**响应**:
```json
{
  "digitalHumanId": "数字人ID",
  "imageUrl": "图像URL",
  "metadata": {
    "style": "realistic",
    "quality": "high"
  }
}
```

#### 5.4.2 获取数字人列表

**接口**: `GET /api/digital-human/list`

**查询参数**:
- `userId`: 用户ID

### 5.5 使用示例

#### 5.5.1 生成数字人

```typescript
// 生成数字人
const response = await digitalHumanApi.generate({
  roleId: roleId,
  style: "realistic",
  quality: "high"
});

console.log(response.imageUrl); // 数字人图像URL
```

#### 5.5.2 实时对话

```typescript
// 发送消息并获取语音
const chatResponse = await chatApi.sendMessage({
  text: "你好",
  contextId: conversationId
});

// 合成语音
const audioData = await voiceApi.textToSpeech({
  text: chatResponse.response,
  voiceType: "female"
});

// 驱动数字人
digitalHuman.driveWithAudio(audioData);
```

### 5.6 性能优化

- **图像缓存**: 缓存生成的数字人图像
- **模型预加载**: 预加载常用3D模型
- **动画优化**: 优化动画渲染性能
- **资源压缩**: 压缩3D模型和纹理资源

---

## 6. 用户管理功能

### 6.1 功能概述

用户管理功能提供用户注册、登录、个人信息管理等功能。

### 6.2 核心特性

- **用户注册**: 支持邮箱注册
- **用户登录**: 支持JWT认证
- **个人信息管理**: 支持修改个人信息
- **密码管理**: 支持修改密码
- **用户画像**: 自动构建用户画像

### 6.3 技术实现

**核心类**: `UserService`, `AuthController`, `UserController`

**主要方法**:
```java
// 用户注册
public User register(RegisterRequest request)

// 用户登录
public LoginResponse login(LoginRequest request)

// 获取用户信息
public User getUserInfo(UUID userId)

// 更新用户信息
public User updateUserInfo(UUID userId, UpdateUserRequest request)
```

### 6.4 API接口

#### 6.4.1 用户注册

**接口**: `POST /api/auth/register`

**请求参数**:
```json
{
  "username": "用户名",
  "email": "邮箱",
  "password": "密码"
}
```

#### 6.4.2 用户登录

**接口**: `POST /api/auth/login`

**请求参数**:
```json
{
  "email": "邮箱",
  "password": "密码"
}
```

**响应**:
```json
{
  "token": "JWT Token",
  "user": {
    "id": "用户ID",
    "username": "用户名",
    "email": "邮箱"
  }
}
```

---

## 7. 对话历史管理

### 7.1 功能概述

对话历史管理功能提供对话列表查询、对话详情查看、对话导出等功能。

### 7.2 核心特性

- **对话列表**: 支持查询用户的对话列表
- **对话详情**: 支持查看对话详情和消息历史
- **对话搜索**: 支持搜索对话内容
- **对话导出**: 支持导出对话为JSON或TXT格式
- **对话删除**: 支持删除对话

### 7.3 技术实现

**核心类**: `ConversationService`, `ConversationController`

**主要方法**:
```java
// 获取对话列表
public List<Conversation> getConversations(UUID userId, int page, int size)

// 获取对话详情
public Conversation getConversation(UUID conversationId, UUID userId)

// 删除对话
public void deleteConversation(UUID conversationId, UUID userId)
```

### 7.4 API接口

#### 7.4.1 获取对话列表

**接口**: `GET /api/conversations`

**查询参数**:
- `userId`: 用户ID
- `page`: 页码
- `size`: 每页大小

#### 7.4.2 获取对话详情

**接口**: `GET /api/conversations/{conversationId}`

#### 7.4.3 删除对话

**接口**: `DELETE /api/conversations/{conversationId}`

---

## 8. 总结

本文档详细介绍了Kinlin AI系统的核心功能模块，包括：

1. **文本对话功能**: 支持多轮对话、上下文理解、RAG增强
2. **语音对话功能**: 支持实时识别、语音合成、完整对话流程
3. **角色管理功能**: 支持内置角色、自定义角色、角色切换
4. **RAG检索增强功能**: 支持文档处理、知识库构建、智能检索
5. **数字人交互功能**: 支持数字人生成、实时语音驱动、多风格切换
6. **用户管理功能**: 支持用户注册、登录、个人信息管理
7. **对话历史管理**: 支持对话列表、详情查看、导出

每个功能模块都提供了详细的技术实现说明、API接口文档和使用示例，方便开发者理解和使用。

---

**文档结束**


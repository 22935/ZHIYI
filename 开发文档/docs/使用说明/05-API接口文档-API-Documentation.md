# 联邦智枢 技术文档 - API接口文档

## 文档版本
- **版本号**: v1.0.0
- **更新日期**: 2025-01-02
- **文档作者**: 联邦智枢 开发团队

---

## 目录

1. [API概述](#1-api概述)
2. [认证授权](#2-认证授权)
3. [对话接口](#3-对话接口)
4. [语音接口](#4-语音接口)
5. [角色管理接口](#5-角色管理接口)
6. [RAG接口](#6-rag接口)
7. [数字人接口](#7-数字人接口)
8. [用户管理接口](#8-用户管理接口)
9. [创新功能接口](#9-创新功能接口)
10. [系统管理接口](#10-系统管理接口)

---

## 1. API概述

### 1.1 基础信息

- **Base URL**: `http://localhost:8090/api`
- **协议**: HTTP/HTTPS
- **数据格式**: JSON
- **字符编码**: UTF-8

### 1.2 通用响应格式

#### 成功响应

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

#### 错误响应

```json
{
  "code": 400,
  "message": "错误信息",
  "error": "详细错误描述"
}
```

### 1.3 状态码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 1.4 认证方式

大部分接口需要JWT Token认证，在请求头中携带：

```
Authorization: Bearer <token>
```

---

## 2. 认证授权

### 2.1 用户注册

**接口**: `POST /api/auth/register`

**请求参数**:
```json
{
  "username": "用户名",
  "email": "user@example.com",
  "password": "password123"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "注册成功",
  "data": {
    "id": "用户ID",
    "username": "用户名",
    "email": "user@example.com"
  }
}
```

### 2.2 用户登录

**接口**: `POST /api/auth/login`

**请求参数**:
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "token": "JWT Token",
    "user": {
      "id": "用户ID",
      "username": "用户名",
      "email": "user@example.com"
    }
  }
}
```

### 2.3 刷新Token

**接口**: `POST /api/auth/refresh`

**请求头**:
```
Authorization: Bearer <token>
```

**响应**:
```json
{
  "code": 200,
  "message": "刷新成功",
  "data": {
    "token": "新的JWT Token"
  }
}
```

---

## 3. 对话接口

### 3.1 发送文本消息

**接口**: `POST /api/chat/send`

**请求头**:
```
Authorization: Bearer <token>
X-User-Id: <用户ID>
```

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

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "response": "AI回复内容",
    "contextId": "对话上下文ID",
    "confidence": 0.95,
    "sources": [
      {
        "document": "文档名称",
        "excerpt": "相关片段",
        "score": 0.92
      }
    ]
  }
}
```

### 3.2 流式发送消息

**接口**: `POST /api/chat/stream`

**说明**: 使用Server-Sent Events (SSE) 实现流式响应

**请求参数**: 同发送文本消息

**响应**: 流式数据
```
data: {"chunk": "回复片段1"}
data: {"chunk": "回复片段2"}
data: {"done": true}
```

### 3.3 获取对话历史

**接口**: `GET /api/chat/history/{contextId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `contextId`: 对话上下文ID

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": "消息ID",
      "role": "user",
      "content": "用户消息",
      "createdAt": "2025-01-02T10:00:00Z"
    },
    {
      "id": "消息ID",
      "role": "assistant",
      "content": "AI回复",
      "createdAt": "2025-01-02T10:00:01Z"
    }
  ]
}
```

### 3.4 清除对话历史

**接口**: `DELETE /api/chat/history/{contextId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `contextId`: 对话上下文ID

**响应**:
```json
{
  "code": 200,
  "message": "清除成功"
}
```

---

## 4. 语音接口

### 4.1 语音转文本

**接口**: `POST /api/voice/speech-to-text`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**请求参数**:
- `audio`: 音频文件（wav, mp3, m4a等格式）

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "text": "识别出的文本",
    "confidence": 0.95
  }
}
```

### 4.2 文本转语音

**接口**: `POST /api/voice/text-to-speech`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

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

### 4.3 实时语音识别

**接口**: `WebSocket /api/voice/realtime-asr`

**说明**: WebSocket连接，支持流式识别

**连接示例**:
```javascript
const ws = new WebSocket('ws://localhost:8090/api/voice/realtime-asr');
ws.send(audioChunk); // 发送音频数据
ws.onmessage = (event) => {
  const result = JSON.parse(event.data);
  console.log(result.text); // 识别结果
};
```

---

## 5. 角色管理接口

### 5.1 获取角色列表

**接口**: `GET /api/roles`

**请求头**:
```
Authorization: Bearer <token>
```

**查询参数**:
- `type`: 角色类型（builtin/custom）
- `userId`: 用户ID（获取自定义角色时必需）

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": "角色ID",
      "name": "角色名称",
      "description": "角色描述",
      "roleType": "BUILTIN",
      "systemPrompt": "系统提示词",
      "dialogueStyle": "对话风格",
      "personality": "性格特点",
      "avatarConfig": "头像配置"
    }
  ]
}
```

### 5.2 获取角色详情

**接口**: `GET /api/roles/{roleId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `roleId`: 角色ID

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "角色ID",
    "name": "角色名称",
    "description": "角色描述",
    "roleType": "BUILTIN",
    "systemPrompt": "系统提示词",
    "dialogueStyle": "对话风格",
    "personality": "性格特点"
  }
}
```

### 5.3 创建自定义角色

**接口**: `POST /api/roles/custom`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

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

**响应**:
```json
{
  "code": 200,
  "message": "创建成功",
  "data": {
    "id": "角色ID",
    "name": "角色名称",
    "description": "角色描述"
  }
}
```

### 5.4 更新角色

**接口**: `PUT /api/roles/{roleId}`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**路径参数**:
- `roleId`: 角色ID

**请求参数**: 同创建角色

**响应**:
```json
{
  "code": 200,
  "message": "更新成功",
  "data": {
    "id": "角色ID",
    "name": "更新后的角色名称"
  }
}
```

### 5.5 删除角色

**接口**: `DELETE /api/roles/{roleId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `roleId`: 角色ID

**响应**:
```json
{
  "code": 200,
  "message": "删除成功"
}
```

---

## 6. RAG接口

### 6.1 上传文档

**接口**: `POST /api/rag/documents`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**请求参数**:
- `file`: 文档文件（txt, md, pdf, doc, docx等格式）
- `userId`: 用户ID

**响应**:
```json
{
  "code": 200,
  "message": "上传成功",
  "data": {
    "documentId": "文档ID",
    "filename": "文件名",
    "size": 1024,
    "uploadTime": "2025-01-02T10:00:00Z"
  }
}
```

### 6.2 查询知识库

**接口**: `POST /api/rag/query`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "query": "查询问题",
  "topK": 5,
  "contextId": "上下文ID（可选）"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "answer": "增强后的回答",
    "sources": [
      {
        "document": "文档名称",
        "excerpt": "相关片段",
        "score": 0.95
      }
    ]
  }
}
```

### 6.3 获取文档列表

**接口**: `GET /api/rag/documents`

**请求头**:
```
Authorization: Bearer <token>
```

**查询参数**:
- `userId`: 用户ID
- `page`: 页码（默认1）
- `size`: 每页大小（默认10）

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 100,
    "page": 1,
    "size": 10,
    "documents": [
      {
        "id": "文档ID",
        "filename": "文件名",
        "size": 1024,
        "uploadTime": "2025-01-02T10:00:00Z"
      }
    ]
  }
}
```

### 6.4 删除文档

**接口**: `DELETE /api/rag/documents/{documentId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `documentId`: 文档ID

**响应**:
```json
{
  "code": 200,
  "message": "删除成功"
}
```

---

## 7. 数字人接口

### 7.1 生成数字人

**接口**: `POST /api/digital-human/generate`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

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
  "code": 200,
  "message": "生成成功",
  "data": {
    "digitalHumanId": "数字人ID",
    "imageUrl": "图像URL",
    "metadata": {
      "style": "realistic",
      "quality": "high"
    }
  }
}
```

### 7.2 获取数字人列表

**接口**: `GET /api/digital-human/list`

**请求头**:
```
Authorization: Bearer <token>
```

**查询参数**:
- `userId`: 用户ID

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": "数字人ID",
      "imageUrl": "图像URL",
      "roleId": "角色ID",
      "style": "realistic",
      "createdAt": "2025-01-02T10:00:00Z"
    }
  ]
}
```

### 7.3 驱动数字人

**接口**: `POST /api/digital-human/drive`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "digitalHumanId": "数字人ID",
  "audioData": "base64编码的音频数据",
  "emotion": {
    "type": "happy",
    "intensity": 0.8
  }
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "lipSync": [
      {"frame": 0, "shape": "A", "intensity": 0.8},
      {"frame": 1, "shape": "E", "intensity": 0.6}
    ],
    "emotions": [
      {"frame": 0, "emotion": "happy", "intensity": 0.8}
    ],
    "gestures": [
      {"frame": 0, "gesture": "wave", "intensity": 0.5}
    ]
  }
}
```

### 7.4 删除数字人

**接口**: `DELETE /api/digital-human/{digitalHumanId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `digitalHumanId`: 数字人ID

**响应**:
```json
{
  "code": 200,
  "message": "删除成功"
}
```

---

## 8. 用户管理接口

### 8.1 获取用户信息

**接口**: `GET /api/user/info`

**请求头**:
```
Authorization: Bearer <token>
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "用户ID",
    "username": "用户名",
    "email": "user@example.com",
    "avatar": "头像URL",
    "createdAt": "2025-01-02T10:00:00Z"
  }
}
```

### 8.2 更新用户信息

**接口**: `PUT /api/user/info`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "username": "新用户名",
  "avatar": "头像URL"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "更新成功",
  "data": {
    "id": "用户ID",
    "username": "新用户名"
  }
}
```

### 8.3 修改密码

**接口**: `POST /api/user/change-password`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "oldPassword": "旧密码",
  "newPassword": "新密码"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "密码修改成功"
}
```

---

## 9. 创新功能接口

### 9.1 情感识别

**接口**: `POST /api/emotion/analyze`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "text": "用户文本",
  "audioData": "base64编码的音频数据（可选）",
  "imageData": "base64编码的图像数据（可选）"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "emotion": "happy",
    "intensity": 0.8,
    "confidence": 0.9,
    "modalities": {
      "text": {"emotion": "happy", "intensity": 0.8},
      "audio": {"emotion": "excited", "intensity": 0.7},
      "image": {"emotion": "neutral", "intensity": 0.5}
    }
  }
}
```

### 9.2 角色融合

**接口**: `POST /api/role-fusion/chat`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "question": "用户问题",
  "roleIds": ["角色ID1", "角色ID2"],
  "context": []
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "fusedResponse": "融合后的回答",
    "style": "融合后的风格",
    "contributions": {
      "角色ID1": 0.6,
      "角色ID2": 0.4
    },
    "roleResponses": {
      "角色ID1": "角色1的回答",
      "角色ID2": "角色2的回答"
    }
  }
}
```

### 9.3 知识图谱查询

**接口**: `POST /api/knowledge-graph/query`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "query": "查询问题",
  "topK": 5
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "entities": [
      {"id": "实体ID", "name": "实体名称", "type": "实体类型"}
    ],
    "relations": [
      {"source": "实体1", "target": "实体2", "relation": "关系类型"}
    ],
    "reasoningPaths": [
      ["实体1", "关系1", "实体2", "关系2", "实体3"]
    ]
  }
}
```

### 9.4 自适应学习反馈

**接口**: `POST /api/adaptive-learning/feedback`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求参数**:
```json
{
  "conversationId": "对话ID",
  "feedbackType": "quality",
  "score": 4.5,
  "comment": "反馈评论"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "反馈提交成功"
}
```

### 9.5 多模态处理

**接口**: `POST /api/multimodal/process`

**请求头**:
```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**请求参数**:
- `text`: 文本内容（可选）
- `image`: 图像文件（可选）
- `audio`: 音频文件（可选）
- `document`: 文档文件（可选）

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "textResult": "文本处理结果",
    "imageResult": {
      "description": "图像描述",
      "ocr": "OCR结果"
    },
    "audioResult": {
      "transcription": "语音转文本"
    },
    "documentResult": {
      "content": "文档内容",
      "metadata": {}
    },
    "fusedResult": "融合结果"
  }
}
```

---

## 10. 系统管理接口

### 10.1 健康检查

**接口**: `GET /api/health`

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "status": "healthy",
    "service": "联邦智枢 Backend",
    "version": "1.0.0",
    "timestamp": "2025-01-02T10:00:00Z"
  }
}
```

### 10.2 获取性能指标

**接口**: `GET /api/metrics`

**请求头**:
```
Authorization: Bearer <token>
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "responseTime": 1.5,
    "throughput": 100,
    "errorRate": 0.01,
    "cpuUsage": 0.6,
    "memoryUsage": 0.7
  }
}
```

### 10.3 获取系统统计

**接口**: `GET /api/statistics/system`

**请求头**:
```
Authorization: Bearer <token>
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "totalConversations": 1000,
    "totalMessages": 5000,
    "activeUsers": 100,
    "averageConversationLength": 5.2
  }
}
```

### 10.4 获取用户统计

**接口**: `GET /api/statistics/user/{userId}`

**请求头**:
```
Authorization: Bearer <token>
```

**路径参数**:
- `userId`: 用户ID

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "totalConversations": 50,
    "totalMessages": 250,
    "averageConversationLength": 5.0,
    "mostUsedRole": "律师",
    "activeHours": [9, 10, 14, 15, 16]
  }
}
```

### 10.5 获取告警信息

**接口**: `GET /api/alerts`

**请求头**:
```
Authorization: Bearer <token>
```

**查询参数**:
- `level`: 告警级别（critical/warning/info）
- `limit`: 返回数量（默认10）

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": "告警ID",
      "level": "warning",
      "message": "响应时间超过阈值",
      "timestamp": "2025-01-02T10:00:00Z"
    }
  ]
}
```

---

## 11. 错误码说明

### 11.1 通用错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 11.2 业务错误码

| 错误码 | 说明 |
|--------|------|
| 1001 | 用户不存在 |
| 1002 | 密码错误 |
| 1003 | Token已过期 |
| 2001 | 对话上下文不存在 |
| 2002 | 消息发送失败 |
| 3001 | 角色不存在 |
| 3002 | 角色创建失败 |
| 4001 | 文档上传失败 |
| 4002 | 文档不存在 |
| 5001 | 数字人生成失败 |
| 5002 | 数字人不存在 |

---

## 12. 使用示例

### 12.1 完整对话流程

```javascript
// 1. 用户登录
const loginResponse = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'password123'
  })
});
const { token, user } = await loginResponse.json();

// 2. 发送消息
const chatResponse = await fetch('/api/chat/send', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    'X-User-Id': user.id
  },
  body: JSON.stringify({
    text: '你好，我想了解一下法律问题',
    roleId: 'lawyer-role-id'
  })
});
const { response, contextId } = await chatResponse.json();

// 3. 获取对话历史
const historyResponse = await fetch(`/api/chat/history/${contextId}`, {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const history = await historyResponse.json();
```

### 12.2 语音对话流程

```javascript
// 1. 录音
const audioBlob = await recordAudio();

// 2. 语音转文本
const formData = new FormData();
formData.append('audio', audioBlob);
const asrResponse = await fetch('/api/voice/speech-to-text', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});
const { text } = await asrResponse.json();

// 3. 发送消息
const chatResponse = await fetch('/api/chat/send', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ text })
});

// 4. 文本转语音
const ttsResponse = await fetch('/api/voice/text-to-speech', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    text: chatResponse.response,
    voiceType: 'female'
  })
});
const audioData = await ttsResponse.blob();

// 5. 播放语音
playAudio(audioData);
```

### 12.3 角色融合对话

```javascript
// 使用多个角色融合回答
const fusionResponse = await fetch('/api/role-fusion/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    question: '如何处理合同纠纷？',
    roleIds: ['lawyer-role-id', 'teacher-role-id']
  })
});
const { fusedResponse, contributions } = await fusionResponse.json();
```

---

## 13. 总结

本文档详细介绍了联邦智枢系统的所有API接口，包括：

1. **认证授权**: 用户注册、登录、Token刷新
2. **对话接口**: 文本对话、流式对话、对话历史
3. **语音接口**: 语音识别、语音合成、实时识别
4. **角色管理**: 角色列表、创建、更新、删除
5. **RAG接口**: 文档上传、知识库查询、文档管理
6. **数字人接口**: 数字人生成、驱动、管理
7. **用户管理**: 用户信息、密码修改
8. **创新功能**: 情感识别、角色融合、知识图谱、多模态处理
9. **系统管理**: 健康检查、性能指标、统计信息、告警

所有接口都提供了详细的请求参数、响应格式和使用示例，方便开发者集成和使用。

---

**文档结束**


# 联邦智枢 - 多角色智能体系统

## 项目概述

联邦智枢（Federal Hub）是一个多角色智能体系统。系统采用 **前端(Vue 3) + 后端(Spring Boot) + AI服务(FastAPI)** 三层架构，支持律师、教师、程序员、作家四种专业Agent角色，具备 ReAct 自主规划执行、技能调用、知识检索、流式对话等核心能力。AI 引擎采用 DeepSeek + 通义千问双引擎，文本生成由 DeepSeek 主力驱动。

### 核心特性

- **多Agent角色系统**: 律师/教师/程序员/作家四种专业Agent，支持无缝切换，每种Agent拥有独立的Skill面板和视觉风格（蓝/绿/紫/琥珀四色主题）
- **ReAct推理引擎**: 基于Thought-Action-Observation循环的自主规划执行，可观测、可追踪
- **流式对话(SSE)**: DeepSeek 主力驱动的文本生成，支持 Server-Sent Events 实时逐字输出
- **双AI引擎**: DeepSeek(文本主引擎) + 通义千问(图像/语音/多模态备用)，Python SDK 层自动路由与回退
- **合同起草规划器**: 交互式 markmap 思维树，5 大职业领域 × 31 个细分专业，Demo/API 双模式，四色主题面板
- **联邦智能体工作台**: 多专业体协同编排，流程步骤可视化，联邦节点状态监控，任务进度追踪
- **知识检索增强(RAG)**: ChromaDB向量数据库 + sentence-transformers嵌入，支持法条/判例/教育知识检索
- **联邦学习优化**: 隐私保护的模型持续优化，联邦学习全局最优模型系统（业界首创RAG联邦优化）
- **数字人系统**: AIGC生成数字人形象，实时语音驱动，多风格切换
- **情感感知对话**: 多模态情感识别，情感驱动的个性化回复
- **智能角色融合**: 多角色协同，融合不同专业角度的回答
- **知识图谱增强**: 结构化知识检索与推理
- **多语言支持**: 简体中文/英文切换，vue-i18n国际化

## 技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.3.4 | 前端框架 |
| TypeScript | 5.4.5 | 类型安全 |
| Vite | 5.0.0 | 构建工具 |
| Element Plus | 2.4.4 | UI组件库 |
| Pinia | 2.1.7 | 状态管理 |
| Vue Router | 4.2.5 | 路由管理 |
| vue-i18n | 9.14.5 | 国际化 |
| Three.js | 0.158.0 | 3D渲染（数字人） |
| vis-network | 10.0.2 | 知识图谱可视化 |
| Axios | 1.6.2 | HTTP客户端 |
| Socket.IO Client | 4.6.1 | WebSocket实时通信 |
| Sass | 1.97.1 | CSS预处理器 |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| Java | 17 | 编程语言 |
| Spring Boot | 3.2.0 | 应用框架 |
| Spring Data JPA | - | 数据持久化 |
| Spring Data Redis | - | 缓存 |
| Spring WebSocket | - | 实时通信 |
| Spring Validation | - | 参数校验 |
| PostgreSQL | 15 | 关系数据库 |
| Redis | 7 | 缓存/会话 |
| JWT | - | 认证授权 |
| MapStruct | - | 对象映射 |
| Hibernate | 6.x | ORM框架 |

### AI服务
| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.9+ | 编程语言 |
| FastAPI | 0.104.1 | Web框架 |
| Uvicorn | 0.24.0 | ASGI服务器 |
| Pydantic | 2.5.0 | 数据验证 |
| OpenAI SDK | 1.12.0 | DeepSeek + 通义千问兼容调用 |
| DashScope SDK | 1.23.1+ | 阿里云AI服务（语音/图像/多模态） |
| DeepSeek API | - | 文本生成主引擎（速度快、成本低） |
| ChromaDB | 0.4.15 | 向量数据库 |
| markmap | 0.18.x | 交互式思维导图 |
| sentence-transformers | 5.x | 文本嵌入 |
| PyPDF2 | 3.0.1 | PDF解析 |
| pdfplumber | 0.10.3 | PDF增强解析 |
| python-docx | 1.1.0 | Word文档解析 |
| openpyxl | 3.1.2 | Excel解析 |

### 基础设施
| 技术 | 用途 |
|------|------|
| Docker | 容器化部署 |
| Docker Compose | 服务编排 |
| Nginx | 反向代理/静态资源 |
| Git | 版本控制 |

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    用户交互层 (Frontend)                       │
│   Vue 3 + TypeScript + Element Plus + Pinia                  │
│   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│   │ 对话 │ │ 语音 │ │ 数字 │ │ 角色 │ │ 知识 │ │ 联邦 │   │
│   │ 界面 │ │ 对话 │ │  人  │ │ 管理 │ │  库  │ │ 学习 │   │
│   └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘   │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP/WebSocket
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                  业务网关层 (Backend)                          │
│   Spring Boot 3.2 + Java 17 + JWT + Redis                   │
│   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            │
│   │ 认证 │ │ 对话 │ │ 角色 │ │ 文件 │ │ Agent│            │
│   │ 授权 │ │ 处理 │ │ 管理 │ │ 管理 │ │ 网关 │            │
│   └──────┘ └──────┘ └──────┘ └──────┘ └──────┘            │
│   PostgreSQL + Redis                                         │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP (REST API)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                  AI引擎层 (AI Service)                        │
│   FastAPI + Python 3.9+ + 通义千问                           │
│   ┌──────────────────────────────────────────────┐          │
│   │           ReAct 推理引擎                       │          │
│   │  Planner → ToolRouter → Executor → Memory    │          │
│   └──────────┬───────────────────────────────────┘          │
│              │ Skill调用                                     │
│   ┌─────────┴──────────────────────────────────┐           │
│   │ 律师Skills │ 教师Skills │ 程序员 │ 作家    │           │
│   │ 案情理解   │ 学生诊断   │ 代码   │ 大纲    │           │
│   │ 法条检索   │ 教案生成   │ 审查   │ 风格    │           │
│   │ 判例检索   │ 作业批改   │ 调试   │ 分析    │           │
│   │ 文书生成   │ 错因推送   │ 架构   │ 情节    │           │
│   │ 风险评估   │ 学习路径   │ 测试   │ 润色    │           │
│   └───────────────────────────────────────────┘           │
│   ChromaDB向量库 + 知识图谱 + 联邦学习                       │
└──────────────────────────────────────────────────────────────┘
```

## 项目结构

```
kinlin_-ai/
├── frontend/                          # 前端项目 (Vue 3 + TypeScript)
│   ├── src/
│   │   ├── views/                     # 页面组件
│   │   │   ├── ChatView.vue              # 对话主页面（4种Agent切换 + 流式输出）
│   │   │   ├── ContractClausePlannerView.vue  # 合同起草规划器（markmap思维树）
│   │   │   ├── FederatedAgentWorkbenchView.vue # 联邦智能体工作台
│   │   │   ├── VoiceChatView.vue         # 语音对话页面
│   │   │   ├── RoleView.vue              # 角色管理页面
│   │   │   ├── RagView.vue               # 知识库页面
│   │   │   ├── FederatedModelManagementView.vue # 联邦模型管理
│   │   │   ├── FederatedLearningView.vue # 联邦学习管理
│   │   │   ├── HistoryView.vue           # 历史记录页面
│   │   │   ├── SettingsView.vue          # 设置页面
│   │   │   ├── UserView.vue              # 用户中心页面
│   │   │   └── LoginView.vue             # 登录页面
│   │   ├── components/
│   │   │   ├── agent/                 # Agent专用组件
│   │   │   │   ├── LawyerSkillPanel.vue     # 律师技能面板（蓝色主题）
│   │   │   │   ├── TeacherSkillPanel.vue    # 教师技能面板（翠绿主题）
│   │   │   │   ├── ProgrammerSkillPanel.vue # 程序员技能面板（紫蓝主题）
│   │   │   │   ├── WriterSkillPanel.vue     # 作家技能面板（琥珀主题）
│   │   │   │   ├── TraceTimeline.vue        # ReAct执行轨迹
│   │   │   │   └── ...（各Agent子卡片组件）
│   │   │   ├── MessageBubble.vue      # 消息气泡
│   │   │   ├── DigitalHuman.vue       # 数字人组件
│   │   │   ├── VoiceRecorder.vue      # 语音录制
│   │   │   └── ...
│   │   ├── stores/                    # Pinia状态管理
│   │   │   ├── chat.ts                # 对话状态（含Agent消息处理）
│   │   │   ├── role.ts                # 角色状态
│   │   │   └── user.ts                # 用户状态
│   │   ├── services/api/              # API服务层
│   │   │   ├── agentLawyer.ts         # 律师Agent API
│   │   │   ├── agentTeacher.ts        # 教师Agent API
│   │   │   ├── agentProgrammer.ts     # 程序员Agent API
│   │   │   ├── agentWriter.ts         # 作家Agent API
│   │   │   └── ...
│   │   ├── router/                    # 路由配置
│   │   ├── i18n/                      # 国际化
│   │   ├── utils/                     # 工具函数
│   │   │   ├── agentDisplay.ts        # Agent显示映射
│   │   │   └── ...
│   │   └── styles/                    # 全局样式
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
├── backend/                           # 后端项目 (Spring Boot + Java 17)
│   ├── src/main/java/com/kinlin/ai/
│   │   ├── controller/                # REST控制器
│   │   │   ├── AgentController.java        # Agent统一入口
│   │   │   ├── ChatController.java         # 对话控制器
│   │   │   ├── AuthController.java         # 认证控制器
│   │   │   ├── RoleController.java         # 角色控制器
│   │   │   ├── VoiceController.java        # 语音控制器
│   │   │   ├── DigitalHumanController.java # 数字人控制器
│   │   │   ├── RagController.java          # RAG控制器
│   │   │   └── ...
│   │   ├── service/                   # 业务服务层
│   │   │   ├── AgentGatewayService.java    # Agent网关服务
│   │   │   ├── ChatService.java            # 对话服务
│   │   │   ├── RoleService.java            # 角色服务
│   │   │   └── ...
│   │   ├── entity/                    # JPA实体
│   │   ├── repository/                # 数据访问层
│   │   ├── dto/                       # 数据传输对象
│   │   │   └── agent/                 # Agent相关DTO
│   │   ├── config/                    # 配置类
│   │   │   ├── SecurityConfig.java         # 安全配置
│   │   │   ├── AgentProperties.java        # Agent配置
│   │   │   └── ...
│   │   └── filter/                    # 过滤器
│   ├── src/main/resources/
│   │   └── application.yml            # 应用配置
│   ├── pom.xml
│   └── Dockerfile
│
├── agent/                             # AI服务 (FastAPI + Python)
│   ├── app/
│   │   ├── main.py                    # FastAPI应用入口
│   │   ├── config.py                  # 配置管理（Settings单例）
│   │   ├── api/                       # API路由
│   │   │   ├── agent_lawyer.py        # 律师Agent入口
│   │   │   ├── agent_teacher.py       # 教师Agent入口
│   │   │   ├── chat.py                # 通用对话
│   │   │   ├── rag.py                 # RAG检索
│   │   │   ├── tts.py                 # 语音合成
│   │   │   └── ...
│   │   ├── agent_core/                # Agent核心
│   │   │   ├── react/                 # ReAct推理引擎
│   │   │   │   ├── planner.py              # 规划器
│   │   │   │   ├── tool_router.py          # 工具路由
│   │   │   │   └── executor.py             # 执行器
│   │   │   ├── skills/                # 技能实现
│   │   │   │   ├── teacher/               # 教师Skills（9个）
│   │   │   │   ├── base.py                # Skill基类
│   │   │   │   └── ...律师Skills（8个）
│   │   │   ├── memory/                # 会话记忆
│   │   │   ├── retrieval/             # 检索模块
│   │   │   ├── schema/                # 数据模型
│   │   │   └── federated/             # 联邦学习适配
│   │   ├── ai_engine/                 # AI引擎
│   │   │   ├── deepseekadapter.py         # DeepSeek适配器（文本主引擎）
│   │   │   ├── qwenadapter.py             # 通义千问适配器（图像/语音/多模态）
│   │   │   ├── speechadapter.py           # 语音适配器（ASR/TTS）
│   │   │   ├── multimodaladapter.py       # 多模态适配器（Qwen-VL）
│   │   │   └── kylin_sdk/                 # 麒麟SDK客户端（引擎路由）
│   │   ├── services/                  # 业务服务
│   │   ├── prompts/                   # Prompt模板
│   │   └── data/                      # 数据文件
│   │       ├── legal/                 # 法条/判例数据
│   │       ├── education/             # 教育知识数据
│   │       └── rag/                   # RAG知识库
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker/                            # Docker配置
│   ├── docker-compose.prod.yml        # 生产环境编排
│   └── nginx/                         # Nginx配置
│
├── 开发文档/                          # 项目文档
│   ├── docs-overview/                 # 概述类文档
│   ├── docs-architecture/             # 架构类文档
│   ├── docs-development/              # 开发指南
│   ├── docs-innovation/               # 创新功能文档
│   ├── docs/                          # 技术文档集
│   └── docs-pdfs/                     # PDF文档
│
└── README.md                          # 本文件
```

## Agent系统详解

### Agent架构

所有Agent共享统一的ReAct推理引擎，通过Skill插件实现专业能力：

```
用户请求 → ReAct Planner(规划) → Tool Router(路由) → Executor(执行)
                                                        ↓
                                              Skill调用 → ChromaDB检索
                                                        ↓
                                              结果聚合 → 响应生成
```

### 四种Agent角色

| Agent | 主题色 | Skills | 前端面板 |
|-------|--------|--------|----------|
| 律师 | 蓝色 #2563eb | 案情理解、法条检索、判例检索、证据分析、文书生成、庭审提纲、管辖确定、诉讼时效、风险评估 | LawyerSkillPanel |
| 教师 | 翠绿 #059669 | 学生诊断、教案生成、作业批改、错因推送、辅导答疑、学习路径、进度报告、课堂互动、家长沟通 | TeacherSkillPanel |
| 程序员 | 紫蓝 #7c3aed | 代码审查、调试追踪、架构建议、单元测试 | ProgrammerSkillPanel |
| 作家 | 琥珀 #d97706 | 大纲查看、风格分析、情节逻辑、润色对比 | WriterSkillPanel |

### Agent API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ai/agent/lawyer/chat` | POST | 律师Agent对话 |
| `/ai/agent/teacher/chat` | POST | 教师Agent对话 |
| `/ai/agent/programmer/chat` | POST | 程序员Agent对话 |
| `/ai/agent/writer/chat` | POST | 作家Agent对话 |
| `/ai/chat/text` | POST | 通用文本对话 |
| `/ai/chat/text/stream` | POST | 流式文本对话 (SSE) |
| `/ai/chat/voice` | POST | 语音对话 |
| `/ai/tts` | POST | 语音合成 |
| `/ai/rag/query` | POST | RAG检索 |
| `/ai/federated-models/list` | GET | 联邦模型列表 |

### Agent请求/响应格式

**请求**:
```json
{
  "text": "用户输入文本",
  "sessionId": "会话ID（可选）"
}
```

**响应**:
```json
{
  "success": true,
  "answer": "Agent回复",
  "sessionId": "会话ID",
  "skillsUsed": ["skill1", "skill2"],
  "trace": [
    {"step": 1, "thought": "...", "action": "...", "observation": "..."}
  ],
  "riskLevel": "low/medium/high",
  "federated": {},
  "message": null,
  "error": null
}
```

## 快速开始

### 环境要求

- Java 17+
- Python 3.9+
- Node.js 18+
- Docker & Docker Compose（推荐）
- PostgreSQL 15+
- Redis 7+

### 1. 配置API密钥

在项目根目录创建 `.env` 文件：

```env
# DeepSeek API密钥（文本生成主引擎，速度快）
DEEPSEEK_API_KEY=sk-your_deepseek_key
DEEPSEEK_MODEL=deepseek-chat

# 通义千问API密钥（图像/语音/多模态 + 文本回退）
DASHSCOPE_API_KEY=sk-your_qwen_key

# 数据库配置（Docker部署时使用默认值即可）
DB_USERNAME=kinlin_ai
DB_PASSWORD=kinlin_ai_password

# Redis密码
REDIS_PASSWORD=redis_password
```

### 2. Docker部署（推荐）

```bash
# 启动所有服务
cd docker
docker-compose -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps
```

服务端口：
- 前端: http://localhost:80
- 后端API: http://localhost:8080
- AI服务: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 3. 开发模式启动

```bash
# 启动数据库（Docker）
cd docker
docker-compose -f docker-compose.dev.yml up -d postgres redis

# 启动后端
cd backend
mvn spring-boot:run

# 启动AI服务
cd agent
pip install -r requirements.txt
python app/main.py

# 启动前端
cd frontend
npm install
npm run dev
```

开发模式端口：
- 前端开发服务器: http://localhost:5173
- 后端API: http://localhost:8080
- AI服务: http://localhost:8000

### 4. 验证服务

```bash
# 检查后端健康
curl http://localhost:8080/health

# 检查AI服务健康
curl http://localhost:8000/health
```

## 关键配置说明

### 后端配置 (application.yml)

```yaml
# 数据库
spring.datasource.url: jdbc:postgresql://localhost:5432/kinlin_ai
spring.datasource.username: postgres
spring.datasource.password: ROOT

# Redis
spring.data.redis.host: localhost
spring.data.redis.port: 6379

# AI服务地址
ai.service.url: http://localhost:8000

# Agent配置
agent.enabled: true
agent.timeout-ms: 120000
agent.python.lawyer-chat-url: http://localhost:8000/ai/agent/lawyer/chat
agent.python.teacher-chat-url: http://localhost:8000/ai/agent/teacher/chat
agent.federated.enabled: false

# JWT
app.jwt.secret: (生产环境必须更换)
app.jwt.expiration: 86400000  # 24小时
```

### AI服务配置 (config.py)

```python
# DeepSeek（文本生成主引擎）
DEEPSEEK_API_KEY: str = ""                    # API密钥
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL: str = "deepseek-chat"
TEXT_ENGINE: str = "auto"                     # auto/DeepSeek/qwen

# 通义千问（图像/语音/多模态 + 文本回退）
DASHSCOPE_API_KEY: str = ""                   # API密钥
QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL_FAST: str = "qwen-turbo"           # 快速模型
QWEN_MODEL_BALANCED: str = "qwen-plus"        # 平衡模型
QWEN_MODEL_ADVANCED: str = "qwen-max"         # 高级模型
QWEN_MODEL_LATEST: str = "qwen3-max"          # 最新模型

# 联邦学习
AGENT_FEDERATED_ENABLED: bool = False
AGENT_FEDERATED_TIMEOUT_MS: int = 1500
```

### 前端代理配置 (vite.config.ts)

开发模式下，前端通过Vite代理转发API请求：
- `/api/*` → `http://localhost:8080`（部分路径去掉/api前缀）
- `/ai/*` → `http://localhost:8080`（Java后端代理到Python服务）

## 开发指南

### 新增Agent角色

1. **后端**: 在 `agent/app/api/` 创建 `agent_xxx.py`，实现Agent入口路由
2. **Skills**: 在 `agent/app/agent_core/skills/` 创建Skill实现
3. **Schema**: 在 `agent/app/agent_core/schema/agent_types.py` 添加请求/响应模型
4. **前端API**: 在 `frontend/src/services/api/` 创建 `agentXxx.ts`
5. **前端面板**: 在 `frontend/src/components/agent/` 创建 `XxxSkillPanel.vue`
6. **状态管理**: 更新 `frontend/src/stores/chat.ts` 添加新Agent消息处理
7. **显示映射**: 更新 `frontend/src/utils/agentDisplay.ts` 添加技能映射
8. **集成**: 更新 `ChatView.vue` 添加新Agent切换逻辑

### 新增Skill

1. 继承 `agent/app/agent_core/skills/base.py` 中的Skill基类
2. 实现 `execute()` 方法
3. 在 `agent/app/agent_core/react/tool_router.py` 中注册
4. 在对应Agent的API文件中添加上下文构建逻辑

### 代码规范

- 前端: TypeScript严格模式，Vue 3 Composition API
- 后端: Java 17，Spring Boot标准分层架构
- AI服务: Python 3.9+，FastAPI异步模式
- 所有配置通过环境变量/`.env`文件管理，不硬编码

## 开发文档索引

### 项目概述类
- [工作日志-Work-Log](./开发文档/docs-overview/工作日志-Work-Log.md) - 开发过程记录
- [推送总结-2026-04-14-PUSH_SUMMARY](./开发文档/docs-overview/推送总结-2026-04-14-PUSH_SUMMARY.md) - 代码提交汇总

### 技术架构类
- [Agent架构蓝图-AGENT_ARCHITECTURE](./开发文档/docs-architecture/Agent架构蓝图-AGENT_ARCHITECTURE.md) - Agent架构设计、技术选型、Skill设计
- [项目阶段总报告-CHECK_REPORT](./开发文档/docs-architecture/项目阶段总报告-CHECK_REPORT.md) - 开发进度、Phase执行记录
- [后端README](./backend/README.md) - 后端技术栈与构建说明
- [AI服务README](./agent/README.md) - AI服务配置说明

### 开发指南类
- [待办事项-TODO](./开发文档/docs-development/待办事项-TODO.md) - 任务跟踪与优先级
- [清除浏览器缓存-Clear-Browser-Cache](./开发文档/docs-development/清除浏览器缓存-Clear-Browser-Cache.md) - 前端调试指南

### 创新功能类
- [联邦学习创新点-Federated-Learning-Innovation](./开发文档/docs-innovation/联邦学习创新点-Federated-Learning-Innovation.md) - 联邦学习全局最优模型系统

### 技术文档集
- [README-项目文档索引](./开发文档/docs/README-项目文档索引.md) - 项目文档导航
- [索引-Index](./开发文档/docs/索引-Index.md) - 完整技术文档导航

### 使用说明类
- [01-项目概述-Project-Overview](./开发文档/docs/使用说明/01-项目概述-Project-Overview.md) - 项目概述和技术架构
- [02-核心功能详解-Core-Features](./开发文档/docs/使用说明/02-核心功能详解-Core-Features.md) - 核心功能详解
- [03-创新功能详解-Innovation-Features](./开发文档/docs/使用说明/03-创新功能详解-Innovation-Features.md) - 创新功能详解
- [04-部署运维指南-Deployment-Operations](./开发文档/docs/使用说明/04-部署运维指南-Deployment-Operations.md) - 部署和运维指南
- [05-API接口文档-API-Documentation](./开发文档/docs/使用说明/05-API接口文档-API-Documentation.md) - API接口文档
- [06-联邦学习专题-Federated-Learning](./开发文档/docs/使用说明/06-联邦学习专题-Federated-Learning.md) - 联邦学习专题

### 架构文档类
- [架构文档-Architecture-Docs](./开发文档/docs/架构/README.md) - 系统架构设计文档
- [Agent架构蓝图-AGENT_ARCHITECTURE](./开发文档/docs-architecture/Agent架构蓝图-AGENT_ARCHITECTURE.md) - Agent架构设计、技术选型、Skill设计
- [项目阶段总报告-CHECK_REPORT](./开发文档/docs-architecture/项目阶段总报告-CHECK_REPORT.md) - 开发进度、Phase执行记录

### 功能实现类
- [快速开始-麒麟SDK和增强RAG-Quick-Start](./开发文档/docs/使用说明/快速开始-麒麟SDK和增强RAG-Quick-Start.md) - 麒麟SDK和增强RAG快速开始
- [数字人图像加载修复-Digital-Human-Image-Fix](./开发文档/docs/使用说明/数字人图像加载修复-Digital-Human-Image-Fix.md) - 数字人图像加载修复说明
- [数字人形象保存-Digital-Human-Profile-Save](./开发文档/docs/使用说明/数字人形象保存-Digital-Human-Profile-Save.md) - 数字人形象保存说明
- [数字人语音对话修复-Digital-Human-Voice-Fix](./开发文档/docs/使用说明/数字人语音对话修复-Digital-Human-Voice-Fix.md) - 数字人语音对话修复说明
- [数字人路径配置-Digital-Human-Path-Config](./开发文档/docs/使用说明/数字人路径配置-Digital-Human-Path-Config.md) - 数字人路径配置说明
- [语音对话功能完整实现-Voice-Dialog-Implementation](./开发文档/docs/使用说明/语音对话功能完整实现-Voice-Dialog-Implementation.md) - 语音对话功能完整实现说明
- [知识库按角色分类-Knowledge-Base-Role-Classification](./开发文档/docs/使用说明/知识库按角色分类-Knowledge-Base-Role-Classification.md) - 知识库按角色分类使用说明
- [麒麟AI_API使用说明-Kinlin-AI-API-Guide](./开发文档/docs/使用说明/麒麟AI_API使用说明-Kinlin-AI-API-Guide.md) - 麒麟AI_API使用说明
- [麒麟SDK与RAG增强实现总结-Kinlin-SDK-RAG-Summary](./开发文档/docs/使用说明/麒麟SDK与RAG增强实现总结-Kinlin-SDK-RAG-Summary.md) - 麒麟SDK与RAG增强实现总结
- [麒麟SDK智能切换与增强RAG指南-Kinlin-SDK-Smart-Switch-RAG-Guide](./开发文档/docs/使用说明/麒麟SDK智能切换与增强RAG指南-Kinlin-SDK-Smart-Switch-RAG-Guide.md) - 麒麟SDK智能切换与增强RAG指南

### 问题修复类
- [问题修复指南-ChromaDB和Pydantic-Issue-Fix-Guide](./开发文档/docs/使用说明/问题修复指南-ChromaDB和Pydantic-Issue-Fix-Guide.md) - ChromaDB和Pydantic问题修复指南
- [更新说明-2025-01-03-麒麟SDK与RAG增强-Update-Notes](./开发文档/docs/使用说明/更新说明-2025-01-03-麒麟SDK与RAG增强-Update-Notes.md) - 更新说明

### 联邦学习专题类
- [联邦学习全局最优模型使用指南-Federated-Learning-Global-Model-Guide](./开发文档/docs/使用说明/联邦学习全局最优模型使用指南-Federated-Learning-Global-Model-Guide.md) - 联邦学习全局最优模型使用指南
- [联邦学习全局最优模型可行性分析-Federated-Learning-Feasibility-Analysis](./开发文档/docs/使用说明/联邦学习全局最优模型可行性分析-Federated-Learning-Feasibility-Analysis.md) - 联邦学习全局最优模型可行性分析
- [联邦学习全局最优模型实现报告-Federated-Learning-Implementation-Report](./开发文档/docs/使用说明/联邦学习全局最优模型实现报告-Federated-Learning-Implementation-Report.md) - 联邦学习全局最优模型实现报告
- [联邦学习全局最优模型快速开始-Federated-Learning-Quick-Start](./开发文档/docs/使用说明/联邦学习全局最优模型快速开始-Federated-Learning-Quick-Start.md) - 联邦学习全局最优模型快速开始
- [联邦学习全局最优模型总结报告-Federated-Learning-Summary-Report](./开发文档/docs/使用说明/联邦学习全局最优模型总结报告-Federated-Learning-Summary-Report.md) - 联邦学习全局最优模型总结报告
- [联邦学习全局最优模型最终版本-Federated-Learning-Final-Version](./开发文档/docs/使用说明/联邦学习全局最优模型最终版本-Federated-Learning-Final-Version.md) - 联邦学习全局最优模型最终版本说明

### PDF文档
- [KFC-Agent文档v7](./开发文档/docs-pdfs/KFC-Agent文档v7.pdf) - Agent系统详细规范
- [麒麟AI SDK开发指南](./开发文档/docs-pdfs/麒麟 AI SDK 开发指南.pdf)

## 常见问题

### 1. 前端启动报错
- 确保Node.js版本 >= 18
- 删除 `node_modules` 后重新 `npm install`
- 清除浏览器缓存（参考开发文档中的清除指南）

### 2. 后端连接数据库失败
- 确认PostgreSQL已启动：`docker ps | grep postgres`
- 检查 `application.yml` 中的数据库配置
- 默认数据库：`kinlin_ai`，用户：`postgres`，密码：`ROOT`

### 3. AI服务启动警告
- `KYLIN_AI_API_KEY` 未设置：正常，系统会使用通义千问
- ChromaDB初始化失败：运行 `python agent/fix_chromadb.py`
- Pydantic命名空间警告：已修复，确保使用最新代码

### 4. Agent响应超时
- 检查 `agent.timeout-ms` 配置（默认120秒）
- 确认AI服务正常运行：`curl http://localhost:8000/health`
- 查看AI服务日志排查Skill执行错误

### 5. Docker部署问题
- 确保Docker Desktop已启动
- 端口冲突：检查80/8080/8000/5432/6379端口是否被占用
- 使用 `docker-compose logs <service>` 查看服务日志

## 许可证

MIT License

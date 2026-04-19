# Kinlin AI 项目技术说明书

> **生成时间**：2025-07-01  
> **基于代码版本**：Git commit `93ecfa9`（分支 `feat/teacher-federated-stability-20260417`）  
> **项目全称**：Kinlin AI — 智能多角色交互助手系统

---

## 1 项目概述

### 1.1 背景

随着大语言模型（LLM）技术的成熟，AI 助手已从简单的问答系统演进为具备自主规划与工具调用能力的智能体（Agent）。然而，通用聊天机器人在法律、教育、编程、创作等专业领域面临三大瓶颈：**缺乏领域知识导致幻觉频发**、**单一对话模式无法完成多步骤专业任务**、**角色切换时无法保持专业一致性**。

### 1.2 目标

Kinlin AI 旨在构建一个**多角色自主智能体系统**，使 AI 能够像律师、教师、程序员、作家一样，通过"思考-规划-执行"的 ReAct 循环自主完成专业任务，同时借助 RAG 知识库保障输出的专业性与可溯源性。

### 1.3 整体定位

本项目是一个**面向专业领域的多 Agent 协作平台**，运行于银河麒麟操作系统，以通义千问大模型为推理引擎，采用"前端 Vue 3 + 网关 Spring Boot + AI 服务 FastAPI"三层架构，支持四类角色的独立 Skill 调用、知识检索增强与联邦学习隐私协同优化。

---

## 2 系统架构

### 2.1 架构总览

```
┌───────────────────────────────────────────────────────────────────┐
│                     用户交互层 (Frontend)                          │
│  Vue 3 + TypeScript + Element Plus + Pinia                       │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │
│  │ 对话   │ │ 技能   │ │ 知识库 │ │ 联邦   │ │ 数字人 │        │
│  │ 界面   │ │ 面板   │ │ 管理   │ │ 学习   │ │ 交互   │        │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘        │
└────────────────────────┬──────────────────────────────────────────┘
                         │ HTTP / WebSocket
                         ▼
┌───────────────────────────────────────────────────────────────────┐
│                    业务网关层 (Backend)                            │
│  Spring Boot 3.2 + Java 17 + JWT + Redis                        │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                   │
│  │ 认证   │ │ 对话   │ │ Agent  │ │ 文件   │                   │
│  │ 授权   │ │ 处理   │ │ 网关   │ │ 管理   │                   │
│  └────────┘ └────────┘ └────────┘ └────────┘                   │
│  PostgreSQL + Redis                                               │
└────────────────────────┬──────────────────────────────────────────┘
                         │ HTTP (REST API)
                         ▼
┌───────────────────────────────────────────────────────────────────┐
│                    AI 引擎层 (AI Service)                         │
│  FastAPI + Python 3.9+ + 通义千问                                │
│  ┌──────────────────────────────────────────────────┐            │
│  │              ReAct 推理引擎                        │            │
│  │   ReactPlanner → ToolRouter → ReactExecutor      │            │
│  └───────────────────┬──────────────────────────────┘            │
│                      │ Skill 调用                                 │
│  ┌───────────────────┴──────────────────────────────┐            │
│  │ 律师 Skills │ 教师 Skills │ 程序员 Skills │ 作家  │            │
│  │ (9 个)      │ (9 个)      │ (4 个)        │ (4个) │            │
│  └──────────────────────────────────────────────────┘            │
│  ChromaDB 向量库 + 会话记忆 + 联邦学习适配器                      │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 架构设计原则

| 原则 | 实现方式 |
|------|----------|
| **分层解耦** | 前端不直连 Python 服务，经 Java 网关统一鉴权与路由 |
| **Skill 插件化** | 所有 Skill 继承 `BaseSkill` 抽象类，通过 `ToolRouter` 按角色注册 |
| **Fail-Open 容错** | 联邦学习、向量检索等可选模块失败时降级而非阻断主流程 |
| **会话隔离** | `SessionMemoryStore` 按 sessionId 维护独立对话历史（上限 20 条） |

---

## 3 技术栈清单

### 3.1 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.3.4 | 前端框架 |
| TypeScript | 5.4.5 | 类型安全 |
| Vite | 5.0.0 | 构建工具 |
| Element Plus | 2.4.4 | UI 组件库 |
| Pinia | 2.1.7 | 状态管理 |
| Vue Router | 4.2.5 | 路由管理 |
| vue-i18n | 9.14.5 | 国际化（中/英） |
| Three.js | 0.158.0 | 数字人 3D 渲染 |
| vis-network | 10.0.2 | 知识图谱可视化 |
| Axios | 1.6.2 | HTTP 客户端 |
| Socket.IO Client | 4.6.1 | WebSocket 实时通信 |
| Sass | 1.97.1 | CSS 预处理器 |

### 3.2 后端（Java 网关）

| 技术 | 版本 | 用途 |
|------|------|------|
| Java | 17 | 编程语言 |
| Spring Boot | 3.2.0 | 应用框架 |
| Spring Data JPA | — | 数据持久化 |
| Spring Data Redis | — | 缓存/会话 |
| Spring WebSocket | — | 实时通信 |
| PostgreSQL | 15 | 关系数据库 |
| Redis | 7 | 缓存/会话存储 |
| JWT | — | 认证授权 |
| MapStruct | — | 对象映射 |
| RestTemplate | — | HTTP 代理调用 |

### 3.3 AI 服务（Python）

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.9+ | 编程语言 |
| FastAPI | 0.104.1 | Web 框架 |
| Uvicorn | 0.24.0 | ASGI 服务器 |
| Pydantic | 2.5.0 | 数据验证 |
| OpenAI SDK | 1.12.0 | 通义千问兼容调用 |
| DashScope SDK | 1.23.1+ | 阿里云 AI 服务 |
| ChromaDB | 0.4.15 | 向量数据库 |
| sentence-transformers | 5.x | 文本嵌入 |
| httpx | — | 异步 HTTP 客户端 |

### 3.4 基础设施

| 技术 | 用途 |
|------|------|
| Docker | 容器化部署 |
| Docker Compose | 服务编排 |
| Nginx | 反向代理/静态资源 |
| Git | 版本控制 |

---

## 4 核心模块详述

### 4.1 多角色 Agent 体系

**[创新点标注]** 本项目采用"统一引擎 + 角色 Skill 插件"架构，四种专业角色共享同一套 ReAct 推理引擎，通过 `ToolRouter` 按角色注册不同 Skill 集合，实现"一套引擎、四种专业能力"的复用设计。

#### 4.1.1 角色与 Skill 映射

| 角色 | 主题色 | Skill 数量 | Skill 列表 |
|------|--------|-----------|-----------|
| 律师 (lawyer) | 蓝色 #2563eb | 9 | case_understanding, statute_retrieval, case_retrieval, evidence_analysis, limitation_calculation, jurisdiction_determination, hearing_outline_generation, document_generation, risk_assessment |
| 教师 (teacher) | 翠绿 #059669 | 9 | student_diagnosis, lesson_plan_generation, homework_grading, error_analysis_question_push, tutoring_qa, learning_path_planning, progress_report_generation, classroom_interaction_design, parent_communication_suggestion |
| 程序员 (programmer) | 紫蓝 #7c3aed | 4 | requirement_analysis, codebase_semantic_search, code_generation, diagram_generation |
| 作家 (writer) | 琥珀 #d97706 | 4 | inspiration_expand, outline_generate, content_write, character_relation_map |

#### 4.1.2 Skill 基类设计

所有 Skill 继承自 `BaseSkill`（位于 `agent/app/agent_core/skills/base.py`），定义统一接口：

```python
class BaseSkill(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def run(self, request: SkillRequest) -> SkillResult:
        raise NotImplementedError
```

- **SkillRequest**：包含 `sessionId`、`text`、`actionInput`（Dict）、`memory`（Dict）
- **SkillResult**：包含 `skillName`、`success`、`output`（Dict）、`message`

未注册的 Skill 自动路由到 `NoOpSkill`（回显输入），保证系统不会因未知 Action 崩溃。

#### 4.1.3 ToolRouter 路由机制

`ToolRouter`（位于 `agent/app/agent_core/react/tool_router.py`）在初始化时为每个角色构建 Skill 字典：

```python
self.skills_by_role: Dict[str, Dict[str, BaseSkill]] = {
    "lawyer": { "case_understanding": CaseUnderstandingSkill(), ... },
    "teacher": { "student_diagnosis": StudentDiagnosisSkill(), ... },
    "programmer": { "requirement_analysis": RequirementAnalysisSkill(), ... },
    "writer": { "inspiration_expand": InspirationExpandSkill(), ... },
}
```

执行时根据角色名查找对应 Skill 字典，若 Action 不存在则降级到 `NoOpSkill`。

#### 4.1.4 前端角色面板

每个角色拥有独立的 Vue 技能面板组件，展示 Skill 执行结果的可视化卡片：

| 角色 | 面板组件 | 可视化卡片 |
|------|---------|-----------|
| 律师 | `LawyerSkillPanel.vue` | EvidenceAnalysisCard, LimitationTimeline, JurisdictionCard, HearingOutlineViewer |
| 教师 | `TeacherSkillPanel.vue` | DiagnosisRadar, LessonPlanViewer, GradingResultCard, QuestionPushList |
| 程序员 | `ProgrammerSkillPanel.vue` | CodeReviewCard, DebugTraceCard, ArchSuggestCard, DiagramViewer, UnitTestCard |
| 作家 | `WriterSkillPanel.vue` | MindMapViewer, OutlineViewer, PolishDiffCard, PlotLogicCard, RelationGraph |

---

### 4.2 ReAct 自主规划引擎

**[创新点标注]** 本项目实现了完整的 ReAct（Reasoning + Acting）推理循环，Agent 不是简单的"输入→输出"，而是先"思考"用户意图、再"规划"需要调用的 Skill 序列、然后逐步"执行"并"观察"结果，最终综合所有 Skill 输出生成回答。区别于传统 Function Calling 的单步调用，ReAct 引擎支持多步串行执行与上下文传递。

#### 4.2.1 三大核心组件

| 组件 | 类名 | 文件路径 | 职责 |
|------|------|---------|------|
| 规划器 | `ReactPlanner` | `agent/app/agent_core/react/planner.py` | 解析用户意图，生成 PlannedAction 序列 |
| 工具路由 | `ToolRouter` | `agent/app/agent_core/react/tool_router.py` | 将 Action 名映射到具体 Skill 实例 |
| 执行器 | `ReactExecutor` | `agent/app/agent_core/react/executor.py` | 逐步执行 Plan，收集 Trace 与 Observation |

#### 4.2.2 ReactPlanner 规划逻辑

`ReactPlanner.plan(text, history, role)` 根据角色分发到不同的规划方法：

- `_plan_lawyer`：分析法律意图（案情理解→法条检索→判例检索→风险评估→文书/庭审）
- `_plan_teacher`：分析教学意图（学生诊断→教案生成→作业批改→错因推送等），支持 Follow-up 检测
- `_plan_programmer`：分析编程意图（需求分析→代码搜索→代码生成→架构图生成），推断目标语言与图表类型
- `_plan_writer`：分析创作意图（灵感发散→大纲生成→正文写作→人物关系图），支持 Follow-up 续写

**Follow-up 检测机制**：Planner 通过分析用户输入是否包含"继续""补充""优化"等 Follow-up Token，结合历史对话上下文，判断当前请求是否为对上一轮 Skill 的追问，若是则仅执行目标 Skill 而非完整流程。

#### 4.2.3 ReactExecutor 执行流程

```python
async def execute(self, plan, session_id, text, memory, role):
    for index, action in enumerate(plan[:self.max_steps], start=1):
        result = await self.tool_router.run(action, request, role=role)
        observations[action.action] = result.output
        memory["observations"][action.action] = result.output
        trace.append(AgentTraceStep(step=index, thought=action.thought, 
                                     action=action.action, observation=...))
    return trace, skills_used, observations
```

关键设计：
- **Observation 传递**：前一步 Skill 的输出自动写入 `memory["observations"]`，后续 Skill 可读取
- **Trace 记录**：每步记录 `thought`（为什么调用）、`action`（调用了什么）、`observation`（返回了什么），前端通过 `TraceTimeline.vue` 可视化展示
- **最大步数限制**：`max_steps=10`，防止无限循环

#### 4.2.4 答案综合策略

各 Agent API 入口（如 `agent_lawyer.py`）在 Skill 执行完毕后，采用分层策略生成最终回答：

1. **优先提取**：若 Skill 输出包含可直接展示的结构化内容（如 Mermaid 代码、法律文书、教案 Markdown），直接作为 answer
2. **LLM 综合**：将所有 Skill 输出拼接为上下文，调用通义千问生成自然语言回答
3. **降级回退**：若 LLM 调用超时或失败，使用 `_build_fallback_answer` 生成结构化降级结果

---

### 4.3 RAG 知识库与向量检索

**[创新点标注]** 本项目构建了覆盖法律、教育、代码三个领域的多 Collection 向量索引体系，每个领域设计独立的索引构建器（Index Builder），支持 ChromaDB 向量检索与关键词检索的双模降级，确保即使向量数据库不可用也能返回基础结果。

#### 4.3.1 ChromaDB 客户端封装

`ChromaLegalClient`（位于 `agent/app/agent_core/retrieval/chroma_client.py`）封装了 ChromaDB 的初始化、Collection 管理与查询：

- **嵌入模型**：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（多语言支持）
- **持久化**：使用 `PersistentClient` 将向量数据存储于本地磁盘
- **降级机制**：若 ChromaDB 或 sentence-transformers 不可用，`is_available()` 返回 False，各 Index Builder 自动降级到关键词搜索

#### 4.3.2 法律知识库

`LegalIndexBuilder`（位于 `agent/app/agent_core/retrieval/legal_index_builder.py`）管理 5 个 Collection：

| Collection 名称 | 数据来源 | 服务 Skill |
|----------------|---------|-----------|
| `law_statutes` | statutes.json + 律师知识库.md | StatuteRetrievalSkill |
| `law_cases` | cases.json | CaseRetrievalSkill |
| `evidence_rules` | evidence_rules.json | EvidenceAnalysisSkill |
| `limitation_rules` | limitation_rules.json | LimitationCalculationSkill |
| `jurisdiction_rules` | jurisdiction_rules.json | JurisdictionDeterminationSkill |

特色设计：
- **Markdown 解析**：自动解析 `律师-法律知识库.md` 中的 `##`/`###` 层级结构，将每个三级标题下的内容作为独立文档入库
- **关键词降级**：向量检索失败时，使用正则分词 + 词频匹配的 `_fallback_search` 方法
- **种子数据**：首次启动时自动生成默认种子文件（如民法典第 188 条、劳动合同法第 82 条等）

#### 4.3.3 教育知识库

`EducationIndexBuilder`（位于 `agent/app/agent_core/retrieval/education_index_builder.py`）管理 4 个 Collection：

| Collection 名称 | 数据来源 | 服务 Skill |
|----------------|---------|-----------|
| `edu_knowledge_points` | knowledge_points.json | StudentDiagnosisSkill, TutoringQASkill |
| `edu_question_bank` | question_bank.json | ErrorAnalysisQuestionPushSkill, HomeworkGradingSkill |
| `edu_lesson_templates` | lesson_templates.json | LessonPlanGenerationSkill |
| `edu_teaching_methods` | teaching_methods.json | ClassroomInteractionDesignSkill |

数据样例（knowledge_points.json）：
```json
{
  "id": "math_g7_num_001",
  "name": "有理数加减运算",
  "subject": "数学",
  "grade": "七年级",
  "prerequisites": ["正负数意义", "数轴表示"],
  "mastery_criteria": "能正确进行同号异号有理数加减并解释符号变化",
  "vector_content": "有理数加减法核心是转化：减去一个数等于加上这个数的相反数..."
}
```

#### 4.3.4 代码索引

`CodeIndexBuilder`（位于 `agent/app/agent_core/retrieval/code_index_builder.py`）管理 1 个 Collection：

| Collection 名称 | 数据来源 | 服务 Skill |
|----------------|---------|-----------|
| `code_index` | 项目源代码文件 | CodebaseSemanticSearchSkill |

特色设计：
- **多语言符号提取**：支持 Python（AST 解析）、Java（正则匹配类/方法）、JS/TS/Vue（正则匹配类/函数/箭头函数）
- **增量索引**：通过文件 SHA1 哈希与修改时间检测变更，仅重新索引变化的文件
- **代码片段提取**：每个符号提取其所在行起最多 25 行代码片段作为检索文本
- **索引清单**：维护 `code_index_manifest.json` 记录文件级索引状态

---

### 4.4 联邦学习集成方案

**[创新点标注]** 本项目采用"Fail-Open 适配器"模式集成联邦学习，即联邦学习模块作为可选增强层，启用时提供风险调整与置信度提升，禁用或失败时完全不影响主流程。当前为**框架预留 + 开关模拟**状态，`AGENT_FEDERATED_ENABLED` 默认为 `false`。

#### 4.4.1 FederatedAdapter 设计

`FederatedAdapter`（位于 `agent/app/agent_core/federated/federated_adapter.py`）核心方法：

```python
async def get_risk_enhancement(self, case_info: Dict) -> Dict:
    if not self.enabled:
        return {}  # 未启用时直接返回空字典，不影响主流程
    # 调用联邦优化端点获取 risk_adjustment 与 confidence
    # 任何异常均被捕获，返回空字典
```

配置项：
- `AGENT_FEDERATED_ENABLED`：是否启用（默认 `false`）
- `AGENT_FEDERATED_BASE_URL`：联邦学习服务地址（默认 `http://localhost:8000/ai`）
- `AGENT_FEDERATED_TIMEOUT_MS`：超时时间（默认 1500ms）

#### 4.4.2 风险调整逻辑

当联邦学习启用时，`FederatedAdapter` 返回：
- `risk_adjustment`：基于联邦优化准确率与效率的加权计算，范围 [-0.15, 0.15]
- `confidence`：综合联邦节点数与优化准确率的置信度
- `federated_nodes_count`：参与联邦学习的节点数

该信息在律师 Agent 的 `risk_assessment` Skill 中被使用，用于微调风险评分。

#### 4.4.3 前端联邦学习面板

`FederatedLearningView.vue` 提供联邦学习可视化界面，包含四个标签页：
- **聚合与隐私**：模型聚合 SVG 可视化 + 隐私保护机制展示
- **模型与版本**：模型管理两列网格 + 版本历史时间线
- **全局模型**：全局模型状态监控
- **RAG 联邦**：RAG 联邦优化配置

---

### 4.5 前端可视化面板

**[创新点标注]** 本项目的前端不仅展示文本回答，还为每个 Skill 输出设计了专用的可视化组件，将 AI 输出从纯文本拓展到结构化图表（思维导图、Mermaid 架构图、人物关系图谱、诊断雷达图等）。

#### 4.5.1 TraceTimeline 执行轨迹

`TraceTimeline.vue` 展示 ReAct 推理引擎的每一步执行过程：
- Step 编号 → Thought（为什么调用）→ Action（调用了什么 Skill）→ Observation（返回了什么）
- 支持展开/折叠，帮助用户理解 Agent 的推理过程

#### 4.5.2 作家可视化组件

| 组件 | 功能 | 数据来源 |
|------|------|---------|
| `MindMapViewer.vue` | 灵感发散树（思维导图） | InspirationExpandSkill 的 creative_tree |
| `OutlineViewer.vue` | 章节大纲展示 | OutlineGenerateSkill 的 outline_markdown |
| `PolishDiffCard.vue` | 润色前后对比 | ContentWriteSkill |
| `PlotLogicCard.vue` | 情节逻辑分析 | ContentWriteSkill |
| `RelationGraph.vue` | 人物关系图谱（vis-network） | CharacterRelationSkill 的 relation_graph |

#### 4.5.3 程序员可视化组件

| 组件 | 功能 | 数据来源 |
|------|------|---------|
| `DiagramViewer.vue` | Mermaid 图表渲染 | DiagramGenerationSkill 的 mermaid_code |
| `MermaidRenderer.vue` | Mermaid 代码渲染引擎 | — |
| `CodeReviewCard.vue` | 代码审查结果 | CodeGenerationSkill |
| `DebugTraceCard.vue` | 调试追踪 | CodeGenerationSkill |
| `ArchSuggestCard.vue` | 架构建议 | RequirementAnalysisSkill |
| `UnitTestCard.vue` | 单元测试建议 | CodeGenerationSkill 的 suggested_tests |

#### 4.5.4 律师可视化组件

| 组件 | 功能 | 数据来源 |
|------|------|---------|
| `EvidenceAnalysisCard.vue` | 证据分析卡片 | EvidenceAnalysisSkill |
| `LimitationTimeline.vue` | 诉讼时效时间线 | LimitationCalculationSkill |
| `JurisdictionCard.vue` | 管辖法院建议 | JurisdictionDeterminationSkill |
| `HearingOutlineViewer.vue` | 庭审提纲展示 | HearingOutlineGenerationSkill |

#### 4.5.5 教师可视化组件

| 组件 | 功能 | 数据来源 |
|------|------|---------|
| `DiagnosisRadar.vue` | 学生诊断雷达图 | StudentDiagnosisSkill |
| `LessonPlanViewer.vue` | 教案展示 | LessonPlanGenerationSkill |
| `GradingResultCard.vue` | 批改结果卡片 | HomeworkGradingSkill |
| `QuestionPushList.vue` | 错因推题列表 | ErrorAnalysisQuestionPushSkill |

---

## 5 数据流与 API 设计

### 5.1 请求响应格式

#### 统一请求格式

```json
{
  "text": "用户输入文本",
  "sessionId": "会话ID（可选，首次为空）"
}
```

对应 Pydantic 模型：`AgentLawyerRequest` / `AgentTeacherRequest` / `AgentProgrammerRequest` / `AgentWriterRequest`

#### 统一响应格式

```json
{
  "success": true,
  "answer": "Agent 最终回答",
  "sessionId": "会话ID",
  "skillsUsed": ["statute_retrieval", "case_retrieval"],
  "trace": [
    { "step": 1, "thought": "...", "action": "...", "observation": "..." }
  ],
  "riskLevel": "low",
  "federated": {},
  "message": null,
  "error": null
}
```

各角色响应还包含角色专属字段：
- **律师**：无额外字段（所有 Skill 输出通过 trace 解析）
- **教师**：无额外字段
- **程序员**：`requirement_analysis`、`codebase_semantic_search`、`code_generation`、`diagram_generation`
- **作家**：`inspiration_expand`、`outline_generate`、`content_write`、`character_relation_map`

### 5.2 Java-Python 网关代理

`AgentGatewayService`（位于 `backend/.../service/AgentGatewayService.java`）负责将前端请求转发到 Python AI 服务：

```
前端 → Spring Boot AgentController → AgentGatewayService → RestTemplate → FastAPI Agent API
```

关键配置（`AgentProperties.java`）：
```java
agent.enabled = true
agent.timeout-ms = 30000
agent.python.lawyer-chat-url = http://localhost:8000/ai/agent/lawyer/chat
agent.python.teacher-chat-url = http://localhost:8000/ai/agent/teacher/chat
agent.python.programmer-chat-url = http://localhost:8000/ai/agent/programmer/chat
agent.python.writer-chat-url = http://localhost:8000/ai/agent/writer/chat
```

容错设计：
- `agent.enabled = false` 时直接返回"Agent 服务已禁用"
- Python 服务不可达时返回"Python agent timeout or unreachable"
- HTTP 错误码时返回"Python agent returned an error status"

### 5.3 API 端点汇总

| 端点 | 方法 | 服务层 | 说明 |
|------|------|--------|------|
| `/api/agent/lawyer/chat` | POST | Java→Python | 律师 Agent 对话 |
| `/api/agent/teacher/chat` | POST | Java→Python | 教师 Agent 对话 |
| `/api/agent/programmer/chat` | POST | Java→Python | 程序员 Agent 对话 |
| `/api/agent/writer/chat` | POST | Java→Python | 作家 Agent 对话 |
| `/ai/agent/lawyer/chat` | POST | Python | 律师 Agent 直接调用 |
| `/ai/agent/teacher/chat` | POST | Python | 教师 Agent 直接调用 |
| `/ai/agent/programmer/chat` | POST | Python | 程序员 Agent 直接调用 |
| `/ai/agent/writer/chat` | POST | Python | 作家 Agent 直接调用 |
| `/ai/chat` | POST | Python | 通用对话 |
| `/ai/tts` | POST | Python | 语音合成 |
| `/ai/rag/query` | POST | Python | RAG 检索 |

---

## 6 部署与运行说明

### 6.1 环境依赖

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Java | 17+ | 后端网关 |
| Python | 3.9+ | AI 服务 |
| Node.js | 18+ | 前端构建 |
| PostgreSQL | 15+ | 关系数据库 |
| Redis | 7+ | 缓存/会话 |
| Docker | 20+ | 容器化部署（推荐） |

### 6.2 配置项

#### 必需配置（.env 文件）

```env
DASHSCOPE_API_KEY=sk-your_api_key_here
```

#### 可选配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `QWEN_MODEL_BALANCED` | qwen-plus | 推荐模型 |
| `QWEN_MODEL_FAST` | qwen-turbo | 快速模型 |
| `QWEN_MODEL_ADVANCED` | qwen-max | 高级模型 |
| `AGENT_FEDERATED_ENABLED` | false | 联邦学习开关 |
| `AGENT_FEDERATED_TIMEOUT_MS` | 1500 | 联邦学习超时 |
| `AGENT_CHROMA_PATH` | 自动 | ChromaDB 数据目录 |
| `AGENT_EMBEDDING_MODEL` | paraphrase-multilingual-MiniLM-L12-v2 | 嵌入模型 |

### 6.3 启动命令

#### Docker 部署（推荐）

```bash
cd docker
docker-compose -f docker-compose.prod.yml up -d
```

服务端口：前端 80、后端 8080、AI 服务 8000、PostgreSQL 5432、Redis 6379

#### 开发模式

```bash
# 数据库
docker-compose -f docker-compose.dev.yml up -d postgres redis

# 后端
cd backend && mvn spring-boot:run

# AI 服务
cd agent && pip install -r requirements.txt && python app/main.py

# 前端
cd frontend && npm install && npm run dev
```

开发端口：前端 5173、后端 8080、AI 服务 8000

### 6.4 验证服务

```bash
curl http://localhost:8080/health    # 后端健康检查
curl http://localhost:8000/health    # AI 服务健康检查
```

---

## 7 测试与验证

### 7.1 单元测试

项目在 `agent/tests/` 目录下提供了以下测试文件：

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_programmer_skills.py` | 程序员 4 个 Skill + Planner 规划 + 端到端路由 |
| `test_teacher_skills.py` | 教师 Skill 测试 |
| `test_writer_skills.py` | 作家 Skill 测试 |
| `test_federated_global.py` | 联邦学习全局模型测试 |
| `test_federated_rag.py` | 联邦 RAG 优化测试 |

### 7.2 测试设计特点

以 `test_programmer_skills.py` 为例：

- **FakeAIService**：模拟 LLM 返回，根据 prompt 内容返回预设 JSON，避免真实 API 调用
- **超时降级测试**：`_assert_timeout_fallback` 通过 patch `asyncio.wait_for` 模拟超时，验证 Skill 的降级输出
- **端到端路由测试**：`test_programmer_route` 直接调用 `programmer_agent_chat` API，验证完整 Planner→Router→Executor 链路
- **Planner 规划测试**：验证输入"分析这个项目并生成微服务架构图"时，Planner 生成包含 `requirement_analysis` 和 `diagram_generation` 的计划

### 7.3 端到端测试用例设计

| 角色 | 输入示例 | 预期 Skill 序列 | 预期输出类型 |
|------|---------|----------------|-------------|
| 律师 | "我在公司工作两年没签合同，能要求双倍工资吗？" | case_understanding → statute_retrieval → limitation_calculation → risk_assessment | 法条引用 + 时效判断 + 风险等级 |
| 教师 | "初一学生有理数加减总是出错，怎么辅导？" | student_diagnosis → tutoring_qa → error_analysis_question_push | 诊断雷达 + 辅导方案 + 推题列表 |
| 程序员 | "帮我生成用户登录的流程图" | diagram_generation | Mermaid 流程图代码 |
| 作家 | "我有一个科幻小说的创意，关于时间旅行" | inspiration_expand → outline_generate | 思维导图 + 章节大纲 |

---

## 8 已知限制与未来展望

### 8.1 已知限制

| 限制 | 说明 |
|------|------|
| 联邦学习为框架预留 | `FederatedAdapter` 当前为开关模拟模式，`AGENT_FEDERATED_ENABLED` 默认 false，真实联邦聚合尚未对接实际分布式训练 |
| 向量检索依赖本地 ChromaDB | 未部署分布式向量数据库，大数据量下性能受限 |
| 会话记忆为内存存储 | `SessionMemoryStore` 基于线程安全的 Dict，服务重启后丢失 |
| LLM 调用存在延迟 | 通义千问 API 调用受网络与配额影响，单次请求可能超时 |
| 代码索引范围有限 | 默认仅索引 `backend/src` 目录，可通过 `AGENT_CODE_INDEX_ROOT` 扩展 |
| 前端数字人为预留功能 | Three.js 数字人组件已搭建，但完整语音驱动与表情同步尚在开发中 |

### 8.2 未来展望

| 方向 | 规划 |
|------|------|
| 联邦学习真实对接 | 对接 PySyft/FATE 等联邦学习框架，实现真实的隐私保护模型协同训练 |
| 多 Agent 协作 | 支持多角色 Agent 同时参与同一任务（如律师+程序员协作完成合规代码审查） |
| 流式输出 | 接入通义千问 SSE 流式接口，实现打字机效果的实时输出 |
| 知识库动态更新 | 支持用户上传文档自动入库，实现知识库的持续扩充 |
| 分布式向量数据库 | 迁移到 Milvus/Qdrant 等分布式方案，支持更大规模的知识检索 |
| 多模态输入 | 接入语音、图像输入，支持语音对话与图片理解 |

---

## 附录 A：关键类名索引

| 类名 | 文件路径 | 职责 |
|------|---------|------|
| `ReactPlanner` | `agent/app/agent_core/react/planner.py` | ReAct 规划器 |
| `ReactExecutor` | `agent/app/agent_core/react/executor.py` | ReAct 执行器 |
| `ToolRouter` | `agent/app/agent_core/react/tool_router.py` | Skill 路由器 |
| `BaseSkill` | `agent/app/agent_core/skills/base.py` | Skill 抽象基类 |
| `ChromaLegalClient` | `agent/app/agent_core/retrieval/chroma_client.py` | ChromaDB 客户端 |
| `LegalIndexBuilder` | `agent/app/agent_core/retrieval/legal_index_builder.py` | 法律索引构建器 |
| `EducationIndexBuilder` | `agent/app/agent_core/retrieval/education_index_builder.py` | 教育索引构建器 |
| `CodeIndexBuilder` | `agent/app/agent_core/retrieval/code_index_builder.py` | 代码索引构建器 |
| `FederatedAdapter` | `agent/app/agent_core/federated/federated_adapter.py` | 联邦学习适配器 |
| `SessionMemoryStore` | `agent/app/agent_core/memory/session_memory.py` | 会话记忆存储 |
| `QwenAdapter` | `agent/app/ai_engine/qwenadapter.py` | 通义千问适配器 |
| `KylinAIClient` | `agent/app/ai_engine/kylin_sdk/client.py` | 麒麟 AI SDK 客户端 |
| `AIService` | `agent/app/services/aiservice.py` | AI 服务统一封装 |
| `AgentGatewayService` | `backend/.../service/AgentGatewayService.java` | Java Agent 网关 |
| `AgentController` | `backend/.../controller/AgentController.java` | Agent REST 控制器 |
| `AgentProperties` | `backend/.../config/AgentProperties.java` | Agent 配置属性 |
| `Settings` | `agent/app/config.py` | Python 全局配置 |

## 附录 B：Prompt 模板清单

| 角色 | 模板文件 | 服务 Skill |
|------|---------|-----------|
| 律师 | `prompts/case_understanding.txt` | CaseUnderstandingSkill |
| 律师 | `prompts/document_generation.txt` | DocumentGenerationSkill |
| 律师 | `prompts/hearing_outline_generation.txt` | HearingOutlineGenerationSkill |
| 教师 | `prompts/teacher/diagnosis_prompt.txt` | StudentDiagnosisSkill |
| 教师 | `prompts/teacher/lesson_plan_prompt.txt` | LessonPlanGenerationSkill |
| 教师 | `prompts/teacher/grading_prompt.txt` | HomeworkGradingSkill |
| 教师 | `prompts/teacher/error_attribution_prompt.txt` | ErrorAnalysisQuestionPushSkill |
| 教师 | `prompts/teacher/learning_path_prompt.txt` | LearningPathPlanningSkill |
| 教师 | `prompts/teacher/interaction_design_prompt.txt` | ClassroomInteractionDesignSkill |
| 教师 | `prompts/teacher/parent_communication_prompt.txt` | ParentCommunicationSuggestionSkill |
| 教师 | `prompts/teacher/qa_tutor_prompt.txt` | TutoringQASkill |
| 教师 | `prompts/teacher/report_generation_prompt.txt` | ProgressReportGenerationSkill |
| 程序员 | `prompts/programmer/requirement_analysis.txt` | RequirementAnalysisSkill |
| 程序员 | `prompts/programmer/code_generation.txt` | CodeGenerationSkill |
| 程序员 | `prompts/programmer/diagram_generation.txt` | DiagramGenerationSkill |
| 作家 | `prompts/writer/inspiration_expand.txt` | InspirationExpandSkill |
| 作家 | `prompts/writer/outline_generate.txt` | OutlineGenerateSkill |
| 作家 | `prompts/writer/content_write.txt` | ContentWriteSkill |
| 作家 | `prompts/writer/character_relation.txt` | CharacterRelationSkill |

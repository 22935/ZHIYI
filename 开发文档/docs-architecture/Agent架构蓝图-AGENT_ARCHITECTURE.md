# 联邦智枢 Agent 架构蓝图

## 0. 技术选型（已确认）

| 决策项 | 选型 |
|--------|------|
| 向量数据库 | Chroma（嵌入式） |
| Agent 工作流 | ReAct 动态规划 |
| 对话记忆 | 仅内存会话级 |
| 联邦学习整合 | 功能隔离 + 开关控制 |
| 前端改造范围 | 复用现有对话组件，扩展功能面板 |
| LLM | 通义千问（OpenAI兼容模式） |
| 前端框架 | Vue 3 + TypeScript + Element Plus |
| 后端框架 | Spring Boot 3.2 + Java 17 |
| AI服务框架 | FastAPI + Python 3.9+ |

---

## 1. 整体架构图

```mermaid
flowchart LR
    U[用户] --> FE[Vue ChatView]
    FE -->|/api/agent/*| J[Java Spring Boot]
    J -->|/ai/agent/lawyer/chat| PY[Python FastAPI]
    J -->|/ai/agent/teacher/chat| PY

    subgraph Agent Core (Python)
      P1[ReAct Planner]
      P2[Tool Router]
      P3[Execution Loop]
      P4[Session Memory<br/>In-Memory]
      P5[Qwen Adapter]

      S1[律师Skills: 案情理解/法条检索/判例检索/证据分析/文书生成/庭审提纲/管辖确定/诉讼时效/风险评估]
      S2[教师Skills: 学生诊断/教案生成/作业批改/错因推送/辅导答疑/学习路径/进度报告/课堂互动/家长沟通]
      S3[程序员Skills: 代码审查/调试追踪/架构建议/单元测试]
      S4[作家Skills: 大纲生成/风格分析/情节逻辑/润色对比]

      VDB[(Chroma)]
      LAW[(法条语料)]
      CASE[(判例语料)]
      EDU[(教育语料)]
    end

    PY --> P1 --> P2 --> P3
    P3 --> S1
    P3 --> S2
    P3 --> S3
    P3 --> S4
    S1 --> VDB
    S2 --> VDB
    VDB --> LAW
    VDB --> CASE
    VDB --> EDU
    P3 --> P4
    P3 --> P5

    subgraph Federated Learning (Isolated)
      FL[现有联邦学习模块<br/>/ai/federated-* /ai/global-model/*]
    end
    S1 -.开关启用时调用.-> FL
    FL -.默认关闭/失败回退.-> S1

    PY --> J --> FE
```

架构原则：
- Java 保持网关与业务域稳定，Agent 核心落在 Python（复用现有 Qwen/AI 服务能力）。
- Skill 统一接口，可插拔、可观测、可灰度启用。
- 联邦学习保持独立运行，不阻塞主对话链路。
- 所有Agent共享ReAct引擎，通过Skill插件实现差异化能力。

---

## 2. 后端包结构

### 2.1 Java（`backend/src/main/java/com/kinlin/ai`）

- `controller/AgentController.java` — Agent统一入口，路由到Python服务
- `service/AgentGatewayService.java` — 调用Python Agent API，处理超时/熔断/降级
- `dto/agent/AgentChatRequest.java` — 请求体（text, sessionId）
- `dto/agent/AgentChatResponse.java` — 响应体（answer, skillsUsed, trace, riskLevel, federated）
- `config/AgentProperties.java` — Agent配置（enabled, timeoutMs, python URLs）
- `config/FeatureToggleProperties.java` — 功能开关（federated.enabled等）

### 2.2 Python（`agent/app`）

- `api/agent_lawyer.py` — 律师Agent入口 `POST /ai/agent/lawyer/chat`
- `api/agent_teacher.py` — 教师Agent入口 `POST /ai/agent/teacher/chat`
- `agent_core/react/planner.py` — ReAct规划器
- `agent_core/react/executor.py` — 执行循环/终止条件/最大步数/异常回退
- `agent_core/react/tool_router.py` — Action路由到具体Skill
- `agent_core/skills/base.py` — Skill抽象协议（输入/输出/错误码/timeout）
- `agent_core/skills/` — 律师Skills（8个）+ 教师Skills（9个，在teacher/子目录）
- `agent_core/memory/session_memory.py` — 会话内存缓存
- `agent_core/retrieval/chroma_client.py` — Chroma客户端封装
- `agent_core/retrieval/legal_index_builder.py` — 法条/判例索引构建
- `agent_core/retrieval/education_index_builder.py` — 教育知识索引构建
- `agent_core/federated/federated_adapter.py` — 联邦学习适配（开关控制）
- `agent_core/schema/agent_types.py` — 统一数据模型

### 2.3 前端（`frontend/src`）

- `services/api/agentLawyer.ts` — 律师Agent API封装
- `services/api/agentTeacher.ts` — 教师Agent API封装
- `services/api/agentProgrammer.ts` — 程序员Agent API封装
- `services/api/agentWriter.ts` — 作家Agent API封装
- `stores/chat.ts` — 对话状态管理（含4种Agent消息处理）
- `views/ChatView.vue` — 对话主页面（4种Agent无缝切换）
- `components/agent/LawyerSkillPanel.vue` — 律师技能面板（蓝色#2563eb）
- `components/agent/TeacherSkillPanel.vue` — 教师技能面板（翠绿#059669）
- `components/agent/ProgrammerSkillPanel.vue` — 程序员技能面板（紫蓝#7c3aed）
- `components/agent/WriterSkillPanel.vue` — 作家技能面板（琥珀#d97706）
- `components/agent/TraceTimeline.vue` — ReAct执行轨迹展示
- `utils/agentDisplay.ts` — Agent技能映射与显示配置

---

## 3. Agent Skills 详细设计

### 3.1 律师Agent Skills

#### 案情理解 Skill（CaseUnderstandingSkill）
- 输入：用户问题、历史对话、可选附件摘要
- 输出：facts, parties, claims, timeline, legal_issues, missing_info
- 内部逻辑：LLM抽取结构化案情 → 识别证据缺口 → 输出标准JSON

#### 法条检索 Skill（StatuteRetrievalSkill）
- 输入：legal_issues, 关键词、地域/时效约束
- 输出：候选法条列表（条文、法源、相关性分数、生效状态）
- 内部逻辑：生成检索query → Chroma相似检索 → 重排 → TopK

#### 判例检索 Skill（CaseRetrievalSkill）
- 输入：案情摘要、争议焦点、诉求类型
- 输出：判例列表（案号/法院层级/裁判要点/相似度/可借鉴点）
- 内部逻辑：Chroma检索 → 二次过滤 → 提炼双向样本

#### 证据分析 Skill（EvidenceAnalysisSkill）
- 输入：案情结构、证据材料
- 输出：证据链分析、证据强度评估、缺失证据建议

#### 文书生成 Skill（DocumentGenerationSkill）
- 输入：文书类型、案情结构、法条判例证据
- 输出：结构化文书草稿（章节、法律依据、引用、风险提示）
- 内部逻辑：模板生成骨架 → 注入法条判例 → 标注需复核段落

#### 庭审提纲 Skill（HearingOutlineGenerationSkill）
- 输入：案情、诉求、法条依据
- 输出：庭审流程提纲、争议焦点、举证提纲

#### 管辖确定 Skill（JurisdictionDeterminationSkill）
- 输入：案情、当事人信息、标的额
- 输出：管辖法院建议、管辖依据

#### 诉讼时效 Skill（LimitationCalculationSkill）
- 输入：案由、事件时间线
- 输出：时效状态、起算点、剩余时间

#### 风险评估 Skill（RiskAssessmentSkill）
- 输入：案情结构、证据完备度、法条判例匹配度
- 输出：risk_level（低/中/高）、风险矩阵、缓释建议
- 内部逻辑：计算基础风险分 → 若federated.enabled=true调用联邦增强 → 合并或回退

### 3.2 教师Agent Skills

#### 学生诊断 Skill（StudentDiagnosisSkill）
- 输入：学生问题、答题记录、学习历史
- 输出：知识薄弱点、认知水平评估、学习风格判断

#### 教案生成 Skill（LessonPlanGenerationSkill）
- 输入：教学目标、课程内容、学生水平
- 输出：结构化教案（教学环节、时间分配、活动设计、评估方式）

#### 作业批改 Skill（HomeworkGradingSkill）
- 输入：学生作业、标准答案、评分标准
- 输出：评分、批改详情、改进建议

#### 错因推送 Skill（ErrorAnalysisQuestionPushSkill）
- 输入：错误答题记录、知识点关联
- 输出：错因分析、针对性练习题推送

#### 辅导答疑 Skill（TutoringQaSkill）
- 输入：学生问题、学科、年级
- 输出：分步骤解答、知识点关联、延伸思考

#### 学习路径 Skill（LearningPathPlanningSkill）
- 输入：学生诊断结果、学习目标
- 输出：个性化学习路径、阶段目标、资源推荐

#### 进度报告 Skill（ProgressReportGenerationSkill）
- 输入：学习数据、时间范围
- 输出：学习进度报告、趋势分析、改进建议

#### 课堂互动 Skill（ClassroomInteractionDesignSkill）
- 输入：教学内容、学生特点
- 输出：互动方案、提问设计、小组活动设计

#### 家长沟通 Skill（ParentCommunicationSuggestionSkill）
- 输入：学生情况、沟通目的
- 输出：沟通要点、建议措辞、关注事项

### 3.3 程序员Agent Skills（前端已实现，后端待开发）

#### 代码审查 Skill（CodeReviewSkill）
- 输入：代码片段、语言、上下文
- 输出：代码质量评估、改进建议、最佳实践

#### 调试追踪 Skill（DebugTraceSkill）
- 输入：错误信息、代码片段、日志
- 输出：问题定位、修复建议、根因分析

#### 架构建议 Skill（ArchSuggestSkill）
- 输入：需求描述、技术栈、约束条件
- 输出：架构方案、技术选型建议、扩展性分析

#### 单元测试 Skill（UnitTestSkill）
- 输入：代码片段、测试框架
- 输出：测试用例生成、覆盖率建议、边界条件

### 3.4 作家Agent Skills（前端已实现，后端待开发）

#### 大纲生成 Skill（OutlineGenerationSkill）
- 输入：主题、体裁、风格要求
- 输出：结构化大纲、章节划分、情节节点

#### 风格分析 Skill（StyleAnalysisSkill）
- 输入：文本样本
- 输出：风格特征、语言特点、修辞分析

#### 情节逻辑 Skill（PlotLogicSkill）
- 输入：故事大纲、角色设定
- 输出：情节逻辑检查、冲突分析、伏笔建议

#### 润色对比 Skill（PolishDiffSkill）
- 输入：原文、润色方向
- 输出：润色后文本、修改对比、修改理由

---

## 4. 联邦学习集成方式

集成策略：
- 默认关闭：`agent.federated.enabled=false`
- 只在 `RiskAssessmentSkill` 内通过适配层调用，不直接侵入 Planner/Router
- 任何联邦异常均"软失败"，主响应继续返回

调用点：
- `risk_assessment_skill.py` 中 `compute_risk()` 后执行：
  1. 检查开关
  2. 调用 `federated_adapter.get_risk_enhancement()`
  3. 合并增强结果（若成功）或忽略（若失败）

配置（Python `.env`）：
```env
AGENT_FEDERATED_ENABLED=false
AGENT_FEDERATED_TIMEOUT_MS=1200
AGENT_FEDERATED_FAIL_OPEN=true
```

配置（Java `application.yml`）：
```yaml
agent:
  federated:
    enabled: false
    trace: true
```

---

## 5. 前端Agent面板设计

### 5.1 设计原则

- 复用现有ChatView对话主视图，不弹新页面
- 每种Agent拥有独立Skill面板，右侧/底部展示
- 统一的ReAct轨迹展示（TraceTimeline，可折叠）
- Agent切换时面板平滑过渡，保持对话上下文

### 5.2 配色方案

| Agent | 主色 | CSS变量 | 视觉风格 |
|-------|------|---------|----------|
| 律师 | #2563eb | --agent-lawyer | 蓝色，专业严谨 |
| 教师 | #059669 | --agent-teacher | 翠绿，温和耐心 |
| 程序员 | #7c3aed | --agent-programmer | 紫蓝，技术感 |
| 作家 | #d97706 | --agent-writer | 琥珀，创意温暖 |

### 5.3 面板组件结构

```
ChatView.vue
├── 对话消息区
├── 输入区
└── Agent面板区（根据当前Agent动态渲染）
    ├── LawyerSkillPanel.vue
    │   ├── EvidenceAnalysisCard
    │   ├── HearingOutlineViewer
    │   ├── JurisdictionCard
    │   ├── LimitationTimeline
    │   └── DiagnosisRadar
    ├── TeacherSkillPanel.vue
    │   ├── LessonPlanViewer
    │   ├── GradingResultCard
    │   └── QuestionPushList
    ├── ProgrammerSkillPanel.vue
    │   ├── CodeReviewCard
    │   ├── DebugTraceCard
    │   ├── ArchSuggestCard
    │   └── UnitTestCard
    └── WriterSkillPanel.vue
        ├── OutlineViewer
        ├── StyleAnalysisCard
        ├── PlotLogicCard
        └── PolishDiffCard
```

---

## 6. 数据流

### 6.1 Agent对话请求流

```
用户输入 → ChatView.vue
  → agentXxx.ts (前端API)
  → Vite代理 /api/agent/xxx/chat
  → Spring Boot AgentController
  → AgentGatewayService
  → HTTP POST /ai/agent/xxx/chat
  → FastAPI agent_xxx.py
  → ReAct Planner (LLM生成计划)
  → Tool Router (路由到Skill)
  → Executor (执行Skill)
  → Session Memory (更新会话)
  → 聚合结果 → 返回响应
  ← AgentChatResponse (answer/skillsUsed/trace/riskLevel/federated)
  ← chat.ts store (更新消息)
  ← ChatView.vue (渲染回复 + Skill面板)
```

### 6.2 Agent响应数据结构

```python
class AgentLawyerResponse(BaseModel):
    success: bool = True
    answer: str
    session_id: str
    skills_used: List[str] = []
    trace: List[AgentTraceStep] = []
    risk_level: Optional[str] = None
    federated: Dict[str, Any] = {}
    message: Optional[str] = None
    error: Optional[str] = None
```

---

## 7. 开发阶段划分

### Phase 1：基础骨架 ✅
1. 建立 `agent_lawyer` API 与 Java 网关 DTO
2. 建立 ReAct 核心框架（planner/router/executor）
3. 定义统一 Skill 接口与 Trace 数据结构

### Phase 2：检索底座 ✅
1. 接入 Chroma 客户端与 collection 管理
2. 构建法条/判例入库脚本与增量更新逻辑
3. 实现法条与判例检索 Skill（含重排）

### Phase 3：律师能力成形 ✅
1. 实现案情理解 Skill
2. 实现文书生成 Skill
3. 实现风险评估 Skill（本地规则版）
4. 串联 ReAct 全流程并补齐失败回退

### Phase 4：联邦隔离接入 + 前端可视化 ✅
1. 实现 `federated_adapter` 与开关控制
2. 前端扩展律师技能面板与轨迹展示组件
3. 实现教师Agent（9个Skills + 前端面板）
4. 实现程序员/作家Agent前端面板

### Phase 5：验收与上线准备 ⏳
1. 端到端联调
2. 质量验收（准确性/可用性/一致性）
3. 可观测性（联邦增强埋点）
4. 灰度与回滚预案
5. 程序员/作家Agent后端Skills实现

---

## 8. 实施约束与验收标准

硬约束：
- 不破坏现有 `/chat/*` 兼容性
- 联邦学习模块默认隔离，不影响主链路可用性
- 所有 Skill 必须可单测、可独立超时控制

验收标准（MVP）：
- 律师/教师Agent可完成完整的Skill调用闭环
- 每次响应可返回 `skillsUsed` 与引用来源
- 联邦学习开关关闭时，系统功能完整可用
- 程序员/作家Agent前端面板可展示，后端Skills可扩展

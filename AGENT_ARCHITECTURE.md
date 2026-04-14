# 联邦智能枢 Lawyer Agent 架构蓝图
# agent开发技术选型
## 0. 选型结论（已确认）
- 向量数据库：`A. Chroma（嵌入式）`
- Agent 工作流：`A. ReAct 动态规划`
- 对话记忆：`A. 仅内存会话级`
- 联邦学习整合：`B. 功能隔离 + 开关控制`
- 前端改造范围：`A. 复用现有对话组件，仅扩展功能面板`

---

## 1. 整体架构图

```mermaid
flowchart LR
    U[用户] --> FE[Vue ChatView]
    FE -->|/api/chat/text| J[Java Spring Boot]
    J -->|/ai/agent/lawyer/chat| PY[Python FastAPI Agent]

    subgraph Agent Core (Python)
      P1[ReAct Planner]
      P2[Tool Router]
      P3[Execution Loop]
      P4[Session Memory<br/>In-Memory]
      P5[Qwen Adapter]
      S1[Skill: 案情理解]
      S2[Skill: 法条检索]
      S3[Skill: 判例检索]
      S4[Skill: 文书生成]
      S5[Skill: 风险评估]
      VDB[(Chroma)]
      LAW[(法条语料)]
      CASE[(判例语料)]
    end

    PY --> P1 --> P2 --> P3
    P3 --> S1
    P3 --> S2
    P3 --> S3
    P3 --> S4
    P3 --> S5
    S2 --> VDB
    S3 --> VDB
    VDB --> LAW
    VDB --> CASE
    P3 --> P4
    P3 --> P5

    subgraph Federated Learning (Isolated)
      FL[现有联邦学习模块<br/>/ai/federated-* /ai/global-model/*]
    end
    S5 -.开关启用时调用.-> FL
    FL -.默认关闭/失败回退.-> S5

    PY --> J --> FE
```

架构原则：
- Java 保持网关与业务域稳定，Agent 核心落在 Python（复用现有 Qwen/AI 服务能力）。
- Skill 统一接口，可插拔、可观测、可灰度启用。
- 联邦学习保持独立运行，不阻塞主对话链路。

---

## 2. 后端包结构（新增）

> 说明：以下为“在现有目录上新增”的建议结构。

### 2.1 Java（`backend/src/main/java/com/kinlin/ai`）

- `controller/AgentController.java`  
职责：提供统一入口（如 `/agent/lawyer/chat`），兼容旧接口渐进迁移。

- `service/AgentGatewayService.java`  
职责：调用 Python Agent API，处理超时、熔断、降级。

- `dto/agent/AgentChatRequest.java`  
职责：请求体（`text`, `roleId`, `contextId`, `panelOptions`）。

- `dto/agent/AgentChatResponse.java`  
职责：响应体（`answer`, `skillsUsed`, `trace`, `riskLevel`, `references`）。

- `config/AgentProperties.java`  
职责：读取配置（`agent.enabled`, `agent.timeoutMs`, `agent.traceEnabled`）。

- `config/FeatureToggleProperties.java`  
职责：读取开关（`agent.federated.enabled` 等）。

### 2.2 Python（`agent/app`）

- `api/agent_lawyer.py`  
职责：律师 Agent 主入口 `POST /ai/agent/lawyer/chat`。

- `agent_core/react/planner.py`  
职责：基于 ReAct 生成 `Thought -> Action -> Observation` 计划。

- `agent_core/react/executor.py`  
职责：执行循环、终止条件、最大步数控制、异常回退。

- `agent_core/react/tool_router.py`  
职责：把 Action 路由到具体 Skill。

- `agent_core/skills/base.py`  
职责：Skill 抽象协议（输入、输出、错误码、timeout）。

- `agent_core/skills/case_understanding_skill.py`
- `agent_core/skills/statute_retrieval_skill.py`
- `agent_core/skills/case_retrieval_skill.py`
- `agent_core/skills/document_generation_skill.py`
- `agent_core/skills/risk_assessment_skill.py`  
职责：五个律师专业 Skill 具体实现。

- `agent_core/memory/session_memory.py`  
职责：会话内存缓存（按 `contextId` 维护短期记忆，进程重启失效）。

- `agent_core/retrieval/chroma_client.py`  
职责：封装 Chroma 客户端、collection 生命周期管理。

- `agent_core/retrieval/legal_index_builder.py`  
职责：法条/判例语料入库、向量化、增量更新。

- `agent_core/federated/federated_adapter.py`  
职责：隔离调用现有联邦模块，受开关控制。

- `agent_core/schema/agent_types.py`  
职责：统一定义 `SkillRequest/SkillResult/TraceStep/RiskReport`。

---

## 3. 五个 Skill 详细设计

## 3.1 案情理解 Skill（CaseUnderstandingSkill）
- 输入：用户问题、历史对话、可选附件摘要。
- 输出：`facts`, `parties`, `claims`, `timeline`, `legal_issues`, `missing_info`。
- 内部逻辑：
1. LLM 抽取结构化案情。
2. 识别证据缺口与待补充问题。
3. 输出供后续检索/评估复用的标准 JSON。

## 3.2 法条检索 Skill（StatuteRetrievalSkill）
- 输入：`legal_issues`, 关键词、地域/时效约束（可选）。
- 输出：候选法条列表（条文、法源、相关性分数、生效状态）。
- 内部逻辑：
1. 生成检索 query。
2. Chroma 相似检索（法条集合）。
3. 重排（关键词命中 + 语义分数 + 时效）。
4. 返回 TopK 并生成引用片段。

## 3.3 判例检索 Skill（CaseRetrievalSkill）
- 输入：案情摘要、争议焦点、诉求类型。
- 输出：判例列表（案号/法院层级/裁判要点/相似度/可借鉴点）。
- 内部逻辑：
1. Chroma 检索判例向量。
2. 根据案由与争点进行二次过滤。
3. 提炼“支持/不利”双向样本，避免单边论证。

## 3.4 文书生成 Skill（DocumentGenerationSkill）
- 输入：文书类型（咨询意见/起诉状草稿/答辩提纲等）、案情结构、法条判例证据。
- 输出：结构化文书草稿（章节、法律依据、引用、风险提示）。
- 内部逻辑：
1. 依据模板生成骨架。
2. 注入检索到的法条与判例。
3. 自动标注“需律师复核”段落与不确定项。

## 3.5 风险评估 Skill（RiskAssessmentSkill）
- 输入：案情结构、证据完备度、法条判例匹配度。
- 输出：`risk_level`（低/中/高）、风险矩阵、缓释建议。
- 内部逻辑：
1. 计算基础风险分（证据、程序、实体、时效）。
2. 若 `agent.federated.enabled=true`，调用 `federated_adapter` 获取增强统计。
3. 联邦不可用或关闭时自动回退本地规则，不影响主流程。

---

## 4. 联邦学习集成方式（按“功能隔离”）

集成策略：
- 默认关闭：`agent.federated.enabled=false`。
- 只在 `RiskAssessmentSkill` 内通过适配层调用，不直接侵入 Planner/Router。
- 任何联邦异常均“软失败”，主响应继续返回。

调用点：
- `risk_assessment_skill.py` 中 `compute_risk()` 后、输出前执行：
1. 检查开关。
2. 调用 `federated_adapter.get_risk_enhancement()`
3. 合并增强结果（若成功）或忽略（若失败）。

配置建议（Python `.env`）：
- `AGENT_FEDERATED_ENABLED=false`
- `AGENT_FEDERATED_TIMEOUT_MS=1200`
- `AGENT_FEDERATED_FAIL_OPEN=true`

配置建议（Java `application.yml`）：
- `agent.federated.enabled: false`
- `agent.federated.trace: true`

---

## 5. 前端改造说明（复用现有对话组件）

保持：
- 继续使用现有聊天主视图与消息流，不弹新页面。

新增/修改：
- `frontend/src/services/api/agentLawyer.ts`  
新增律师 Agent 接口调用。

- `frontend/src/stores/chat.ts`  
扩展消息结构：`skillsUsed`, `trace`, `riskLevel`, `references`。

- `frontend/src/views/ChatView.vue`  
在现有消息区右侧/底部新增“能力面板”与“执行轨迹折叠区”。

- `frontend/src/components/agent/LawyerSkillPanel.vue`  
显示本轮使用的 Skill、法条/判例引用、风险等级。

- `frontend/src/components/agent/TraceTimeline.vue`  
展示 ReAct 步骤（Thought/Action/Observation）摘要。

交互规则：
- 与其他页面一致，单页面内切换，不弹出新窗口。
- 对话返回后按需展示 `trace`（可折叠，默认简略）。

---

## 6. 开发阶段划分（Phase 1-5）

## Phase 1：基础骨架
1. 建立 `agent_lawyer` API 与 Java 网关 DTO。
2. 建立 ReAct 核心框架（planner/router/executor）。
3. 定义统一 Skill 接口与 Trace 数据结构。

## Phase 2：检索底座
1. 接入 Chroma 客户端与 collection 管理。
2. 构建法条/判例入库脚本与增量更新逻辑。
3. 实现法条与判例检索 Skill（含重排）。

## Phase 3：律师能力成形
1. 实现案情理解 Skill。
2. 实现文书生成 Skill。
3. 实现风险评估 Skill（本地规则版）。
4. 串联 ReAct 全流程并补齐失败回退。

## Phase 4：联邦隔离接入 + 前端可视化
1. 实现 `federated_adapter` 与开关控制。
2. 前端扩展技能面板与轨迹展示组件。
3. 保证与现有 Chat 交互逻辑一致。

## Phase 5：验收与上线准备
1. 回归测试：接口、超时、降级、引用正确性。
2. 质量评估：法律问答准确率、文书可用率、风险判定一致性。
3. 发布策略：灰度开关、日志监控、回滚预案。

---

## 7. 实施约束与验收标准

硬约束：
- 不破坏现有 `/chat/*` 兼容性。
- 联邦学习模块默认隔离，不影响主链路可用性。
- 所有 Skill 必须可单测、可独立超时控制。

验收标准（MVP）：
- 律师角色可完成“案情理解 -> 检索 -> 风险评估 -> 文书草稿”的闭环。
- 每次响应可返回 `skillsUsed` 与引用来源。
- 联邦学习开关关闭时，系统功能完整可用。


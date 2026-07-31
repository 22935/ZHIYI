# 知弈律师 AgentOS 技术设计文档

# Zhiyi Lawyer AgentOS Technical Design Document

日期：2026-05-17

状态：正式设计草案

范围：先完整实现律师业务链路，再扩展教育、程序员、作家等其他行业包。

---

## 1. 文档目标

本文用于把“驾驭工程智能体”的技术实现口径固定下来，方便后续研发、评审和验收。

本文回答四个问题：

1. 律师业务链路应该如何从用户输入跑到最终交付物。
2. 多智能体如何协作，工作流如何安排，是否需要调度。
3. 既然叫 AgentOS，哪些能力应按操作系统思想实现。
4. 旧聊天体系如何迁移，本地模型和 RAG 智能辅助如何演进。

核心结论：

```text
第一阶段只做完整律师链路。
专业能力全部进入 AgentOS WorkflowRun。
旧的 /agent/{role}/chat 专业聊天体系必须迁移干净。
AgentOS Core 只管理运行时，不写死行业业务。
律师能力通过 Legal Workflow Pack 注册进入 Core。
```

---

## 2. 当前实现基线

当前项目已经具备 AgentOS 的核心骨架。

### 2.1 已实现的 Core 能力

代码位置：

- `agentOS/src/agentos/core/types.py`
- `agentOS/src/agentos/core/workflow_runtime.py`
- `agentOS/src/agentos/core/orchestrator.py`
- `agentOS/src/agentos/core/state_machine.py`
- `agentOS/src/agentos/core/trace.py`
- `agentOS/src/agentos/core/checkpoint.py`
- `agentOS/src/agentos/core/review.py`
- `agentOS/src/agentos/core/evaluation.py`

已具备能力：

- `AgentTask`：任务对象。
- `WorkflowDefinition`：工作流定义。
- `WorkflowRun`：一次运行实例。
- `WorkflowStep`：工作流步骤。
- `TraceEvent`：执行轨迹。
- `Checkpoint`：恢复点。
- `ReviewDecision` / `ReviewRecord`：人工审核。
- `WorkflowMetric`：治理指标。
- `WorkflowRuntime.start()`：启动工作流。
- `WorkflowRuntime.apply_review()`：提交人工审核。
- `WorkflowRuntime.resume_from_checkpoint()`：从恢复点继续。
- `TraceStore.export_json()` / `export_markdown()`：导出审计轨迹。

### 2.2 已实现的 API 能力

代码位置：

- `agent/app/api/agentos_core.py`
- `backend/src/main/java/com/kinlin/ai/controller/AgentOsGatewayController.java`
- `backend/src/main/java/com/kinlin/ai/service/AgentOsGatewayService.java`
- `frontend/src/services/api/agentos.ts`
- `frontend/src/services/api/workflow.ts`
- `frontend/src/views/AgentOsConsoleView.vue`

已有接口：

```text
POST /ai/core/tasks
GET  /ai/core/tasks
POST /ai/core/workflows/runs
POST /ai/core/workflows/start
GET  /ai/core/workflows/runs
GET  /ai/core/workflows/runs/{runId}
GET  /ai/core/workflows/runs/{runId}/trace
GET  /ai/core/workflows/runs/{runId}/checkpoints
GET  /ai/core/workflows/runs/{runId}/reviews
POST /ai/core/workflows/runs/{runId}/reviews
POST /ai/core/workflows/runs/{runId}/resume
POST /ai/core/workflows/runs/{runId}/cancel
GET  /ai/core/workflows/metrics
POST /ai/chat/workflows/upgrade
```

Java 网关提供：

```text
/api/agentos/*
/agentos/*
/ai/*
```

并转发到 Python 的 `/ai/core/*`。

### 2.3 已实现的 Pack 能力

当前已存在：

```text
agent/packs/legal
agent/packs/education
agent/packs/programmer
agent/packs/writer
```

但成熟度不同：

| Pack | 当前状态 | 判断 |
|---|---|---|
| legal | 多步骤流程，含人工审核 | 第一阶段重点完善 |
| education | 单步骤最小流程 | 后续扩展 |
| programmer | 单步骤需求分析 | 后续扩展 |
| writer | 单步骤大纲生成 | 后续扩展 |

### 2.4 需要清理的遗留点

虽然 AgentOS 已经具备主链路，但旧专业聊天入口仍在 Java 和前端中残留。

需要重点清理：

- `backend/src/main/java/com/kinlin/ai/controller/AgentController.java`
- `backend/src/main/java/com/kinlin/ai/service/AgentGatewayService.java`
- `backend/src/main/java/com/kinlin/ai/config/AgentProperties.java` 中旧的 `lawyerChatUrl`、`teacherChatUrl`、`programmerChatUrl`、`writerChatUrl`
- `frontend/src/services/api/agentLawyer.ts`
- `frontend/src/services/api/agentTeacher.ts`
- `frontend/src/services/api/agentProgrammer.ts`
- `frontend/src/services/api/agentWriter.ts`
- `frontend/src/stores/chat.ts` 中旧专业 Agent 发送链路
- `frontend/src/views/ChatView.vue` 中旧专业模式触发逻辑

迁移原则：

```text
普通聊天可以保留。
专业 Agent 能力必须统一进入 WorkflowRun。
```

---

## 3. 第一阶段产品边界

第一阶段只做律师链路，不同时做教育、程序员、作家。

### 3.1 目标场景

第一阶段聚焦两个场景：

1. 合同审查
2. 案件分析

建议优先完整做合同审查，因为合同审查更容易形成结构化流程和交付物。

### 3.2 目标用户

第一阶段面向：

- 企业法务
- 律所律师
- 律师助理
- 政企法律事务人员
- 合同管理人员

### 3.3 用户要得到什么

用户不是只得到一段回答，而是得到一套可追踪的工作成果：

- 案情摘要
- 合同关键条款识别
- 争议焦点
- 法律依据
- 证据清单
- 风险等级
- 风险理由
- 补充材料建议
- 合同审查意见
- 初步文书草稿
- 最终审查结论
- 全流程 Trace
- Checkpoint 恢复点
- 审核记录

---

## 4. 使用流程

### 4.1 从聊天升级为律师工作流

用户流程：

```text
用户在聊天页输入法律问题
  -> 点击“升级 Workflow”
  -> 前端调用 /ai/chat/workflows/upgrade
  -> 系统创建 AgentTask
  -> 系统推荐 legal workflow
  -> 系统启动 WorkflowRun
  -> 用户进入 AgentOS Console 查看执行过程
```

适用场景：

- 用户先自然描述问题。
- 系统判断这是专业任务。
- 用户希望进入可审计、可恢复的工作流。

### 4.2 从律师工作台直接发起

用户流程：

```text
用户进入律师工作台
  -> 选择“合同审查”或“案件分析”（功能要固化吗？可拓展性是不是就变差了）
  -> 上传合同、证据、案情说明
  -> 点击开始
  -> 前端调用 /ai/core/workflows/start
  -> 系统创建 AgentTask 和 WorkflowRun
  -> 控制台展示步骤状态
```

适用场景：

- 用户目标明确。
- 输入材料较完整。
- 需要直接生成交付物。

### 4.3 审核者使用流程

审核者流程：

```text
收到 waiting_review 状态
  -> 查看风险评估结果
  -> 查看上游 Trace 和引用依据
  -> 选择 approved / rejected / rerun / cancelled
  -> 填写审核意见
  -> 系统写入 ReviewRecord
  -> 工作流继续、失败、重跑或取消
```

审核动作必须进入 Trace 和 Review 列表，不能只写前端状态。

### 4.4 失败恢复流程

失败恢复流程：

```text
某一步执行失败
  -> WorkflowRun.status = failed
  -> Console 显示失败步骤和错误
  -> 用户选择最近 checkpoint
  -> 调用 /ai/core/workflows/runs/{runId}/resume
  -> 系统恢复 stateSnapshot
  -> run.recoveryCount + 1
  -> 继续执行后续步骤
```

恢复成功与否要进入治理指标。

---

## 5. 律师工作流设计

### 5.1 合同审查工作流

目标 workflow：

```text
legal_contract_review_v1
```

推荐步骤：

```text
case_intake
  -> clause_extraction
  -> statute_retrieval
  -> evidence_analysis
  -> risk_assessment
  -> human_review
  -> document_draft
  -> final_review
  -> completed
```

当前已有步骤：

```text
case_intake
statute
evidence
risk
draft
final_review
```

建议补强步骤：

- `clause_extraction`：合同条款抽取。
- `citation_check`：法条和案例引用校验。
- `deliverable_packaging`：最终交付物结构化整理。

### 5.2 案件分析工作流

目标 workflow：

```text
legal_case_analysis_v1
```

推荐步骤：

```text
case_intake
  -> issue_spotting
  -> statute_retrieval
  -> case_retrieval
  -> evidence_analysis
  -> limitation_check
  -> jurisdiction_check
  -> risk_assessment
  -> human_review
  -> final_opinion
```

第一阶段可以不一次性实现所有步骤，但 workflow 配置要预留扩展点。

### 5.3 每个律师 Agent 的职责

| Agent | 职责 | 输入 | 输出 |
|---|---|---|---|
| CaseIntakeAgent | 理解案情、抽取事实 | 用户文本、上传材料 | 案情摘要、当事人、争议焦点、缺失材料 |
| ClauseExtractionAgent | 抽取合同条款 | 合同文本 | 关键条款、风险条款、缺失条款 |
| StatuteAgent | 检索法律依据 | 争议焦点、合同类型 | 法条、司法解释、依据说明 |
| CaseRetrievalAgent | 检索类案 | 案由、争议焦点 | 类案摘要、裁判规则 |
| EvidenceAgent | 分析证据 | 证据材料、案情 | 证据清单、证明力、证据缺口 |
| RiskAgent | 评估风险 | 上游所有结果 | 风险等级、风险分数、风险理由 |
| DraftAgent | 生成文书 | 审核后的分析结果 | 审查意见、文书草稿 |
| ReviewAgent | 最终审查 | 文书草稿、上游结果 | 最终意见、遗漏提示、质量结论 |

### 5.4 Agent 协作方式

不采用“多个 Agent 自由群聊”的方式。

采用确定性工作流协作：

```text
上一步 Agent 输出结构化结果
  -> WorkflowMemory 保存 observations
  -> 下一步 Agent 读取 observations
  -> Orchestrator 决定下一步
  -> Trace 记录每一步
```

理由：

- 律师场景需要可审计。
- 风险结论必须能追溯依据。
- 人工审核节点必须明确。
- 失败后必须知道从哪里恢复。

---

## 6. 工作流调度设计

### 6.1 当前调度方式

当前调度是同步推进：

```text
WorkflowRuntime.start()
  -> promote_workflow_to_acg()
  -> ACGExecutor.ready_steps()
  -> Orchestrator.dispatch_agent()
  -> Agent.run()
  -> 写 trace
  -> 写 checkpoint
  -> 判断 waiting_review / failed / completed
```

优点：

- 简单。
- 易测试。
- 适合 MVP。
- 控制台能直接看到状态。

不足：

- 长任务会占住请求。
- 多用户并发时资源控制弱。
- 本地模型场景下 GPU 争抢无法治理。
- 人工审核长期等待需要更强持久化和后台调度。

### 6.2 第一阶段调度要求

律师完整链路第一阶段需要做到：

- 每个步骤可独立执行。
- 每个步骤有超时。
- 每个步骤有最大重试次数。
- 失败后写明错误来源。
- 人工审核可以暂停工作流。
- Checkpoint 可恢复。
- 本地模型调用可被 ModelAdapter 统一管理。

### 6.3 第二阶段调度升级

第二阶段引入后台任务调度：

```text
API 只负责创建 WorkflowRun
  -> Scheduler 拉取 pending step
  -> Worker 执行 step
  -> Store 保存状态
  -> Console 轮询或 WebSocket 订阅状态
```

建议新增模块：

```text
agentOS/src/agentos/core/scheduler.py
agentOS/src/agentos/core/worker.py
agentOS/src/agentos/core/resource_manager.py
agentOS/src/agentos/stores/queued_workflow_store.py
```

调度策略：

- 按 `priority` 排队。
- 按 `domain` 做资源限流。
- 按 `modelProvider` 做并发限制。
- 本地模型默认串行或小并发。
- 风险高的 step 必须进入 `waiting_review`。

---

## 7. AgentOS 与操作系统思想对应

这里的 OS 不是要写真正的操作系统内核，而是借用操作系统的管理思想。

### 7.1 概念映射

| 操作系统概念 | AgentOS 对应概念 | 当前/目标代码 |
|---|---|---|
| Kernel | AgentOS Core | `agentOS/src/agentos/core/*` |
| Process | WorkflowRun | `WorkflowRun` |
| Thread / Task | WorkflowStep | `WorkflowStep` |
| Scheduler | Orchestrator / Scheduler | `orchestrator.py`，后续 `scheduler.py` |
| System Call | Skill / Tool 调用 | `agentOS/src/agentos/skills/*` |
| Driver | ModelAdapter / RetrievalAdapter | `agentOS/src/agentos/adapters/*` |
| Memory | WorkflowMemory / Checkpoint | `memory/workflow_memory.py`、`checkpoint.py` |
| File System | 知识库、模板库、运行产物 | `agent/app/data/*` |
| Permission | Policy / Review / Risk | `review.py`，后续 `policy.py` |
| Log | TraceEvent | `trace.py` |
| Process Table | WorkflowStore | `stores/*workflow_store.py` |
| IPC | WorkflowMemory observations | `WorkflowMemory.from_run()` |
| Crash Recovery | Checkpoint Resume | `resume_from_checkpoint()` |

### 7.2 AgentOS Core 必须承担的职责

AgentOS Core 不是行业代码集合，而是运行时：

- 管任务生命周期。
- 管状态。
- 管调度。
- 管记忆。
- 管权限。
- 管恢复。
- 管审计。
- 管评估。

行业包只提供专业能力：

- Agent
- Skill
- Workflow YAML
- Prompt
- Data
- Policy
- Template

### 7.3 不应该做的事情

Core 不应该：

- 写死法律流程。
- 写死某个 Agent 的步骤。
- 直接拼行业 prompt。
- 直接调用某个模型厂商。
- 直接读取某个行业知识库路径。

正确做法：

```text
Core 代码化
Pack 插件化
Workflow 声明化
Agent 接口化
Skill 工具化
Policy 配置化
Model Adapter 抽象化
RAG Pipeline 可替换化
```

---

## 8. 旧聊天体系迁移方案

### 8.1 保留什么

保留普通聊天：

```text
/ai/chat/text
/ai/chat/text/stream
```

普通聊天用于：

- 非专业闲聊。
- 简单问答。
- 用户意图初筛。
- 引导用户升级 Workflow。

### 8.2 移除什么

移除旧专业 Agent 聊天：

```text
/api/agent/lawyer/chat
/api/agent/teacher/chat
/api/agent/programmer/chat
/api/agent/writer/chat
/agent/lawyer/chat
/agent/teacher/chat
/agent/programmer/chat
/agent/writer/chat
```

并清理对应服务：

- Java `AgentController`
- Java `AgentGatewayService`
- Java `AgentProperties.Python.*ChatUrl`
- 前端 `agentLawyer.ts` 等旧 API 文件
- `chat.ts` 中 `sendLawyerMessage()` 等旧专业发送函数

### 8.3 替代方式

专业能力统一调用：

```text
POST /ai/core/workflows/start
POST /ai/chat/workflows/upgrade
```

前端行为：

```text
用户选择律师模式
  -> 不再调用 agentLawyerApi.chat()
  -> 调用 agentosApi.upgradeChatToWorkflow()
  -> 返回 workflowRunId
  -> 消息列表展示“已创建 WorkflowRun”
  -> 跳转或提示进入 AgentOS Console
```

### 8.4 数据保存变化

旧专业聊天保存的是：

```text
sessionId
userText
assistantText
agentMode
```

迁移后需要保存：

```text
conversationId
messageId
workflowRunId
workflowId
workflowStatus
domain
intent
source
finalAnswer
traceSummary
reviewStatus
```

Java 侧可以先把这些放入 Message metadata，后续再拆 WorkflowRun 表。

---

## 9. 本地模型实现方案

### 9.1 目标

本地化目标：

- 敏感数据不出域。
- 支持国产 OS / 信创环境。
- 支持本地大模型、本地 embedding、本地 reranker。
- 云模型和本地模型通过同一个接口接入。

### 9.2 统一模型接口

建议统一为 OpenAI-compatible 适配层。

新增配置：

```env
MODEL_PROVIDER=cloud
OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1
OPENAI_COMPATIBLE_API_KEY=ollama
CHAT_MODEL=qwen3:8b
EMBEDDING_MODEL=qwen3-embedding
RERANKER_MODEL=qwen3-reranker
MODEL_TIMEOUT_MS=120000
MODEL_MAX_CONCURRENCY=1
```

新增或改造：

```text
agentOS/src/agentos/adapters/model_adapter.py
agent/app/services/aiservice.py
agent/app/services/embeddingservice.py
```

目标结构：

```text
ModelAdapter
  -> CloudModelProvider
  -> OllamaProvider
  -> VllmProvider
  -> LlamaCppProvider
```

第一阶段可先实现：

```text
OpenAICompatibleModelProvider
```

只要服务兼容 OpenAI API，就通过同一个 provider 接入。

### 9.3 本地推理选型

| 方案 | 适用场景 | 优点 | 注意点 |
|---|---|---|---|
| Ollama | 单机开发、演示、本地快速部署 | 简单、模型管理方便、支持 OpenAI 兼容接口 | 高并发和生产治理能力有限 |
| llama.cpp | CPU/GGUF/轻量部署 | 资源占用低，适合边缘和国产化验证 | 需要自己管理模型和参数 |
| vLLM | GPU 服务化、生产推理 | 吞吐高，适合服务化部署 | 部署和显存要求更高 |
| 云模型 | 初期效果验证 | 效果强，接入快 | 敏感数据可能不能出域 |

推荐路线：

```text
开发演示：Ollama
国产化轻量部署：llama.cpp + GGUF
生产 GPU 私有化：vLLM
云端兜底：DeepSeek / Qwen API
```

---

## 10. RAG 智能辅助方案

### 10.1 当前 RAG 基线

当前已有：

- `agent/app/services/ragservice.py`
- `agent/app/services/ragenhanced.py`
- `agent/app/services/embeddingservice.py`
- `agentOS/src/agentos/adapters/retrieval/chroma_client.py`
- `agentOS/src/agentos/adapters/retrieval/legal_index_builder.py`

当前能力：

- 文档上传。
- 文本抽取。
- 关键词搜索。
- Chroma 向量检索。
- 知识图谱增强。
- 简化 rerank。
- DashScope embedding 或降级 TF-IDF。

当前问题：

- RAG 和 WorkflowRun 结合还不够紧。
- 检索结果没有成为每个步骤的标准 TraceEvent。
- embedding、reranker、本地模型适配不统一。
- 法律材料的 chunk、metadata、引用格式需要专门设计。

### 10.2 律师 RAG 应该嵌入工作流

RAG 不是聊天前拼上下文，而是每一步的智能辅助。

| 工作流步骤 | RAG 作用 |
|---|---|
| case_intake | 检索同类案由、材料清单、常见争议 |
| clause_extraction | 检索条款模板、异常条款、合同类型规则 |
| statute_retrieval | 检索法律法规、司法解释、内部法规库 |
| case_retrieval | 检索类案和裁判规则 |
| evidence_analysis | 检索证据规则、举证责任、证据模板 |
| risk_assessment | 检索风险规则、历史审核意见、组织风控政策 |
| document_draft | 检索文书模板、条款库、历史草稿 |
| final_review | 检索质量检查清单、禁用表达、引用校验规则 |

### 10.3 法律知识库结构

建议将法律知识库拆成不同 collection：

```text
legal_statutes
legal_cases
legal_contract_templates
legal_clause_library
legal_evidence_rules
legal_risk_rules
legal_review_checklists
legal_org_private_docs
```

每个 chunk 至少带 metadata：

```json
{
  "docId": "doc_001",
  "sourceType": "statute",
  "title": "中华人民共和国民法典",
  "article": "第五百七十七条",
  "jurisdiction": "CN",
  "effectiveDate": "2021-01-01",
  "domain": "contract",
  "securityLevel": "internal",
  "version": "2026-05-17"
}
```

### 10.4 检索流程

推荐检索流程：

```text
Query Rewrite
  -> Hybrid Retrieval
  -> Metadata Filter
  -> Rerank
  -> Citation Build
  -> Evidence Pack
  -> Agent Step Input
  -> TraceEvent
```

解释：

- `Query Rewrite`：把用户口语转成法律检索语。
- `Hybrid Retrieval`：向量检索 + 关键词检索。
- `Metadata Filter`：按地区、时间、文档类型过滤。
- `Rerank`：使用 reranker 对候选材料排序。
- `Citation Build`：构建可引用依据。
- `Evidence Pack`：给 Agent 的结构化上下文。
- `TraceEvent`：记录本次检索用了哪些材料。

### 10.5 RAG 输出格式

每次检索不要只返回字符串，建议返回：

```json
{
  "query": "逾期交付违约责任",
  "results": [
    {
      "sourceId": "statute_001",
      "title": "中华人民共和国民法典",
      "locator": "第五百七十七条",
      "content": "一方不履行合同义务...",
      "score": 0.91,
      "sourceType": "statute"
    }
  ],
  "citations": [
    "《中华人民共和国民法典》第五百七十七条"
  ]
}
```

这类结构化结果要进入 `WorkflowStep.output` 和 `TraceEvent.payload`。

---

## 11. 数据与持久化

### 11.1 当前 Store

当前已有：

- `MemoryWorkflowStore`
- `SQLiteWorkflowStore`

选择方式：

```env
AGENTOS_WORKFLOW_DB_PATH=agent/data/workflow.db
```

如果未配置，则使用内存存储。

### 11.2 第一阶段要求

律师链路第一阶段必须启用 SQLite 或数据库持久化。

原因：

- 人工审核可能跨越较长时间。
- Checkpoint 不能因进程重启丢失。
- Trace 是审计材料，不能只存在内存。
- Console 运行列表需要可查询。

### 11.3 后续数据库表

Java 或 Python 后续可增加正式表：

```text
workflow_runs
workflow_steps
workflow_checkpoints
workflow_trace_events
workflow_reviews
workflow_artifacts
workflow_metrics
```

第一阶段可以先由 SQLite JSON payload 支撑，但接口语义要按正式表设计。

---

## 12. API 口径

### 12.1 创建律师合同审查任务

```http
POST /ai/core/workflows/start
Content-Type: application/json
```

```json
{
  "title": "合同审查：供应商逾期交付",
  "domain": "legal",
  "intent": "contract_review",
  "reviewMode": "human_in_loop",
  "input": {
    "source": "workbench",
    "caseText": "供应商逾期交付，合同约定违约金。",
    "contractText": "...",
    "region": "CN",
    "materials": []
  }
}
```

### 12.2 审核风险节点

```http
POST /ai/core/workflows/runs/{runId}/reviews
Content-Type: application/json
```

```json
{
  "stepId": "risk",
  "decision": "approved",
  "reviewer": "legal_reviewer",
  "comment": "风险说明可进入文书生成"
}
```

### 12.3 导出审计轨迹

```http
GET /ai/core/workflows/runs/{runId}/trace?format=markdown
```

用于：

- 审计报告。
- 项目验收。
- 失败复盘。
- 用户解释。

---

## 13. 验收标准

### 13.1 律师链路验收

必须满足：

- 能从 Chat 升级为律师 WorkflowRun。
- 能从 Workbench 直接发起律师 WorkflowRun。
- 合同审查流程至少包含案情、法条、证据、风险、审核、文书、最终审查。
- 风险节点能暂停等待人工审核。
- 审核通过后能继续跑完整流程。
- 任一步失败后能看到错误和 Trace。
- 有 checkpoint 时能恢复。
- 最终输出结构化交付物。
- 控制台能看到步骤、Trace、Checkpoint、Review、Metric。

### 13.2 旧体系迁移验收

必须满足：

- 前端不再调用 `agentLawyerApi.chat()` 等旧专业 API。
- Java 不再暴露 `/api/agent/{role}/chat` 专业入口。
- Java 不再配置旧 Python 专业聊天 URL。
- 专业模式全部转为 WorkflowRun。
- 普通聊天仍可使用。

### 13.3 本地模型验收

必须满足：

- 可以通过配置切换云模型和本地 OpenAI-compatible 模型。
- Chat model、embedding model、reranker model 可以分别配置。
- 本地模型失败时返回明确错误，不吞异常。
- 本地模型调用记录进入 Trace 摘要。

### 13.4 RAG 验收

必须满足：

- 法律知识库分 collection 或 metadata。
- 每次检索结果能进入 step output。
- 每次检索依据能进入 TraceEvent。
- 最终法律结论能展示引用来源。
- RAG 不命中时要明确说明，而不是编造依据。

---

## 14. 实施阶段

### Phase 1：律师主链路补强

目标：

```text
把 legal_contract_review_v1 做成完整可演示、可审计、可恢复的律师业务链路。
```

工作：

- 补 `ClauseExtractionAgent`。
- 补法律 RAG step。
- 补引用和依据输出格式。
- 补最终交付物结构。
- 强化风险审核节点。

### Phase 2：旧聊天体系迁移

目标：

```text
专业 Agent 入口全部迁移到 AgentOS。
```

工作：

- 清理 Java `AgentController`。
- 清理 Java `AgentGatewayService`。
- 清理前端旧专业 API。
- 改造 `ChatView` 专业模式。
- 增加 WorkflowRun 消息 metadata。

### Phase 3：本地模型适配

目标：

```text
支持 Ollama / llama.cpp / vLLM 等本地模型服务。
```

工作：

- 新增 OpenAI-compatible provider。
- 统一 chat、embedding、reranker 配置。
- 增加本地模型健康检查。
- 增加并发限制。

### Phase 4：律师 RAG 智能辅助

目标：

```text
RAG 深度进入律师每个关键步骤。
```

工作：

- 设计法律知识库 metadata。
- 建立法规、案例、模板、证据规则集合。
- 实现混合检索。
- 接入 reranker。
- 输出 citation pack。

### Phase 5：调度升级

目标：

```text
长任务、人工审核、本地模型资源都能被后台调度治理。
```

工作：

- 新增 Scheduler。
- 新增 Worker。
- 新增 ResourceManager。
- 支持后台执行和控制台订阅。

---

## 15. 参考资料

### 15.1 本地模型与 OpenAI-compatible 服务

- Ollama OpenAI compatibility：<https://docs.ollama.com/openai>
- Ollama Embeddings：<https://docs.ollama.com/capabilities/embeddings>
- vLLM OpenAI-Compatible Server：<https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html>
- llama.cpp：<https://github.com/ggml-org/llama.cpp>
- Qwen 本地运行：<https://qwen.readthedocs.io/en/v3.0/run_locally/ollama.html>

### 15.2 Embedding / Reranker

- Qwen3 Embedding GitHub：<https://github.com/QwenLM/Qwen3-Embedding>
- Qwen3 Embedding paper：<https://arxiv.org/abs/2506.05176>

### 15.3 RAG 与向量检索

- Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks：<https://arxiv.org/abs/2005.11401>
- Qdrant Hybrid Search with Reranking：<https://qdrant.tech/documentation/search-precision/reranking-hybrid-search/>
- Chroma Adding Data to Collections：<https://docs.trychroma.com/docs/collections/add-data>
- Milvus Overview：<https://blog.milvus.io/docs/overview.md>

---

## 16. 一句话总结

第一阶段要把知弈从“多角色聊天系统”收敛成：

```text
以律师合同审查和案件分析为第一业务样板，
以 AgentOS Core 为统一运行时，
以 WorkflowRun 为专业任务生命周期，
以 Trace / Checkpoint / Review / Metrics 为治理能力，
以本地模型和 RAG 为私有化智能辅助底座的职业智能体操作系统。
```




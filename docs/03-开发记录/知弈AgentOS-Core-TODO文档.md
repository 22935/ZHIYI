# 知弈 AgentOS Core TODO 文档

日期：2026-05-15

定位：知弈第一层通用智能体操作系统底座

英文名：Zhiyi AgentOS Core

对应第二层：Industry Workflow Packs（行业职业工作流包）

---

## 0. 当前进度摘要

### 已完成

- `agentOS/src/agentos/core/types.py`：已定义 `AgentTask`、`WorkflowDefinition`、`WorkflowRun`、`WorkflowStep`、`TraceEvent`、`Checkpoint`、`ReviewDecision`。
- `agentOS/src/agentos/core/workflow_runtime.py`：已跑通任务创建、工作流启动、状态查询、人工审核、恢复和取消。
- `agentOS/src/agentos/core/orchestrator.py`、`state_machine.py`、`trace.py`、`checkpoint.py`、`review.py`、`evaluation.py`：已形成核心运行闭环。
- `agentOS/src/agentos/agents/*`：已提供 `BaseAgent`、`AgentRegistry` 和统一运行上下文。
- `agent/packs/*/manifest.yaml`：已建立 pack manifest 发现与注册机制，默认运行时按 manifest 自动加载已安装 packs。
- `agent/packs/education`、`programmer`、`writer`：已补最小 Workflow 与轻量 Agent，可完成 lesson plan、requirement analysis、story outline 的 WorkflowRun 冒烟路径。
- `agentOS/src/agentos/skills/*`：已保留为 Pack Agent 可复用的原子能力层。
- `agentOS/src/agentos/stores/*`：已完成内存 store 和 SQLite store，默认运行时可通过 `AGENTOS_WORKFLOW_DB_PATH` 选择落盘，并支持 `WorkflowStore` 任务/运行分页查询。
- 旧的 `/ai/agent/{role}/chat` 入口、ReAct 兼容链路和旧请求/响应类型已移除，当前统一以 `/ai/core/*` 的 `WorkflowRun` 生命周期为准。
- `agent/app/api/agentos_core.py`：已开放 `/ai/core/tasks`、`/ai/core/workflows/runs`、`/ai/core/workflows/start`、`/ai/chat/workflows/upgrade`、审核、恢复、取消和列表查询接口。
- `backend/src/main/java/com/kinlin/ai/controller/AgentOsGatewayController.java`：Java 网关已提供 `/api/agentos/*` 与 `/agentos/*` 统一入口，转发到 Python AgentOS `/ai/core/*` 生命周期接口。
- Trace 已支持按 WorkflowRun 独立导出 JSON 与 Markdown，Python 入口为 `/ai/core/workflows/runs/{runId}/trace`，Java 网关入口为 `/api/agentos/core/workflows/runs/{runId}/trace`。
- Review 已从单一 trace 事件升级为可查询的 `ReviewRecord` 列表，Python 入口为 `/ai/core/workflows/runs/{runId}/reviews`。
- Checkpoint 已支持独立列表查询，Python 入口为 `/ai/core/workflows/runs/{runId}/checkpoints`。
- Evaluation 已提供基础治理指标，Python 入口为 `/ai/core/workflows/metrics`。
- 前端已新增 `/agentos-console`，接入运行列表、运行详情、步骤状态、Trace、Checkpoint、审核和治理指标。
- Chat 已支持将当前输入和上下文升级为 `WorkflowRun`；Workbench API 模式已支持直接发起 `WorkflowRun`。
- 文档已同步到 `agentOS/src/agentos` 作为 AgentOS Core canonical 路径；领域 Pack 以 `agent/packs` 为 canonical 路径。

### 进行中

- WorkflowStore 的备份、配置和索引治理能力。
- 非 legal pack 仍停留在最小 smoke workflow，需要继续深化为多步骤专业工作流。

### 下一步

- 继续补强 WorkflowStore 备份、索引和长期运行稳定性。
- 继续把非 legal pack 从最小 smoke workflow 深化为多步骤专业工作流。
- 继续定义 `AgentCapability`、`MemoryScope` 和联邦经验边界。

---

## 1. 总体判断

知弈要成为“面向信创与信息敏感行业的职业智能体操作系统”，第一阶段不能先追逐所有行业场景，而要先完成通用底座。

两层架构如下：

```text
第一层：知弈 AgentOS Core
  通用智能体操作系统底座

第二层：Industry Workflow Packs
  政务、金融、教育、医疗、法律等行业职业工作流包
```

第一层解决“任何行业都需要的共性工程能力”：

- 多 Agent 编排
- 状态机
- 工作流运行
- Checkpoint 恢复
- Trace 可观测
- 人工审核
- 权限与审计
- 私有化部署
- 国产 OS / 信创适配
- 工作流评估
- 联邦经验抽象

第二层解决“每个行业自己的专业知识和流程”：

- 行业知识库
- 行业 Agent
- 行业工作流模板
- 行业审查规则
- 行业数据连接器
- 行业评估指标

当前最重要的结论：

```text
先把 AgentOS Core 做稳，再用行业包扩展行业。
```

---

## 2. AgentOS Core 的边界

### 2.1 Core 要做什么

Core 是知弈的操作系统内核，不直接绑定某一个行业。

它负责：

- 接收任务
- 建立 WorkflowRun
- 选择 WorkflowDefinition
- 调度 Agent
- 管理 Agent 状态
- 管理步骤状态
- 保存中间产物
- 记录 Trace
- 创建 Checkpoint
- 支持恢复和重试
- 支持人工审核
- 输出评估指标
- 提供控制台 API

### 2.2 Core 不做什么

Core 第一阶段不做：

- 不做大模型训练
- 不做行业知识库深度建设
- 不做完整政务/金融/教育/医疗工作流
- 不做复杂多模态
- 不做数字人深度交互
- 不做大规模联邦训练
- 不做低代码工作流设计器

这些可以作为第二层行业包或后续产品化能力。

### 2.3 Core 与行业包的关系

```text
AgentOS Core
  提供运行时、状态、调度、记忆、观测、审计、恢复、评估

Industry Workflow Pack
  提供行业 Agent、行业 Skill、行业 Workflow、行业知识、行业规则
```

行业包不应该绕过 Core 直接调用模型。

所有行业能力都要通过 Core 运行，这样才能统一获得：

- 可观测性
- 可恢复性
- 审计能力
- 权限控制
- 评估数据
- 联邦经验

---

## 3. Core 的用户流程

Core 面向的是平台运行流程，不是单一行业流程。

### 3.1 管理员流程

```text
部署系统
  -> 配置模型供应商
  -> 配置本地知识库和向量库
  -> 配置用户权限
  -> 安装行业工作流包
  -> 配置审计和日志策略
  -> 开放给业务用户使用
```

管理员关心：

- 数据是否出域
- 是否支持国产 OS / 私有部署
- 权限是否可控
- 日志是否完整
- 模型调用是否可追踪
- 是否能审计每一次 Agent 行为

### 3.2 业务用户流程

```text
选择行业场景
  -> 发起任务
  -> 上传材料或输入文本
  -> 查看系统生成的工作流计划
  -> 确认执行
  -> 观察 Agent 执行状态
  -> 在关键节点审核
  -> 获得最终交付物
  -> 反馈是否采纳或修改
```

业务用户关心：

- 能否完成工作
- 输出是否专业
- 过程是否看得懂
- 出错后能不能恢复
- 能否保留人工审核权

### 3.3 审核者流程

```text
收到待审核节点
  -> 查看上游步骤和证据
  -> 查看 Agent 推理轨迹和引用材料
  -> 选择通过 / 驳回 / 要求重跑 / 人工修改
  -> 写入审计记录
  -> 推进后续步骤
```

审核者关心：

- 结果是否可信
- 依据是否完整
- 风险是否明确
- 谁触发了什么动作
- 是否能追责和复盘

### 3.4 运维与研究人员流程

```text
查看任务运行统计
  -> 识别失败步骤
  -> 分析循环、崩溃、恢复失败
  -> 对比不同 Agent / Workflow 表现
  -> 生成评估报告
  -> 优化工作流和调度策略
```

运维和科研人员关心：

- 工作流完成率
- 长任务稳定性
- Agent 协作质量
- 恢复成功率
- 专业任务准确率
- 评估数据能否支持论文或项目验收

---

## 4. Core 模块架构

AgentOS Core 建议拆成十个模块。

```text
1. Task Intake
2. Workflow Runtime
3. Orchestrator
4. Agent Registry
5. State Machine
6. Memory Layer
7. Checkpoint & Recovery
8. Trace & Observability
9. Human Review
10. Evaluation & Governance
```

### 4.1 Task Intake

职责：

- 接收用户任务
- 判断任务类型
- 决定是否进入 Workflow
- 收集必要输入
- 建立 `AgentTask`

TODO：

- [x] 定义 `AgentTask` 数据结构。
- [x] 定义任务入口 API：`POST /ai/core/tasks`。
- [x] 支持从 Chat 升级为 Workflow。
- [x] 支持从 Workbench 直接发起 Workflow。
- [x] 给任务增加 `domain`、`intent`、`priority`、`securityLevel` 字段。

完成标准：

- [ ] 用户输入一个复杂任务后，系统能创建结构化任务对象。
- [ ] 任务可以指向某个行业包，但不依赖行业包实现。

### 4.2 Workflow Runtime

职责：

- 创建 `WorkflowRun`
- 加载 `WorkflowDefinition`
- 生成步骤列表
- 管理运行生命周期
- 输出运行结果

TODO：

- [x] 定义 `WorkflowDefinition`。
- [x] 定义 `WorkflowRun`。
- [x] 定义 `WorkflowStep`。
- [x] 实现 `WorkflowRuntime.start()`。
- [x] 实现 `WorkflowRuntime.get_status()`。
- [x] 实现 `WorkflowRuntime.cancel()`。

完成标准：

- [ ] 一个固定工作流可以从 `pending` 跑到 `completed`。
- [ ] 前端能查询工作流状态。

### 4.3 Orchestrator

职责：

- 决定下一步执行哪个 Agent
- 决定是否需要人工审核
- 决定失败后重试、降级或终止
- 汇总最终结果

TODO：

- [x] 新建 `agentOS/src/agentos/core/orchestrator.py`。
- [x] 实现 `select_next_step()`。
- [x] 实现 `dispatch_agent()`。
- [ ] 实现更显式的 `handle_step_result()` / `handle_failure()` 对外封装。
- [x] 实现 `compose_final_output()`。

完成标准：

- [ ] Orchestrator 不直接写业务逻辑，而是调度 workflow 和 agent。
- [ ] 单个步骤失败时，不会导致整个系统黑盒崩溃。

### 4.4 Agent Registry

职责：

- 注册可用 Agent
- 描述 Agent 能力边界
- 控制 Agent 可调用工具
- 提供 Agent 选择依据

TODO：

- [x] 定义 `AgentProfile`。
- [ ] 定义 `AgentCapability`。
- [x] 实现 `AgentRegistry.register()`。
- [x] 实现 `AgentRegistry.resolve()`。
- [x] 支持行业包注册自己的 Agent。

完成标准：

- [ ] Core 可以不知道具体行业细节，但能发现行业包提供的 Agent。
- [ ] Orchestrator 调度 Agent 时只依赖统一接口。

### 4.5 State Machine

职责：

- 管理任务状态
- 管理工作流状态
- 管理步骤状态
- 管理 Agent 状态

统一状态建议：

```text
pending
planning
running
waiting_review
retrying
failed
completed
cancelled
```

TODO：

- [x] 新建 `agentOS/src/agentos/core/state_machine.py`。
- [x] 定义合法状态迁移。
- [x] 阻止非法状态跳转。
- [x] 每次状态变化写入 trace。
- [ ] 状态变化能被前端 Workbench 消费。

完成标准：

- [ ] 所有任务都能解释“当前在哪里”。
- [ ] 失败、重试、取消、恢复都有明确状态。

### 4.6 Memory Layer

职责：

- 保存当前会话上下文
- 保存工作流中间产物
- 保存用户偏好
- 保存职业经验
- 保存联邦匿名经验

记忆分层：

```text
Session Memory
  当前会话短期上下文

Workflow Memory
  当前工作流步骤输入、输出、中间产物

Profile Memory
  用户偏好、常用风格、组织配置

Career Memory
  职业规则、模板、历史经验

Federated Memory
  跨组织匿名统计模式，不共享原始数据
```

TODO：

- [x] 保留现有 `SessionMemoryStore`。
- [x] 新增 `WorkflowMemoryStore`。
- [x] 新增 `SQLiteWorkflowStore` 作为持久化 seam。
- [ ] 定义 `MemoryScope`。
- [ ] 定义哪些内容允许进入 `FederatedMemory`。
- [ ] 明确敏感行业默认不上传原始内容。

完成标准：

- [ ] 工作流中断后，中间产物不会丢失。
- [ ] 记忆分层清楚，不把用户隐私混进联邦经验。

### 4.7 Checkpoint & Recovery

职责：

- 在关键步骤后保存快照
- 支持失败后恢复
- 支持从某一步重跑
- 支持人工选择恢复点

TODO：

- [x] 定义 `Checkpoint`。
- [x] 实现 `create_checkpoint()`。
- [x] 实现 `list_checkpoints()`。
- [x] 实现 `resume_from_checkpoint()`。
- [x] 支持恢复后继续生成 trace。

完成标准：

- [x] 人为制造某一步失败后，可以从上一 checkpoint 继续。
- [x] 前端可以展示恢复点。

### 4.8 Trace & Observability

职责：

- 记录每一步发生了什么
- 记录 Agent 输入输出
- 记录模型调用摘要
- 记录错误与耗时
- 支持前端回放

TODO：

- [x] 定义统一 `TraceEvent`。
- [x] 将旧链路 trace 记录升级为更通用的 `TraceEvent`。
- [x] 支持事件类型：`task_created`、`step_started`、`agent_called`、`tool_called`、`checkpoint_created`、`review_required`、`step_failed`、`run_completed`。
- [x] 支持 WorkflowRun trace 独立导出，格式包括 JSON 和 Markdown。
- [x] 前端新增 `TraceEventTimeline` 展示 WorkflowRun Trace。
- [x] 后续支持导出审计报告。

完成标准：

- [x] 不看后端日志，也能知道任务执行过程。
- [x] Trace 能解释失败来自任务、Agent、Skill、模型还是数据。

### 4.9 Human Review

职责：

- 在关键节点等待人工确认
- 支持通过、驳回、重跑、终止
- 记录审核人和意见

TODO：

- [x] 定义 `ReviewDecision`。
- [x] 支持状态 `waiting_review`。
- [x] 定义 `ReviewRequest`。
- [x] 前端增加审核面板。
- [x] 后端或 Python 侧记录更完整的审核日志。

完成标准：

- [x] 敏感任务不会完全自动越过关键决策点。
- [x] 审核动作可追踪。

### 4.10 Evaluation & Governance

职责：

- 衡量系统是否稳定
- 衡量 Agent 是否协作良好
- 衡量专业输出是否可靠
- 支持科研和项目验收

核心指标：

```text
TCR: Task Completion Rate
AWS: Agent Workflow Stability
ACS: Agent Collaboration Score
PWS: Professional Workflow Score
RSR: Recovery Success Rate
HRR: Human Revision Rate
```

TODO：

- [x] 定义基础 `evaluation.py`。
- [x] 定义 `WorkflowMetric`。
- [x] 定义 `EvaluationRun`。
- [x] 记录完成率、失败率、恢复率和失败类型分布。
- [ ] 支持按 Agent、Workflow、行业包聚合统计。
- [x] 形成基础评估报告。

完成标准：

- [x] 能证明 Core 不只是能跑，而是更稳定、更可控。
- [x] 能为科研论文提供可量化数据。

---

## 5. 推荐目录结构

### 5.1 Python AgentOS Core

```text
agentOS/src/agentos/
  core/
    __init__.py
    types.py
    orchestrator.py
    workflow_runtime.py
    workflow_registry.py
    state_machine.py
    checkpoint.py
    trace.py
    review.py
    evaluation.py

  agents/
    base.py
    registry.py

  memory/
    workflow_memory.py
    profile_memory.py
    federated_memory.py

agent/app/api/
  agentos_core.py
```

### 5.2 Java Backend Core Gateway

```text
backend/src/main/java/com/kinlin/ai/
  controller/
    AgentOsController.java
    WorkflowController.java

  service/
    AgentOsGatewayService.java
    WorkflowPersistenceService.java

  dto/agentos/
    AgentTaskRequest.java
    WorkflowRunResponse.java
    WorkflowStepResponse.java
    CheckpointResponse.java
    ReviewDecisionRequest.java
```

### 5.3 Frontend Console

```text
frontend/src/
  services/api/
    agentos.ts
    workflow.ts

  stores/
    workflow.ts

  views/
    AgentOsConsoleView.vue

  components/agentos/
    WorkflowRunPanel.vue
    WorkflowStepList.vue
    AgentStateBadge.vue
    CheckpointPanel.vue
    TraceEventTimeline.vue
    HumanReviewPanel.vue
    MetricSummaryPanel.vue
```

---

## 6. API 草案

### 6.1 创建任务

```text
POST /ai/core/tasks
```

请求：

```json
{
  "title": "合同纠纷初步分析",
  "domain": "legal",
  "intent": "contract_dispute_analysis",
  "input": {
    "caseText": "...",
    "evidence": [],
    "region": "北京"
  },
  "securityLevel": "internal"
}
```

响应：

```json
{
  "taskId": "task_001",
  "status": "pending",
  "recommendedWorkflow": "legal_contract_dispute_v1"
}
```

### 6.2 查询任务列表

```text
GET /ai/core/tasks?status=pending&domain=legal&source=chat&page=1&pageSize=20
```

支持过滤：

- `status`
- `domain`
- `source`
- `page`
- `pageSize`

响应：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "pageSize": 20
}
```

### 6.3 启动工作流

```text
POST /ai/core/workflows/runs
```

请求：

```json
{
  "taskId": "task_001",
  "workflowId": "legal_contract_dispute_v1",
  "reviewMode": "human_in_loop"
}
```

响应：

```json
{
  "runId": "run_001",
  "status": "running",
  "currentStepId": "case_intake",
  "steps": []
}
```

### 6.4 查询工作流列表

```text
GET /ai/core/workflows/runs?status=waiting_review&domain=legal&workflowId=legal_contract_review_v1&source=workbench&page=1&pageSize=20
```

支持过滤：

- `status`
- `domain`
- `workflowId`
- `source`
- `page`
- `pageSize`

响应：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "pageSize": 20
}
```

### 6.5 查询工作流详情

```text
GET /ai/core/workflows/runs/{runId}
```

响应：

```json
{
  "runId": "run_001",
  "status": "waiting_review",
  "currentStepId": "risk_review",
  "steps": [],
  "checkpoints": [],
  "trace": []
}
```

### 6.6 导出 Trace

```text
GET /ai/core/workflows/runs/{runId}/trace?format=json
GET /ai/core/workflows/runs/{runId}/trace?format=markdown
```

JSON 响应：

```json
{
  "runId": "run_001",
  "taskId": "task_001",
  "workflowId": "legal_contract_review_v1",
  "domain": "legal",
  "status": "completed",
  "eventCount": 8,
  "events": []
}
```

Markdown 响应用于审计报告草稿和人工复盘。

### 6.7 查询 Checkpoint

```text
GET /ai/core/workflows/runs/{runId}/checkpoints
```

响应：

```json
{
  "runId": "run_001",
  "total": 1,
  "items": []
}
```

### 6.8 查询审核记录

```text
GET /ai/core/workflows/runs/{runId}/reviews
```

响应：

```json
{
  "runId": "run_001",
  "total": 1,
  "items": []
}
```

### 6.9 人工审核

```text
POST /ai/core/workflows/runs/{runId}/reviews
```

请求：

```json
{
  "stepId": "risk_review",
  "decision": "approved",
  "comment": "风险说明可进入文书生成"
}
```

### 6.10 从 Checkpoint 恢复

```text
POST /ai/core/workflows/runs/{runId}/resume
```

请求：

```json
{
  "checkpointId": "ckpt_003",
  "mode": "retry_from_checkpoint"
}
```

### 6.11 查询治理指标

```text
GET /ai/core/workflows/metrics?domain=legal&workflowId=legal_contract_review_v1&source=workbench
```

响应：

```json
{
  "evaluationId": "eval_001",
  "workflowId": "legal_contract_review_v1",
  "metrics": {
    "totalRuns": 1,
    "completionRate": 1.0,
    "failureRate": 0.0,
    "recoverySuccessRate": 0.0,
    "reviewCount": 1
  }
}
```

---

## 7. 分阶段 TODO

### Phase 1：Core 类型与状态机

目标：先把 AgentOS Core 的“语言”定义清楚。

TODO：

- [ ] 新建 `orchestration/types.py`。
- [ ] 定义 `AgentTask`。
- [ ] 定义 `WorkflowDefinition`。
- [ ] 定义 `WorkflowRun`。
- [ ] 定义 `WorkflowStep`。
- [ ] 定义 `Checkpoint`。
- [ ] 定义 `TraceEvent`。
- [ ] 新建 `state_machine.py`。
- [ ] 写状态迁移单元测试。

验收：

- [ ] 状态迁移非法时能抛出明确错误。
- [ ] 类型对象可以序列化为 JSON。

### Phase 2：最小 Workflow Runtime

目标：让一个固定工作流跑起来。

TODO：

- [ ] 实现 `WorkflowRuntime.start()`。
- [ ] 实现 `WorkflowRuntime.run_next_step()`。
- [ ] 实现 `WorkflowRuntime.get_status()`。
- [ ] 实现 `WorkflowRuntime.cancel()`。
- [ ] 用内存存储先跑通，不急着上数据库。

验收：

- [ ] 一个 3 步 demo workflow 可以从开始跑到完成。
- [ ] 每一步都能看到输入、输出、状态和耗时。

### Phase 3：Agent Registry 与 BaseAgent

目标：让 Core 能调度 Agent，而不是直接调 Skill。

TODO：

- [ ] 新建 `agents/base.py`。
- [ ] 定义 `BaseAgent.run()`。
- [ ] 定义 `BaseAgent.review()`。
- [ ] 新建 `agents/registry.py`。
- [ ] 支持注册 demo agent。
- [ ] 支持根据 `domain` 和 `capability` 查找 Agent。

验收：

- [ ] WorkflowStep 可以指定 `agentName`。
- [ ] Runtime 能通过 Registry 找到并执行 Agent。

### Phase 4：Trace 与 Checkpoint

目标：让运行过程可观测、可恢复。

TODO：

- [x] 新建 `trace.py`。
- [x] 每次任务、步骤、Agent、工具调用都写入 `TraceEvent`。
- [x] 新建 `checkpoint.py`。
- [x] 每个步骤完成后创建 checkpoint。
- [x] 实现从 checkpoint 恢复。
- [x] 增加 Trace JSON / Markdown 导出接口。

验收：

- [x] TraceEventTimeline 可以展示完整执行链。
- [x] 人为制造步骤失败后，可以从上一 checkpoint 恢复。

### Phase 5：Human Review

目标：敏感行业任务必须支持人在环路。

TODO：

- [x] 新建 `review.py`。
- [x] 支持 `waiting_review` 状态。
- [x] 定义审核决定：`approved`、`rejected`、`rerun`、`cancelled`。
- [x] 前端新增 `HumanReviewPanel`。
- [x] 审核决定写入 trace。

验收：

- [x] 工作流能在指定步骤暂停等待人工审核。
- [x] 审核通过后继续执行。

### Phase 6：Java 网关与前端控制台

目标：让 Core 从 Python 内部能力变成产品能力。

TODO：

- [x] Java 新增 `AgentOsGatewayService`。
- [x] Java 新增 `AgentOsController`。
- [x] 前端新增 `agentos.ts`。
- [x] 前端新增 `workflow.ts`。
- [x] 前端新增 `AgentOsConsoleView.vue`。
- [x] 接入 `WorkflowRunPanel`、`WorkflowStepList`、`CheckpointPanel`、`TraceEventTimeline`。
- [x] 支持从 Chat 升级为 Workflow。
- [x] 支持从 Workbench 直接发起 Workflow。

验收：

- [x] 用户能从前端创建工作流。
- [x] 用户能查看步骤状态、trace、checkpoint。
- [x] 用户能执行审核和恢复。

### Phase 7：Evaluation & Governance

目标：把“可治理”变成可量化能力。

TODO：

- [x] 新建 `evaluation.py`。
- [x] 记录任务完成率。
- [x] 记录恢复成功率。
- [ ] 记录循环率。
- [x] 记录失败类型分布。
- [x] 前端展示指标摘要。

验收：

- [x] 能输出基础运行报告。
- [ ] 能比较不同 workflow 或 agent 的稳定性。

---

## 8. 第一层完成标准

知弈 AgentOS Core 第一层完成，不以行业功能数量衡量，而以运行时能力衡量。

必须满足：

- [ ] 任意行业包都能注册 Agent。
- [ ] 任意行业包都能注册 WorkflowDefinition。
- [x] Core 能创建 WorkflowRun。
- [x] Core 能调度 Agent。
- [x] Core 能管理状态机。
- [x] Core 能保存 checkpoint。
- [x] Core 能从 checkpoint 恢复。
- [x] Core 能输出 trace。
- [x] Core 能等待人工审核。
- [x] Core 能生成运行评估指标。
- [x] Core 能通过 Java 网关服务前端。
- [x] 前端有可用的 AgentOS Console。

不要求：

- [ ] 不要求所有行业包完成。
- [ ] 不要求联邦学习全面上线。
- [ ] 不要求复杂低代码编排器。
- [ ] 不要求自训练大模型。

---

## 9. 与科研方向的连接

知弈 AgentOS Core 可以支撑以下科研方向：

```text
Stateful Governed Multi-Agent Runtime
有状态可治理多智能体运行时

Checkpoint-based Agent Workflow Recovery
基于检查点的智能体工作流恢复机制

Human-in-the-loop Agent Governance
人在环路的智能体治理机制

Workflow-level Agent Evaluation
工作流级智能体评估体系

Federated Experience for Sensitive-domain Agents
面向敏感行业的联邦经验共享机制
```

可实验变量：

- 有状态 vs 无状态
- 有 checkpoint vs 无 checkpoint
- 有人工审核 vs 无人工审核
- 单 Agent vs 多 Agent
- 直接 Skill 调用 vs Orchestrator 调度

可量化指标：

- 工作流完成率
- 恢复成功率
- 长任务稳定率
- Agent 协作成功率
- 专业输出质量
- 人工修改率
- 平均执行成本

---

## 10. 接下来 10 项工作

建议按顺序执行：

- [x] 1. 移除 `/ai/agent/{role}/chat` 旧入口和兼容执行链，统一保留 `/ai/core/*`。
- [x] 2. 给 `WorkflowStore` 补 `list_tasks()` / `list_runs()` 的查询入口或分页查询。
- [x] 3. 让 Pack `manifest.yaml` 驱动默认注册流程。
- [x] 4. 给 `legal` 之外的 `education`、`programmer`、`writer` 补最小 Workflow。
- [x] 5. 把前端工作台接入 `/ai/core/*`。
- [x] 6. 给 Java 网关补 AgentOS 的统一入口。
- [x] 7. 给 Trace 增加导出能力。
- [x] 8. 给 Review 增加更完整的审计记录。
- [ ] 9. 让 `WorkflowStore` 支持更稳定的持久化配置与备份策略。
- [x] 10. 输出第一份可对外展示的 Core 运行评估报告。

---

## 11. 最终目标

第一层完成后，知弈就不是一个“多角色聊天系统”，而是一个可以被行业包复用的 AgentOS 底座。

最终形态：

```text
知弈 AgentOS Core
  负责稳定、可控、可审计、可恢复、可评估

Industry Workflow Packs
  负责政务、金融、教育、医疗、法律等行业专业能力
```

这条路线能同时服务产品、工程和科研：

- 产品上：避开通用 Agent 平台红海，进入信创与敏感行业场景。
- 工程上：先做统一运行时，再扩行业包。
- 科研上：围绕状态、恢复、治理、评估形成系统型创新。

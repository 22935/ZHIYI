# PR-S01 规划提议协议：实施与验收合并记录

> **文档性质**：阶段证据合并稿——实施记录 4 篇 + 独立代码级架构验收 2 篇
>
> **覆盖时间**：2026-10-11 ~ 2026-10-12
>
> **当前定位**：S01 是规划内核的 Proposal 层；后续 S02 / S03 建立在其概念之上
>
> **合并日期**：2026-10-30

## 0. 合并说明与导读

本册把 **S01 阶段（2026-10-11 ~ 2026-10-12）** 的 6 篇记录合并为一篇：4 篇实施记录 + 2 篇独立代码级架构验收。正文逐字保留原文，仅做两类机械处理：标题层级下移一级、指向已合并文档的相对链接改写；结论、数字、命令与代码块未改动。来源清单见文末附录。

### 0.1 这一阶段在解决什么

S01 处理的是「**模型如何参与规划而不越权**」。四步递进，每一篇只新增一种 Proposal 能力，且都不写正式计划：

1. **S01-01 最小类型化动作协议**：给 Planner 一个统一、封闭、可拒绝的动作入口，模型只能提议，不能携带身份、权限或执行事实。
2. **S01-02 有界 ReAct 规划循环**：把单次 `decide_runtime` 变成有预算上限的「观察—提议」循环，预算耗尽必须收敛为显式等待。
3. **S01-03 HTN 方法选择**：在方法目录上做分层展开，产出可验证的展开 Proposal，而不是直接生成执行步骤。
4. **S01-04 自适应视界**：让模型在候选视界里选择子集，但选中集合必须由服务端重算并满足依赖闭合。

### 0.2 一页结论

| 步骤 | 实施记录 | 独立架构验收 | 最终判定 | 关键证据 |
|---|---|---|---|---|
| S01-01 | 新增 3 文件、未改既有文件 | 未单独出具（由后续验收覆盖） | 通过，默认关闭、无生产装配 | 全量 1100 passed（既有 1079 + 新增 21） |
| S01-02 | 预算循环：模型 4 次 / 动作 6 次 / 240s | 提交前复核修复后通过 | 通过 | 1118 passed；补修「撤销后仍可交付」 |
| S01-03 | 方法选择 + 分层展开 Proposal | **ACCEPT（修复后）** | 通过 | 5 类 P1 修复，新增 22 项对抗，全量 1184 passed |
| S01-04 | 视界选择 Proposal，服务端重算闭合子集 | **CONDITIONAL** | 有条件通过，保持未提交 | 7 类 P1 修复；1ms 定时下 1281 passed，默认 Windows 仍有既有 20ms 流式计时失败 |

> 结论只覆盖 Proposal 链路。四篇均未接入生产装配、未运行真实 LLM 行为评测、未开启默认 Flag。

### 0.3 贯穿全阶段的不变量

- **模型侧无身份**：请求结构 `extra=forbid`，模型不能提交 commit、permit 或执行身份，只能携带请求侧的 sha256 指纹。
- **Runtime 分配身份**：编号、会话、登记表、版本均由 Runtime 侧生成，模型只看见逻辑 key。
- **Proposal 只读**：只写会话内存登记表与审计 Sink，不回写正式计划、不激活执行图。
- **固定检查顺序 + 封闭拒绝码**：拒绝理由是一个封闭集合，便于审计与回归。
- **revise 必须指纹一致**：修订只能针对会话内已登记的 `plan_revision`，避免基于过期版本继续规划。
- **默认关闭**：所有新路径由环境开关 opt-in，默认不装配。

### 0.4 明确未完成与下一阶段入口

- 会话、登记表为**进程内存态**，重启不恢复；幂等只在会话生命周期内成立。
- **真实 LLM 未验证**：预算按字符近似，默认成本/风险/候选数未调参。
- **HTN 条件为精确匹配**，不是通用求解器；Proposal 内容不持久，批准不等于采用。
- **S01-04 遗留条件**：默认 Windows 环境全量仍复现既有 20ms 流式计时失败，需单独解决回归稳定性；该条件在 S02 期间仍未关闭。
- 下一阶段：S02 把 Proposal 变成可持久、可审计的承诺（见 [`PR-S02-规划提交与图变更-合并记录.md`](PR-S02-规划提交与图变更-合并记录.md)）。

### 0.5 阅读建议

按 1 → 6 顺序阅读即可还原当时节奏：先看实施记录了解合同与预算，再看对应验收了解独立发现的反例。第 4、6 篇（S01-03 验收、S01-04 验收）是理解「Proposal 边界如何被反例收紧」的关键。

## 篇目与阅读顺序

1. **PR-S01-01：Unified Planner 最小类型化动作协议与只读观察能力实施记录** — 实施记录，2026-10-11 — 原文件 `PR-S01-01-统一Planner最小动作协议实施记录-2026-10-11.md`
2. **PR-S01-02：Bounded ReAct Planning Loop 实施记录** — 实施记录，2026-10-11 — 原文件 `PR-S01-02-BoundedReActPlanningLoop实施记录-2026-10-11.md`
3. **PR-S01-03：HTN Method Selection 与分层展开 Proposal** — 实施记录，2026-10-12 — 原文件 `PR-S01-03-HTNMethodSelection实施记录-2026-10-12.md`
4. **PR-S01-03 独立代码级架构验收** — 独立代码级架构验收，2026-10-12 — 原文件 `PR-S01-03-独立代码级架构验收-2026-10-12.md`
5. **PR-S01-04：Adaptive Horizon Proposal** — 实施记录，2026-10-12 — 原文件 `PR-S01-04-AdaptiveHorizonProposal实施记录-2026-10-12.md`
6. **PR-S01-04 独立代码级架构验收** — 独立代码级架构验收，2026-10-12 — 原文件 `PR-S01-04-独立代码级架构验收-2026-10-12.md`

---

## 1. 原文｜PR-S01-01：Unified Planner 最小类型化动作协议与只读观察能力实施记录

<!-- 原始记录：PR-S01-01-统一Planner最小动作协议实施记录-2026-10-11.md -->

> 原文件 `PR-S01-01-统一Planner最小动作协议实施记录-2026-10-11.md` ｜ 2026-10-11 ｜ 实施记录 ｜ 原文 8820 字节

**日期**：2026-10-11
**基准**：master `86b62c46`（工作树干净，未提交、未推送、未部署）
**状态**：代码与测试完成；新路径默认关闭，未接入任何生产装配

---

### 结论

PR-S01-01 已按任务书完成：新增 3 个文件（合同、网关、测试），未修改任何既有文件。AgentOS 全量测试 1100 通过（既有 1079 + 新增 21），其中包含 planner/contracts/architecture 子集 205、runtime 子集 280 的定向回归。既有 Planner、TaskPlan、ACG、Runtime Planning 行为零改动——`git status` 证实除 3 个新增文件外工作树无任何变更。

### 已确认的证据

- `python -m pytest -q`（apps/agentOS，空载顺序）：**1100 passed**，两次全量（加固前后）均全绿。
- 新增测试 `tests/components/planner/test_unified_actions.py`：21 passed，覆盖任务书全部验收项。
- `git status --porcelain`：仅 `contracts/planner_actions.py`、`components/planner/unified_actions.py`、`tests/components/planner/test_unified_actions.py` 三个新增文件。

### 真实修改文件

| 文件 | 角色 |
|---|---|
| `apps/agentOS/src/contracts/planner_actions.py` | 版本化动作协议合同（模型侧请求 + Runtime 侧结果，全部 `extra="forbid"` 冻结） |
| `apps/agentOS/src/components/planner/unified_actions.py` | `PlannerActionGateway` / `PlannerActionSession`：会话签发、只读投影、提案登记、确定性拒绝 |
| `apps/agentOS/tests/components/planner/test_unified_actions.py` | 21 个测试（合同层 + SQLite 真实 Run 边界集成） |

### 接口合同

#### 模型侧（不可信输入，唯一入口形态）

`PlannerActionRequest`：`requestRef`（会话内唯一、无空白、≤128）+ `query`（`run_state` | `capability_catalog` | `evidence_refs` 封闭枚举）或 `proposal`（按 `kind` 判别联合）二选一。请求中**没有任何身份字段**——`sessionId`/`actionId`/`runId`/`missionId`/`planVersion` 等键因 `extra="forbid"` 直接拒绝（测试 `test_request_rejects_forged_identity_fields`）。

三类提案：

- `candidate_tasks`：`PlannedTaskDraft`（无 key 候选任务；key 由 Runtime 分配为 `cand:{actionId}:{i}`）；
- `plan_revision`：复用既有 `TaskPlanPatch` 合同（版本算术、语义纯度由原合同保证）；
- `method`：`targetKey`（必须是当前 TaskPlan 中的 key）+ `capabilityId`（必须在可见目录中解析）+ 有界理由。

#### Runtime 侧（权威分配）

- `PlannerActionSession`：由 `open_session(run_id)` 签发，冻结绑定 `mission_id / run_id / graph_id / graph_version / plan_version / observation_id`，携带读授权集合、动作数预算与截止期。会话只能从持久 planningLoop 当前轮次派生，Run 终态或无当前轮次时拒绝签发。
- 结果三态：`PlannerReadResult`（封闭投影 + `truncated` 标志）、`PlannerProposalReceipt`（`status="registered"`，只含 `proposalId`/`kind`/`contentFingerprint`/`assignedKeys`，**不含原文**）、`PlannerActionRejection`（12 个封闭拒绝码 + 有界理由 + `retryable`）。

#### 确定性检查顺序（固定，见模块 docstring）

协议版本 → 载荷严格校验 → 会话存在 → 会话未撤销 → 预算（次数/截止期，耗尽后重放同样被拒）→ 重复 `requestRef`（同指纹幂等重放 / 异指纹 `DUPLICATE_ACTION`）→ 持久绑定 CAS → 读授权 → 执行（超时/失败显式拒绝）。

绑定 CAS 在每个动作前对持久状态复核：Run 存在、Mission 一致、非终态、`planningLoop.current.observationId` 未变、`taskPlan.planVersion` 未变；任一失配返回 `BINDING_MISMATCH` / `STALE_OBSERVATION` / `PLAN_VERSION_MISMATCH` 并**顺带撤销会话**（后续提交统一 `SESSION_REVOKED`）。

#### 拒绝码（封闭 Literal）

`PROTOCOL_VERSION_UNSUPPORTED` `INVALID_PAYLOAD` `UNKNOWN_SESSION` `SESSION_REVOKED` `BUDGET_EXHAUSTED` `DUPLICATE_ACTION` `BINDING_MISMATCH` `PLAN_VERSION_MISMATCH` `STALE_OBSERVATION` `UNAUTHORIZED_TARGET` `TOOL_TIMEOUT` `TOOL_FAILED`

### 权威边界落实

- **PROPOSE 不产生正式写入**：登记只写入会话内存登记表（`session.registered_proposals`）与审计 Sink；不触碰 `taskPlan` / `taskBindings` / `acg_blueprint` / Run 状态。测试逐字段对比提交前后的持久 Run 快照（含 execution_state 键集合不变、无 `supersededByRunId`）。正式落库仍归既有 RuntimePlanningDecision → SemanticRevisionService（S02）链路，本 PR 未改动该链路任何代码。
- **READ 最小投影**：run_state 只含步骤状态/审计结论/剩余与阻塞（无 `outputRef`/`commitId`/`payload`/`excerpt`/`auditRef`）；capability_catalog 只含规划词汇字段（无 `promptProfile`/`inputContract`/`outputContract`/`pluginId`）；evidence_refs 只含检查结论（无摘录）。测试以 dump 关键词断言。
- **不可信内容不可升级**：结构上不存在把提案文本拼入提示词的代码路径（本 PR 无任何 LLM 调用）；字符串字段里的伪造 JSON 永远是字符串（pydantic 严格类型）；回执与审计事件只携带 sha256 指纹，测试用注入文本验证原文不出现在任何回执/审计/后续 READ 中。
- **默认关闭**：新增测试扫描 `src/` 全部 `.py`，断言除两个自身模块外无人引用 `planner_actions`/`unified_actions`——即无生产装配、无环境变量、无 Flag 改动、无部署变更。

### 复用与克制

- 提案校验复用 `TaskPlanPatch`（含执行身份拒绝、版本算术）、`SemanticTaskKey`、`CapabilityCatalog.resolve`；
- 集成测试复用既有 ExecutionRuntime + SQLite 存储装配模式（对齐 `tests/runtime/test_planning_loop.py` 的 harness）；
- 未新建第二套 Planner/Runtime/Topology Compiler/Mission 状态；未引入数据库迁移；未为未来 ReAct/HTN 循环预建多余基础设施（无消息总线、无会话持久化表——会话是边界内临时对象，重启后旧 sessionId 确定性地得到 `UNKNOWN_SESSION`）。

### 已知限制（如实登记）

- 会话与登记表为进程内存态：跨进程重启后不恢复。这是"最小 PR"的刻意取舍；若未来模型循环需要跨重启续会话，应在接入 PR 中随持久化边界一起设计，而不是现在预建。
- TOOL_TIMEOUT 采用"执行后测耗时、超时丢弃结果"的事后判定，不能抢占阻塞中的提供者；当前提供者全部是本地 SQLite 读，风险可控，接入外部工具时需升级为可抢占执行。
- 提案中的 `plan_revision` 只做合同校验与版本/归属绑定，不做 `apply_task_plan_patch` 级全量引用校验——该权威属 S02，接入时由 SemanticRevisionService 复核。

### 下一个 PR 的建议（PR-S01-02）

1. 在 RuntimePlanningCoordinator 边界内 opt-in 装配网关（环境开关，默认关），把 `decide_runtime` 的单轮决策升级为"READ → PROPOSE → RuntimePlanningDecision 收口"的受限多轮循环（预算沿用会话机制）；
2. 将登记的 `plan_revision` 候选桥接到既有 revise 决策通道（仍走 `validate_decision` + `SemanticRevisionService`，不新增第二落库路径）；
3. 为 READ 增加分页/游标参数（当前 v1 无参数、整投影 + truncated 标志）；
4. 审计 Sink 接入 TraceStore（在 facade 锁内落 trace，替代当前注入式 Sink）。

### 提交前审计附记（2026-10-11，随本提交收敛）

对网关做了四项代码级审计：

1. **READ 时效性成立**：每次 `submit` 在授权与执行前都重载持久 Run 并复核 Mission/非终态/observationId/planVersion（`_check_binding` CAS），读负载取自持久化的当前轮 Observation，而非会话创建时的缓存。
2. **PROPOSE 零正式写入成立**：仅写会话内存登记表与注入式 audit sink，测试逐字段对比持久快照。
3. **发现并修复一个真实竞争**：网关原无锁，并发 `submit` 对 `actions_used`/幂等日志的 check-then-act 可能双重执行同 ref 或双重扣预算。修复=会话注册表锁 + 每会话提交锁（`session.lock`），并新增不变量测试（同 ref 并发提交恰好一次真实执行 + 一次幂等重放，预算只扣一次，与交错次序无关）。迟到结果竞争不存在：网关是纯同步 API，无后台路径。
4. **基线复现**：空载全量 1100 通过（既有 1078 + 本 PR 22）；`tests/adapters/test_model_runtime_streaming.py` 的 TTFT 计时测试在全量负载下抖动失败、隔离复跑通过，且用 `--ignore` 排除本 PR 全部文件后同样失败——确认为既有壁钟敏感抖动，与本 PR 无因果关系（该测试不导入任何本 PR 模块）。

---

## 2. 原文｜PR-S01-02：Bounded ReAct Planning Loop 实施记录

<!-- 原始记录：PR-S01-02-BoundedReActPlanningLoop实施记录-2026-10-11.md -->

> 原文件 `PR-S01-02-BoundedReActPlanningLoop实施记录-2026-10-11.md` ｜ 2026-10-11 ｜ 实施记录 ｜ 原文 10109 字节

**日期**：2026-10-11
**基准**：master `6bc5f8c9`（PR-S01-01 提交）之上的未提交工作区，等待独立架构验收
**状态**：代码与测试完成；新路径经环境开关 opt-in、默认关闭；未 commit、未 push、未部署

---

### 结论

S01-02 将单次 `decide_runtime` 演进为受预算约束的真实"模型—工具—模型"循环，并通过 Fake LLM + 真实 Runtime/SQLite 测试验证了完整受控路径（READ 多轮反馈、PROPOSE→revise→SemanticRevisionService 桥接、各类失败收敛）。AgentOS 全量 **1116 通过 / 0 失败**（既有 1079 + S01-01 22 + S01-02 15），其中 planner/contracts/architecture 子集 221、runtime 子集 280 定向回归全绿。

### 真实调用链

```
RuntimePlanningCoordinator.boundary()               （既有权威，未改动）
  └─ planner_for_run(run) → PlanningEngine          （facade；flag 开时挂循环）
       └─ engine.decide_runtime(observation, task_plan)
            └─ BoundedReActPlanningLoop.decide()     （components/planner/react_loop.py，新）
                 ├─ gateway.open_session(run_id)     （S01-01 网关，绑定持久 planningLoop 当前轮）
                 ├─ 循环 ≤ max_model_calls：
                 │    ├─ call_planning_model(llm, schema=PlannerLoopTurn)   （既有结构化输出适配）
                 │    ├─ use_tool → gateway.submit() → PlannerToolFeedback  （封闭投影回灌下一轮提示）
                 │    └─ decide → RuntimePlanningDecision
                 │         ├─ observationId 必须等于当前指纹
                 │         ├─ revise 必须与会话内登记的 plan_revision 指纹一致
                 │         └─ gateway.verify_binding() 交付前最后 CAS 复核
                 └─ 任何预算耗尽/故障/非法 → 显式 wait（可恢复 WAITING_REVIEW）
  └─ validate_decision / apply_decision              （既有审定与应用，未改动）
       └─ revise → SemanticRevisionService           （既有 S02 权威，未改动）
```

### 接口合同

- `PlannerLoopTurn`（contracts/planner_actions.py 新增）：`turnKind=use_tool|decide` 判别联合，use_tool 恰带一个 `actionRequest`（S01-01 `PlannerActionRequest`），decide 恰带一个 `finalDecision`（既有 `RuntimePlanningDecision`）。
- `PlannerToolFeedback`：工具结果的有界反馈投影（read 投影 / 登记回执（仅指纹与 Runtime 分配键）/ 拒绝码+理由），作为不可信数据进入下一轮提示。
- `ReActPlanningBudget`：统一预算——模型调用次数（默认 4）、工具动作次数（默认 6，透传网关）、上下文字符预算（默认 600k，按提示长度近似）、壁钟截止期（默认 240s，同时作为会话 TTL 与 `call_planning_model` 的共享 deadline）。
- `PlannerActionGateway.verify_binding(session)`（新增公共方法）：决策交付前对持久 Run/Observation/PlanVersion 的最后复核，失配返回拒绝并撤销会话。

### 修改文件（未提交）

| 文件 | 变更 |
|---|---|
| `contracts/planner_actions.py` | +`PlannerLoopTurn`、`PlannerToolFeedback`（41 行） |
| `components/planner/react_loop.py` | 新增 `BoundedReActPlanningLoop` + `ReActPlanningBudget` + `react_planning_enabled()` |
| `components/planner/unified_actions.py` | +`verify_binding`（6 行） |
| `components/planner/service.py` | +`react_loop` 构造参数与 `decide_runtime` 分派（默认 None，行为不变） |
| `runtime/workflow_runtime.py` | `_planning_engine_for_run` opt-in 装配：`AGENTOS_PLANNER_REACT_LOOP` 开 + 已注入意图 LLM 时逐 Run 构造引擎并挂循环，审计走 `trace_store` Runtime Event（与 planning_loop 同款）；关闭时路径与原先完全一致 |
| `tests/.../test_react_loop.py` | 新增 15 个测试 |
| `tests/.../test_unified_actions.py` | 源码扫描不变量演进：协议只允许经 opt-in 缝隙引用（react_loop/service/flag 门控 facade） |

### 关键设计决策

1. **结构化输出适配而非原生 Tool Calling**：审计确认 `IntentLLM` 协议只有 `generate_json(prompt, schema)`，网关无工具调用接口；判别 Schema 完全复用既有 `call_planning_model` 的超时/重试/提示词元数据边界，零网关重构。
2. **revise 桥接以登记指纹为凭**：`decide revise` 携带的 `TaskPlanPatch` 必须与本会话内已 PROPOSE 并通过网关校验的 `plan_revision` 候选指纹一致，否则收敛 wait——PROPOSE 因此成为 revise 的必经前置，模型无法凭空直提修订。candidate_tasks/method 永远只是候选，无任何进入执行图的通道。
3. **迟到结果丢弃**：每次模型调用返回后先查截止期，超时则丢弃内容直接收敛——`test_deadline_discards_late_model_result` 用"模型在截止期后返回 complete"验证了决策未被采用。
4. **重启/重入安全**：会话是边界内临时对象，重启后旧 sessionId 确定性 `UNKNOWN_SESSION`；轮次权威仍是持久 RuntimePlanningState（"observed→requested→decided→applied"标记逻辑未动），重复观察不重复调用模型、重复应用被 applied 标记拦截（既有测试覆盖，本轮未改）。
5. **测试时钟与模型时钟解耦**：注入测试单调钟时不向 `call_planning_model` 传递本循环 deadline（其内部用真实 monotonic，混用会造成假超时），循环自身的截止检查仍然生效。

### 实际测试结果

| 套件 | 结果 |
|---|---|
| `tests/components/planner/test_react_loop.py`（新） | 15 passed |
| `tests/components/planner` + `tests/contracts` + `tests/architecture` | 221 passed |
| `tests/runtime` | 280 passed |
| 全量 `python -m pytest -q` | **1116 passed / 0 failed**（3:49） |

Fake LLM 每一轮都从真实提示读取 `toolFeedback` 并断言其内容后才出牌（读取不到期望反馈即抛错）——证明反馈回路真实存在，不是脚本模拟。覆盖矩阵：真实多轮 READ→反馈→决策、重复工具请求幂等重放、PROPOSE→revise→SemanticRevisionService 全链（源 Run SUPERSEDED、替换 Run plan v2 完成执行）、未登记修订收敛 wait、边界中途 Observation 变化/会话撤销收敛、模型预算/动作预算耗尽、截止期迟到结果丢弃、模型故障、非法轮输出、伪造 observationId、工具故障反馈后继续、模型故障经审核批准恢复（等价重启恢复）、flag 默认关单次路径逐字节不变（提示词无 toolFeedback、单次调用）、facade opt-in 行为。

测试中发现并修正的三处问题（均为本轮引入，未触及生产既有路径）：测试注入时钟与 `call_planning_model` 真实单调钟混用造成假超时（修复=仅共享真实时钟时传递统一 deadline）；测试桩 Agent 不满足 task_understanding 输出合同（缺 `task_summary`，对齐既有桩）；子类覆写网关方法名写错（`_read_evidence`）。

### 失败恢复语义

所有非正常终止统一收敛为显式 `wait` 决策（reason 前缀 `Bounded ReAct Planner:`），由既有协调器审定并落到 WAITING_REVIEW 屏障——外部审核批准即可恢复，无伪造 complete/success；模型抛出的意外异常同样被收敛（单次路径的既有语义是协调器兜底 safe wait，两条路径一致）。

### 剩余风险与停留在此 Proposal 阶段的能力

- **candidate_tasks 与 method**：仅会话内登记，无消费方；进入执行图的唯一通道仍是 plan_revision→revise→S02。HTN 方法选择、Adaptive Rolling Horizon（按远期意图动态决定提交视界）、S02 Planning Commit、S03 Progressive ACG 均未实施（范围边界）。
- **revise 语义仍是"版本化替换整个 Run"**（替换 Run 重执行全部步骤，测试如实断言）；已执行前缀不可变是后续 PR 的目标。
- **上下文预算按提示字符数近似**，非精确 token 计量；预算默认值（4 次模型调用/6 次动作/240s）未经真实模型调参，接入真实 LLM 前需实测校准。
- **会话内存态**：跨重启不恢复（设计取舍，重启后确定性 UNKNOWN_SESSION）；网关会话字典在长寿命进程内按 Run 积累（每会话 ≤ max_actions 条记录，量级可控，未来可加淘汰）。
- **真实 LLM 端到端未验证**：本轮全部为确定性 Fake LLM；真实模型在该判别 Schema 下的服从率、多轮行为质量需在验收环境用真实供应商实测。

### 2026-10-12 提交前复核

- 当前 HEAD 为 `6bc5f8c9`，S01-02 的 8 个变更路径均未暂存；没有其他工作树。
- 用户在本轮提供了独立架构验收全文，结论 **ACCEPT（无 P0）**：planner/contracts/architecture 221、runtime 280、全量 1116 通过。已对照实际变更核实四项权威边界：替换 Run 的既有重执行语义、共享绝对截止期、最终应用 CAS、持久轮次与幂等恢复。该报告针对补充修复前的 5 修改 + 2 新增 + 1 文档；不把其结论冒称为修复后的独立验收。
- 代码复核发现最终决策交付前 `verify_binding()` 未检查会话撤销状态，撤销后直接返回 `decide` 可绕过工具提交侧的撤销门禁。补充签发实例归属、撤销状态与截止期检查，保留动作预算耗尽后模型仍可安全作出最终决策的原有行为。
- 新增 2 项回归：撤销后直接返回 `complete` 收敛为 `wait`；外部网关的会话及过期会话均不能交付决策。
- 修复后定向运行 `test_react_loop.py` + `test_unified_actions.py`：**39 passed**；重新启动全量 `python -m pytest -q`：**1118 passed / 0 failed**（224.14s，既有 PyPDF2 弃用警告 1 项）。`git diff --check` 通过。
- 按用户授权将 S01-02 的 8 个明确路径整理为本地 Commit，标题 `feat(agentos-planner): 实现受控 ReAct 规划循环与工具反馈闭环`；未 Push、未部署、未操作生产数据库。提交 hash 由 Git 查询，不写入自身提交树。

---

## 3. 原文｜PR-S01-03：HTN Method Selection 与分层展开 Proposal

<!-- 原始记录：PR-S01-03-HTNMethodSelection实施记录-2026-10-12.md -->

> 原文件 `PR-S01-03-HTNMethodSelection实施记录-2026-10-12.md` ｜ 2026-10-12 ｜ 实施记录 ｜ 原文 10739 字节

日期：2026-10-12。基线：`872ee9bd`（S01-02 本地提交）。状态：独立代码级架构验收 ACCEPT（修复后），本轮按用户授权整理为本地提交。未 Push、未部署，未修改生产数据库或正式 ADR。

### 基线与审计

S01-02 独立验收全文由用户在本轮提供，原结论 ACCEPT，原全量 1116 通过。提交前复核补充了最终交付的会话归属、撤销和截止期检查及 2 项测试，修复后全量 **1118 passed**；提交标题为 `feat(agentos-planner): 实现受控 ReAct 规划循环与工具反馈闭环`。

独立报告的非阻断 P2 仍保留：ReAct 的内部供应商重试实际次数留在局部 call_audit，未上抛运行审计；实际请求受既有绝对 deadline 与重试上限约束。本 PR 未扩大此观测改动范围。

审计链：`TaskDecomposer.decompose` → `SemanticPlanner` → `TaskPlan` → `TaskPlanTopologyCompiler`；Runtime 边界 → `PlanningEngine.decide_runtime` → ReAct → `PlannerActionGateway`。现有 `PlannedTask.parentKey` 和 `TaskPlanRelation` 已具备层次与依赖语义，无需复制计划模型。SemanticPlanner/TaskDecomposer 的正式计划生产路径保持原有行为；HTN 只接到 opt-in 工具缝隙。

### 方法表示与选择算法

- Abstract Task：现有正式计划中任务的 `metadata.taskType` 标签，如 `analysis`。目标仍由已有 semantic key 定位，不新建正式任务身份。
- `HTNMethod`：受信任代码目录中的 `methodId`、`abstractTask`、版本、优先级、适用条件、子任务、局部排序和定义来源。`HTNSubtask.task` 直接复用 `PlannedTask`；其 key 是定义内稳定槽位。设置 `abstractTask` 表示继续展开，否则恰有一个可见目录 capability，是原子槽位。方法不能设置执行身份、父 key 或材料 workset。
- Applicability：闭合集合的等值条件合取，支持冻结 Basis 来源类型、显式 constraintId 的精确值、当前唤醒原因，以及可信观测中指定任务的状态/审核结果。缺失或歧义观测不满足条件；冻结/继承约束同 ID 不同值拒绝。只读取 Run 的冻结 Basis，不读取最新 Mission 语义替代它。
- 查询返回各候选的真实定义、适用状态及封闭拒绝原因。根方法由模型选择已有 methodId；子层只对适用方法按 `preferredMethodIds`、定义优先级、methodId 稳定排序。未知方法、条件不满足和展开失败明确拒绝，不伪造有效计划，也不自动偷偷换另一种根方法。
- 目录最多 128 个方法、总定义 120k 字符；保存不可变序列化快照并计算内容 SHA-256 revision。请求只能引用 revision，不能提交定义、条件、权限或执行事实。展开全程使用同一目录快照，发生变化即拒绝。
- 内置最小词汇：`analysis.standard`（理解→分析）、`analysis.evidence`（已冻结 SEMANTIC Basis 时可选：理解→证据子任务）、`evidence.compare`（检索→证据分析→比较）。可由可信装配代码注入其他目录，未新增模型写目录入口或数据库状态。

### 展开与验证边界

1. 目标必须有明确 taskType、冻结来源引用，且可信当前观测及持久步骤状态均为未开始、无工作/审核收据。拒绝已完成、运行中、失败、跳过、待审任务，以及已有层次、受验证控制的目标或材料 workset；这些改动需要后续正式规划/恢复规则。
2. 有界深度优先递归；活动抽象类型栈检测循环。每个孩子继承父约束、验收条件及来源，并追加可信方法定义引用。来源必须属于冻结 Basis/约束来源或精确 Basis 指纹引用；子槽位不得发明新来源。引用仍是 UNVERIFIED，不被升格为已核实业务证据。
3. 候选 key = `htn:` + SHA-256(parent key, methodId, local slot) 的前 32 位；与文本、会话、Run、方法版本和目录内容版本无关。同逻辑槽位跨请求、方法版本变化和重启稳定，碰撞既有 key 则拒绝。父关系同时保留 parentKey 和 parent relation。
4. 方法局部 `depends_on` 使用既有“前置 source→后继 target”方向；抽象子组的先后约束保守展开到各组原子后代之间。没有另写 DAG 排序、能力绑定或拓扑修复器。
5. 原子投影交给 **既有** `validate_task_plan_for_execution` / `TaskPlanTopologyCompiler.validate_existing_plan`，采用固定模板声明边，不走模型 repair。能力前置条件、DAG、终端连接和产物生产者仍由现有门禁校验；抽象父节点不冒充产物/能力生产者。包含外部已有节点的层次结构另经现有 TaskPlan 合同检查。以上 TaskPlan 对象仅在内存用于验证，未写正式计划。
6. Proposal 保留目标原有 `boundaryRelations`，不将外部依赖接线转成正式执行图。与正式图的原子接线/提交由后续 S02/S03 负责。

预算默认：深度 8（根层为 0）、总节点 64（含抽象父）、展开依赖/父边 256、候选评估 256、节点内容 120k 字符，并共享网关单动作截止期；现有 ReAct 的轮数、工具数、上下文与总截止期继续生效。拓扑校验新增边同样计入预算。

### 工具闭环与权威

```
ReAct READ method_catalog(targetKey)
  → 可信候选定义 + applicability + catalogRevision
ReAct PROPOSE method(targetKey, methodId, catalogRevision, preferredMethodIds?)
  → 确定性展开 + 现有语义/拓扑门禁
  → 会话登记 + HTNExpansionProposal 回执
  → 下一模型轮真实 toolFeedback
  → wait（经既有 Runtime 审核等待链）
```

`HTNExpansionProposal` 仅封装既有 PlannedTask/TaskPlanRelation、原子 key、方法选择轨迹及 Basis/Observation/PlanVersion/目录绑定信息，不是 TaskPlanPatch、Runtime Graph 或 Planning Commit。模型 rationale 不进入展开或审计。

使用 HTN 的会话不可登记 plan_revision，已登记 revision 的会话也不可进入 HTN。HTN 轮次最终动作仅允许 wait，禁止通过 revise/recover/continue/complete 兑现层次提案。因此不能接到既有“替换 Run 重执行全部节点”的通道。标准 Planner/ReAct 的非 HTN 修订与 SemanticRevisionService 行为保持原样。

默认关闭：`AGENTOS_PLANNER_HTN` 未设置时，不装配方法目录；生产入口还需 S01-02 的 `AGENTOS_PLANNER_REACT_LOOP` 开启且注入 LLM。旧 capability-only method 建议仍兼容。HTN 请求显式拒绝关闭/未装配状态。会话内有效重复请求幂等重放；按既有协议，预算耗尽/会话过期后不重放。HTN 重放前重新检查持久 Run/Plan/Observation/Graph/步骤状态、开关及目录版本，不能用缓存越过世界变化。重启不恢复旧 sessionId，新会话可确定性重建相同 Proposal。

### 实际验证

所有数据库均由测试创建在临时目录；模型为确定性 Fake LLM。真实 Runtime 测试使用独立重建的 ExecutionRuntime 与既有 SQLite/ACG/身份/审核组件，通过 `execute_prepared_run` 的恢复边界运行查询、选择、展开反馈和 wait。逐项核对正式计划、绑定、ACG 和冻结 Basis 不变，Agent 未执行；重复进入审核等待不重复调模型。

| 测试 | 实际结果 |
|---|---|
| 新增 `tests/components/planner/test_htn.py` | 44 passed |
| planner + contracts + architecture + runtime | 546 passed（435.61s，该轮采集 43 个新增用例）；随后补充第 44 个用例及真实 Runtime 重建验证，定向 44 passed |
| 最终代码全量 `python -m pytest -q` | **1162 passed / 0 failed**（390.66s = 6:30；S01-02 基线 1118 + HTN 44；仅既有 PyPDF2 弃用警告 1 项） |

覆盖多合法方法、约束/观测适用性、未知/不适用/冲突方法、多层与子方法排序、循环、非法 DAG、缺少能力前置生产者、来源、产物生产者、五类预算与截止期、稳定身份、目录深层不可变、模型伪造合同拒绝、已有执行收据/层次/workset 拒绝、外部依赖保留、版本/观测/图/状态/开关变化时缓存失效，以及晚于 Run 的 Mission 修订不改变冻结选择。ReAct 测试既消费目录反馈决定方法，又消费真实工具拒绝反馈后改选合法方法；直接网关登记逐字比对 Run 与 outbox 无写入。

扩大回归中测试 harness 直接给枚举字段赋字符串产生 1 项 Pydantic 序列化警告；已改用 `StepStatus.COMPLETED`，随后定向 44 项无警告通过。未跳过失败用例或降低架构门禁。

最终 `git diff --check` 通过。HEAD 仍为 `872ee9bd`，S01-03 范围为 4 修改 + 4 新增（含本记录），暂存区为空；代码、测试、记录均留在工作区待独立验收。

本轮首个 Runtime 集成测试的 harness 直接从 PENDING 调协调器，违反既有 PENDING→WAITING_REVIEW 生命周期。已修正为真实重启 RUNNING Run → `execute_prepared_run` 的恢复边界，不修改状态机或降低门禁；随后该用例通过。

### 剩余限制

- 条件是有限、精确值匹配；不解释任意自然语言矛盾，不进行成本搜索、最优性保证、全局回溯或自动生成方法。目录作者须维护 methodId/slot 的稳定语义。
- 需可信计划显式 taskType 与冻结来源；不会自动把每个普通原子任务改造成抽象任务。保守拒绝已有执行前缀、层次、受控节点和材料分块对象，不承诺 HTN 已解决其正式变更问题。
- Proposal/登记仅在会话内存中存在，不新增正式持久状态，跨重启按同一冻结输入重新展开。真实供应商模型的策略质量和 schema 服从率未实测。
- 正式 Planning Commit、外部执行图接线、资源绑定、执行承诺、Adaptive Rolling Horizon 均未实施；无 S02/S03、LLM Gateway 或 ADR 变更。

### 独立验收与提交前复核

独立验收报告为 `PR-S01-03-独立代码级架构验收-2026-10-12.md`，结论 ACCEPT（修复后），最终全量 1184 passed。五类 P1 已保留：发布前复核及完整动作截止期、撤销授权后禁用缓存、同版本内容变化的会话指纹、父能力覆盖、约束内部来源闭合校验。新增对抗测试 22 项，原 44 项 HTN 断言未修改。

提交前逐文件比对独立验收最终 SHA-256，源码与测试全部 MATCH；再次运行 HTN/对抗/ReAct/网关四文件：**105 passed**（61.20s）。`git diff --check` 通过。将四修改与六新增路径整理为本地 Commit：`feat(agentos-planner): 实现 HTN 方法选择与分层展开提案`；提交 Hash 由提交完成后的 Git 查询及下一阶段记录保存，避免写入自身提交树。

---

## 4. 原文｜PR-S01-03 独立代码级架构验收

<!-- 原始记录：PR-S01-03-独立代码级架构验收-2026-10-12.md -->

> 原文件 `PR-S01-03-独立代码级架构验收-2026-10-12.md` ｜ 2026-10-12 ｜ 独立代码级架构验收 ｜ 原文 12457 字节

日期：2026-10-12。本轮从实际 Diff、源码和独立新增的对抗测试重新验证，未把实施记录的结论作为通过依据。

**判定：ACCEPT（修复后通过）。** 入场代码存在 5 类 P1，已做最小修复并由反例回归验证；最终全量 **1184 passed / 0 failed**。未发现 HTN 可直接改正式计划或触发替换 Run 的 P0 路径。本结论只针对 S01 的方法选择与展开 Proposal，不意味着已完成全局执行 DAG 提交验证。

### 固定证据与变更范围

- HEAD：`872ee9bdbee3daed4849a2aa931bc97dd0d7dfc0`，S01-02 本地基线；父提交 `6bc5f8c9` 为 S01-01。
- 入场工作区：4 个修改文件（react_loop、unified_actions、planner_actions、workflow_runtime）+ 4 个未跟踪文件（HTN 算法、HTN 合同、HTN 原测试、实施记录）；暂存区为空。
- 初始状态、完整 tracked binary Diff、S01-02 Commit 说明、未跟踪文件列表、8 个文件原始字节及 SHA-256 已固定于 `.tmp-tests/s01-03-audit-xuulexgj/`。`sha256.json` 可对比审计前后。
- 本轮只修改 `components/planner/htn.py` 与 `components/planner/unified_actions.py`，新增 `test_htn_adversarial.py` 和本报告。原有 44 项 HTN 测试文件、ReAct、合同、Runtime 装配、实施记录均与入场 SHA-256 一致；未弱化原有断言。
- 没有 Commit、Push、部署、生产数据库操作、数据库迁移或正式 ADR 变更；真实集成测试仅使用临时目录中的 SQLite。

### 确认并修复的 P1

| 问题 | 可复现证据 | 修复及源码位置 |
|---|---|---|
| 计算期间世界变化/会话过期后仍登记结果；复核耗时不计入动作截止期 | 真实 selector 返回后修改 Flag、Observation、步骤状态、Catalog，或使 TTL 耗尽，原代码仍返回 registered；展开后持久读取超时也可登记 | `unified_actions.py:408` 在反馈发布、journal 和登记前复核；`:424` 检查授权、版本、绑定、事实、TTL 与动作 deadline；登记推迟至 `:414`。缓存结果同样复核 |
| 撤销方法查询授权后仍回显缓存 | 成功 READ 后移除 method_catalog grant，原代码重放旧 READ | `unified_actions.py:353` 在 HTN 缓存分支前检查 grant；最终发布前再检查。整会话撤销仍经原 session lock |
| 相同版本号的计划/图/绑定/Runtime 内容变化没有使缓存失效 | 分别修改 TaskPlan 约束、ACG metadata、taskBindings 或 runtimeRevision，原代码仍重放旧展开 | `unified_actions.py:505` 新增仅会话内的 context fingerprint，封存 plan/graph/bindings/basis/scope/runtimeRevision/status；既有绑定检查中比较，不新增持久状态 |
| 父任务 capabilityRequirements 被抽象 root 清空后缺少覆盖检查 | 父任务明确要求 risk_analysis，standard 方法只有理解与 analysis，却通过验证 | `htn.py:290` 在既有拓扑门禁后比较规范 capability 集合，缺少父要求拒绝为 HTN_CAPABILITY_REQUIREMENT_LOST。不是要求每个原子节点携带父任务全部能力 |
| 约束内部来源可以绕过来源验证 | 新子约束 sourceRefs 引用 invented:source，原代码只校验 task.sourceRefs，因此接受 | `htn.py:74` 校验约束内 sourceRefs 的类型与闭合来源集，覆盖根任务及每个子任务 |

最初对抗测试 **8 failed / 5 passed**；随后同版本上下文复用的四个反例 **4 failed**；最终复核耗时反例 **1 failed**。修复期间保留了原有“缺少能力前置生产者”用例的 HTN_TOPOLOGY_INVALID 目标，将能力覆盖检查放在既有 Compiler 校验之后，未修改该用例。

### 1. 方法语义：成立，但不是完整搜索规划器

- `contracts/htn.py:16` 的冻结、extra=forbid 合同定义 Method、封闭条件、Subtask 和 Proposal，子任务直接使用 PlannedTask；Abstract Task 是现有任务 metadata.taskType。请求只能引用 methodId/catalogRevision/preferredMethodIds，不能提交新定义或伪造适用性（`planner_actions.py:140`）。
- `htn.py:149` 对同一 abstractTask 枚举多个定义，以冻结 Basis、显式约束和可信步骤/审核投影做条件合取，并解析可见能力；未知事实不满足条件。选择过滤适用集合后才接受根方法或子方法排序。
- `htn.py:207` 按 abstractTask 引用递归选择新的方法，维护活动抽象类型栈、父关系和叶节点集合。内置 analysis 有 standard/evidence 两种方法，evidence 继续选择 evidence.compare；实测多层展开，不只是静态 parentKey 填充。
- `htn.py:45` 将目录定义序列化为不可变字符串快照；访问者只能获得重建对象，改变原定义或返回的嵌套字典不会改目录。目录内容 SHA-256 是 revision；方法版本与整个定义内容均参与 revision。修改定义而不升 version 也会改变 revision，使旧请求失效。
- `htn.py:239` 的 key 只依赖父 logical key、methodId 和 slot。**同 slot 的能力/目标被重定义，key 仍可相同**；实测 version 2 由 analysis 改为 risk_analysis 时 key 不变，revision 和 methodVersion 变化。它是 logical identity，不是语义内容不变的证明。S01 没有采用旧执行收据的路径；目录作者须保持槽位语义，后续消费者不得仅按 key 复用完成节点。这是非阻断限制。

### 2. 继承、预算和拓扑：局部证明成立

- 冻结 Basis 每次重新校验 fingerprint/mission/ref；不以最新 Mission 语义替代旧 Run。父约束与冻结约束、验收条件、来源逐层保留；同 constraintId 的冲突拒绝。修复后能力要求由原子后代覆盖，task 与 constraint 的来源都闭合于冻结输入/定义来源；引用不会成为“已验证证据”。
- 深度上限 8、总节点 64、局部边 256、候选评估 256、节点内容 120k 字符；目录最多 128 方法、总定义 120k 字符。活跃类型栈检测展开循环，逐节点/逐边检查预算，最终 Compiler 新增边也计入总数。
- `htn.py:257` 的局部排序对左右子组的原子后代做笛卡尔积，单条排序最坏产生 `|L| × |R|` 条边。实测 16×16 产生 256 条依赖，加父边后超过默认 256 总边预算被拒；提高测试预算至 512 时恰有 256 条依赖，验证不是漏边后“通过”。预算在每次 append 后检查，最多多构造一条触发拒绝。
- 模板构建/候选扫描有受目录和节点数量限制的成本；现有正式输入层次检查遍历原 TaskPlan，最坏 O(P²)。原子拓扑阶段仍受既有 Compiler 搜索上限约束，超时后丢弃结果，并非可抢占的计算取消。
- `htn.py:276` 只把**局部原子投影**送到既有 validate_task_plan_for_execution → TaskPlanTopologyCompiler.validate_existing_plan；边采用 FIXED 模板声明，不进入模型 repair。HTN 没有另写能力绑定、DAG 校验或拓扑修复器。完整节点集合另经既有 TaskPlan 结构合同检查，这不等于全局执行图证明。
- `htn.py:301` 的 boundaryRelations 仅保留原声明。对抗测试捕获 Compiler 输入，确认 external 节点及 boundary relation 均不在局部投影中，也不在已校验的内部 relations 中。其原子接线、完成前缀、全局能力生产者/控制和 DAG 验证必须由后续正式提交链处理；本轮不冒充已提交边。

### 3. ReAct/Proposal：权威隔离成立

链路：`react_loop.py:165` 结构化 PlannerLoopTurn → `:191` gateway.submit → READ method_catalog / PROPOSE method → 确定性展开与门禁 → `:195` toolFeedback → 下一模型轮。Fake LLM 实际消费目录/拒绝/展开反馈后改变方法选择；不是外层脚本跳过工具的演示。

`react_loop.py:219` 限制 HTN 使用后的最终动作只有 wait。网关禁止 HTN 会话登记 plan_revision，反向也禁止已经登记 revision 的会话进入 HTN；并发提交由同一 session lock 串行化。模型不能设置执行绑定、资源、Run 身份或提高权限。生产装配的 selector 与 gateway 使用同一个 Run scoped capability_catalog（`workflow_runtime.py:2227`）。

独立算法没有 Store、Graph Builder、Binding 或 SemanticRevisionService 接口；网关只登记会话内数据。原测试逐字比较工具前后 Run 与 outbox 无写入。完整 ReAct 最终 wait 会经**既有** Runtime 写轮次、checkpoint 和等待状态（`planning_application.py:89`），这不是 HTN Proposal 写正式计划；只有 action=revise 才能走 `:106` 的 SemanticRevisionService，而 HTN 轮次无法交付 revise。不能把“完整循环完全不写 Run”当作已验证事实。

### 4. 并发、过期、恢复：最终校验与安全边界

- 两线程同时提交完全相同的展开请求：一份登记、一次预算扣减、一份重放；失效 grant、session 撤销、过期 TTL、目录变化、观测/步骤变化、同版本内容变化不能复用旧结果。
- 新增 result fence 位于登记、缓存发布和 journaling 之前；不递归获取已经持有的 session lock。异常/迟到结果不留下 registered proposal 或 journal 成功条目。
- **不是持久 Planning CAS**：网关检查是基于持久读取和进程内 session lock 的发布前早检，不保证跨进程原子封锁全部世界变化。正式状态应用仍依赖 `workflow_runtime.py:1093` 的 Runtime Revision/取消/操作员输入 Fence 及 `:1103` 的既有锁；HTN 本身无法提交计划或图，因此不提前实现 S02。
- 重启使旧 sessionId 失效，从同一冻结输入及目录可重建相同候选/展开。真实 Runtime 测试丢失全部内存 Proposal 后加载原 SQLite/checkpoint，审核批准恢复原计划，最终仅执行原 A 节点；没有新增 HTN 节点、替换 Run 或改变 TaskPlan/ACG。等待屏障不依赖内存 Proposal。
- HTN Proposal 的内容不持久保存，重启后不能把 generic review approval 解释为已经审核/采用了某份丢失提案。后续如需展示/采用提案，必须有独立可核验的正式合同。
- 两个 Flag 都关、仅 HTN 开、仅 ReAct 开三个组合均实测回到原决策路径；已有双开真实反馈测试保持通过。

### 5. 本轮实测结果

工作目录均为 `apps/agentOS`，系统 Python，临时 SQLite/Fake LLM；未使用真实供应商 LLM。

| 命令 | 实测结果与快照 |
|---|---|
| `python -m pytest -q tests/components/planner/test_htn.py tests/components/planner/test_react_loop.py tests/components/planner/test_unified_actions.py` | 入场代码 83 passed，48.38s |
| `python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime` | 第一修复快照 564 passed，279.41s；不是最终内容 Fence/截止期补充之后的快照 |
| `python -m pytest -q tests/components/planner/test_htn_adversarial.py tests/components/planner/test_htn.py tests/components/planner/test_react_loop.py tests/components/planner/test_unified_actions.py` | **最终代码 105 passed**，69.78s（原 HTN 44 + 对抗 22 + ReAct 17 + 网关 22） |
| `python -m pytest -q` | **最终代码 1184 passed / 0 failed**，359.00s；仅既有 PyPDF2 弃用警告 1 项。较早修复快照 1179 / 1183 passed 不代替此次最终结果 |

新增测试覆盖重定义、跨组边、来源与父能力丢失、局部/全局边界、并发、授权、上下文、deadline、内存 Proposal 丢失、真实审核恢复及 Flag 兼容。原约束冲突/来源/DAG/循环/预算等 44 项保留原文件与断言。

最终核对：`git diff --check` 通过，HEAD 仍为 `872ee9bd`，暂存区为空；对比原 8 个文件只改变上述 2 个源码文件，新增对抗测试与报告。审计源码差异及最终 SHA-256 另存于固定证据目录。未 Commit、Push、部署或改变生产数据。

### 剩余风险与下一阶段边界

非阻断：trusted method/slot 自然语言语义不能自动证明不变；精确条件匹配不是通用约束求解器；不具备最优搜索/回溯；Proposal 为内存态；真实 LLM 策略质量与服从率未实测；S01-02 内部重试计数未上抛审计的 P2 继续保留。

后续正式规划阶段必须重新证明外部依赖与全局 DAG，校验全部控制/审核及已完成副作用前缀，结合语义内容与版本决定 key/收据的复用，不能仅依据局部 Proposal 或同 key 采用工作承诺。本轮未实施 S01-04、S02、S03。

---

## 5. 原文｜PR-S01-04：Adaptive Horizon Proposal

<!-- 原始记录：PR-S01-04-AdaptiveHorizonProposal实施记录-2026-10-12.md -->

> 原文件 `PR-S01-04-AdaptiveHorizonProposal实施记录-2026-10-12.md` ｜ 2026-10-12 ｜ 实施记录 ｜ 原文 10248 字节

状态：实现完成，独立代码级验收为 CONDITIONAL；S01-04 保持未提交。条件及最新证据见文末独立验收补充。不 Push、不部署，不升级数据库，不修改正式 ADR。

### 基线

S01-03 已按独立 ACCEPT 报告核对完整变更及源码 SHA-256，保留五类 P1 修复，提交前重新运行 HTN/对抗/ReAct/网关测试：105 passed，61.20s。

本地提交：`ce1d67d117f678f211409fb4f47dee80fc24d37b`，`feat(agentos-planner): 实现 HTN 方法选择与分层展开提案`。提交后工作区为空，未 Push。

### 合同与算法

- 新增冻结且 `extra=forbid` 的 `PlanningFrontier`、`HorizonProposal`、`HorizonSelection`，schemaVersion=1，algorithmVersion=`adaptive-horizon.v1`。复用 `TaskPlanRelation`，不复制 TaskPlan。Proposal 表达候选、实际前置已完成的 readyKeys、延迟任务及原因、内部与跨窗口依赖、资源观察、任务内容指纹及预算；绑定 Mission、Frozen Basis 指纹、Observation、PlanVersion、Run 状态、策略/能力目录 revision 和完整输入指纹。
- 只读取正式 TaskPlan；原约束、来源、验收及能力字段保持原样，全部包含在 Plan/任务指纹中。使用 Run 的冻结 Basis，当前 Mission 编辑不会漂移旧 Run。
- 先调用既有 `validate_task_plan_for_execution` / `TaskPlanTopologyCompiler`，使用其已验证的依赖（含能力与终端规则推导的边），再做候选集合运算。Frontier 及 Proposal 的集合、分区、预算、依赖边界校验不承担 DAG 编译、修复或 GraphVersion 提交。
- 状态分为 completed、active、considerable、dependency_blocked、review_wait、failed、terminal、unknown、resource_wait、control_wait。完成前置要求可信观察提供 commit/audit 引用及 allow 或已解除审核阻塞的 review 结果；未知证据、部分/失败验证不会被当作已满足前置。已完成、执行中、重试、失败、取消及条件跳过节点均不重新列为候选。整个 Run 等待审核、completionBlockers 或循环控制分别保留审核/控制屏障。
- 可选任务先按风险升序、直接后继数降序、成本升序、稳定 Key 排序；每次加入节点后重新考虑前置已完成或已入选的后继。未来工作可在候选窗口内，但 readyKeys 只包含真实前置已完成的工作。未完成且不在窗口的前置不能被删掉以让消费者入选；所有原依赖均保留在 Frontier，全部跨窗口边另行列出。
- 风险取任务声明与可信能力目录风险的最大值（normal/elevated/high/critical=1/2/4/8）；成本取至少 1、能力数量与 Workset 已声明估算单元数的最大值。默认成本预算12、风险预算8、候选上限16；高风险任务隔离，审核型任务之后截断窗口。均为规划估算单位，不是费用报价、执行资源配额或资源预留。
- 反例：成本预算1时，独立 A/B/C 选择 A；加入 B→C 后选择 B；改任务排列仍选择 B。相同三个任务由低风险改为高风险，窗口由3个缩至1个；A 成本20时跳过 A，选择 B/C。不是固定节点数或前缀切片。
- 原输入上限256节点、1024声明关系、300k字符；编译后最多4096依赖。无新增递归展开；候选打包预计算后继数，最坏约 O(VE + V²(D + log V))，D 为最大入度，受上述输入及截止期约束。共享 Compiler 的内部工作受输入规模及返回后截止检查约束，未增加强制线程中断。

### 工具与权威隔离

`AGENTOS_PLANNER_ADAPTIVE_HORIZON` 默认关闭；只有 ReAct 同时启用且存在 LLM 装配时挂接。HTN Flag 独立。

ReAct 可查询 `planning_frontier` / `candidate_horizon`，再提交 `kind=horizon`、准确 inputFingerprint 和 selectedKeys。服务器重新计算候选，只接受其依赖闭合子集；模型不能提供预算、完成状态、预留、身份、权限、方法定义或执行图。回执仅在本会话内登记。真实结构化工具反馈进入下一轮模型提示，最终只允许 wait；Horizon 与 plan_revision 双向互斥。

复用会话锁、请求指纹日志、动作数/TTL/完整动作截止期、授权和版本 Fence。计算及缓存复用前后检查 Flag、策略/能力目录、授权、Run/Plan/Observation；内容 Fence 额外覆盖步骤、执行输入、收据相关状态。迟到结果不进入 journal 或 registry。审计仅记录指纹、计数、预算使用和拒绝码，不记录任务/来源/提案正文。

工具计算及登记不调用 WorkflowStore 写入，不修改正式 TaskPlan、ACG、Run 或执行收据。整个 ReAct 最终 wait 仍由既有 RuntimePlanningCoordinator 持久化轮次和审核屏障；该既有持久化与提案登记是不同操作。没有调用 SemanticRevisionService、新建替换 Run、绑定资源或激活候选窗口。

不采用 HTNExpansionProposal 作为 Horizon 输入，`sourceExpansionRef` 等字段明确拒绝。HTN 的局部原子投影及 boundaryRelations 不具备全局提交证明，不能冒充执行边。混合会话保留 HTN Catalog Fence；重启只能从正式计划、冻结 Basis 和可信观察重新计算，不能复用丢失的内存展开。未提前实现 S02。

### 验证

所有 Runtime 集成测试使用测试临时 SQLite，真实准备 Run、构造 Observation、经过工具反馈及 Runtime wait；未调用真实模型供应商。

新增 Horizon 测试覆盖稳定性、自适应反例、全部执行分类、审核和资源观察、完整依赖边界、Compiler 推导依赖、预算/输入/截止期、模型越权、合同伪造、并发幂等、请求冲突、失效权限、版本/内容变化、HTN 混合会话目录变化、重启重建、审核恢复丢失 Proposal、Frozen Basis 及 Flag 组合。

运行目录为 `apps/agentOS`，Python 3.14；结果均为本轮实际执行。

| 命令 / 范围 | 实际结果 |
| --- | --- |
| `python -m pytest -q tests/components/planner/test_horizon.py` | 77 passed，32.40s；后续强化 SQLite 全库只读断言，单独复跑对应测试 1 passed，2.32s，并由最终全量再次覆盖 |
| `python -m pytest -q tests/components/planner/test_horizon.py tests/components/planner/test_htn.py tests/components/planner/test_htn_adversarial.py tests/components/planner/test_react_loop.py tests/components/planner/test_unified_actions.py` | 中间实现快照 169 passed，94.37s（当时 Horizon 64 项）；不代替最终全量 |
| `python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime` | 中间实现快照 638 passed，381.68s（当时 Horizon 69 项）；后续合同/审核完成证据及新增反例由最终全量覆盖 |
| `python -m pytest -q` | 首轮 1260 passed / 1 failed，411.86s；唯一失败为未修改的既有 20ms 流式活动计时测试，单独普通重跑亦复现 |
| 以下完整套件命令 | **最终 1261 passed / 0 failed**，405.49s；1184 基线 + 77 Horizon。仅既有 PyPDF2 弃用警告 1 项 |

```powershell
python -c "import ctypes, pytest; timer = ctypes.WinDLL('winmm'); assert timer.timeBeginPeriod(1) == 0; result = pytest.main(['-q']); timer.timeEndPeriod(1); raise SystemExit(result)"
```

`test_private_provider_activity_keeps_stream_alive_until_public_json_arrives` 的夹具每10ms输出活动，首事件窗口20ms。Windows 默认定时唤醒精度下发生超时；测试进程临时请求1ms定时分辨率后，单项 1 passed（0.60s），完整原套件也全绿。未改该测试、未放宽时限、未跳过失败用例、未修改 LLM Gateway；测试进程结束前恢复定时请求。普通默认环境的时间敏感失败仍如实保留，不宣称普通全量首轮通过。

最终 `git diff --check` 通过；原有测试文件未修改，架构门禁未降低。S01-04 仅4个修改文件 + 2个新增源码文件 + 1个新增测试文件 + 本记录，暂存区为空，HEAD 保持 S01-03 提交。

### 限制

成本/风险为确定性保守估算，未通过真实供应商或负载进行策略调参；资源观察只是绑定 Observation 时的快照。循环控制计划保守暂停 Horizon 选择，循环迭代仍由原 Runtime 决定。HTN 展开到全局 DAG 的验证与正式 Planning Commit 均不在本轮；没有 Scheduler 消费方或持久化 Proposal 权威。既有20ms流式测试对普通 Windows 定时环境敏感，以上计时环境条件应随验收结果保留。

### 独立代码级验收补充（2026-10-12）

独立验收依据实际 Diff、源码及先失败后修复的反例，确认并最小修复7类P1：完成输出/验证证据不足、编译依赖受节点输入顺序影响、观察与Run步骤映射不一致、蓝图控制屏障丢失、不支持的risk逸出异常、步骤级审核要求丢失，以及取消信号早于终态持久化（含最后策略读取期间的取消竞争）。保留原77项Horizon断言，仅为completed夹具补齐outputRef；新增20项独立对抗测试。未改共享Compiler、LLM Gateway、Scheduler、SemanticRevisionService或既有20ms用例。

最终定向Horizon/HTN/ReAct/Gateway **202 passed，97.29s**；扩大回归中间快照 **665 passed，264.40s**，最后取消检查由最终定向和完整套件覆盖。相同最终源码快照：默认Windows全量 **1280 passed / 1 failed，359.71s**；请求1ms定时分辨率的完整原套件 **1281 passed / 0 failed，384.29s**。两次全量各有1项既有PyPDF2弃用警告。默认失败仍是既有 `test_private_provider_activity_keeps_stream_alive_until_public_json_arrives`，未修改、跳过或放宽测试，未将1ms结果冒充默认环境通过。

结论 **CONDITIONAL**：本轮未发现未修复的Horizon P0/P1；默认Windows回归稳定性仍需单独处理。候选合同可按Proposal-only边界冻结，所有相关Flag保持默认关闭；不授权生产开启或执行提交。完整调用链、文件行号、可复现命令、性能边界和剩余风险见[独立代码级架构验收](PR-S01-规划协议与BoundedReAct-合并记录.md)。HEAD仍为 `ce1d67d117f678f211409fb4f47dee80fc24d37b`，本轮未提交、未Push、未部署、未升级业务数据库或修改正式ADR。

---

## 6. 原文｜PR-S01-04 独立代码级架构验收

<!-- 原始记录：PR-S01-04-独立代码级架构验收-2026-10-12.md -->

> 原文件 `PR-S01-04-独立代码级架构验收-2026-10-12.md` ｜ 2026-10-12 ｜ 独立代码级架构验收 ｜ 原文 13308 字节

结论：**CONDITIONAL（有条件通过）**。已确认并修复 7 类 P1，最终相关测试及请求 1ms 定时分辨率的全量通过；未发现未修复的 Horizon P0/P1 或写入正式计划、激活执行图的路径。条件在于默认 Windows 环境最终全量仍复现既有 20ms 流式计时失败，不能宣称默认环境全量通过。该条件不要求扩大 Horizon 权威；应单独解决默认环境回归稳定性，保留原测试目标与时限。

### 固定证据与边界

HEAD / S01-03 基线：`ce1d67d117f678f211409fb4f47dee80fc24d37b`，10 文件的正式本地提交。入场为 4 个 tracked 修改 + 4 个未跟踪文件，暂存区为空。完整 tracked binary Diff、Git 状态及所有入场文件 SHA-256 已固定在 `.tmp-tests/s01-04-audit/`；未将实施记录的结论作为证据。

本轮只修改已证实缺陷涉及的 Horizon 算法、合同、网关及 facade 装配；保留原测试断言，为 completed 测试输入补齐合法 outputRef，并新增 `test_horizon_audit.py` 20 项独立对抗测试。未修改共享 Topology Compiler、SemanticRevisionService、Scheduler、ACGLowerer、LLM Gateway 或既有 20ms 流式测试。

以下生产源码路径以 `apps/agentOS/src/` 为根；测试路径以 `apps/agentOS/tests/components/planner/` 为根。

### P1 反例及最小修复

| 类别 | 修复前的可复现行为 | 修复及证据位置 |
| --- | --- | --- |
| 完成证据不完整 | verification 节点 completed + commit/audit，但 report=None，仍满足 C 的前置；缺少 outputRef 的 completed A 也允许 B 入选 | `components/planner/horizon.py:111` 要求 outputRef/commit/audit；verification 能力必须明确 passed。`test_horizon_audit.py:12`、`:51`，均先实测失败再修复 |
| 隐式编译依赖受 tuple 顺序影响 | A/B + V1/V2 无显式全部推导边时，反转 nodes 改变能力绑定/终端连接依赖 | `horizon.py:73` 将节点按稳定 Key 排序后交给原 Compiler；显式关系保持 fixed，不改正式 TaskPlan。测试 `:23`；修复前真实失败 |
| 重开会话可接受不对应的观察 | 修改并重算 Observation 指纹，taskKey 与 Run TaskBinding 不符，新会话仍返回成功空 Horizon | `components/planner/unified_actions.py:610` 核对 Run/Mission、全部步骤、唯一 stepId 和完整 step/task 绑定。测试 `:36`、`:170`（缺失/重复/错 Run/坏绑定） |
| Runtime 控制被语义投影丢失 | 只看 TaskPlan.controlPolicies，IF 蓝图仍可把条件工作视为普通候选 | `unified_actions.py:637` 只读检测控制存在；`contracts/horizon.py:48` 的 controlBarrier 绑定进输入指纹，pending 工作保守 control_wait。测试 `:59` 使用真实 prepare_run 通过的 IF 图及冻结 Legacy Basis；不解释分支、不建立第二个图控制器 |
| 不支持的 risk 逸出异常 | TaskPlan 合同允许 metadata.risk 为对象，Horizon 用其作 dict key，抛 TypeError 而非协议拒绝 | `horizon.py:100` 检查字符串与已知枚举，返回 HORIZON_UNKNOWN_RISK。测试 `:192`，修复前真实 TypeError |
| 步骤级审核要求丢失 | Run step.reviewRequired=True、能力目录 requiresReview=False，Frontier 却显示不需审核 | `unified_actions.py:632` 从当前 Run 的实际步骤提取可信 reviewKeys；`horizon.py:142` 与目录审核要求取 OR，并绑定指纹。测试 `:202`、`:213`；后继窗口截断，模型不能提交 reviewKeys |
| 取消信号早于终态持久化 | Runtime 已发协作式取消信号，Run 行尚为 RUNNING；计算后仍能登记成功 receipt/journal；信号在最后一次策略读取期间到达时，早期检查也不足 | `unified_actions.py:475`、`:510` 计算前后读取取消信号，最后一次检查位于所有可阻塞读取之后；`runtime/workflow_runtime.py:2224` 注入只读 callback。测试 `:223`、`:243` 使用真实 Runtime 信号入口；两种竞争均先实测失败，修复后拒绝且无新缓存/登记 |

首次验证节点反例因不合法终端拓扑被 Compiler 拒绝；调整为合法 A→V→C、V/C 均为 verification 后才确认上述完成证据缺陷。未将夹具错误当成生产缺陷。IF 反例最终使用合法 Legacy 显式包路径；正式 Semantic 创建仍拒绝任意注入 ACG，原权威规则保持。

### 真实调用链与合同审计

`ExecutionRuntime._attach_react_loop` → `BoundedReActPlanningLoop.decide` → 严格 `PlannerLoopTurn/PlannerActionRequest` → Gateway 会话/预算/授权及世界 Fence → READ frontier / candidate_horizon 或 PROPOSE HorizonSelection → `AdaptiveHorizonSelector.frontier`（共享 Compiler）→ `propose`（确定性有界选择）→ 发布前再复核 → 会话内 registry/journal → `_to_feedback` → 下一轮结构化模型输出 → `_hand_off` 强制 wait → 原 RuntimePlanningCoordinator / RuntimePlanningApplication 的持久化审核屏障。

- `horizon.py:105` 起按真实观察分类。完成节点仅作为前置证据，永不重新选择；缺输出/收据/审核、未知或失败验证保持 unknown。running/retrying 为 active，失败、取消和 skipped 不满足前置。pending 若已有执行证据或不在 remainingStepIds 中也不被当作新工作。Run 等待审核、观察 completionBlockers、控制声明和资源 ready=False 分别保留屏障。
- 完成证据来源是既有 `runtime/planning_observation.py:21` 的 `_committed`：验证 output 的 Run/step 归属及不可变 commit，再验证 audit 决定归属/摘要，合法 retry 复用沿既有来源链回溯；`:57` 复核人工审核，`:65` 提取真实验证结果。Horizon 不是第二个执行收据审计器。持久层拒绝改写已存在的 audit/output/commit，冻结 Basis 每次 upsert 保持不可变（`support/stores/_policy.py:16`）。
- Compiler 的依赖完整进入 Frontier（声明 + 能力绑定 + 终端连接）。`contracts/horizon.py:57` 仅检查闭合引用及未满足依赖一致性；`:99` 检查分区、预算及全部内/跨窗口边。它们不做 DAG 编译、修复、GraphVersion 提交或控制路由。
- `horizon.py:163` 的策略按风险、直接后继数、成本、Key 排序，逐层考虑闭合前置；风险/成本/候选预算共同限制，高风险隔离，可信审核要求截断未来工作。已完成前置或已入选前置才允许消费者进入窗口；readyKeys 只认可真实已完成前置。共享前置、多层依赖、非闭合子集、跳过、审核与隐式依赖反例均覆盖。
- 风险取任务与可信能力目录最大值，成本只取至少1/能力数量/Workset估算单元的最大值，始终是规划估计。资源投影明确 observed_ready / unknown / not_ready，reservationStatus 固定 not_reserved；readyKeys 不表示资源已预留或任务可激活。
- 模型输入仅允许 kind/inputFingerprint/selectedKeys；预算、状态、执行身份、权限、控制与审核真值均不能由模型提供。选择必须是服务端重新计算集合的依赖闭合子集；不接受 HTN 内存展开作为输入。混合 HTN 会话仍受原 catalog revision Fence。

### 并发、权威与恢复

`unified_actions.py:365` 起所有操作在会话锁下运行；同 requestRef 同指纹复用、不同载荷拒绝。计算前、缓存复用前及结果返回后核查 Flag、策略/能力目录、授权、Run 状态/取消信号、Observation、PlanVersion、同版本 TaskPlan/图/绑定/执行输入内容及完整步骤映射；TTL 与完整动作时间包含 provider 和复核。过期、撤权、取消及迟到结果不新增成功 registry/journal。已有历史成功数据即使仍在内存中也不得复用。

`unified_actions.py:453` 后的登记仅写会话对象，无 WorkflowStore/值/收据/图写入。真实 SQLite 集成逐表对比所有测试库，包含 Run、outbox、audit、commit/value，确认工具查询及登记零持久变更。

`components/planner/react_loop.py:218` 禁止 Horizon 会话交付 continue/recover/revise/complete/abort；plan_revision 双向互斥。`runtime/planning_application.py:103` 的 wait 沿原链存规划审核 checkpoint，只有 revise 才进入 SemanticRevisionService；Horizon 不产生这种决策。Scheduler/Lowerer/语义修订模块无 Horizon 消费入口。

重启丢失 session/Proposal 后，旧 sessionId 明确 UNKNOWN_SESSION，只能从可信正式输入重算。持久化 checkpoint 不带 Horizon 执行承诺；普通批准仍按 `runtime/review.py:68` 检查主体、checkpoint 与既有收据，然后恢复原图。真实测试证明 Proposal 丢失后只执行原 A，无新 Run、无图版本或正式计划变化。恢复服务只重驱动原 recover/revise，不将 wait 提案转成执行图。

### 性能边界

原输入最多256节点、1024声明关系、300k字符，Compiler 返回最多4096依赖；不是全系统规模或实时性承诺。Horizon 自身约 O(VE + V²(D + logV))；内容/策略/会话 Fence 另有与 Run 状态及目录序列化大小有关的成本。共享 Compiler 的能力绑定搜索已有512状态上限，但其预处理、图校验和同步调用没有强制抢占保证。

每次非缓存 frontier/horizon 查询或选择提案只调用一次共享 Compiler；query 后 PROPOSE 有意重新编译验证，不消费旧读结果。缓存重放不调用 Compiler，但重新检查有效性。测试 `test_horizon_audit.py:129` 证明输入超限在 Compiler 前拒绝；同步 Compiler 跨过截止期后结果丢弃。单动作默认5s、会话和 ReAct 的240s总截止期共同防迟到登记，不能中断已经在执行的同步 Python/SQLite 计算。

### 实测结果

全部命令在 `apps/agentOS`、Python 3.14 运行；Runtime 测试只用临时 SQLite。最终测试开始时固定源码 SHA-256，后续复核无漂移。

| 命令 / 快照 | 结果 |
| --- | --- |
| 初始3个已校正最小反例 | 3 failed，2.13s；后续 outputRef、控制、risk、reviewRequired、真实取消信号及最后策略读取期间的取消竞争各自先实测失败；共7类、9个最小失败反例 |
| `python -m pytest -q tests/components/planner/test_horizon.py tests/components/planner/test_horizon_audit.py tests/components/planner/test_htn.py tests/components/planner/test_htn_adversarial.py tests/components/planner/test_react_loop.py tests/components/planner/test_unified_actions.py --tb=short` | 最终 **202 passed**，97.29s：77 Horizon + 20 独立对抗 + 105 HTN/ReAct/Gateway |
| `python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short` | 中间快照 **665 passed**，264.40s；随后补最后策略读取的取消检查及1个反例，最终定向及双环境完整套件覆盖该改动，未将665标为最终快照 |
| `python -m pytest -q --tb=short` | 最终默认 Windows：**1280 passed / 1 failed / 1 warning**，359.71s；唯一失败为下述既有20ms测试 |
| 1ms 定时完整原套件（下方命令） | 同一最终源码/测试快照：**1281 passed / 0 failed / 1 warning**，384.29s；1184 S01-03基线 + 77 Horizon + 20独立对抗 |

```powershell
python -c "import ctypes, pytest; timer = ctypes.WinDLL('winmm'); assert timer.timeBeginPeriod(1) == 0; result = pytest.main(['-q', '--tb=short']); timer.timeEndPeriod(1); raise SystemExit(result)"
```

最终默认环境失败：`tests/adapters/test_model_runtime_streaming.py::test_private_provider_activity_keeps_stream_alive_until_public_json_arrives`。夹具在`:90`每10ms发活动，TTFT=20ms、idle=30ms、total=200ms；最终运行在 `src/adapters/model_runtime.py:538` 超时。该用例在实施阶段也曾失败；本轮较早默认全量分别1279/1280通过，表明它具有环境/调度敏感性，而非默认环境保证通过。1ms对照不能替代默认环境结果，也未证明计时失败的所有根因。该测试、生产时限及 LLM Gateway 完全未修改，未跳过任何用例；1ms请求只用于测试进程并恢复。唯一其他警告是既有 PyPDF2 弃用警告。

### 剩余风险及 S01 冻结建议

建议冻结 S01 的候选合同与受控工具边界，三个 Flag 默认关闭；Horizon 保持 Proposal-only，不接入 Scheduler 或普通审核批准的图替换路径。冻结不等于生产开启批准，也不等于全局 DAG 提交、资源承诺或已完成执行前缀问题已经解决。

剩余限制：同步计算不可抢占；风险/成本启发式未做真实模型/负载调参；资源就绪仅是 Observation 时刻的观察；含控制节点的图保守等待（包括已解析部分控制的图）；HTN 全局接入未实现；发布前复核不是持久化 Planning CAS，后续正式消费仍需重新核验版本、权限和依赖，不能信任过期内存回执；既有20ms测试仍可能受 Windows 调度影响。未发现需要提前实施 S02/S03 才能完成本轮候选边界修复的阻塞。

本轮不 Commit、不 Push、不部署、不升级业务数据库，不修改正式 ADR。

收口状态：HEAD 保持 S01-03 基线，暂存区为空；4个 tracked 修改 + 6个未跟踪文件（包含本报告及实施记录）。最终8个代码/测试文件与全量开始前 SHA-256 快照一致；文档仅在测试结束后补齐结论与结果。

---

## 附录：来源清单与合并说明

| # | 原文件 | 日期 | 性质 | 原文大小 |
|---:|---|---|---|---:|
| 1 | `PR-S01-01-统一Planner最小动作协议实施记录-2026-10-11.md` | 2026-10-11 | 实施记录 | 8820 字节 |
| 2 | `PR-S01-02-BoundedReActPlanningLoop实施记录-2026-10-11.md` | 2026-10-11 | 实施记录 | 10109 字节 |
| 3 | `PR-S01-03-HTNMethodSelection实施记录-2026-10-12.md` | 2026-10-12 | 实施记录 | 10739 字节 |
| 4 | `PR-S01-03-独立代码级架构验收-2026-10-12.md` | 2026-10-12 | 独立代码级架构验收 | 12457 字节 |
| 5 | `PR-S01-04-AdaptiveHorizonProposal实施记录-2026-10-12.md` | 2026-10-12 | 实施记录 | 10248 字节 |
| 6 | `PR-S01-04-独立代码级架构验收-2026-10-12.md` | 2026-10-12 | 独立代码级架构验收 | 13308 字节 |

> **合并规则**：正文逐字保留，仅做两类机械处理：(1) 标题层级下移一级，原文 H1 由本节标题替代；(2) 指向已合并 / 已归档文档的相对链接改写为新文件名。结论、数字、命令与代码块未改动。
>
> **完整性校验**：合并时对每篇原文做归一化比对（忽略标题层级与链接目标），本篇 6 篇全部一致。
>
> **恢复原件**：原文件已从当前目录移除，完整内容保留在 Git 历史中。整理提交前用 `git checkout HEAD -- "docs/开发记录/<原文件名>"`；提交后用 `git checkout HEAD~1 -- "docs/开发记录/<原文件名>"`。

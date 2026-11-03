# PR-S02 规划提交与图变更：实施与验收合并记录

> **文档性质**：阶段证据合并稿——实施记录 3 篇 + 独立代码级架构验收 3 篇
>
> **覆盖时间**：2026-10-13 ~ 2026-10-15
>
> **当前定位**：规划提交权威、持久化与图修订接受链；S03 的前置基线
>
> **合并日期**：2026-10-30

## 0. 合并说明与导读

本册把 **S02 阶段（2026-10-13 ~ 2026-10-15）** 的 6 篇记录合并为一篇：3 篇实施记录 + 3 篇独立代码级架构验收。正文逐字保留原文，仅做两类机械处理：标题层级下移一级、指向已合并文档的相对链接改写；结论、数字、命令与代码块未改动。来源清单见文末附录。

### 0.1 这一阶段在解决什么

S01 解决了「模型只能提议」，S02 解决「**Proposal 如何变成可信、可持久、可审计的承诺**」。仍是三步递进：

1. **S02-01 Planning Commit Authority**：先做独立的内存接受权威，把提交从模型手里收回到 Service，验证接受链与幂等语义。
2. **S02-02 Durable Planning Commit**：把接受事实落到 SQLite——来源合同、CAS、接受记录与 outbox 在同一 `BEGIN IMMEDIATE` 内提交，并接入首次规划与 revise。
3. **S02-03 Graph Revision Commit + Safe-Cut**：把已接受的规划提交变成最小无控制 DAG 的图修订，并用 Safe-Cut 把「哪些前缀仍可信」纳入同一账本。

### 0.2 一页结论

| 阶段 | 实施记录结论 | 独立架构验收 | 最终判定 |
|---|---|---|---|
| S02-01 | 独立内存实现，未接生产、未提交 | ACCEPT（限已声明内存权威范围） | 通过；修复 1 类 P1（guard 退出未回滚），317 passed |
| S02-02 | 最终全量 1356 passed，等待验收 | ACCEPT（仅修复后快照），含 Freeze 冻结验证 | 通过；修复 6 类 P1，1380 passed；原始 `66249bbe` 不可原样冻结 |
| S02-03 | 最小 DAG 自测完成，控制图保守拒绝 | ACCEPT，可作 S03 前置基线 | 通过；修复 7 类 P1，新增 50 项对抗，1460 passed |

### 0.3 贯穿全阶段的不变量

- **唯一接受权威**：Plan 的接受只能经 `PlanningCommitService` / 持久化 Store，模型与 Provider 不持提交权。
- **版本 CAS**：`expectedCommitmentRevision` + `parentCommitId` 构成提交链；拒绝不消耗版本，同 Key 同请求幂等重放。
- **接受 ≠ 物化**：状态固定为 `COMMITTED_NOT_MATERIALIZED`，历史 Receipt 不是执行许可。
- **事务边界**：CAS 校验、接受记录、outbox 在同一 `BEGIN IMMEDIATE` 内提交，避免部分提交。
- **Safe-Cut fail-closed**：无法证明可信的前缀一律拒绝，控制图统一 `CONTROL_BARRIER_BLOCKED`。
- **重验而非信任历史**：S03 必须重新验证来源，不能凭历史 `ACCEPTED` / `PROVEN` 直接放行。

### 0.4 明确未完成与下一阶段入口

- **跨 DB / 多实例仍为 UNVERIFIED**：Workflow SQLite、Identity、Registry 之间没有联合 CAS 或分布式事务。
- **outbox 无消费方**，deferred Run 不自动激活；S02-02 的接受不会自动物化。
- **控制图未开放**：S02-03 只覆盖最小无控制 DAG，控制屏障一律拒绝。
- 全库写锁时长、索引与上限登记为 P2，无硬时限保证。
- 下一阶段：S03 物化、激活与 Checkpoint/Identity 交接（见 [`PR-S03-01-图物化与回归门禁-合并记录.md`](PR-S03-01-图物化与回归门禁-合并记录.md)）。

### 0.5 阅读建议

先读 S02-01 建立「Service 只有接受权」的直觉，再读 S02-02 看持久化如何把这个权威落到事务里，最后读 S02-03 看图的修订如何复用同一账本。三篇验收都列出了独立复现的反例，是判断「提交权威是否真的收口」的主要材料。

## 篇目与阅读顺序

1. **PR-S02-01：Planning Commit Authority** — 实施记录，2026-10-13 — 原文件 `PR-S02-01-PlanningCommitAuthority实施记录-2026-10-13.md`
2. **S02-01 代码级验收** — 独立代码级架构验收，2026-10-13 — 原文件 `PR-S02-01-独立代码级验收-2026-10-13.md`
3. **PR-S02-02：Durable Planning Commit 与首次规划 / revise 接入** — 实施记录，2026-10-14 — 原文件 `PR-S02-02-DurablePlanningCommit实施记录-2026-10-14.md`
4. **PR-S02-02 Durable Planning Commit 独立代码级架构验收** — 独立验收（含 Freeze 冻结验证），2026-10-14 — 原文件 `PR-S02-02-独立代码级架构验收-2026-10-14.md`
5. **PR-S02-03 Graph Revision Commit 与 Safe-Cut** — 实施记录，2026-10-14 — 原文件 `PR-S02-03-GraphRevisionCommit实施记录-2026-10-14.md`
6. **PR-S02-03 Graph Revision Commit 独立代码级架构验收** — 独立代码级架构验收，2026-10-15 — 原文件 `PR-S02-03-独立代码级架构验收-2026-10-15.md`

---

## 1. 原文｜PR-S02-01：Planning Commit Authority

<!-- 原始记录：PR-S02-01-PlanningCommitAuthority实施记录-2026-10-13.md -->

> 原文件 `PR-S02-01-PlanningCommitAuthority实施记录-2026-10-13.md` ｜ 2026-10-13 ｜ 实施记录 ｜ 原文 7374 字节

状态：独立内存实现，未接入生产链，保持未提交。HEAD 为 S01-03 `ce1d67d117f678f211409fb4f47dee80fc24d37b`；入场已有未提交 S01-04，本轮未修改其8个代码/测试文件，SHA-256复核无漂移。未Commit、Push、部署、升级数据库或修改ADR。

### 范围与合同

新增 `src/contracts/planning_commit.py`、`src/components/planner/planning_commit.py`、`tests/components/planner/test_planning_commit.py` 及本记录。没有增加公开API、Feature Flag、Runtime挂接、数据库表或第二份TaskPlan/Graph/Run。

合同使用 `extra=forbid`、`frozen=True`，保留snake_case及既有camelCase别名约定：

- `FrozenPlanningSources`：Mission/Revision、Observation ID及指纹、PlanVersion、GraphVersion、Strategy指纹；正整数版本拒绝bool，指纹为64位小写SHA-256。仅支持已有正式规划上下文；首次规划无Observation/Graph时的来源合同留待S02-02明确，当前不伪造0版本或观察。
- `PlanningCommitRequest`：Proposal ID/type/指纹、Sources、RequestedScope、IdempotencyKey。Scope为1–256个唯一语义Key，排序规范化；执行身份、资源、调度状态和permission等额外字段均拒绝。它是可信应用侧请求，不注册为模型结构化输出。
- `PlanningCommitReceipt`：ACCEPTED / REJECTED / IDEMPOTENT_REPLAY。接受及重放必须携带Commit身份和Revision；拒绝不得伪造接受身份。
- `PlanningCommitRejection`：结构化code/reason，包括要求的8类以及STALE_OBSERVATION、STALE_STRATEGY。
- `PlanningCommitRecord`：要求字段之外保存完整Sources、Proposal ID/type、Scope及规范化Request指纹，以免回放丢失接受依据。sourceRevision明确为Mission源版本；status固定ACCEPTED；不保存第二套计划正文或执行对象。

### 调用及信任边界

`trusted application request → accept → revalidate contract → store lock → provider planning_guard → authorize → idempotency check → validate_sources → trusted proposal validation → recheck sources/authorization/idempotency → append immutable record → receipt`。

`CurrentPlanningStateProvider`提供`get_current_sources(mission_id)`的单一一致快照，替代独立采样三个版本的方法；还必须提供`planning_guard`、`authorize`和`validate_proposal`。Provider必须在guard内保护授权、Sources及候选注册表，依据真实候选证明ID/type/内容/来源绑定、Scope、已编译依赖闭合和控制/审核边界。权限来自注入的可信调用上下文，不来自request。无默认放行Provider，也未提供生产Runtime适配器。

服务只协调接受，不重新编译拓扑、不新增依赖算法、不凭合法JSON及相等版本认定Proposal可信。本轮单测Provider使用测试候选注册表；真实HTN/Horizon/初始计划及revise适配应在S02-02复用现有验证权威。

`validate_sources()`是只读预检；`accept()`在保护区内再次验证Mission、Plan、Graph、Observation和Strategy。可信Provider失败或guard退出失败不留下新成功记录，错误响应不暴露异常正文。锁顺序固定为Commit Store → Provider，生产适配器不得反向获取。

### 内存登记与幂等

InMemoryPlanningCommitStore支持按commitId、idempotencyKey及Mission最新记录查询；多Service共享同一Store时由RLock串行化接受、Revision分配和查询。commitmentRevision按Mission递增，与PlanVersion/GraphVersion/RuntimeRevision分开；parentCommitId指向该Mission前一接受记录。拒绝不消耗Key或Revision。

同Key、同规范化请求返回原Commit的IDEMPOTENT_REPLAY；不仅不同Proposal指纹冲突，同指纹但Scope/Sources/ID/type改变也返回DUPLICATE_CONFLICT。Scope顺序变化不算内容变化。历史接受之后Sources推进不改变历史事实，重放仅重新校验当前授权，并不声明旧Proposal仍可被执行；撤权则拒绝回执重放。历史记录不删除。

幂等Key在Store内为全局命名空间。不同Key即使引用同一Proposal也视为新接受请求，不做内容去重。单Store事务内的暂存记录在guard退出失败时回滚全部索引，其他线程不能观察半接受状态。RLock允许同线程Provider回调重入共享Store的服务，因此接受前再次检查幂等绑定；重入期间已接受的同内容请求返回原回执，不同内容返回冲突，不覆盖索引。

### 验证

在`apps/agentOS`、系统Python 3.14执行：

| 命令 | 结果 |
| --- | --- |
| `python -m pytest -q tests/components/planner/test_planning_commit.py --tb=short` | 45 passed，5.01s |
| `python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short` | 711 passed，917.47s；补最后两项重入反例及幂等复核前的快照 |
| `python -m pytest -q tests/components/planner/test_planning_commit.py -k reentrant --tb=short` | 修复前2 failed，45 deselected，5.90s；同线程回调重入导致第二次ACCEPTED并覆盖Key绑定 |
| `python -m pytest -q tests/components/planner/test_planning_commit.py tests/contracts tests/architecture --tb=short` | 最终114 passed，12.30s；含完整47项Planning Commit测试及67项合同/架构测试 |

首轮44项通过、1项fixture setup error：真实Runtime fixture遗漏其runtime_boundary依赖导入。补齐测试导入后45项通过，没有跳过测试或改变断言目标。

覆盖请求/回执合同、记录不可变性、幂等内容冲突、所有来源Fence、伪造候选及扩大Scope、非闭合范围、控制阻塞、撤权、Provider失败、guard退出失败、验证中状态改变、Mission父承诺、并发重复与不同请求、同线程回调重入、共享Store和重启丢失内存语义。真实Runtime集成只使用临时SQLite，对比全部测试数据库（包括TaskPlan身份投影、Run、ACG、收据、Outbox等）及Agent调用，接受/重放均无变化。

最后修改仅涉及新接受服务的幂等复核及其两项反例，最终运行覆盖完整新增组件、合同门禁、架构门禁及真实Runtime零变更测试；未重复与该修改无调用关系的整个Runtime目录。没有运行AgentOS全量套件，不将扩大回归称为全量。既有测试、门禁和计时条件均未修改。`git diff --check`通过，暂存区为空。

### 限制与后续

本轮未挂接PlannerActionGateway、ReAct、RuntimePlanningApplication或SemanticRevisionService；未创建Run、绑定资源、调度节点或激活图。

记录仅存进程内；重启后ID及幂等索引丢失，新Store可重新从Revision 1接受相同请求。不同Store或不同进程不共享承诺版本，不具备durable authority或多实例CAS保证。接生产前需明确持久化、授权及安全边界的真实Provider、首次规划来源、候选内容可恢复引用和Outbox对账。当前记录只有候选引用及摘要，不能独立恢复Proposal正文，也不能作为执行令牌。

接受期间不执行LLM、拓扑求解或Runtime操作；Provider应只做有界可信校验。内存Store无容量/TTL策略；全Store锁优先保证最小实现的一致性，尚未优化跨Mission吞吐，也不提供硬截止期。S02-02接入时应保持Proposal ≠ Commit、Commit ≠ Execution、Commit ≠ Graph Activation。

---

## 2. 原文｜S02-01 代码级验收

<!-- 原始记录：PR-S02-01-独立代码级验收-2026-10-13.md -->

> 原文件 `PR-S02-01-独立代码级验收-2026-10-13.md` ｜ 2026-10-13 ｜ 独立代码级架构验收 ｜ 原文 2195 字节

结论：ACCEPT（限已声明的独立内存权威范围）。依据重新读取合同、服务、测试及Git状态，未直接采信实施记录；不代表生产Runtime接入或durable authority验收。

发现并修复1个P1：`PlanningCommitService.accept`在Provider guard退出抛出KeyboardInterrupt时未回滚已追加记录。新增`test_interrupted_guard_exit_does_not_publish_acceptance`先运行得到1 failed / 47 deselected（5.97s），随后将回滚保护扩展到BaseException，并重新传播中断；异常回执逻辑保持不变。

最终实测，在apps/agentOS运行：

`python -m pytest -q tests/components/planner/test_planning_commit.py tests/components/planner/test_horizon.py tests/components/planner/test_horizon_audit.py tests/components/planner/test_htn.py tests/components/planner/test_htn_adversarial.py tests/components/planner/test_react_loop.py tests/components/planner/test_unified_actions.py tests/contracts tests/architecture --tb=short`

317 passed，213.43s，包含48项Commit测试、202项S01相关测试及67项合同/架构测试。没有修改旧测试或计时条件。S01-04最终8个代码/测试文件与原验收SHA-256一致；原默认Windows全量20ms计时失败记录仍保留，不宣称该条件消失。

检查成立：模型无法通过Request提交执行身份/权限；Sources必须由可信Provider复核；同Key内容冲突拒绝；完整请求规范化绑定；Store锁串行化并发并在发布前处理回调重入；拒绝不消耗版本；按Mission父承诺顺序；Guard失败回滚；真实临时SQLite及Agent调用零变更。没有WorkflowStore、SemanticRevisionService、Scheduler、Executor写入通道。

边界：Provider必须真实证明来源和候选合法性，不允许默认放行适配器；纯内存实现重启不保留幂等或版本；未交付生产Provider、持久化候选、Commit CAS或图激活。这些属于S02-02及后续S03。源合同当前要求已有Plan/Graph/Observation，首次规划须在后续明确空来源语义。

本阶段完成后按用户授权分别固定S01-04和S02-01本地提交，不Push、不部署、不操作生产数据库。

---

## 3. 原文｜PR-S02-02：Durable Planning Commit 与首次规划 / revise 接入

<!-- 原始记录：PR-S02-02-DurablePlanningCommit实施记录-2026-10-14.md -->

> 原文件 `PR-S02-02-DurablePlanningCommit实施记录-2026-10-14.md` ｜ 2026-10-14 ｜ 实施记录 ｜ 原文 7942 字节

状态：实施完成，最终全量通过；根据后续用户授权整理提交并推送。尚未进行独立架构验收。

### 基线

- S01-04 本地提交：`59f949e12d5da261d80b75aacb89a5842c52c3e8`。
- S02-01 本地提交 / 当前 HEAD：`26764272cb4f3f65bf6673458cd1468111d33d8c`。
- 固定基线前补测 S02-01 中断回滚：provider guard 退出抛出 `KeyboardInterrupt` 时撤销临时记录并重新抛出中断。联合基线回归 317 passed（213.43s）。S01-04 原 Windows 默认计时环境的 CONDITIONAL 记录保留。

### 合同及持久化

`FrozenPlanningSources.sourceKind` 区分 initial/runtime。首次规划尚无正式 Plan/Graph/Observation，相应四字段必须为空；runtime 相应字段必须完整。来源均由 Runtime adapter 捕获，模型无法提交接受请求或执行身份。`expectedCommitmentRevision` 用于 Mission 接受头的 CAS，版本独立于 TaskPlan.planVersion。

Record 复用原 `TaskPlan` / `TaskPlanPatch` 保存原始候选内容及校验摘要，不新增任务/图/Run 合同。状态为 ACCEPTED，物化状态固定 `COMMITTED_NOT_MATERIALIZED`。同 key 的请求全字段摘要绑定；相同请求重放历史 receipt，不同内容或来源冲突拒绝。历史 receipt 不作为当前执行许可。

`SQLitePlanningCommitStore` 使用现有 Workflow SQLite 文件，仅新增 planning_commit_schema、planning_commit_records、planning_commit_outbox。`BEGIN IMMEDIATE` 内接受头读取、CAS、记录和 outbox 原子提交；Mission+revision 唯一约束及跨连接写锁防止双接受。故障回滚不留下成功记录或事件。读取重新验证候选摘要与索引身份。

构造器使用 mode=rw，既不创建 DB，也不自动升级。`upgrade_schema()` 是显式管理入口，本轮只在测试临时目录调用；业务数据库未升级。没有 outbox 消费、激活、调度或资源绑定逻辑。

### 接受链与权威隔离

配置入口是 `ExecutionRuntime(planning_commit_store=...)` / `enable_planning_commit(store)`，默认不配置，未新增环境 Feature Flag。ledger 必须与 Runtime Workflow store 指向同一 SQLite 文件。

- 首次 ACG 规划：prepare_run 保留既有 Run 创建权威并冻结 Basis，改为 deferred、持久化 planningCommitRequired。随后独立生成 L1/L2 语义候选，重复校验来源后接受。原 ACGLowerer、绑定与图物化路径不进入；Run 继续停留 deferred。
- Runtime revise：原结构化 RuntimePlanningDecision / TaskPlanPatch → 现有决策绑定验证 → Commit 接受 → 普通 wait → 原 RuntimePlanningApplication 保存审核屏障。决策在持久化 decided 前转换，恢复不会把 revise 当成替换执行指令。
- 直接 apply_semantic_patch：在 opt-in 模式返回 Commit receipt，既不调用 SemanticRevisionService，也不创建 replacement Run。
- 恢复入口另有同一决策 gate。接受后 checkpoint 失败时先完成已持久化 decided-wait 屏障，再刷新易变 observation；不会重新规划形成第二份承诺。
- 持久化标记存在而权威缺失时，执行与 revise 均停止。普通审核批准只能恢复原图，不采用接受候选。

Commit 服务本身只写 ledger/outbox。Run 模式标记、runtimeRevision、wait 审核屏障属于既有 Runtime 编排操作，必须与“接受不写正式计划/图/执行收据”的保证区分。

### 可信校验

Run lock 在 ledger 事务之前取得，provider 不反向取得 Run lock。事务内读取正式 Mission revision、Run 的 Basis/TaskPlan/Graph/步骤/收据引用/输入/冻结 scope；来源指纹另包含能力目录与 Identity 最新 TaskPlan snapshot。接受前后校验来源及可信调用方读写权限、Mission ACTIVE、取消状态。

仅支持完整 initial_plan 与 plan_revision；HTN/Horizon 不被隐式采用。局部 scope 拒绝。正式 Basis 缺失或漂移、过期 Observation/Plan/Graph/接受头、权限撤销、活跃任务拒绝。观察必须覆盖实际 Run 每个步骤，状态与绑定一致。

复用 `apply_task_plan_patch` / `validate_task_plan_for_execution` 的现有 Topology Compiler；没有第二个 DAG 编译器。原始候选字符上限 300000，最终节点最多 256、关系最多 1024，修订进入编译前有输入上限。已开始/完成/失败等非 pending 节点及其父级不可修改；pending 但已有 attempt、输出、时间戳或收据引用亦受保护。替换不得减少来源、验收、能力或约束；新增任务必须继承 Frozen Mission 约束，Workset 来源和冻结能力 scope 重新验证。

控制图/控制策略保守拒绝，等待后续 safe-cut 设计。本轮不实现 S03，不改 SemanticRevisionService、Scheduler、Executor 或 ACGLowerer 的覆盖规则。

### 实测

工作目录：`apps/agentOS`。以下均为实际运行，未跳过或放宽已有用例。

- `python -m pytest -q tests/components/planner/test_planning_commit.py tests/components/planner/test_planning_commit_runtime.py tests/contracts tests/architecture --tb=short`：140 passed，13.27s（随后补充控制策略测试）。
- `python -m pytest -q tests/components/planner/test_planning_commit_runtime.py --tb=short`：26 passed，13.67s（控制策略反例补入后的快照）。
- 补充 worker 竞争反例及修复后，重跑 Commit + Runtime Commit + contracts + architecture 同一命令：142 passed，24.75s；新增集此时为 27 项。
- `python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short`：739 passed，252.79s；此运行收集后新增控制策略反例，由上述 26 项定向测试及随后全量覆盖。
- 修复 worker 竞争前启动的 `python -m pytest -q --tb=short`：1355 passed，1 个 PyPDF2 弃用警告，280.26s，Windows 默认定时环境，未请求 1ms；该结果是中间快照，不能代替最终代码全量验证。
- 最终代码重新运行 `python -m pytest -q --tb=short`：**1356 passed / 0 failed**，1 个 PyPDF2 弃用警告，285.32s（4:45）。Windows 默认定时环境，未请求 1ms；包括最终 27 项新增集成测试及既有流式计时用例。本次通过不否定 S01-04 已登记的默认 Windows 20ms 测试波动。
- 最后一次返回类型注解修正后补跑 `python -m pytest -q tests/components/planner/test_planning_commit_runtime.py tests/architecture --tb=short`：41 passed，18.70s；随后 worker 竞争修复由 142 项及最终全量覆盖。
- 新增测试使用真实临时 SQLite、Runtime/语义服务、原 TaskPlan/ACG 合同与原审核/恢复入口；不调用真实 LLM 供应商。
- 故障注入复现接受后 checkpoint 失败导致第二个 Commit；修复后同一 outbox 仅一条、无 Agent 执行、恢复到 WAITING_REVIEW。所有已有测试保留。
- 首次接受返回后的 worker 旧快照覆盖操作员输入：新增反例先得到 1 failed / 26 deselected（1.69s），随后 opt-in worker 直接返回持久化最新 Run，不再保存旧快照或刷新无关 Identity outbox。最终测试结果见后续快照。

### 限制与下一阶段

尚无应用装配默认接入、业务 DB 升级、前端 Commit 查询接口或 outbox 消费。首次接受后 deferred Run 不自动完成/激活，等待后续物化阶段。HTN/Horizon 的 durable 接受、部分窗口、安全控制图修订均不在本轮。

Identity snapshot 位于独立数据库，读取摘要双检不能承诺跨数据库原子性；后续物化必须再次验证相关正式来源并执行对应 CAS。当前同步拓扑验证具有输入上限，但没有可抢占硬截止期。单进程 Runtime 生命周期锁仍是既有前提；未声明跨实例完整执行隔离。

实施阶段未提交或推送；后续用户明确授权本轮提交并推送。未部署、未升级业务数据库、未修改正式 ADR。

---

## 4. 原文｜PR-S02-02 Durable Planning Commit 独立代码级架构验收

<!-- 原始记录：PR-S02-02-独立代码级架构验收-2026-10-14.md -->

> 原文件 `PR-S02-02-独立代码级架构验收-2026-10-14.md` ｜ 2026-10-14 ｜ 独立验收（含 Freeze 冻结验证） ｜ 原文 20004 字节

最终等级：**ACCEPT（仅针对修复后的工作区快照）**。六类已证实 P1 均已解决，无未解决 P0/P1；阶段目标成立，可冻结为 S02-03 的代码基线。已推送的原始 `66249bbe` 不能原样冻结，冻结必须包含本轮未提交修复。本报告依据本轮重新读取的源码及实际实验，不采用实施记录自述作为证明。

### 1. 基线与范围

入场 HEAD / GitHub mirror master：`66249bbe97db3f43854d471402e9663e3272e157`；父提交 S02-01：`26764272cb4f3f65bf6673458cd1468111d33d8c`。本地工作区、暂存区均为空，无后续改动。重新检查远端 ref 与父子关系；没有 fetch/merge/commit/push 操作。

S02-02 原提交完整范围为 8 文件、1250 插入 / 17 删除：contracts/planning_commit.py、components/planner/planning_commit.py、support/stores/planning_commit_store.py、runtime/planning_commit.py、runtime/planning_loop.py、runtime/workflow_runtime.py、tests/components/planner/test_planning_commit_runtime.py，以及实施记录。已读取 S02-01 两份记录；旧记录的测试计数只作为历史材料，未当成本轮测试。

本轮最小修复范围：

- `apps/agentOS/src/runtime/planning_commit.py`：读取执行收据、验证正式来源一致性、审核屏障、编译后的已执行前缀保护。
- `apps/agentOS/src/runtime/workflow_runtime.py`：修复 accepted-before-decided 恢复窗口及新输入与等待恢复的竞争。
- `apps/agentOS/src/support/stores/sqlite_workflow_store.py`：3 行不可逆 Planning Commit 模式 Fence，保护每次既有 Run upsert。
- `apps/agentOS/tests/components/planner/test_planning_commit_runtime.py`：原“未标记初始 Run”反例改用测试临时 DB 的直接 SQL 构造损坏输入；生产 save_run 现在拒绝去掉模式标记。原拒绝目标与断言保持不变。
- 新增 `apps/agentOS/tests/components/planner/test_planning_commit_audit.py`：24 项对抗测试。
- 新增本报告。没有修改其他业务模块、正式 ADR、Schema migration 或生产装配。

最终测试源码快照（10 个 S02 合同/服务/存储/Runtime/测试文件，路径+逐文件 SHA-256 清单的 SHA-256）：`49ea14e0e411fbe2c49de1bd6972f0966fa3114f5f997a240743c821c519bd13`。该清单包含本轮 SQLiteWorkflowStore Fence 和新对抗测试；文档不参与源码摘要。最终回归期间不再变更源码。

### 2. 真实入口和权威

1. `workflow_runtime.py:619` prepare_run 在显式配置下选择 deferred，并在原 Run 创建链写入 planningCommitRequired；原链仍负责创建 Run、冻结 Basis 与 scope。这不是 Commit 服务创建 Run。
2. `runtime/planning_commit.py:338` accept_initial：Run 锁内授权并捕获 Sources/接受头 → 释放锁执行既有 L1/L2 → 绑定 Frozen Basis/约束并纯解析 TaskPlan snapshot version → 重新取得 Run 锁 → PlanningCommitService.accept。没有 L3、ACGLowerer、资源绑定或正式 TaskPlan snapshot 写入。
3. `workflow_runtime.py:1151` decision_gate：真实 RuntimePlanningDecision/TaskPlanPatch → 原 decision binding validation → 接受服务 → plain wait。Coordinator 在保存 decided 前执行 gate（planning_loop.py:135）；最终仍由既有 RuntimePlanningApplication 保存 wait/checkpoint/review。
4. `workflow_runtime.py:2201` apply_semantic_patch 在显式配置或持久模式下返回 Commit receipt。SemanticRevisionService 及 replacement Run 路径只保留在原默认兼容分支。
5. `workflow_runtime.py:1175` 从原 Observation 的 durable idempotency key / proposal identity 恢复接受后的 plain wait；它使用历史事实，不重新接受候选或取得执行许可。authority 缺失时执行入口停止，正常存储不能移除模式标记。

仓库搜索 PlanningCommitService 与 ledger 表写入：生产接受只有 runtime/planning_commit.py 的三个服务调用；INSERT 只在 SQLitePlanningCommitStore._append（109 行），由 PlanningCommitService._accept（159 行）调用。`_append` 是内部存储原语，不是模型/API 接受入口。ReAct/Gateway/HTN/Horizon 不引用 Commit 写入模块；method、HTN、Horizon 的会话登记仍只是 Proposal。

接受事务只写 planning_commit_records/outbox；Runtime 的 prepare、模式标记和 wait 生命周期写入与其分开。ordinary approval 可继续原图，不能使用内存 Proposal 或新接受正文。既有 SemanticRevisionService、Scheduler、Executor、ACGLowerer 和共享 Topology Compiler 未修改。

### 3. 架构不变量判定

| 不变量 | 最终源码结论 | 证据与边界 |
| --- | --- | --- |
| A 接受权威唯一 | CONFIRMED | service._accept 单一接受编排，私有存储 append；模型 Request 不注册为输出 schema，extra=forbid；默认旧链不是新绕过入口。 |
| B 接受 / 物化分离 | CONFIRMED | 状态固定 COMMITTED_NOT_MATERIALIZED；初始 worker 返回最新 Run，不走下沉；revise 先转 wait；真实审核测试只执行原节点。 |
| C CAS / 幂等 / 原子性 | CONFIRMED | BEGIN IMMEDIATE 在头读取前获得；全字段摘要包括 Sources/scope/expectedRevision；每 Mission revision 唯一；跨连接不同 key 竞争仅一个成功；Record/outbox 同事务。 |
| D 可信 Sources / 权限 | CONFIRMED（单 Workflow DB 及双检范围） | Frozen Basis 与当前 Mission revision、Plan/Graph/Observation、编译包 hash、步骤绑定、scope、catalog、Identity、node commits 受校验；验证后重复 Sources 与读写授权。 |
| E 安全修订 | CONFIRMED（完整语义计划、无 safe-cut） | 原始 touched 检查 + 已编译输入关系/受保护节点一致性；prepared/committed 收据、attempt、输出、时间戳、祖先均保护；控制图/控制策略/未解决节点审核拒绝。 |
| F 恢复 / 生命周期 | CONFIRMED（已测试故障窗口） | observed-before-decided、decided-before-checkpoint、checkpoint ack 丢失、applied Run save 失败均恢复 plain wait，只有一份接受事实；Run 最新输入不被 worker 覆盖。 |

以下不在上述 CONFIRMED 的保证内：Identity / execution value DB 与 Workflow DB 的联合原子快照、多实例生命周期隔离、磁盘损坏/断电真实实验，均为 UNVERIFIED 或明确未实现；双读摘要不能伪称解决跨 DB 原子性。任意管理员 SQL 改写 trusted DB 不属于受支持的 Runtime 写入合同。

### 4. 已证实 P1 与最小修复

本轮没有发现 P0。六类 P1 均由失败反例建立，不以推测定级。

| 编号 | 基线缺陷 / 失败证据 | 最小修复及最终证据 |
| --- | --- | --- |
| P1-1 接受恢复窗口 | Commit 后、decided 保存前崩溃，持久 round 仍 observed/decision=None；恢复再调模型，可改变候选或跳过接受等待。原 pending callback 只支持 decided-wait。初始反例 2 failed 中的一项（10.32s）。进一步新操作员 inbox 输入使旧 Fence 抛 ExecutionStateChanged（1 failed / 1 passed，3.91s）。 | workflow_runtime.py:1175 支持 observed/decided，校验 server proposal identity，从既有接受事实补 plain wait。1195 行在 Run 锁内完成等待，只在此**不消费输入、不接受、不执行**的恢复路径允许未消费 inbox；终态、取消、runtimeRevision Fence 不变，其他路径输入 Fence 不变。新输入继续留在独立 inbox。 |
| P1-2 模式可丢失 | save_run 可以把已持久 planningCommitRequired 删除；重启 authority=None 后有旧执行链回退条件。与 P1-1 一起稳定 2 failed（10.32s）。 | sqlite_workflow_store.py:404 在原事务 upsert 禁止移除或禁用 true 标记。无新正式状态系统。 |
| P1-3 收据遗漏 | pending、attempt=0，但真实 value store 已有 node commit；替换仍 ACCEPTED（receipt_only 反例）。 | runtime/planning_commit.py:108、190 将真实 node commit 纳入 Sources 指纹与保护集，prepared 也保守保护，不因投影落后放开副作用节点。初始无步骤 worker 不跨线程读取 SQLite value connection。 |
| P1-4 编译后前缀变化 | 真实 Runtime 生成两节点正式 seq 计划，测试持久化其完成状态并生成对应 Observation；新增 analysis 无原始依赖声明，Compiler 自动连接到旧验证 sink；原 guard 仍 ACCEPTED。校正 fixture 后撤除新增 guard 验证得到 1 failed / 17 deselected，7.98s。 | runtime/planning_commit.py:213 比较 Compiler 返回的全部关系中受保护节点的前置关系，并比较受保护节点正文。原 Compiler 唯一生成/验证 DAG，无第二个拓扑算法。 |
| P1-5 审核屏障遗漏 | 真实 WAITING_REVIEW step + checkpoint + matching Observation，增加任务仍 ACCEPTED（1 failed / 7 passed，20.80s）。 | runtime/planning_commit.py:144 拒绝 waiting_review 步骤、非 planner 的 reviewPayload、未解决 controlFrames。战略 planner wait 可提出候选，普通批准不采用新候选。 |
| P1-6 来源只比较新旧、未证明内部一致 | 捕获前已有 graph body/package hash 不一致、binding 指向未知 semantic key、scope=None；三者均 ACCEPTED（3 failed，2.50s）。 | runtime/planning_commit.py:128、167 使用原 Blueprint/CompiledACGPackage 合同及 stable_checksum 验证关联；检查 binding 唯一性/步骤覆盖/语义原子覆盖，缺 scope 拒绝。不创建或编译执行图。 |

P1-4 最早 fixture 误用被路由为单节点 htn 的 workflow，不能证明隐式依赖缺陷；已改为独立真实 runtime_at，仅注册 seq，先断言 Compiler 实际新增通往旧 sink 的边，再复现 guard 缺失。没有把错误 fixture 的失败计作生产缺陷。

原测试只调整一处损坏输入构造方式，不改变断言目标；没有跳过、放宽计时或削弱架构门禁。修复期间曾出现初始 worker 跨线程读取 value store 的 2 项失败（43 passed，82.30s），以及 schema import 的 2 次 collection error（1.03s/0.83s）；已修正，均由最终测试覆盖。

### 5. 并发、来源变化与故障实验

新增对抗集 24 项，均采用临时 SQLite 或真实 Runtime 合同：

- 同 Mission、不同 key、同 expectedRevision 的两个连接并发，恰好一个 ACCEPTED，一个 STALE_COMMITMENT，revision=1、outbox 一条。旧测试另覆盖 8 次同 key 并发重放及全字段冲突。
- 不同 Mission 使用同 Workflow DB：第一请求在 validate_proposal 内持写锁，第二请求在默认 timeout=5 秒后 STORAGE_UNAVAILABLE（实测等待断言 ≥4s）；无其记录或 outbox，释放后成功。此实验**证明跨 Mission 阻塞存在**，不是吞吐优化。
- 对 Record/outbox INSERT 分别用临时 trigger 故障，均零半记录；对 conn.commit 前故障回滚；对 commit 后 ack 故障，Record/outbox 已存在、响应保守失败，重试 IDEMPOTENT_REPLAY，revision 不增长。回执失败不能被当成“肯定未提交”，必须用原 key 重试/对账。
- 初始 L2 worker 期间真实修改 input、取消信号、授权、Mission、Identity task snapshot、capability catalog、execution scope，七类变化分别以 STALE_* / AUTHORITY_DENIED 拒绝，不发布接受。
- Observation/Graph/Plan Fence、scope 全覆盖、未知方法 Proposal 非消费、已完成 / pending attempt 前缀、非法 DAG、control policy、authority 缺失、旧 worker 后到输入、普通审核仅执行旧图，由原集成与新集共同覆盖。
- Commit 成功后 decided save、checkpoint 写前/写后 ack、applied Run save 各故障保持单接受；恢复不调用模型，不调用 SemanticRevisionService，不派发 Agent。新操作员内容仍在持久 inbox，未被等待恢复确认消费。

### 6. 测试与快照

环境：Python 3.14.5；Windows 11 / 10.0.26100；工作目录 apps/agentOS。本轮不调用 timeBeginPeriod，不请求 1ms；未修改、跳过或放宽已有 20ms streaming 用例。历史 Windows 默认定时波动记录继续保留。

下文缩写：T=`python -m pytest -q tests/components/planner/test_planning_commit.py tests/components/planner/test_planning_commit_runtime.py tests/contracts tests/architecture --tb=short`；A=`python -m pytest -q tests/components/planner/test_planning_commit_audit.py --tb=short`；R=`python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short`；F=`python -m pytest -q --tb=short`。

| 快照 / 命令 | 实际结果 |
| --- | --- |
| 入场 66249bbe，T | 142 passed，58.94s |
| 初始两反例，A | 2 failed，10.32s；生产源码仍为基线 |
| 第一恢复/模式修复，A + 原 Runtime Commit 集 | 29 passed，24.64s |
| receipt + 初版 sink fixture，A `-k 'sink or receipt_only'` | 2 failed / 2 deselected，2.33s；sink fixture 尚不足以证明生产缺陷 |
| 新编译保护 + 初版 sink，A | 1 failed / 3 passed，2.97s；sink fixture仍需校正 |
| sink fixture 调试 `-k sink -s` | 1 failed / 3 deselected，2.02s；随后两次校正运行仍因前提不成立失败（8.45s、8.05s），不记生产缺陷 |
| 扩展至十项，A | 2 failed / 8 passed，12.71s；Mission ID 形状及 fixture import 错误，已修正 |
| 修正十项 A | 10 passed，13.07s |
| 七类 worker Sources + review，A `-k 'worker_source or node_review'` | 1 failed / 7 passed / 10 deselected，20.80s，证实 P1-5 |
| 正确 seq fixture、暂撤编译后 guard，A `-k compiler_generated` | 1 failed / 17 deselected，7.98s，证实 P1-4；随后恢复 guard |
| 加入 review guard / receipts，A + 原 Runtime Commit 集 | 2 failed / 43 passed，82.30s，揭示修复中的初始 worker 跨线程错误 |
| 修复初始无步骤 worker，原集 `-k 'initial_planning or worker_does'` | 2 passed / 25 deselected，1.76s |
| 来源内部不一致，A `-k incoherent` | 3 failed / 18 deselected，2.50s，证实 P1-6 |
| 来源合同修正期间，两次 A + 原集 collection | 各 2 errors，1.03s / 0.83s；正确 import 修复后下项通过 |
| 来源合同修正，A + 原 Runtime Commit 集 | 48 passed，27.88s（加最后恢复输入反例前） |
| 追加 inbox 竞争，A `-k before_decided` | 1 failed / 1 passed / 20 deselected，3.91s，证实 P1-1 第二窗口 |
| inbox 等待恢复修复，A | 22 passed，14.92s |
| 追加两故障窗口，A `-k barrier_write` | 2 passed / 22 deselected，1.86s |
| 最终快照 49ea14e0e411，T | **142 passed，25.35s** |
| 同一最终快照，A | **24 passed，16.47s** |
| 同一最终快照，R | **765 passed，273.20s（4:33）** |
| 同一最终快照，F | **1380 passed / 0 failed，282.53s（4:42），1 个既有 PyPDF2 弃用警告** |

命令中的 `-k` 和 `-s` 与 `--tb=short` 是实际复现/调试参数；所有最终集均不筛选/跳过用例。中间通过结果不替代最终全量。

### 7. P2、明确限制与下一阶段入口

1. **P2：全 DB 写锁时长。** ledger transaction 在 provider Sources/授权/拓扑验证之前 BEGIN IMMEDIATE，直到结果记录/outbox 一同 commit 才释放。Initial 的 L1/L2 位于事务外；initial 接受验证调用一次既有 semantic gate，revision apply_patch 调用一次。节点/关系/候选字符上限及 binding search 上限限制工作量，但不能承诺硬耗时或跨 Mission 吞吐。旧正式来源的总体大小、收据数、同步编译不可抢占，仍需后续负载验证；不为吞吐取消任何 Fence。
2. **P2：错误分类与 ack 歧义。** INSERT 故障在 service 内可能收敛 AUTHORITY_DENIED，BEGIN/COMMIT 故障为 STORAGE_UNAVAILABLE；错误分类不够精确。提交后的 ack 丢失可能返回 REJECTED 但历史事实已存在，调用方必须以同 key 对账，不创建新 key。没有虚假 ACCEPTED、丢接受或双提交。
3. **明确保留：跨 DB/多实例。** Identity 与 value store 是独立数据库，只能摘要双检；Runtime 生命周期锁仍为单进程约束。没有联合事务、分布式 Run Fence、断电/损坏/真实多进程 kill 实验。不把线程故障注入等同于断电验收。
4. **明确保留：Proposal 及执行边界。** 不接受 HTN/Horizon 的 durable 消费，不开放局部窗口或 safe-cut；不消费 outbox，不提供前端 API，不启用生产装配/升级业务 DB。初始已接受 Run 保持 deferred，没有“接受就执行”的隐含承诺。
   来源投影现在包括 nodeCommits，旧实现签发的 strategyFingerprint 不保证通过新版当前来源校验；旧 Record 仍是历史事实，不能把校验失败解释为允许用新 key 再接受。strategyFingerprint 当前主要是上下文摘要，尚无独立显式验证策略版本；S02-03 接入物化前应明确策略/Compiler 版本和来源投影版本，不能只凭同名字段推断语义一致。
5. **S02-03 前置：** 使用唯一 PlanningCommitService，声明 Graph Revision 候选的可信来源、不可变正文/摘要、源 Run/Graph 的可恢复关联及接受头 CAS；禁止把历史 Receipt 当成新许可。控制图 safe-cut 必须定义已开始前缀、控制帧与审核边界，复用原编译权威并比较真实有效依赖。图修订接受与后续物化/激活须明确分层交接，物化阶段重验 Mission/Basis/Plan/Graph、权限与跨 DB 来源，执行正式 GraphVersion CAS；不能凭 outbox 直接派发。需要扩展来源引用时不复制 TaskPlan/Graph/Run。本轮不实现这些功能。

最终 `git diff --check` 通过；HEAD 仍为 `66249bbe97db3f43854d471402e9663e3272e157`，暂存区为空。修改范围严格为本报告第 1 节列出的 4 个原文件与 2 个新增文件，没有范围外修改。测试前后源码清单摘要均为 `49ea14e0e411fbe2c49de1bd6972f0966fa3114f5f997a240743c821c519bd13`。

源码清单的固定顺序（均相对 apps/agentOS）：src/contracts/planning_commit.py、src/components/planner/planning_commit.py、src/support/stores/planning_commit_store.py、src/runtime/planning_commit.py、src/runtime/planning_loop.py、src/runtime/workflow_runtime.py、src/support/stores/sqlite_workflow_store.py、tests/components/planner/test_planning_commit.py、tests/components/planner/test_planning_commit_runtime.py、tests/components/planner/test_planning_commit_audit.py。每行构造为 `path + " " + sha256(file bytes)`，以 LF 连接后取 SHA-256。

全部修改保持未提交；未 Commit、Push、部署、升级业务数据库或修改正式 ADR。ACCEPT 不等于生产默认启用或下一阶段物化验收。

### 8. PR-S02-02-Freeze 冻结验证

本节为后续用户授权的本地冻结提交记录，不改变前述独立验收的历史状态或结论。冻结前 HEAD 为 `66249bbe97db3f43854d471402e9663e3272e157`，分支 master，暂存区为空；完整 diff 与新增测试全文已复核，仅涉及第 1 节的六个文件。

重新按第 6 节算法计算源码摘要，结果为 `49ea14e0e411fbe2c49de1bd6972f0966fa3114f5f997a240743c821c519bd13`，与验收快照完全一致。没有修改运行时代码、测试、正式 ADR、生产配置或数据库 Schema。

环境仍为 Python 3.14.5、Windows 11 / 10.0.26100；未请求 1ms 定时精度。工作目录 apps/agentOS，实际重新运行：

- `python -m pytest -q tests/components/planner/test_planning_commit.py tests/components/planner/test_planning_commit_runtime.py tests/components/planner/test_planning_commit_audit.py tests/contracts tests/architecture --tb=short`：**166 passed，28.17s**（原定向 142 项与新增对抗 24 项）。
- `python -m pytest -q --tb=short`：**1380 passed / 0 failed，292.12s（4:52）**，1 个既有 PyPDF2 弃用警告。

`git diff --check` 通过。冻结范围为六类 P1 修复、对应测试及本验收报告，作为一个原子修复提交；不 Push、Merge、部署或升级业务数据库。第 7 节的 P2、跨数据库原子性、多实例和物化/激活限制继续保留。该冻结仅确认 S02-02 修复基线具备进入 S02-03 的条件。

---

## 5. 原文｜PR-S02-03 Graph Revision Commit 与 Safe-Cut

<!-- 原始记录：PR-S02-03-GraphRevisionCommit实施记录-2026-10-14.md -->

> 原文件 `PR-S02-03-GraphRevisionCommit实施记录-2026-10-14.md` ｜ 2026-10-14 ｜ 实施记录 ｜ 原文 13030 字节

状态：最小 DAG 范围内实施与最终自测完成，等待独立代码级验收；全部修改未提交。控制图切口保守拒绝，不声称完整支持或独立验收 ACCEPT。

### 基线与真实权威链

入场 HEAD 为 S02-02 冻结提交 `1b508748535b211afcb0546ae2c216a83daeca47`，工作区、暂存区干净。已读取 S02-02 独立报告及真实实现；原始提交 `66249bbe` 的六类 P1 修复保留，既有测试目标不变。

真实链路：

`TaskPlanPatch → PlanningCommitService → durable plan_revision Record → Runtime.accept_graph_revision → 可信来源预检 → SemanticGraphPatchService.apply → 原 Topology Compiler → 原 ACGLowerer → derive_graph_patch → Safe-Cut → PlanningCommitService → 同一 ledger / 原子 outbox`。

SemanticGraphPatchService.apply 仅调用语义 patch 校验与纯下沉；derive_graph_patch 仅计算 diff。SemanticRevisionService.prepare 则会分配并构造 replacement Run、同步步骤、编译执行包；commit 会写 value store graph patch、替换 Run、谱系与正式状态。因此本轮完全不调用 SemanticRevisionService.prepare/commit，也不调用 Runtime Binder。ACGLowerer 保持全节点覆盖，未修改共享 Topology Compiler、Scheduler 或执行控制引擎。

### 最小方案与合同

- `contracts/graph_revision.py`：PlanningSourceProvenance、SafeCutProof、GraphRevisionProposal，extra=forbid/frozen，显式版本化。复用原 TaskPlan、TaskImplementationBinding、GraphPatch、RuntimeBlueprintSpec，不复制正式计划或图合同。
- PlanningCommit 的 ProposalType 增加 graph_revision，Record 保存可选 sourceProvenance；proposalPayload 可包含完整 GraphRevisionProposal。请求仍没有 run_id、executor、permission 等客户端权威字段。
- GraphRevisionProposal 绑定源 commitId、Mission/revision、源 Proposal 内容指纹、源 Run/Graph、原 PlanVersion、Frozen Basis/scope 摘要、Compiler 版本、下沉/验证/来源投影版本。GraphPatch 中明确 baseGraphVersion 与候选 version=base+1。
- 新语义修订接受时由 Runtime 注入 `runtime-static-v1` 证明。包含 Run 输入、Basis、scope、原 Plan/Graph/编译包/绑定、步骤、完整已知收据、规范化控制执行态、能力目录、逻辑 Agent profiles、Identity snapshot、操作员 inbox。只剔除 plain planner wait 改变的 checkpointId/reviewPayload/currentStepId，并单独验证这些当前证据；原 Observation、Plan/Graph 版本必须仍对应。
- 已冻结旧 Record 不更新。没有 provenance 的旧语义修订明确拒绝派生；未知 provenance/Compiler 版本不能冒充当前版本。新来源投影 version 与 S02-02 旧 strategyFingerprint 分开，不重新解释历史指纹。
- 返回仍为 PlanningCommitReceipt。Record.status=ACCEPTED，materializationStatus=COMMITTED_NOT_MATERIALIZED；候选图 version 是正文的一部分，不修改正式 GraphVersion，不代表 APPLIED。

### 存储、CAS 与唯一来源

复用原 planning_commit_records/outbox、全字段请求摘要、Mission commitmentRevision CAS 和 BEGIN IMMEDIATE。parentCommitId 为源 plan_revision；派生新接受时源必须仍为 Mission 接受头。没有第二个接受服务或接受事务。

在显式 upgrade_schema 中增加 partial UNIQUE expression index `planning_graph_source_unique`，约束 graph_revision 的 proposalPayload.sourceCommitId。没有新表或正式图状态系统。事务内还查询已有图修订：同 key 原样重放；不同 key 不给同源再接受第二份图。不同 Source 或 Run 复用同 key 拒绝。

构造器不自动 DDL；旧无 index 的 v1 ledger 可读、可继续原语义接受，但新图接受返回 STORAGE_UNAVAILABLE，需显式准备 index 后重开 store。测试只在临时 DB 调用该管理入口，未升级业务 DB。旧 Record 原始 JSON 在新图接受前后逐字节不变。

昂贵语义预检、拓扑和下沉均在 ledger 写事务外；下沉也在 Run 锁外。最终接受：Run lock → SQLite write transaction → 当前 Sources/权限双检 → 源 commit/接受头验证 → 已认证派生摘要与当前 Safe-Cut 证据比对 → 原 CAS/append/outbox。保留原锁顺序，没有反向取得 Run 锁。

最终事务不重跑 Topology Compiler。Runtime 内部 provider 仅认可本次纯推导生成的私有摘要证书；客户端构造一个 schema-valid GraphPatch 或 proof 不足以通过。历史重放无需再次下沉，但必须当前授权，且没有执行许可。

输入政策：最多 256 步骤、1024 原图边、1024 收据、64 inbox 输入、256 Agent profiles、512 能力描述；来源 Run / 完整候选各最多 2M JSON 字符。同步读取和验证无可抢占硬截止期；跨 DB 最后一次检查到落盘的间隙仍非联合事务，不能宣传为解决跨数据库原子性。

### Safe-Cut 范围

允许最小的无控制 DAG 修订；执行事实不变、静态有效依赖不变的 pending 后缀/独立扩展可接受。

保护 completed/failed/cancelled/skipped/non-pending、attempt/retry_count、输出/resolved_input/时间戳、Run/执行态/checkpoint 中完成与跳过集合、prepared/committed 收据、受控引用及其语义祖先。

分别验证：

1. Compiler 返回的 next_plan 中受保护语义节点正文、绑定身份、有效输入关系必须一致；不只看原始 patch。
2. 下沉后受保护执行节点全部字段、实际前置边以及寻址到该节点的逻辑资源/通信/证据/记忆决定保持一致。新增边可引用既有输出，但若重建的逻辑资源合同变化，则保守拒绝。
3. GraphPatch 必须等于原 derive_graph_patch 对原图/候选图计算的 diff。
4. checkpoint 必须实际存在并属于当前 Run/Graph/version；未知前缀身份、活跃 worker、未解决 node/control review、控制帧/迭代/历史控制审核都拒绝。

Proof 保存保护的 semantic/node keys、涉及节点、原/候选图摘要、原实际依赖摘要、步骤/收据/控制/审核证据摘要、checkpoint 摘要及版本/result=PROVEN。原 Run/Checkpoint 保持可信数据来源，证据摘要不能用于 S03 直接激活。

#### 控制图取舍

真实 Runtime 支持 CONDITION 分支选择与 skipped 集、LOOP 的 controlFrames/loopIterations/loopPaths、并行与 Join/consensus 规则、controlReviewDecisions。当前状态未提供足以证明任意历史条件区域的完整不可变选择记录。

更关键的是，现有 semantic patch lowering 只重建 TaskPlan 声明的 verification loops；任意旧 conditional/parallel/join 没有完整保留合同。S02-02 源语义接受本就拒绝控制图。若为本轮强行开放源接受或拼接控制节点，会破坏冻结边界。因此保留 `reject-control-regions-v1`：原/候选图含 control、当前或 checkpoint 存在控制活动/历史，返回结构化 CONTROL_BARRIER_BLOCKED；不存在可完整证明的控制图路径时不清空帧、不忽略控制、不放宽原审核。这一范围缩小是明确限制，不是全控制图 Safe-Cut 的完成声明。

### 确定性及只读并发修复

ACGLowerer 原本生成随机 edgeId 并 touch 时间；图承诺层为候选规范化为原图时间、保留旧边全部字段，为新边按 sourceCommitId/端点/type 派生稳定 ID。没有改写原 Lowerer。不同线程/重启得到同正文；已接受重放读取 ledger，不重新推导。

并发反例先暴露 SQLiteExecutionValueStore 线程绑定的写连接不可跨线程读取（2 failed，2.20s）。仅将 list_node_commits 和 checkpoint.load 的 SELECT 改为独立 mode=ro 连接，无 DDL、写连接共享或执行状态修改；没有重构 Executor/Recovery。随后同 key 并发仍冲突（1 failed/1 passed，4.78s），诊断为随机 edgeId，稳定 ID 修复后同 key ACCEPTED + IDEMPOTENT_REPLAY、不同 key 仅一个 ACCEPTED。Source CAS 与数据库 UNIQUE 为最终防线。

### 自测证据

环境：Python 3.14.5 / Windows 11，默认计时，不请求 1ms。工作目录 apps/agentOS。新增集最终 30 项，真实临时 Workflow/Identity/value/checkpoint SQLite，原 Runtime 与图合同。

覆盖合法 DAG、已完成前缀的独立 pending 扩展、多节点闭合、proof 序列化、重启重放；过期 Mission/Plan/Graph/来源/Scope、执行收据、控制帧、未解决审核、其他 Run、过期接受头；同源跨连接 CAS、INSERT/outbox/commit ack 故障、取消/撤权/authority 缺失/新操作员输入；旧无 index/无 provenance 兼容；没有认证推导的 provider 被拒绝；checkpoint 版本及控制证据。

对全部测试业务 DB 做差异比较，接受本身只有 ledger/outbox 变化。恢复旧 Runtime waiting 转换不采用图候选；普通批准仍完成原来的单节点 v1 图，未执行新节点。源接受 JSON 不修改。

实际运行记录：

| 命令 / 快照 | 结果 |
| --- | --- |
| Graph 新集 + 原 Commit 单元集，初版 | 7 failed / 58 passed，10.94s：控制节点读取方法名及拒绝码优先级修正，无放宽旧测试 |
| Graph 初始 17 项 | 17 passed，14.59s |
| 跨连接反例 | 修复前 2 failed，2.20s；只读连接修复后 1 failed / 1 passed，4.78s；稳定 edgeId 后 2 passed，2.18s |
| 17 项 + 并发 2 项 + S02-02/contracts/architecture | 185 passed，41.78s，中间快照 |
| 补充变化与安全后缀集 | 26 passed，50.32s，中间快照 |
| 新增集 + S02-02 三组 + contracts/architecture | 192 passed，98.04s；195 passed，53.67s，均为后续补 checkpoint/审核验证前快照 |
| 恢复/审核/checkpoint 定向 | 3 passed / 27 deselected，3.30s |
| 最终定向：`python -m pytest -q tests/components/planner/test_graph_revision_commit.py tests/components/planner/test_planning_commit.py tests/components/planner/test_planning_commit_runtime.py tests/components/planner/test_planning_commit_audit.py tests/contracts tests/architecture --tb=short` | **196 passed，57.41s** |
| 扩大：`python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short` | **795 passed，432.66s** |
| 最终全量：`python -m pytest -q --tb=short` | **1410 passed，0 failed，1 warning，1307.32s（21:47）**；既有 PyPDF2 弃用警告，Windows 默认计时，未跳过/放宽用例 |

最终源码快照（相对仓库根，按路径排序的本轮 10 个 .py 文件，各行 path+空格+文件字节 SHA256，再 LF 拼接取 SHA256）：`2144d79d3500e01a1e486adffed62517ff6dd760d5ac55ee5c3c8a1d16f974d0`。文档不参与摘要。最终定向/扩大/全量期间不再修改源码；若失败需要修改，重新登记快照并跑最终全量。

一次扩大回归的会话在交互中断后无法回收结束结果，不作为通过证据；随后在同一源码快照重新执行，取得上述 795 项完整结果。最终扩大及全量输出分别保留于系统临时目录 `S02-03-final-broad.log`、`S02-03-final-full.log`，未写入仓库或业务数据库。

### 完整文件差异及下一阶段交接

修改：contracts/planning_commit.py、components/planner/planning_commit.py、support/stores/planning_commit_store.py、runtime/planning_commit.py、runtime/workflow_runtime.py、components/executor/value_store.py、components/recovery/checkpoint.py。

新增：contracts/graph_revision.py、runtime/graph_revision.py、tests/components/planner/test_graph_revision_commit.py，以及本记录。未修改 S02-02 原测试、SemanticRevisionService、ACGLowerer、Topology Compiler、Scheduler、控制引擎、正式 ADR、默认生产装配或业务 DB。

无已知未解决 P1；需要独立验收进一步检验来源投影白名单、推导摘要证书、partial UNIQUE index 与恢复兼容、Safe-Cut 对逻辑资源边界的保守性。P2/限制包括：控制图不支持；跨 DB 仅双检；单进程 Run 生命周期锁；同步有限输入校验仍持全库写锁且无硬延迟；旧源无版本证明不派生；图消费者/前端/业务 DB index 准备未接入。

S03 接收唯一 ledger Record 的 GraphRevisionProposal（源 commit/Run/Graph、next_plan、next_bindings、完整 candidate_graph、派生 patch、proof、版本与摘要）。S03 必须重新验证接受头、正式 GraphVersion/PlanVersion、权限/Basis/scope、收据及控制/审核状态，并执行正式 GraphVersion CAS；历史 PROVEN 与 ACCEPTED 不能直接转为激活/执行。outbox 仍无人消费。

本轮未 Commit、Push、Merge、部署、升级业务数据库或修改正式 ADR；不预先宣称独立验收 ACCEPT。

最终 `git diff --check` 通过；HEAD 仍为入场冻结提交，暂存区为空，差异只有上列 7 个修改文件与 4 个新增文件。最终回归后源码摘要与定向前完全一致。达到本轮最小实施完成标准，具备进入 S02-03 独立代码级验收的条件；控制图完整 Safe-Cut、生产物化与激活均未验收。

---

## 6. 原文｜PR-S02-03 Graph Revision Commit 独立代码级架构验收

<!-- 原始记录：PR-S02-03-独立代码级架构验收-2026-10-15.md -->

> 原文件 `PR-S02-03-独立代码级架构验收-2026-10-15.md` ｜ 2026-10-15 ｜ 独立代码级架构验收 ｜ 原文 26086 字节

### 1. 结论及审计快照

**ACCEPT：七类已证实 P1 均完成最小修复，无未解决 P0/P1；可将修复后的最小 DAG 接受基线冻结为 S03 的前置基线。** 冻结建议不等于已执行 Git 提交。本报告仅评价无控制 DAG 的图修订接受，不评价 S03 物化、激活或生产启用。原实施记录的通过数量没有直接用作本轮证据。

入场 HEAD / master：`1b508748535b211afcb0546ae2c216a83daeca47`，父级原始 S02-02 为 `66249bbe97db3f43854d471402e9663e3272e157`。入场暂存区为空，7 修改 + 4 新增，与实施登记一致。读取完整 tracked diff、新文件全文、S02-02 独立验收及冻结记录、S02-03 实施记录和真实调用方后开始测试。

入场 10 个 Python 文件的 SHA-256 清单聚合值：`2144d79d3500e01a1e486adffed62517ff6dd760d5ac55ee5c3c8a1d16f974d0`。与实施快照一致。入场实施记录文件字节 SHA-256 为 `94ad484added7d6e27f007f1bf591768461c306ea003aac9b6c1f6e3a61c66a3`。完整 11 文件 manifest、tracked binary diff 和所有 untracked 原始字节已保存在本机临时目录 `S02-03-audit-e7w9jpho`；这些是审计证据副本，不是业务数据库。

本轮在入场变更上仅修复 `src/runtime/graph_revision.py`、`src/runtime/planning_commit.py`、`src/components/planner/planning_commit.py`、`src/components/recovery/checkpoint.py` 和来源投影合同 `src/contracts/graph_revision.py`，新增独立 `tests/components/planner/test_graph_revision_audit.py` 及本报告；不改原测试、实施记录、Compiler、Lowerer、SemanticRevisionService、Scheduler 或控制引擎。

最终源码清单如下，路径相对 apps/agentOS。聚合算法仍使用相对仓库根路径：路径排序，每行 `path + 空格 + sha256(file bytes)`，以 LF 连接后 SHA-256；不含文档。11 个 Python 文件聚合值：`edf59d1c57715d22bad5ba832606bf15fbe532df61e2f31035c9d535c80d1164`。

| 文件 | 最终文件 SHA-256 |
| --- | --- |
| src/components/executor/value_store.py | 7d5a33a59fcb4bd6520c7f3eb8da612e90b69248e53ea7d1d7797a7cf5af9f26 |
| src/components/planner/planning_commit.py | acbae9d36809287671d87714118112ae0d6d75fefd8b3b0c628051405b5f00af |
| src/components/recovery/checkpoint.py | b0ff61241c82896654e78a6d682b752a6a88c3aee5eed5afc6517ce0c052d715 |
| src/contracts/graph_revision.py | a78e1054fa34cbe4e8a833a58f8512632dda87c76eb8adc189e3dd9302703dd4 |
| src/contracts/planning_commit.py | 1cd7cf54666fc8b26119ba1f859b748fc51252802a674793b460637f205f3de1 |
| src/runtime/graph_revision.py | 9a8bd570487f1c70a9d4e20d75f1944b579300af7f369a4c294022604f7e058b |
| src/runtime/planning_commit.py | b48f49f3fa62ea0b69de1c2248098fa88843a13e878129a4646f8e84193d6f0a |
| src/runtime/workflow_runtime.py | b3d8f699a945a9ff2f78ade0f00aa3c6fa9695f76a7a854b1dc69d3ffc380009 |
| src/support/stores/planning_commit_store.py | dce60422a87dc60a69521be8fece480d503e9238d484e41f18600fd459e84c56 |
| tests/components/planner/test_graph_revision_audit.py | 30910acaad042bc93e1e9893aa3bef9bdc1a6836af427b562878ce9b8580893d |
| tests/components/planner/test_graph_revision_commit.py | 07643568e46ecb9ec269bf535ec8d1d2550ee385b41909b268c65788febf6516 |

### 2. 真实调用链与副作用

| 阶段 / 源码 | 输入及权威 | 读取 / 写入 / 事务位置 |
| --- | --- | --- |
| workflow_runtime.py:1128 → runtime/planning_commit.py:324 | 显式服务端 Run ID、sourceCommitId、幂等 key；没有客户端图载荷入口 | authority 缺失拒绝；不修改 Run |
| graph_revision.py:240 | 同 Mission/Run 的已接受 TaskPlanPatch、当前接受头、来源 provenance、当前授权 | Run 锁内读取 Workflow ledger/Mission/Run、Identity latest Plan、value receipts、目录与 Agent profiles、操作员 inbox、checkpoint；无正式写入 |
| runtime/planning_commit.py:153 / service.py:648 | 原语义修订验证、冻结 Basis/scope、Observation、完整依赖 | 事务外预检调用原 apply_task_plan_patch / Topology Compiler；验证已执行前缀、来源及约束，实际目录快照与 Frozen Sources 完整比对 |
| semantic_patch.py:33 → semantic_patch_planning.py:30 → acg_lowerer.py:82 | 原正式 TaskPlan、Graph、bindings、已接受 patch、可信目录和 scoped registry | Run 锁外纯计算：再次语义编译、冻结逻辑实现、全节点 Lowering；构造内存候选，不绑定资源、不持久化 |
| graph_revision.py 候选规范化 → semantic_patch.py:84 | 保留原图 ID，候选 version=base+1；保留已有边正文，新边按 source/端点/type 派生 ID，时间归一到源图 | 仅修改内存候选；原 derive_graph_patch 计算节点及边投影 diff |
| graph_revision.py:103 / :207 | 原图/候选图、下一版 Plan/bindings、真实执行态、receipts、checkpoint | Run 锁内 Safe-Cut；最终事务中重验 source/head、派生证书及 proof；不重新编译拓扑 |
| components/planner/planning_commit.py:159 → planning_commit_store.py:65/:120 | 同一接受权威、请求全字段摘要、当前来源/授权双检、Mission 接受 revision CAS | BEGIN IMMEDIATE；Record 与 outbox 在同一连接/事务 INSERT；异常回滚；没有其他正式写入 |

新图请求中的语义预检与纯 apply 分别经过现有编译入口；最终 ledger 事务内没有 Compiler/Lowerer。历史同 key 重放不再下沉。Lowerer 自身仍运行原 blueprint、semantic preservation 和 bindings 校验。Safe-Cut 做保护边界比较，不拥有新 DAG 编译规则。

SemanticRevisionService.prepare（semantic_revision.py:77）会分配 replacement Run 并构建全新执行态；commit（:247）会写图补丁、替换 Run 和转换 outbox（:359）。本链没有调用两者，也不调用 Runtime Binder 或 Scheduler。`COMMITTED_NOT_MATERIALIZED` 与 `PROVEN` 都只说明接受/验证事实。

### 3. 七类已证实 P1 与最小修复

#### P1-1：Checkpoint 只验证身份，没有验证执行证据一致性及已确认头

入场 graph_revision.py:52-63 只按 Run 中 checkpointId 读取并检查 Run/Graph/version。Safe-Cut 仅合并 checkpoint 的 completed/skipped IDs，忽略其他执行通道；checkpoint 的 consensus 等历史也可能漏过。相同图版本并不证明 Run 投影与 checkpoint 一致。

反例：接受一个替换 pending A 的合法语义 patch 后，在真实 checkpoint SQLite 保存包含额外 output/context/memory/trace/provenance、consensus 或 communication usage 的合法状态载荷，更新 Run 的 checkpoint 引用但保留滞后的执行通道。7 项均错误 ACCEPTED。这里不把任意引用当成真实完成证据；缺陷恰是系统无法证明该证据与 Run 一致却仍签发 PROVEN。

另用真实 `acg_state_persistence.save_checkpoint` 模拟 checkpoint 已提交、Run 投影尚未落盘的窗口，新 checkpoint 带 node review。原代码因 Run 未引用新头而忽略它并 ACCEPTED。该反例在修正测试的属性名后独立失败，排除了 fixture 拼写错误。

修复：graph_revision.py:79 读取最新已提交头与正文，要求其 ID 已被当前 Run 确认；无头但有引用、或头未投影均拒绝。比较全部 ACG 执行通道，仅剔除 checkpointId、currentStepId、reviewPayload；非 Planner review 仍由原独立屏障检查拒绝。checkpoint.py:135 改为独立 mode=ro 连接的一次 SELECT，头和正文在同一个 SQLite 读取快照中返回，连接 finally 关闭。没有新增写入口或修改执行持久化顺序。

严格一致性可能保守拒绝部分可恢复的旧/领先 checkpoint，属于可用性取舍；不能在接受阶段替 Runtime 擅自合并恢复事实。

#### P1-2：执行态显式身份冲突被规范化掩盖

入场 source_provenance 无条件覆盖 state.graph_id / graph_version；Safe-Cut 不检查 state.run_id。真实 Run 的 state 显式指向 foreign Run、foreign Graph 或 Version=99 时，三项均可接受语义来源并进一步错误 ACCEPTED 图修订。

修复：graph_revision.py:26 的 execution_state 先检查显式 Run/Graph/version。仅对旧投影未提供的图字段补齐值；不覆盖冲突。该函数同时用于 provenance、checkpoint 一致性和 Safe-Cut。异常来源在源接受或图接受阶段拒绝，没有重新解释旧 Record。

#### P1-3：节点执行通道遗漏及未知身份被静默忽略

入场代码保护受控 refs，但漏掉 outputSummaries、blackboardSnapshots、debateSessions；只遍历已知 binding，还会忽略指向未知节点的 refs。三个已知 A 通道与两个 foreign-node 通道的反例均错误 ACCEPTED。

修复：graph_revision.py 的 node_evidence 合并八类现有节点证据通道的全部 key 到 protected_nodes；再执行原来 `protected_nodes <= bindings.keys()` 检查。已知节点的正文、绑定、原语义祖先、有效前置关系与逻辑资源必须保持；未知引用拒绝。没有创造执行事实，也不把摘要升级为“已完成”；只禁止不能证明安全的身份替换。

#### P1-4：遗漏实际 Workflow 依赖，锁外推导存在可阻止的 TOCTOU

`_workflow_for_run`（workflow_runtime.py:2371）读取当前 WorkflowRegistry 定义，下沉使用其 domain；入场 provenance 没有绑定 run.workflow_id、实际定义或 domain/version。通过真实 register API 在纯推导返回后重新登记同 ID Workflow（改变 version/domain），图接受仍返回 ACCEPTED。失败反例为 `-k 'after_derivation and workflow'`：1 failed / 41 deselected，7.19s。这不是跨 DB 无法原子保证的最后瞬间窗口，而是最终来源检查本应能检测却遗漏的输入。

修复：来源投影绑定 workflowId 和实际 WorkflowDefinition 全正文，检查其 version 与 Run 准备时的 workflowVersion 一致。对只改 domain、不改 version 的重定义，也会因完整投影摘要变化而拒绝。来源投影显式升级为 runtime-static-v2，contracts/graph_revision.py:24 接受带明确版本的 v1/v2 历史模型，但不再默认填版本。v1 记录可读、字节不改；不能静默充当 v2 重新认证。旧 v1 的同 key 回执仅是历史事实。修复后 Workflow version/domain 竞争和 v1 兼容反例 3 passed / 41 deselected，5.86s。

#### P1-5：祖先声明被单值映射覆盖

原语义接受与 Graph Safe-Cut 都把 parentKey 和 parent relations 汇总到单值字典。真实 Workflow 通过原 Compiler/Lowerer 生成三个执行节点：A.parentKey=P1，另有 P2→A 的 parent relation；A 仍 pending、attempt=1，且真实 value store 已有 prepared node receipt。该计划通过现有正式合同，不能把多种已允许的父声明当作测试非法前提而忽略。

修改被覆盖的祖先 P1 objective，原语义接受和原 Graph 接受均错误 ACCEPTED。首次测试用不完整 completed 状态调用真实 observe，先被“completed step has no durable output”拒绝，属于 fixture 错误；改为真实 prepared receipt 的 started/pending 边界后，得到真正失败：1 failed / 44 deselected，8.11s。随后单独证实语义接受也漏检：1 failed / 1 passed / 44 deselected，9.59s。

修复：runtime/planning_commit.py:36 新增纯保护集合函数 with_semantic_ancestors，汇总所有 parentKey/parent 关系并以 visited 集遍历，语义接受与 Graph Safe-Cut 共同复用。它不生成任务、排序或执行边，不是第二套 Compiler。正常语义接受提前拒绝；另一个测试仅模拟已证实的旧单父源守卫，保留历史已接受来源场景，让真实 Graph Safe-Cut 证明自己仍会拒绝。两层验证修复后 2 passed / 44 deselected，8.10s。

#### P1-6：前后指纹相同，实际计算却读取了临时变化的活对象

纯下沉接收的是全局 Catalog 与 scoped AgentRegistry 的活视图。反例先捕获同一源、同一状态的基准候选且不接受；然后仅在 SemanticGraphPatchService.apply 内临时增加实际 Agent profile.binding_priority，返回前恢复。所有前后 Source Fence 均看到原 profile，第二次仍 ACCEPTED，但持久候选的新增节点/routerScore、GraphPatch、Proof 摘要与基准不同：1 failed / 46 deselected，7.39s。它不是最后一次跨 DB 检查后的不可避免窗口，而是实际消费的输入没有绑定到声明的 Frozen Sources。

修复：graph_revision.py:40 深拷贝 Workflow、能力描述与 scoped profiles；以该批副本及实际 Run 输入计算 provenance，先与源接受证明比对。预检和下沉使用同一 Catalog 副本、Workflow domain 和只携带 profile 的私有 AgentRegistry；不注册生产 Agent，不复制执行器、不绑定资源。runtime/planning_commit.py:30 复用原 CapabilityCatalog 形成私有目录；语义验证把实际目录代入完整 Frozen Sources 重新比对，验证与 provenance 保存同一份已验证目录。Graph Record 的来源元数据直接使用已验证候选的绑定来源，不再重新采样另一批活输入。

新增临时 capability.output_contract 变化反例覆盖同一问题。临时变化恢复后，因计算实际使用冻结副本，候选完整 JSON 仍与基准相同；永久变化仍由现有 Source Fence 拒绝。此修复不声称各数据库/配置源在接受瞬间具有全局原子视图。

#### P1-7：新增 provenance 回调位于最后授权 Fence 之后

原 PlanningCommitService 在最终 Source/授权复核与接受头 CAS 之后，构造 Record 时才调用 get_source_provenance；该方法会读取多个来源。在该实际读取返回前设置取消信号或撤销 Mission 权限，两项均错误 ACCEPTED，留下第二条 ledger/outbox：2 failed / 48 deselected，9.81s。

修复：components/planner/planning_commit.py:159 把候选正文与 provenance 捕获放到最后一次 Source/授权复核之前；之后再重放检查、读取接受头并 CAS/构造不可变 Record/append。既有幂等与重入纪律保留，不让捕获回调成为最终 Fence 后的可阻止窗口。反例转为 2 passed / 96 deselected，8.25s；随后与实际输入/新进程/祖先路径组合 7 passed / 43 deselected，36.32s。

未发现 P0；七类 P1 的失败反例修复后全部通过，并由最终定向、扩大及全量回归覆盖。没有遗留阻塞级缺陷；第 5 节的 P2 与明确不支持范围继续保留。

### 4. 六组不变量证据

| 组 | 结论 | 源码与实验证据 |
| --- | --- | --- |
| A 唯一接受权威 | CONFIRMED | 只有原 PlanningCommitService append ledger。GraphProvider 验证 source 完整 Record、同 Mission/Run、来源证明、当前接受头、source Proposal 指纹和派生摘要。contracts/planning_commit.py:138 在读取 Record 时重算正文指纹；篡改源正文仅保留 ID/旧摘要会失败。parentCommitId 与 sourceCommitId 均为接受头，revision 增一。无通往模型/客户端的图正文 API |
| B Safe-Cut | 入场 VIOLATED；修复后 CONFIRMED | P1-1/2/3/5 已有失败反例。真实 receipts/attempt/输出/已完成、失败、跳过、所有已声明祖先、Compiler 隐式前置关系沿 S02-02 语义 gate 与本轮 graph-level 比较共同保护；不允许新节点成为已执行节点前置。寻址到保护节点的 binding/skill/memory/evidence/communication 逐项比较；控制图和未解决 worker/review 保守拒绝 |
| C 确定性与内容完整性 | CONFIRMED | 同输入两个独立 Python 新进程，从临时 DB 的独立备份重建 Runtime，经真实 adapter 各自推导/接受；完整候选 JSON 与父进程预接受候选相等。schema 的 digest 和 ledger 的 hash 都是 alias JSON、sort_keys、紧凑分隔、UTF-8/ensure_ascii=False。对 graph、Plan、bindings、patch、proof 分别单字段改动并重算客户端摘要仍拒绝，因为派生证书不匹配 |
| D SQLite | CONFIRMED（有效正式 schema 范围） | 实测 partial UNIQUE 命中 `proposalPayload.sourceCommitId`；跨不同 key 直接插入同源的合法正文触发 IntegrityError。两次 upgrade_schema 保持旧行字节不变；冲突历史升级在事务内失败、DB 不变；无 index 旧 ledger 重开后拒绝图接受。null/缺失/整数/嵌套 Source 不通过 typed Record；带外 raw SQL 可绕过业务 schema，本系统不声称 SQLite 管理员不可篡改 |
| E 竞争与恢复 | 入场 VIOLATED；修复后 CONFIRMED | 原两连接同源并发集、Record/outbox/commit ack 故障及重启重放重新运行；新增 attempt、receipt、scope、Plan、Graph、Observation、checkpoint、Agent profile、Workflow version/domain 在锁外推导后永久变化均拒绝；瞬时 profile/catalog 变化不能污染实际冻结输入；provenance 捕获期间取消/撤权在最终 Fence 被拒绝。历史回执重放仍检查当前授权。Identity/Workflow/value/checkpoint 没有联合事务，最后检查之后的跨 DB 窗口仍明确保留 |
| F S02-02 与 S03 隔离 | CONFIRMED | 检查 workflow_runtime.py:1160/:1184 的 gate 和 accepted-before-decided 恢复仍只处理 plan_revision 并持久 wait；:2210 的 apply_semantic_patch 在 opt-in 时只接受。sqlite_workflow_store.py:404 保留 planningCommitRequired 不可丢失检查。新图接受不修改正式 Run/Plan/Graph/Checkpoint/receipts，普通批准继续原 v1 图；缺 authority 不回退执行候选。没有 outbox 消费者或正式 GraphVersion 激活入口 |

“私有派生证书”是可信服务端代码内的内容绑定，不是能防御任意 Python 代码执行的密码学签名。任意注入恶意 Provider/直接调用私有存储不是客户端权限模型；没有以此声称抵抗宿主进程失陷。

GraphPatch 的边差异沿用原三元投影，不包含所有 edge metadata/resourcePlan/全局 metadata。图承诺同时保留完整 candidateGraph、nextPlan、nextBindings 及其总摘要，不能把单独 GraphPatch 宣传为完整物化命令。原有边完整对象被保留，新增边 ID 确定；无控制图条件下该投影没有被当作通用控制图证明。

### 5. P2、复杂度及未覆盖边界

1. **P2：同名错误索引。** planning_commit_store.py:56 只查 sqlite_master 名称；同名非 UNIQUE/错误表达式索引会被误判为可用，upgrade_schema 的 IF NOT EXISTS 也不会纠正。独立反例证实这一配置缺口，但 BEGIN IMMEDIATE、source graph 查询和接受头 CAS 仍阻止第二份接受；未证实错误接受不变量被绕过，因此不升级为 P1、不在本轮扩展 Schema 改造。后续管理工具应核验索引完整定义与能力版本。
2. **P2：输入限制不等于硬时间/内存界。** GraphProvider 限制 256 steps、1024 edges/receipts、64 inbox、256 profiles、512 descriptors，Run/candidate 各 2M JSON 字符。超长 Run 字符串和 1025 receipts 均明确拒绝。读取/反序列化先于部分上限检查；单条外部 receipt、checkpoint、catalog/profile 的总字节及嵌套深度没有统一上限；不能声称这些开销被 Run 2M 完整覆盖。
3. **P2：写锁持有时间及错误分类。** Compiler/Lowerer 在事务外；事务内仍反复投影和序列化来源、读取外部 DB、比较资源/证据。设 N 节点、E 边、R 收据、L 逻辑资源项、B 投影字节，Safe-Cut 的节点/收据、边和资源扫描约 O(N·(R+E+L)+B)，父链有 visited 集；外部 IO/JSON 成本另计。Checkpoint 历史条数 C 未设上限，现有表也没有 (thread_id, version) 排序索引，最新头查询还有历史扫描/排序成本。BEGIN IMMEDIATE 是整个 Workflow SQLite 的写锁，不能保证跨 Mission 吞吐或可抢占 deadline。继承的拒绝码有些归到 AUTHORITY_DENIED/STORAGE_UNAVAILABLE；不改变接受原子性。
4. **保留限制：** 单进程 RunLock，跨 DB 双检，非分布式事务；独立进程实验验证重建确定性，不等同于真实 kill/断电、WAL 损坏或多实例共享 Run 锁验证。只读 SELECT 返回一个已提交语句快照，不能把多次跨库 SELECT 宣称为一个全局快照。普通节点 review 可以继续原图；未物化图候选不会作为恢复输入。
5. **控制范围：** 所有 control nodes、frames、loop history、consensus、control review 继续 fail-closed。现有 Lowerer 不能证明任意旧 conditional/parallel/join 保留；本轮没有开放通用 safe-cut。逻辑资源重建触及已执行前缀时可能保守拒绝，即使理论上可安全重用；属于可用性限制。

### 6. 可复现测试与最终快照

环境为 Python 3.14.5、Windows 11 / 10.0.26100，apps/agentOS 工作目录。Windows 默认计时环境，没有请求 1ms，没有修改、跳过或放宽原测试。新增独立集最终 50 项。

| 实际复现/中间验证 | 实际结果及解释 |
| --- | --- |
| `python -m pytest -q tests/components/planner/test_graph_revision_audit.py --tb=short` 初版 | 8 failed / 7 passed，13.12s；其中 7 个真实 checkpoint 漏检，1 个测试属性名错误 |
| 修正 fixture 后 `-k unpublished` | 1 failed / 14 deselected，1.80s；确认真实 checkpoint-before-Run 窗口 |
| checkpoint 修复后，独立初集＋原 graph 集 | 45 passed，34.57s |
| `-k silently` | 3 failed / 28 deselected，10.98s；显式执行态身份冲突 |
| 新进程测试初版 | 1 failed / 27 passed，57.20s；仅子进程 import 路径错误，修正后 `-k fresh_processes` 为 1 passed / 30 deselected，14.98s |
| 身份修复，`-k 'silently or checkpoint'` 加原 graph 集 | 14 passed / 47 deselected，23.76s；这是定向选择，不替代最终完整集 |
| 独立集扩展中间快照 | 31 passed，76.63s；36 passed，76.19s |
| `-k existing_execution`，修复前 | 3 failed / 36 deselected，12.15s；输出摘要/黑板/辩论通道漏检；修复后 3 passed / 36 deselected，8.42s |
| `-k unknown_execution`，修复前 | 2 failed / 39 deselected，9.41s；未知节点证据漏检 |

修复第四类 P1 前，中间快照 a4914744f702 的独立集 41 passed，99.31s；指定定向集 196 passed，151.49s。中间扩大 836 passed，968.98s（16:08）；其运行期间继续源码审计发现并修复 Workflow Fence 缺口，因此不把该进程结果当作最终磁盘源码验证；最终全部重新执行。

再一轮中间快照 a8013d830774：44 passed，113.00s；指定定向 196 passed，135.93s。祖先反例在审计尾项检查中暴露后，已核实 PID/父进程命令行并终止本助手启动的中间扩大进程（无最终汇总，不计通过），停止其自动后续全量；最终仍会完整重跑所有范围。未终止其他进程或跳过最终用例。

中间快照 4f87d10b9f96：46 passed，110.24s；指定定向 196 passed，154.25s。瞬时 profile 反例暴露后终止本助手的中间扩大。中间快照 b37aaf77f191：48 passed，127.02s；指定定向 196 passed，157.72s；最后 provenance 捕获反例暴露后同样终止本助手的中间扩大。两次均核对了 pytest PID 和父 PowerShell 的本任务专属日志命令；没有全量汇总，不计为最终通过，未触及其他进程。

最终源码 edf59d1c5771 的完整命令（按序执行，不并发运行测试）：

```powershell
python -m pytest -q tests/components/planner/test_graph_revision_audit.py --tb=short
python -m pytest -q tests/components/planner/test_graph_revision_commit.py tests/components/planner/test_planning_commit.py tests/components/planner/test_planning_commit_runtime.py tests/components/planner/test_planning_commit_audit.py tests/contracts tests/architecture --tb=short
python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short
python -m pytest -q --tb=short
```

| 最终集 | 结果 |
| --- | --- |
| 独立对抗 | **50 passed，123.79s** |
| 用户指定定向/架构 | **196 passed，131.28s** |
| 扩大 | **845 passed，1050.17s（17:30）** |
| 全量 | **1460 passed，1 warning，1142.90s（19:02）** |

最终输出保存在系统临时目录的 S02-03-audit-final-adversarial/targeted/broad/full.log。中间失败不会被最终结果覆盖为“始终通过”；原实施报告 1410 通过不算本轮最终结果。最终测试后已重算 11 文件源码聚合 SHA-256，与上述 edf59d1c57715d22bad5ba832606bf15fbe532df61e2f31035c9d535c80d1164 完全一致。git diff --check 通过（仅 Git 行尾转换提示，无空白错误）。HEAD 仍为 1b508748535b211afcb0546ae2c216a83daeca47，暂存区为空，工作区为 7 修改 + 6 新增，全部属于入场实现、五个生产文件的审计修复、新增对抗测试和本报告；无范围外变更。全量唯一 warning 是既有 PyPDF2 弃用提示，没有失败、跳过或放宽计时用例。

### 7. S03 前置条件及本轮边界

S03 必须从唯一 ledger 的 graph_revision Record 读取完整候选及源 commit/Run/Graph/Plan/策略版本、provenance、proof、bindings；先验证记录正文和接受链，再重新取得当前权限/Basis/scope、正式 Plan/GraphVersion、执行收据、checkpoint 和审核/控制状态。正式 GraphVersion CAS、物化/激活原子交接、幂等恢复与执行前缀复用应由 S03 明确建立；历史 ACCEPTED/PROVEN 或单独 outbox 事件都不能直接授权执行。

本轮不改写旧接受记录。修复前签发的历史 graph_revision 即使具有同名 proof version，也不能当成按修复后代码完成重验；同 key 回执仍仅报告历史事实。S03 必须执行当前验证策略，不能依据版本字符串或幂等回执省略重验。

若要超出当前无控制 DAG 范围，先补齐正式控制历史和可证明的控制区域边界，明确 branch/loop/join/review 的 safe-cut 合同；不能在物化时忽略本阶段的控制拒绝策略。

本轮不实现 S03、不消费 outbox，不修改正式 ADR/生产配置，不部署、不升级业务数据库，不 Commit/Push/Merge。修复与新增验收测试全部保持未提交。冻结只针对经验证的最小 DAG 接受基线，不代表物化/激活或生产部署已经验收。

---

## 附录：来源清单与合并说明

| # | 原文件 | 日期 | 性质 | 原文大小 |
|---:|---|---|---|---:|
| 1 | `PR-S02-01-PlanningCommitAuthority实施记录-2026-10-13.md` | 2026-10-13 | 实施记录 | 7374 字节 |
| 2 | `PR-S02-01-独立代码级验收-2026-10-13.md` | 2026-10-13 | 独立代码级架构验收 | 2195 字节 |
| 3 | `PR-S02-02-DurablePlanningCommit实施记录-2026-10-14.md` | 2026-10-14 | 实施记录 | 7942 字节 |
| 4 | `PR-S02-02-独立代码级架构验收-2026-10-14.md` | 2026-10-14 | 独立验收（含 Freeze 冻结验证） | 20004 字节 |
| 5 | `PR-S02-03-GraphRevisionCommit实施记录-2026-10-14.md` | 2026-10-14 | 实施记录 | 13030 字节 |
| 6 | `PR-S02-03-独立代码级架构验收-2026-10-15.md` | 2026-10-15 | 独立代码级架构验收 | 26086 字节 |

> **合并规则**：正文逐字保留，仅做两类机械处理：(1) 标题层级下移一级，原文 H1 由本节标题替代；(2) 指向已合并 / 已归档文档的相对链接改写为新文件名。结论、数字、命令与代码块未改动。
>
> **完整性校验**：合并时对每篇原文做归一化比对（忽略标题层级与链接目标），本篇 6 篇全部一致。
>
> **恢复原件**：原文件已从当前目录移除，完整内容保留在 Git 历史中。整理提交前用 `git checkout HEAD -- "docs/开发记录/<原文件名>"`；提交后用 `git checkout HEAD~1 -- "docs/开发记录/<原文件名>"`。

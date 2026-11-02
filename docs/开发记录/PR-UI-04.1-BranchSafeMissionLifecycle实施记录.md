# PR-UI-04.1｜Branch-safe Mission Lifecycle Projection

日期：2026-11-02。最终状态：**SELF-TESTED**，等待独立复验。

## 1. 入场与失败复现

入场分支 master，HEAD 与 origin/master 均为 `f6e3e4c7289f134682095b617c470194eb60ec4e`。工作区、暂存区、untracked 均为空。本轮没有覆盖原有修改，也没有 Reset、Clean、Commit、Push、Merge 或部署。

先新增 `apps/agent/tests/test_branch_safe_mission_lifecycle.py` 的真实 HTTP / SQLite 失败测试，运行失败后才改生产代码。使用生产组合、可信用户中间件、真实 WorkflowStore、RunExecutionCoordinator 和测试 Agent：

1. 创建 Mission，等待初始 Run 的真实 coordinator Task 完成，确认来源 Run 与兼容 Mission 均为 COMPLETED。
2. 暂停 coordinator.submit，并发提交不同 clientRequestId 的两个 successor。
3. 从 WorkflowStore 读取完整 Run，确认两个 PENDING；通过真实 GET 查询，两个 canCancel=true。
4. 携带原 runtimeRevision 调用取消接口，得到 409。来源 Mission 仍 COMPLETED，目标 Run 仍 PENDING，但目标取消信号已为 true。

原始证据保存在 `C:\Users\LZX\AppData\Local\Temp\pr-ui-04.1\before`：

- `pending-cancel.log`：1 failed，真实 API 返回 409。
- `pending-cancel-snapshot.json`：取消前的 Mission、来源完整 Run、两个分支完整 Run、capabilities、取消信号，以及响应和取消后完整状态。

根因是 cancel 在持久化 Run 之前置位信号，并调用 MissionManager.mark_cancelled。Mission 状态机拒绝 COMPLETED → CANCELLED，导致命令失败且留下部分副作用。没有靠删除状态机限制掩盖故障。

## 2. 生命周期回调审计

| 回调 | 原问题 / 实际调用 | 本轮收敛 |
| --- | --- | --- |
| mark_running | 执行启动、旧工作流适配路径直接迁移 Mission | 有 Run 时按真实集合刷新 |
| mark_running_for_new_run | 仅为新 Run 特判重开终态，按回调写 RUNNING | 校验所属 Mission，统一刷新集合 |
| mark_waiting_review | ACG interrupt、Planning application 等直接写 WAITING_REVIEW | 不覆盖其他仍运行分支 |
| mark_completed | ACG 完成先写 Run 生命周期，再无条件迁移 Mission | 不被其他分支的 CANCELLED/FAILED 阻断 |
| mark_cancelled | cancel 中在 Run 持久化前执行，可能失败 | cancel 不再调用该回调，存储事务直接维护汇总 |
| mark_failed | Review 拒绝、旧步骤失败路径直接迁移 Mission | 不影响同 Mission 其他活跃 Run |
| mark_failed_for_run | Recovery / 重启失败路径通过 latest Run 选择写入者 | 删除 latest 作为控制者的逻辑，所有真实 Run 共同参与 |
| mark_retrying | 内部恢复回调 | 同样统一刷新，不新增分支权威 |

`workflow_runtime.py`、`acg_execution.py`、`runtime_recovery.py`、`review.py`、`planning_application.py` 的调用已逐一检查。部分回调发生在 Run 保存前，部分发生在保存后；因此不能依靠回调顺序得到正确的多分支汇总。本轮在共同持久化边界处理，不复制多套回调算法。

旧 mark_failed_for_run 的 latest 保护只能减少旧失败覆盖新 Run，无法表达多个活跃分支，不能推广成隐式 Branch Head。MissionManager._task 原来直接使用传入对象，执行协程长期持有的 Mission 快照可能覆盖新的状态和字段；现在按 missionId 重读存储快照。Memory Store 也改为保存/返回副本，防止绕过持久化边界修改内部 Mission。

## 3. 最终状态语义

WorkflowStore.RuntimeRunRecord 仍是每个执行实例的生命周期权威。Mission.status 只表示所有已保存 Run 的兼容汇总，不参与 Run 执行授权，不增加 currentRunId、Mission Branch Head 或状态管理器。

统一汇总顺序如下，取实际集合中第一个存在的状态：

```text
RUNNING > RETRYING > PLANNING > WAITING_REVIEW > PENDING
        > FAILED > CANCELLED > COMPLETED > SUPERSEDED
```

含义：只要存在活跃工作，兼容 Mission 不得因其他分支终止而变成终态。多个活跃状态共存时，优先显示正在执行/恢复/规划的工作，再显示审核或已接受的待执行工作；全部终态后保留失败、取消的可见性。SUPERSEDED 历史只有在没有其他状态时决定汇总。来源关系不被当成 supersession。

汇总包含已保存的历史 Run，软删除不篡改执行事实；终态来源 FAILED 与后继 COMPLETED 并存时 Mission 可为 FAILED，这只是兼容汇总，不能阻止后继命令或修改真实 COMPLETED Run。没有 Run 的旧 Mission 仍使用原 StateMachine；COMPLETED → CANCELLED 等非法终态迁移仍然拒绝。

汇总使用已有 runs 状态和 tasks JSON，无新增持久化事实、Schema、表、索引或授权合同。Run 创建、普通 save_run、save_run_with_events、Graph patch 都经过相同保存边界。Legacy save_mission 也在事务中重算 status，避免过期对象覆盖已推导的生命周期状态。

## 4. 并发与取消原子性

SQLite 在 BEGIN IMMEDIATE 的同一连接、同一事务内保存 Run、更新新鲜 Mission 的 status/updated_at，并写既有 lifecycle outbox。汇总查询读当前真实 Run 集合，更新从当前 tasks payload 出发，保留其他 Mission 字段。不同 SQLite Store / 线程 / 进程写入由数据库事务串行化，不依靠单进程 Mission 锁。

Memory Store 复用既有 RLock；save_run 委托现有 save_run_with_events 事务语义，扩展回滚快照至 Mission。Run、Mission、终态索引和 outbox 一起回滚。Graph patch 也扩展相同回滚范围。get_run / get_mission 读取也进入同一锁，防止读到 Run 已写而 Mission 尚未汇总的事务中间状态。

取消顺序：

1. 进入既有 Run 锁，重新读取完整 Run，检查 expectedRuntimeRevision 和非终态条件。
2. 以副本构造 CANCELLED、生命周期字段和一条 RUN_CANCELLED Trace，保留已完成步骤及已有 Trace。
3. `save_run(..., expected_snapshot=latest)` 在存储事务内比较完整原始记录，然后提交 Run、Mission 汇总和 outbox。除了版本冲突，同版本下并发进度变化也拒绝，避免覆盖完成事实。
4. 事务成功后才置位该 Run 的协作取消事件。持久化/CAS 失败不置位信号，不写半条 Trace，也不改变其他 Run。
5. Identity outbox/实时通知在提交后重试或记录错误，不把已提交取消变成返回失败的命令。这里只处理通知失败；没有捕获 InvalidStateTransition 后忽略 Mission 迁移。

调度侧继续使用既有协作取消信号和持久化终态检查；晚到的活跃快照受原 Store 终态保护。没有强制终止模型、工具或系统进程，没有改 coordinator 的既有行为。

内部重复取消已取消 Run 直接返回已保存记录，不增 Trace。公开 API 保留 PR-UI-04 的终态 409 合同：丢失响应后用同一 Run/版本重发不会新增副作用，GET 可确认原取消已提交；不自动改 ID、版本或重新执行。测试检查完整持久记录相等。

## 5. Superseded Delete 语义

选择沿用现有 API、Memory/SQLite 软删除合同：明确 superseded 的终态 Run 可以软删除。它只隐藏列表记录，不删除步骤、Trace、来源关系或证据。

Python 能力投影在 Mission active、可信 owner/tenant、当前 Mission 写权限充分时返回 canDelete=true；其他执行/恢复能力继续关闭。缺写权限返回 false，DELETE 也拒绝。仅有 supersededByRunId 但实际仍活跃的异常快照不开放删除。

前端校验允许 superseded 的 canDelete，但仍拒绝 canCancel/canRerunSuccessor 等变更能力，并要求 canDelete 对应真实终态。既有 Run Picker 的删除链直接复用，不增加 UI 或授权链。Memory/SQLite 原有 SUPERSEDED 软删除约束保留，不改数据库状态机。

## 6. 修改范围

| 文件 | 必要性 |
| --- | --- |
| agentOS/src/support/stores/_policy.py | 唯一纯函数定义兼容汇总规则 |
| agentOS/src/support/stores/workflow_store.py | 明确原子汇总与可选完整快照 CAS 合同 |
| memory_workflow_store.py、sqlite_workflow_store.py | 同事务保存、聚合、回滚和 CAS，阻止过期 Mission 状态覆盖 |
| components/mission_manager/service.py | 新鲜 Mission 读取、统一回调，删除新 Run/最新失败的重复特判 |
| runtime/workflow_runtime.py | 取消先提交后信号，通知失败与命令结果分离 |
| agent/app/execution/run_capabilities.py | superseded 软删除能力与实际命令一致 |
| frontend/workbench/runtime/runCapabilities.ts | 前端校验接受合法删除，仍拒绝非法执行能力 |
| agent/tests/test_branch_safe_mission_lifecycle.py | 真实 HTTP/SQLite 多分支、执行、审核、故障注入、重放及 Delete |
| agentOS/tests/support/test_branch_safe_mission_projection.py | Memory/SQLite 汇总、全部回调、过期对象、CAS/回滚与重启 |
| agent/tests/test_run_capability_projection.py | 状态矩阵明确 canDelete 合同 |
| frontend 的 capabilities fixture、runCapabilities.spec、MissionLifecycle.integration.spec | 真实 Host 集成与独立分支删除/控制回归 |

没有改 Mission Launch、幂等身份、Runtime Planner 决策内核、Review/C2 授权规则、前端布局、Java、后端路由或请求格式。

## 7. 对抗测试与阶段证据

`after/initial.log`：32 passed，首先证明原始 Pending 取消、已有取消互斥和 Store 合同恢复。

`after/adversaries-3.log`：106 passed，2 warnings。包含首次完整新增分支场景与 Store 对抗。最初失败测试只抛 Agent 错误，原有 Planner 会选择暂停审核；后续使用真实 Planner abort 决定构造确定性终态失败，并精确断言 ACGSuperstepError 和完整 FAILED 记录，没有修改生产 Planner。

`after/projection-planner.log` 为探索回归，遇到既有子进程 fixture 的导入错误后停止该次测试进程，日志保留。`after/planner-first-error.log` 明确根因是 test_react_loop 不在子进程 PYTHONPATH。最终命令传入绝对 PYTHONPATH，未改测试、deadline、excludes 或环境缓存。

第一轮完整 Planner 回归 `release/planner.log` 为 209 passed / 1 failed：新增汇总路径写 Mission outbox 时使用紧凑 JSON，旧 save_mission 使用带空格 JSON；两者规范化哈希相同，但既有 outbox 按原字符串检查，误报 payload conflict。已统一新增汇总路径与原 save_mission 的序列化格式，不放宽 outbox 去重约束。新增“汇总后原样 save_mission 不增加事件、不误报冲突”Memory/SQLite 回归；`after/outbox-serialization-fixed.log` 为 44 passed，包括原失败 Planner 用例。旧 `release` 结果和停止的组合门禁保留，最终证据重新生成到 `release-final`。

`release-final` 随后全部通过：后端 203、Runtime/Store/Architecture 527、Planner 210、前端全量 1053、前端定向 114、类型检查和构建。最终并发复核另写确定性读取测试：暂停 Memory 的 Mission 汇总后，旧 get_run/get_mission 无锁读取能返回事务中间状态。`before/memory-read-atomicity.log` 保留 1 failed 的反例；只给两个 getter 加既有锁后，`after/memory-read-atomicity-fixed.log` 为 44 passed。该修复后的全部同快照门禁重新运行在 `verified`，不拿上一次全绿结果替代最终验证。

覆盖 A–E：

- 已完成来源 + 并发创建两个 PENDING successor；两个 canCancel；取消 A 后 B 完整记录不变且仍可取消。
- 实际启动两条 ACG 执行，由 asyncio.Event 控制节点到达与释放；A 完成时 B 仍 RUNNING；B 取消后 A 完整记录不变。
- A 取消后 B 进入真实 WAITING_REVIEW、checkpoint 与 Review Authority；审批 B 后完成，A 完整取消记录不变。
- 完成→失败、失败→完成、审核→完成、完成→审核四个次序，逐次检查已经终结分支完整记录不变。
- 真正不同 SQLite Store 并发提交两个终态、重开数据库、独立 Python 子进程读回完整 Mission/Run；包括取消记录。
- 同版本快照冲突、过期 runtimeRevision、持久化失败、outbox 事务失败、提交后 Identity 通知失败；检查完整 Run、Mission、outbox 和信号，无部分副作用。
- 全部七类生命周期回调的过期 Mission 对象、无 Run 时原有状态机终态限制、Memory/SQLite 相同汇总矩阵。
- superseded Delete 实际 HTTP、写权限撤销、完整证据保留、Store 原约束与前端实际 Workbench Host 集成。

## 8. 最终同源码快照门禁

最终结果以 `C:\Users\LZX\AppData\Local\Temp\pr-ui-04.1\verified` 为准，阶段日志不替代最终门禁。

| 门禁 | 结果 |
| --- | --- |
| Python 后端定向（分支/API/Capabilities/Review/C2/Revision/Trusted Auth） | 203 passed，14 warnings，无失败/跳过 |
| MissionManager + 全 support Memory/SQLite + 全 Runtime + Architecture | 528 passed，2 warnings，无失败/跳过 |
| 相关 Planner / Materialization / Activation / Handoff / Permit 扩大回归 | 210 passed，无失败/跳过 |
| 前端全量 | 143 files / 1053 tests 全通过 |
| 前端 MissionWorkspaceView / MissionLifecycle 集成 / Capabilities / StatusBar / Continuity 定向 | 6 files / 114 tests 全通过 |
| TypeScript | exit 0 |
| Web Build | exit 0，包含 vue-tsc 与 Vite Web 构建 |
| git diff --check / untracked 文本核对 | 工作区与暂存区检查 exit 0，3 个新增文本文件无尾随空白/缺失末尾换行 |

Python 组合门禁使用原 `apps/agentOS/pytest.ini`、`--rootdir=.`，绝对路径加入 agentOS/src、agentOS、agent、tests/runtime、tests/components/planner、agent/tests；同时给子进程设置 PYTHONPATH。faulthandler_timeout=90 仅打印诊断栈，不改变既有测试 deadline。没有 Disabled、删除测试、跳过真实存储或缩小原断言。

三个 Python 分组分别完整执行：

- `backend.log`：test_branch_safe_mission_lifecycle、test_run_action_capabilities、test_run_capability_projection、test_run_authority_c2、test_agentos_v2_api、test_agentos_v2_workspace_api、test_mission_revision_decisions、test_internal_service_auth，以及 C2 HTTP / Permit / Dispatch / Human Review / Dispatch Projection / Admission。
- `runtime-store-architecture.log`：整个 `apps/agentOS/tests/support`、`apps/agentOS/tests/runtime`、`apps/agentOS/tests/architecture`，包括原 WorkflowStore Memory/SQLite 合同和新增 MissionManager 对抗测试。
- `planner.log`：test_graph_activation、test_graph_materialization、test_graph_revision_commit、test_planning_commit_audit、test_planning_commit_runtime、test_graph_handoff、test_execution_permit、test_execution_permit_audit。

前端执行 `npm test -- --maxWorkers=2 --minWorkers=1`，定向选中 MissionLifecycle.integration、MissionWorkspaceView、runCapabilities、lifecycleProjection、WorkbenchStatusBar、WorkspaceContinuity 六个文件；另执行 `npx vue-tsc -p tsconfig.json --noEmit` 和 `npm run build:web`。

三个 Python 分组共 941 项通过。warning 保留原日志，主要为既有 Starlette/httpx、Pydantic Config 弃用及 tuple/list 序列化提示，没有过滤 warning 制造通过。

最终门禁前，按 `git ls-files --cached --others --exclude-standard apps` 收集 2227 个路径，排序去重，逐文件 SHA-256，JSON manifest 为 `verified/source-before.json`。范围包含全部 apps 生产及测试源码。

- HEAD：`f6e3e4c7289f134682095b617c470194eb60ec4e`。
- manifest SHA-256：`E083E9B6992DCBC93CAC1697953F277E762C7212487F8D83BB8BE79288BC93F2`。
- 验证后重新生成 `verified/source-after.json`，2227 个路径的差异为 0，manifest SHA-256 与上述完全一致；详见 `verified/source-verification.json`。
- 最终 HEAD 仍为入场基线，暂存区为空；仅本轮源码、测试与本报告有改动。
- 本报告在 docs 中，不改变上述 apps 源码快照。

## 9. 未解决问题与独立复验建议

兼容 Mission.status 只提供确定性汇总，无法在一个枚举中表达全部分支；具体运行情况必须查看各 Run。历史失败仍可能使全部终态后的 Mission 汇总显示 FAILED，这是明确的汇总策略，不影响独立 Run 的结果或权限。没有声称唯一“当前执行分支”。

现存通用 save_mission 并没有成为全面的 Mission 元数据 CAS；本轮保证生命周期投影原子性，MissionManager 回调重读快照，Run 状态更新不覆盖 Mission 其他字段。并发用户编辑其他 Mission 元数据的通用事务设计不在本轮扩展范围。

汇总按 Mission 的既有 Run 状态集合计算，成本随该 Mission 的 Run 数量增长，未增加持久化计数或隐式 Branch Head。本轮没有针对超大历史 Mission 作性能基准，也没有为性能推断省略真实状态核对。

取消与已经在执行的工具/模型之间仍遵循原有协作取消边界；正在进行的节点可以收尾，取消后不能恢复该 Run 的活跃执行状态。Identity / SSE 通知可能暂时延迟，持久 outbox 和 WorkflowStore 是恢复依据。

本结果不代表远端 CI、真实模型、浏览器视觉或生产部署验收。本轮只运行隔离的临时数据测试，无外部不可逆任务。

**SELF-TESTED**。原始故障已通过失败日志和完整状态快照证明，并通过同一最终源码快照上的全部门禁。取消一个 Run 不再通过 Mission 级终态迁移决定成败，其他分支仍可合法执行、完成、审核或取消；Run 历史和原有状态机约束保留。

本轮未 Commit、Push、Merge 或部署；等待独立复验，不自行宣布 ACCEPT。

# PR-UI-04｜Run Authority & Action Capabilities 实施记录

日期：2026-11-02。最终状态：**SELF-TESTED**；不代表独立 ACCEPT。

## 1. 入场与修改保护

- 分支 `master`，入场 HEAD、`origin/master` 均为 `1d5969cf97c0e6d028434016c5c530a75fb027a5`。
- 入场暂存区、untracked 为空。已有用户修改是删除 `docs/架构设计/架构图/知弈AgentOS-ACG架构图.png`（HEAD 中 220008 字节）；保持原样，不属于本轮清理范围。
- 重新读取 PR-UI-03 实施记录并沿当前源码核验，未使用历史设计建议代替运行合同。
- 本轮未 Reset、Checkout、Stash、Clean，未提交、推送、合并、部署，未修改业务数据。

## 2. 真实分支语义与决策

运行状态权威是 WorkflowStore 的 RuntimeRunRecord。Identity Graph / Workspace 是可延迟的身份投影；不能以其更新时间、选中标记覆盖运行状态。

| 路径 | 真实语义 | 是否替代来源 Run |
| --- | --- | --- |
| 初始 Mission / Run | 创建独立运行快照及幂等身份 | 无来源 |
| POST missions/{missionId}/runs | 终态来源创建新 Run，保留来源链 | 否 |
| retry_failed_step / successor_run | 校验已提交输出、失败步骤与版本，再创建后继 | 否 |
| public current_run | 本轮关闭公开原地重试，返回 409 | 不再开放 |
| Runtime Planner 内部恢复 | 原有 reuse_source_run 内部恢复权威 | 保留内部合同 |
| Mission Revision 后继 | 旧 Run 取消后，按修订决定创建后继 | 来源关系，不等于 supersession |
| Review rerun | 原有 Review Authority 创建后继 | 来源关系 |
| Graph patch | semantic_revision 与 save_graph_patch_transition 原子保存来源 SUPERSEDED、双方替代关系及 outbox | 是 |
| Cancel / Delete / Review / Formal | 当前 Run、当前权限和对应原有权威重新检查 | 不根据 UI 能力授予权限 |

同一 Mission 可以有多个活跃 Run，同一 sourceRunId 可以有多个不同 successor。SQLite `save_prepared_run_once` 使用 BEGIN IMMEDIATE 与请求键/指纹保证同一请求重放；它没有“同一来源只能一个后继”的约束。真实临时 SQLite 并发测试和重新打开数据库、独立 Python 进程读回测试证明了这一点。

因此不增加单一 currentRunId，不增加 Mission Branch Head，不以 selected/latest 作为授权。parentRunId、sourceRunId 表示来源；supersedesRunId、supersededByRunId 才表示显式替代。MissionRunRevision.status=CURRENT 仍只表示语义修订状态；WorkspaceRunSummary.isActive 保持旧的选中含义。

## 3. Action Capabilities 完整合同

Run 查询及现有 Workspace 每个 Run 行增加可空 `actionCapabilities`。旧服务端没有字段时，前端关闭相关操作；Java 只透传白名单 DTO，不创造能力。服务端只计算，不持久化，不接受客户端提交的 capability 作为权限。

```typescript
interface RunActionCapabilities {
  schemaVersion: 1
  missionId: string
  runId: string
  runtimeRevision: number
  status: string
  isExecutionActive: boolean
  isSuperseded: boolean
  lineage: {
    parentRunId?: string | null
    sourceRunId?: string | null
    supersedesRunId?: string | null
    supersededByRunId?: string | null
  }
  canInspect: boolean
  canDiscuss: boolean
  canCancel: boolean
  canReview: boolean
  canExecuteFormalAction: boolean
  formalActions: Array<'materialize' | 'activate' | 'handoff' | 'permit' | 'dispatch'>
  canResolveToolApproval: boolean
  canAnswerPlanner: boolean
  canCollaborate: boolean
  canRetrySuccessor: boolean
  retryStepId: string | null
  canRerunSuccessor: boolean
  canDecideRevision: boolean
  canApplyRevision: boolean
  canDelete: boolean
  unavailableReasons: Array<{ action: string; code: string }>
}
```

原因使用定型列表而非任意字典，遵循现有 Java 投影白名单边界。原因包括 TRUSTED_SCOPE_UNAVAILABLE、IDENTITY_SCOPE_CONFLICT、UNKNOWN_STATUS、RUN_SUPERSEDED、MISSION_NOT_ACTIVE、RUN_NOT_ACTIVE、SNAPSHOT_CHANGED、AUTHORITY_DENIED、AUTHORITY_UNAVAILABLE，以及 Review / Formal / Recovery 的证据不足原因。

能力按各自条件计算：

- Inspect / Discuss：可信用户、租户、冻结 owner 与原有语义读权限匹配。
- Cancel：真实 active 状态、原有写权限；不要求先同意 Copilot 任务协作。
- Review / Planner answer：真实 checkpoint、Run/review payload、原有状态引用校验、具体 subject；不会因为能 Cancel 就能 Review。
- Formal：原有 require_c2、当前语义 basis、Planning/Materialization/Activation/Handoff/Permit/Dispatch 的现有只读校验共同证明下一步。
- Tool approval：实际运行的 Permit Run、现有审批服务中属于该 Run 的 pending 事实。
- Retry successor：真实失败步骤，复用 Recovery Coordinator 的 validate_only 校验；返回确切 retryStepId 与源版本。Permit 执行的内部恢复不能安全等同公开 partial successor，保持不可用并给出原因。
- Rerun successor：可用终态来源的新快照提交，实际命令仍执行原有准备和语义检查。
- Revision decision / apply：原有语义快照、决定收据、目标修订、用户和租户；取消后才开放符合条件的 apply。
- Delete：终态 Run 与现有 Mission 写权限。

未知状态、缺 owner/租户证据、身份冲突、明确 superseded 或查询过程中运行版本变化均关闭变更能力。显式 superseded 保留查看/讨论，不能恢复为原地执行目标。

## 4. 后端权威与命令路径

可信上下文仍来自原有 InternalServiceAuthMiddleware / Java trusted forwarder，不从请求布尔值推断用户。租户为空只在现有 semantic authority 能证明 `__unscoped__` 命名空间时兼容，缺字段本身不能授予权限。

`app/execution/run_capabilities.py` 是只读投影器；不创建新执行状态机或授权记录。GET Run 从 WorkflowStore 读取状态和同版本能力；Workspace 逐 Run 独立计算，不能把 selected 行的能力套给其他行。Identity 普通延迟不覆盖运行状态；明确 Mission 身份冲突或删除事实会关闭能力。

命令仍重新经过原有 owner/tenant、Mission write、Runtime / Review / C2 / Revision Authority。公开原地重试关闭，但内部 Planner 恢复未改。旧请求的 operationId、clientRequestId、幂等键、请求指纹保持原合同。已接受 successor 的同身份重放先返回原结果，不因之后来源状态改变而丢失已提交任务。

Cancel 可携带可选 expectedRuntimeRevision；Java 校验非负并透传，Python 在既有 Run 锁内、写取消信号前比较版本。终态公开 Cancel 返回原有固定 409 文本；内部重复 CANCELLED 返回当前记录，不追加历史 Trace。其余 Runtime 修改仅限这一处局部检查，未重构 Scheduler、Planner 或 ExecutionBackend。

没有新增持久化事实、表、索引或 Schema 迁移。能力未写入 executionState；WorkflowStore 事务及真实运行权威保持原样。

## 5. 前端恢复与冗余清理

`runCapabilities.ts` 校验 schema、Run/Mission、版本、状态、所有布尔字段、formal action 和状态一致性；lifecycleProjection 在 Run detail 与 Workspace 中选择匹配的新事实。同版本能力冲突时关闭操作，明确替代证据不会被旧 detail 反向抹除。

WorkbenchContext 只派生已有能力，没有新增 Store。停止、Review、Formal、Tool approval、Planner answer、Revision、Delete 分别判断。终态来源可创建新 successor，但不把来源重新变成运行目标。停止会捕获版本并在对话框返回后检查选中身份；后续刷新真实事实，不拼接乐观状态与旧能力。

恢复操作在 await 前捕获能力、失败步骤和版本。过期目标不会偷偷改步骤、改成完整重跑或换身份；不确定请求继续用原快照恢复。Copilot proposal 也必须匹配其原始 Run 与版本。

保留既有 FormalExecutionControls 链。修复一个真实 UI 缺口：没有 C2 formalControl 的普通 active Run，拥有 canCancel 时也能显示并触发停止按钮。单独区分任务执行同意和安全停止；前者仍约束正式执行、Review、工具操作，不能意外隐藏合法停止。

界面显示 Selected、Latest created、Active Runs、Lineage；不再制造 Current 执行权威。Editor Follow、canonical Artifact 身份、Run URL、请求代次、KeepAlive/双视图连续性和 SSE 清理仍受现有集成测试约束。RunProgressEditor / Registry 无需创建平行控制链，沿现有 Context / EditorGroup 传递即可。

按用户追加要求清理本轮相关冗余：删除空置 currentRunId/isCurrent/恒定缺失标记、无用 status 判断和 import、未调用的投影辅助函数；复用已读取的 formal control，删除重复读取与不可达 catch。未删除不相关兼容模块、视觉布局或用户文件。

## 6. 失败反例与对抗证据

证据目录：`C:\Users\LZX\AppData\Local\Temp\pr-ui-04`。失败日志保留，未删除缓存或改写测试报告。

1. `pr-ui-04-terminal-cancel-before.log`：终态重复 Cancel 原来返回成功并可能重写 Trace；修复后命令拒绝、历史记录不变。
2. `pr-ui-04-legacy-cancel-before.log`：真实 Host 集成中 canCancel=true，但普通 Run 找不到停止按钮；修复后实际点击停止按钮并检查源 Run/revision，独立分支能力不受影响。
3. `final/python.log` 保留中间扩大回归的 9 failed / 558 passed：固定错误文本兼容、C2 关闭时历史 GET、读查询新增写权限探测导致的六个旧回调断言，以及旧 Desktop blanket 子进程断言。逐项修复后才重新运行最终全门禁，不以小范围绿灯冒充扩大回归。
4. 原六个读权限合同保留撤权/恢复的拒绝与成功断言；隔离 Run body 的只读 callback，能力允许探测原有 write 权限但不得写入。新增完整 Run 记录查询前后相等断言。
5. 中间 Java 新断言误认非法输入应为 400，现有全局合同实际为 422；已改为精确 422，未放宽接受范围。

新增 Python 覆盖真实 HTTP/生产组合与临时 SQLite、同来源不同后继并发、同请求重放、重开数据库与独立进程、Memory/SQLite 状态矩阵、租户/用户/读写分离、伪造能力、来源与 supersession 区分、迟到版本、真正失败 ACG 的部分恢复、真实 Review、C2 完整阶段与旧语义修订拒绝。GET 能力不创建 Run 或正式授权事实。

新增/扩展前端用真实 Router、Pinia、WorkspaceViewHost、Registry、EditorGroup、Graph、Observation 与 SSE 测试多活跃分支、实际 Cancel 点击、动作不互相授权、缺失/冲突/旧版能力、superseded 禁止、恢复目标不得静默漂移。保留原连续性、Follow、canonical Artifact、丢失响应重放、URL/代次隔离测试；集成清理断言检查无残留 SSE。

### 已存在的 Desktop 架构断言冲突

扩大回归原测试一律禁止 Electron 出现 child_process，但 HEAD 已由 `49e02578` 引入 LSP、Git、搜索、诊断四个 IDE helper。本轮未改 Desktop 生产源码，基线差异证据在 `pr-ui-04-desktop-baseline-diff.log`。

保留原测试名称和“不成为 Agent 执行权威”的边界，改为精确核查四个既存 helper：命名 spawn import、禁止 shell、固定命令形状、时限/输出边界、禁止携带 Run/Mission/Permit/operation 身份、禁止通用 runner 导出；同时检查 13 个 IDE IPC 的 renderer owner 和 root 校验。强化禁止引入 WorkflowStore / ExecutionRuntime / NodeRunner / ACGExecutionGraph 等权威。新增未审查进程入口、向既有 helper 注入 Run 身份两项拒绝反例，不是无条件允许子进程。额外运行四个 helper 的 26 项真实功能测试。

## 7. 最终同快照验证

最终证据在上述目录的 `release` 子目录；`delivery`、`final` 是保留的中间结果，不作为本轮最终成功凭据。

| 门禁 | 最终结果 |
| --- | --- |
| Python 后端定向 + WorkflowStore 合同 + Runtime/Architecture 扩大回归 | 570 passed，14 warnings，无失败/跳过 |
| Java Gateway/Projection/Controller/可信上下文/架构 | 70 tests，0 failures/errors/skipped |
| 前端全量 `npm test -- --maxWorkers=2 --minWorkers=1` | 143 files / 1051 tests 全通过 |
| `npx vue-tsc -p tsconfig.json --noEmit` | exit 0 |
| Desktop 四个既存 IDE helper 功能回归 | 26 passed，无失败/跳过 |
| 前端最终定向 | 18 files / 218 tests 全通过 |
| `npm run build:web` | exit 0，包含 vue-tsc 与 Vite Web 构建 |
| `git diff --check` 与未跟踪文本检查 | 工作区及 index 检查 exit 0；12 个新增文本文件无尾随空白/缺失末尾换行 |

Python 使用 `-c apps/agentOS/pytest.ini --rootdir=.`，显式绝对 pythonpath 指向 agentOS/src、agentOS、agent、runtime tests；组合运行避免 pytest 根目录导致错误 collection。`faulthandler_timeout=90` 仅打印诊断栈，不修改测试 deadline。包含 test_run_action_capabilities、test_run_capability_projection、test_run_authority_c2、v2 API/Workspace、Revision、Internal Auth、C2 HTTP/Permit/Dispatch/Human Review/Projection/Admission、WorkflowStore contract 与完整 runtime、architecture 目录。

Java 执行 RunActionCapabilitiesProjectionTest、RunProjectionBoundaryTest、WorkspaceProjectionMapperTest、WorkspaceProjectionSerializationTest、AgentOsRunControllerTest、AgentOsMissionControllerTest、AgentOsReviewControllerTest、AgentOsGatewayServiceTest、QueryProjectionArchitectureTest、MissionProjectionArchitectureTest、TrustedUserContextForwarderTest。

前端定向包含 src/workbench/runtime、MissionLifecycle.integration、MissionWorkspaceView、FormalExecutionControls、AcgCopilotPanel、MissionRevisionNotice、WorkbenchStatusBar、WorkspaceContinuity。没有删除测试、Disabled、改 excludes、降低安全断言或调整既有 deadline。

Python 14 条 warning 包含既有 Pydantic tuple/list 序列化提示，保留原日志，不算无 warning。构建输出及 warning 以 release/build.log 为准。

## 8. 源码快照与最终范围

在最终所有门禁开始前生成 `release/source-before.json`：`git ls-files --cached --others --exclude-standard apps`，按路径排序去重，逐文件 SHA-256，缺文件写 MISSING，再序列化 JSON。范围包含全部 apps 源码与测试，也包含架构检查所读取的 Desktop 基线文件。

- 文件数：2225。
- manifest SHA-256：`A0BBE0654D25FCA67C80BFB3026D0464605A7E0316B89BC8A5FAF312A88A9E97`。
- HEAD：`1d5969cf97c0e6d028434016c5c530a75fb027a5`。
- 验证后重新生成 `release/source-after.json`：2225 文件，逐路径差异 0，manifest SHA-256 与上述完全相同。核对记录为 `release/source-verification.json`。
- 最终 HEAD 未变，暂存区为空，Desktop 生产源码 diff 为空，用户原有 PNG 删除保持原样。
- 本报告位于 docs，不在 apps 源码快照内；用户原有 PNG 删除单独保护。

主要生产修改范围为 Python v2/C2 API、只读 capabilities 投影器及 Runtime cancel 的小补丁；Java 增量 DTO/白名单 mapper/可选取消版本透传；前端能力校验、生命周期投影与既有控制链。测试文件负责对抗、兼容与集成验证；没有后端 Schema、依赖版本、SSE 协议、Launcher 身份内核或 Desktop 生产修改。

## 9. 尚存限制与复验建议

- 本结果是本地自动化验证，不代表远端 GitHub CI、真实模型、真实浏览器视觉验收或生产环境已通过；没有部署。
- 无法证明唯一 Mission 执行分支，故有意不提供 Current Run/Branch Head；Latest 只作展示。
- 缺可信 scope、缺正式证据、同版本冲突时仍关闭操作；权限恢复或新事实到达后再刷新。
- Permit Run 的公开 partial successor 未伪装为内部恢复，仍关闭；用户可在合法完整快照条件下创建新 Run。
- Capabilities 是查询时的 UI offer，可能过时；不是授权令牌，命令端的现有版本、身份和 Authority 检查始终必需。
- 独立复验应优先尝试多活跃分支、旧 Run 请求迟到、撤销权限、过期版本、同请求重放和显式 supersession；不应只看按钮显示。

## 10. 结论

**SELF-TESTED**。所列门禁全部通过，且最终源码快照一致，可以提交独立复验。后端提供逐 Run 的能力事实，前端按动作恢复控制；没有制造唯一 Current Run，也没有将 UI 能力当作命令授权。部分恢复无法满足正式执行权威时仍保持关闭。

本轮未 Commit、Push、Merge 或部署；未自行宣布 ACCEPT。

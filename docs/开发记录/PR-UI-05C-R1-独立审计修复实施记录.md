# PR-UI-05C-R1 独立审计修复实施记录

日期：2026-11-04。状态：**SELF-TESTED，等待独立审计。**

## Git 入场

分支 master，HEAD 为 `ca50ce778369df5b856751efd217e6239b4efc6d`；本地、GitHub、Gitee master 一致。暂存区、tracked diff 与 untracked 均为空。相对 05C 实施提交 f3da8c46，新增的 6aac5718、2a3a5eb0、ca50ce77 均为已提交 Runtime/启动性能优化，本轮排除，未改写这些提交或相关源文件。

## 反例与 P1

先新增测试再运行旧实现。pr-ui-05c-r1-before.log：2 文件、25 项，5 失败/20 通过，退出 1；复现空 Progress 访问 phase、显式生命周期标签被 Progress 覆盖、MISSING 缓存无法发现延迟 Artifact。

另一次旧实现运行 pr-ui-05c-r1-identity-before.log：2 文件、45 项，2 失败/43 通过，退出 1；复现合法临时 Progress 在摘要中显示 UNKNOWN，以及用户编辑模式下“查看交付物”未打开 Artifact。

WorkflowProgressBar 使用 `lifecycleLabel ?? (progress ? ... : ...)` 明确优先级；共享阶段另作为 lifecyclePhase 输入决定颜色。存在共享标签时运行文案使用该标签，不展示冲突 Progress 的失败/运行文案；未传共享阶段时保持独立调用方 Progress 展示。覆盖 null、冲突、无标签、均缺失、UNKNOWN、已完成未恢复 Progress 六项。

## P2-01 单一展示解释

RunLifecycleProjection 类型直接由共享纯函数导出。Chat 将同一个 lifecycle 传给进度条与摘要；摘要在收到该投影时不再重新推断状态或选择 Progress。Run/View 仅提供同 Mission/Run 范围的证据与指标，旧 Run/View 被排除。独立摘要调用者保留基于明确 Run 的兼容路径；无 Run 且没有外部已验证投影时，不从未证明选中身份的 Progress 自行取得权威。

新增摘要七项来源/身份/版本测试；真实 Shell 测试卸除进度条和摘要的 stub，证明 Run completed 与 Progress running 冲突时两个真实组件均显示“已完成”，颜色保持 completed，不出现旧运行文案。

## P2-02 定向交付导航合同

普通入口继续只调用 conversationWorkbenchTarget，保留用户编辑器选择；“查看交付物”通过同一身份校验后附加受约束一次性意图，不传 artifactId 或文件路径。

明确新增 query 合同：

| 字段 | 值域与条件 |
| --- | --- |
| entryIntent | 只允许 run-deliverable |
| entryIntentId | UUID 格式，每次明确点击生成，用于一次性消费 |
| entryIntentMissionId | 必须等于当前 Mission 路径身份 |
| entryIntentRunId | 必须等于显式 query.runId，禁止重新绑定其他 Run |

Workbench 进入、刷新或意图变化后通过原 loadWorkspace 请求精确 Mission/Run；保留原 AbortController、可见性和请求代次保护。仅在新 Workspace 身份校验通过后，复用 projectLifecycle 的 canonical deliverable 判定，再调用现有 openEntry。该操作是明确用户编辑器选择，覆盖既有 user/follow 模式；不重建 EditorGroup、Copilot 或运行 Store，不 fallback 最新 Run。

消费成功或确认缺失/非法意图后清除四个意图字段，保留 runId 和其他合法 query；缓存 Workbench 内记录已消费 UUID，历史 URL 重放同一 UUID 不再次打开。清除路由失败时显示错误且已消费 ID 不重复处理。Workspace 请求本身失败时保留当前已渲染编辑器与原错误处理；意图只可在后续同身份的正式重新查询成功后处理，不借缓存打开 Artifact。路由 Mission/Run 改变会使旧控制器失效；绑定字段失配的意图拒绝消费目标。

真实 Shell/Router/Pinia/Workbench 覆盖 follow、用户选择、其他 Artifact、普通导航保持编辑器、返回再进入、快速双击、首次历史 Run URL、已消费重放、撤销/foreign/legacy、错误 Mission/Run、迟到响应跨 Mission/Run；保留既有所有连续性与 SSE 释放断言。

## P2-03 后端一致性调查与缓存

仅只读核实以下源合同，没有修改 Python：

- apps/agentOS/src/runtime/acg_execution.py::_complete_run（约 1165 行）：先设置 COMPLETED、save_run，再发布终态并 flush identity outbox。
- apps/agentOS/src/runtime/v2/identity_projection.py::_project_artifacts（约 859 行）：从 sealed ContentManifest 建立 Artifact 与 binding，使用独立 V2 事务；没有以 Run 已终态作为永久禁止投影的合同。
- 同文件 _on_run_finished（约 1109 行）：V2 终态经 lifecycle_service 单独落地。
- apps/agentOS/src/runtime/v2/workspace.py::MissionWorkspaceProjector.project（约 235/289 行）：按选中 Run 读取 Artifact Entries，并对成功 Run 缺少 canonical 交付物给出诊断；没有交付 revision 或证明负结果永久有效的读取合同。

无法证明所有 Runtime/投影/交付写入与 completed 原子一致，因此只缓存 READY。MISSING 和 UNAVAILABLE 在下一次 Chat 激活时重新查询，不使用 TTL，不增加后台轮询。保留字符串身份键监听、在途去重、scope/可见性 Abort 和迟到结果丢弃。

新增 MISSING→后端登记→重新激活 READY、UNAVAILABLE→重新激活、非终态不读等反例；原 READY 去重、等价 Run 刷新不重复请求、切换 Run/Conversation 隔离仍保留。既有 Shell MISSING 场景改为明确断言再次读取一次，READY 保留零额外读取断言，不以删除断言掩盖合同变化。

## P3 依赖方向

runLifecycle → workbench/runtime/runCapabilities 为纯函数依赖；runCapabilities 仅反向依赖 API 类型，无共享投影反向 import、Store、HTTP 或定时器。未发现循环、重复规则或实质测试问题。本轮记录目录分层技术债，保留原能力校验权威，未跨目录重构。

## 修改清单

路径相对 apps/frontend：

- components/agentos/WorkflowProgressBar.vue 及 spec：优先级、共享颜色/文案、nullable 反例。
- components/agentos/AgentOsRunSummaryCard.vue 及 spec：共享投影输入、证据身份范围及来源反例。
- views/ChatView.vue：同一投影传递、区分普通与交付导航。
- views/MissionWorkspaceView.vue：一次性意图校验、重新查询、现有 Entry 定向打开、消费与错误处理。
- features/workspace/navigation.ts：严格意图值域及绑定合同。
- features/workspace/runLifecycle.ts：共享类型导出。
- composables/useRunDelivery.ts 及 spec：只缓存 READY，延迟登记恢复。
- components/app/WorkspaceContinuity.spec.ts：实际组件与多轮导航对抗。
- docs/开发记录/本实施记录。

## 验证

最终门禁采用同一份冻结前端源码。日志前缀为 Windows `%TEMP%/pr-ui-05c-r1-gate-*`，所有测试/类型/构建命令 cwd 为 apps/frontend。中间失败与中间通过日志均保留，不用中间结果代替最终门禁。

最终结果：

| 命令 | 退出码 | 实际结果 |
| --- | --- | --- |
| `npm test -- src/features/workspace/runLifecycle.spec.ts src/composables/useRunDelivery.spec.ts src/composables/useWorkflowProgress.spec.ts src/components/agentos/WorkflowProgressBar.spec.ts src/components/agentos/AgentOsRunSummaryCard.spec.ts src/views/ChatView.spec.ts src/views/MissionWorkspaceView.spec.ts src/components/app/WorkspaceContinuity.spec.ts src/workbench/runtime/lifecycleProjection.spec.ts --maxWorkers=2 --minWorkers=1` | 0 | 9 文件、217 项通过；38.03 秒 |
| `npm test -- --maxWorkers=2 --minWorkers=1` | 0 | 145 文件、1163 项通过；290.09 秒 |
| `npx vue-tsc -p tsconfig.json --noEmit` | 0 | 无类型错误 |
| `npm run build:web` | 0 | Vite 构建 22.02 秒 |
| `git diff --check` | 0 | 无 whitespace error |

原有 1136 项保留，新增 27 项：进度条 6、摘要 7、交付缓存 2、真实 Shell 12。最终 Continuity 47 项，Chat 38、MissionWorkspace 31、原生命周期 24、Progress 18、共享投影 25 项均保留。全量未报告未处理 Promise rejection；既有网络/环境控制台输出不作为真实远程 API 验收证据。

源码清单涵盖全部 Git tracked apps/frontend 文件，以路径排序、逐文件 SHA-256 生成 JSON；文件为 `%TEMP%/pr-ui-05c-r1-source.json`，共 619 个文件。清单 SHA-256 为 `efea9b20e77b2269034b92056cac58744fb07859e444faf4a7881e5f6380a04e`。最终测试、类型、构建之后逐文件核对一致；报告本身及后端不纳入前端源码清单。

## 剩余边界

本轮自动化包含真实 Shell/Router/Pinia/Workbench 交互，但不等于真实浏览器视觉或远端 Runtime E2E 验收。READY 缓存是登记观测，查看按钮仍在 Workbench 重新验证，不能证明成果已下载或签收。一次性意图仅控制视图选择，不授予执行或数据权限。未新增 SSE、轮询服务或全局导航 Store，未修改后端、Dispatch/Permit/Handoff、Mission Launch 或运行权威。

不提交、推送、合并或部署，等待独立审计。

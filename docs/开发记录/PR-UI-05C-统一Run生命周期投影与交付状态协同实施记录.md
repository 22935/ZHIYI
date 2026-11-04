# PR-UI-05C 统一 Run 生命周期投影与交付状态协同

日期：2026-11-04。状态：**SELF-TESTED，等待独立审计。**

## 基线与范围

入场分支 master，HEAD 和 GitHub master 均为 `5f607d4197eacba55b69b0ae988bb8e80545b7bc`。暂存区为空，无入场 untracked。保留原有五项 AgentOS Python 修改及两项运行准备脚本修改；未读取或编辑其源文件，未暂存或清理。

## 状态来源差异及共享合同

原 useChatWorkflowPresentation 与摘要卡分别采用 Progress、Run、AcgView 和消息缓存优先级；Workbench 则使用 projectLifecycle 及正式能力冲突检测。现在从原 projectLifecycle 原样抽取 mapRunPhase 到 features/workspace/runLifecycle.ts，Workbench 继续保留原能力冲突、历史只读、推荐 Editor/Inspector、交付验证及 Lifecycle Follow。两个空间复用同一阶段中文标签，不新增状态机。

projectRunLifecycle 是纯函数，不访问 Pinia、网络、SSE、定时器，也不提供执行权限。它核验输入 Mission/Run，优先使用 Run；能力版本/作用域校验复用 runCapabilities。Progress 只在身份匹配时参与观测，低 revision 丢弃，同版本状态冲突与高版本 Progress 保留 Run 并标记 RECONCILING；高版本观测复用 loadActiveAcgView 刷新权威数据。缺少 Run 时匹配 Progress 标为 PROGRESS_TEMPORARY，无来源为 UNAVAILABLE，身份不符为 IDENTITY_MISMATCH，证据不全为 PARTIAL。

保留全部既有阶段及正式状态语义：Dispatch 接受不等于完成，激活暂停不等于执行，许可就绪不等于派发，成功终态不等于交付登记。未知阶段映射 UNKNOWN，消息 workflowStatus 与 AcgView.status 不参与生命周期判断。

## Progress 身份及接入

useWorkflowProgress.start 新增 optional expectedMissionId，在赋值及回调前核对 response.runId 和已知预期 Mission。错误响应不更新 progress，不发 onProgressChanged/onTerminal，沿用原 generation、AbortController、错误重试和终态停止机制。

检查全部调用者：Chat 从 binding/已验证 Run 传入 Mission，历史面板从 summary 传入，ACG 新建和恢复从命令返回身份传入；独立 ACG 页只带 runId 的旧入口无法预知 Mission，保留 optional 参数并始终验证 Run ID，不从 Mission 猜测身份。

Chat 主状态、进度条阶段、摘要卡及终态判断均使用共享投影。匹配 Progress 提供计数与百分比，同步冲突显示非阻塞提示。绑定/消息状态更新优先保留已验证 Run，过期 Progress 不覆盖它；审核继续复用现有面板。

## 交付协同与异步安全

新增局部 useRunDelivery：仅对当前可见 Conversation 的已验证 completed/succeeded Run 调用一次 getMissionWorkspace(missionId,{runId,signal})。核验返回 missionId 与 activeRun.runId，逐条检查 canonical artifact、同 Run、final/run_deliverable、非空 artifactId/contentRef，复用 isRunDeliverableEntry。

READY 表示登记证据齐全；MISSING 表示身份匹配的查询成功但无满足条件的 Entry；UNAVAILABLE 表示查询失败、错误身份或尚未确认；非成功终态为 NOT_COMPLETE。不会以 finalArtifacts 替代 canonical proof。

请求绑定 Conversation、Mission、Run、可见性与 generation；切换时 Abort 并忽略迟到结果，scope 销毁取消请求。成功加载的 (missionId,runId) 结果在当前 Chat 实例中去重；失败查询可在后续重新激活时重试。READY 的查看按钮复用 05B 已验证导航，进入对应 Run 的 Workbench，由既有 Lifecycle Follow 定位交付物；没有发明路由参数。

## 测试设计与实施中失败

新增共享投影表驱动状态/正式阶段、版本冲突、错误身份、临时来源、消息/AcgView 冲突测试；新增真实 scope 下的 canonical 交付反例、Deferred Promise 迟到响应、Abort 与去重测试；Progress 增加错误 Mission/Run 回调隔离测试；真实 Shell/Pinia/Router 增加 READY/MISSING/UNAVAILABLE 恢复和再次激活测试。

首轮暴露旧 fixture 缺少 Mission、以及用 Progress completed 与 Run running 冲突驱动新任务入口。补齐 fixture 身份，使连续性场景的 Run 本身终态；保留原断言。没有删除或 skip 原测试，没有放宽 deadline 或安全断言。中间日志 pr-ui-05c-target.log/target2.log 保留，最终结果另列。

## 修改文件

新增：features/workspace/runLifecycle.ts 及其 spec；composables/useRunDelivery.ts 及其 spec。

修改：workbench/runtime/lifecycleProjection.ts；composables/useWorkflowProgress.ts 及其 spec；useChatWorkflowPresentation.ts；components/agentos/AgentOsRunSummaryCard.vue、WorkflowProgressBar.vue；views/ChatView.vue 及其 spec；views/MissionWorkspaceView.vue；components/app/WorkspaceContinuity.spec.ts；components/history/AcgHistoryPanel.vue；views/AcgVisualizationView.vue；本记录。路径相对 apps/frontend，记录位于 docs/开发记录。

## 验证与源码

日志位于 Windows `%TEMP%/pr-ui-05c-*.log`，命令 cwd 为 apps/frontend。最终前端清单包含所有 tracked 前端文件及四个新增源码/测试文件，按路径排序逐文件计算 SHA-256；清单 pr-ui-05c-source.json 的 SHA-256 为 `0f792706619f17bb71abd14c6f8c0dcbf042ba946a7aeab546b4c38839a45dbc`。本记录与未修改的并行 Python 工作不纳入前端清单。

最终命令与结果（全部对应最后一次生产源码与测试清单，验证后逐文件复核一致）：

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `npm test -- src/features/workspace/runLifecycle.spec.ts src/composables/useRunDelivery.spec.ts src/workbench/runtime/lifecycleProjection.spec.ts src/composables/useWorkflowProgress.spec.ts src/views/ChatView.spec.ts src/views/MissionWorkspaceView.spec.ts src/components/app/WorkspaceContinuity.spec.ts src/components/workspace/FormalExecutionControls.spec.ts src/features/workspace/navigation.spec.ts src/components/agentos/AgentOsRunSummaryCard.spec.ts src/components/agentos/WorkflowProgressBar.spec.ts --maxWorkers=2 --minWorkers=1` | 0 | 11 文件、240 项通过，83.83 秒 |
| `npm test -- --maxWorkers=2 --minWorkers=1` | 0 | 145 文件、1136 项通过，377.18 秒 |
| `npx vue-tsc -p tsconfig.json --noEmit` | 0 | 无类型错误 |
| `npm run build:web` | 0 | Vite 构建 49.82 秒 |
| `git diff --check` | 0 | 无 whitespace error |

最终日志分别为 pr-ui-05c-target-final.log、pr-ui-05c-full-final.log、pr-ui-05c-tsc-final.log、pr-ui-05c-build-final.log。全量未报告未处理 Promise rejection；部分既有 Workbench 测试有 jsdom 网络错误输出，但对应断言通过，不能将这些输出解释为真实 API 验证通过。

最终新增共享投影 25 项、交付 14 项、Progress 隔离 2 项、真实 Shell 交付恢复 3 项。原有 Continuity 32 项保留，最终 35 项；正式控制 26 项、导航 24 项、原生命周期 24 项、Chat 38 项、MissionWorkspace 31 项保留。

中间全量 pr-ui-05c-full.log 在已加载旧 delivery 实现时执行到新加入的请求去重反例，记录 1 项失败（重复两次查询）。修复为按 Conversation/Mission/Run/终态/可见性字符串键监听，并在同一键下保留在途请求；final 全量从修复后源码重新启动，1136 项通过。所有中间失败保留，没有修改日志制造通过。

## 剩余边界

组件/Shell 自动测试不等于真实浏览器视觉验收或远端 Runtime E2E。旧只带 Run ID 的独立 ACG 恢复入口无法在首个响应前预知 Mission；交付查询失败时允许下次激活重试，不把失败缓存成缺失。Workspace canonical Entry 是登记证据，不证明已下载或用户已签收。无新增 SSE、轮询服务、全局 Store 或执行身份；保留原正式控制、审核、编辑器与 Copilot 连续性。

未提交、推送、合并或部署。等待独立审计。

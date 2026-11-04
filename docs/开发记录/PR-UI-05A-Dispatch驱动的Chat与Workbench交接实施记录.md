# PR-UI-05A Dispatch 驱动的 Chat / Workbench 交接

日期：2026-11-04。状态：**SELF-TESTED**，等待 GPT 独立审计。

## 入场 Git 与修改范围

入场 master/HEAD 为 `e0d19c97c24401f7500a4bc85cad13df89e1abb5`，暂存区为空。已有五个 Python 修改：workflow_runtime.py、memory_workflow_store.py、sqlite_workflow_store.py、workflow_store.py、test_workflow_store_contract.py。本轮保留这些并行工作，不纳入前端交付，也未修改它们。

| 文件 | 本轮职责 |
| --- | --- |
| src/features/acg/formalControl.ts | 有类型的正式操作成功事件、各阶段终态回执校验 |
| src/components/workspace/FormalExecutionControls.vue | 等待服务端回执，校验后发 succeeded；切换 Mission/Run 或卸载后拒绝迟到事件 |
| src/views/ChatView.vue | 校验当前 Conversation/Run 关联后内嵌现有控制；Dispatch 提示、去重及用户确认后的验证导航 |
| src/features/workspace/navigation.ts | 补全同一 Run 全局唯一所有者检查，并在异步查询返回后复核 binding |
| FormalExecutionControls.spec.ts、ChatView.spec.ts、navigation.spec.ts | 正式回执、提示和身份验证回归 |
| WorkspaceContinuity.spec.ts | 新增实际 Shell / Pinia / Router / Chat / Workbench 的交接与返回测试；保留原 20 项 |

表中路径均相对 apps/frontend。本轮不提交、推送、合并或部署。

## Dispatch 来源与成功合同

Chat 复用 FormalExecutionControls 和原 submitFormalControl；没有另写 Materialize/Activate/Handoff/Permit/Dispatch 控制器，也未改变 operationId 生成、持久化重试身份和 Mission Launch。

正式回执必须 echo 当前请求 operationId，且状态符合该操作：materialize=MATERIALIZED_INACTIVE、activate=ACTIVATED_PAUSED、handoff=STATE_PREPARED、permit=ISSUED、dispatch=ACCEPTED，或者 IDEMPOTENT_REPLAY。Dispatch 额外要求非空 dispatchId。校验成功后才发 succeeded，载荷包含 action、operationId、status、dispatchId（若有）、missionId、runId。

已核对 `apps/agent/app/api/agentos_c2.py`：Dispatch 路由返回 request.operation_id 与 accepted.public(replay)，其他正式路由使用 receipt_response echo operationId；Activate 先 prepare 再 commit 并返回 commit 回执。本轮只读取这些实现，未修改它们。

HTTP 成功状态自身不构成成功事件；403/409/422、ACK 丢失、缺失 dispatchId、错误 operationId 和未知 receipt status 均不发事件。组件仍只逐步推进一次用户操作，成功后仅请求刷新，不乐观修改 Run 或继续提交下一步。

提示只消费当前 Chat 控制组件产生的 dispatch 成功事件，不从 permitStatus、dispatchEligible、Run running、Lifecycle、轮询或恢复历史记录推断。文案明确是服务端接受执行命令，不宣称 202 意味执行完成。

## 身份、去重与导航

正式控制展示要求 activeWorkflowRun 与当前明确选中 Run 一致，具有 formalControl 证据，与当前 Conversation binding 的 Mission 一致，且同一 Run 全局只有一个有效 canonical owner。superseded lineage 和终态 Run 为历史只读；正式能力仍由既有组件校验。已有 WorkflowReviewPanel 在正式组件展示时不重复呈现；无正式证据的兼容入口保留。新的内嵌控制不另接取消控制器，原运行控制入口继续可用。

提示是非阻塞的内联区域，提供“进入 Workbench”和“稍后”。仅收到回执不会导航；稍后只关闭提示。以 Run/Dispatch 为键，在 sessionStorage 记录已经提示的身份，并以组件局部 Set 处理 storage 不可用的情况；刷新和挂载不提交 Dispatch，同一 Dispatch 的显式幂等重放不重复提示。storage 不可用时局部 Set 只保证当前挂载期间去重，跨挂载持久去重依赖 sessionStorage 可用。

进入动作调用 conversationWorkbenchTarget，传当前 workflowBindings、当前 Conversation ID、明确选中 Run ID 和 agentosApi.getWorkflowRun。它验证 Run 存在、Mission/Run 匹配、binding 有效、Alias 归属唯一；显式 Run 无匹配时不会选择其他 Run。补丁还拒绝没有共享 Alias 的竞争 canonical owner，以及查询过程中失效的 binding。Chat 在返回后复核提示对象、可见 Conversation、选中 Run、Mission 及 binding index 身份，拦截旧请求和导航竞争；失败保留 Chat 并给出提示。

## Workbench / Copilot 复用

进入原 `/agentos/missions/:missionId/workspace?runId=:runId`，没有修改 WorkspaceViewHost、CachedWorkspaceView、MissionWorkspaceView、projectLifecycle、followLifecycle 或 ACG Copilot。沿现有选择的 Mission/Run 接线观察 Runtime，未创建新 Copilot session、全局管理器、SSE 或启动器。

新增 Shell 测试由真实 Chat 控制按钮发起 Dispatch，回执后仍处于 Chat；用户点击进入才打开真实 MissionWorkspaceView，返回时保留 Chat 实例、Conversation、原消息，Dispatch 总调用一次，SSE 峰值不超过一。现有 Continuity 的消息、编辑器、ACG 视图、历史恢复与迟到启动隔离测试全部保留。

## 验证

| 命令 | 结果 / 退出码 |
| --- | --- |
| npm test -- src/components/workspace/FormalExecutionControls.spec.ts src/views/ChatView.spec.ts src/features/workspace/navigation.spec.ts src/components/app/WorkspaceContinuity.spec.ts --maxWorkers=2 --minWorkers=1 | 4 文件，96 项通过；exit 0 |
| npx vue-tsc -p tsconfig.json --noEmit | 通过；exit 0 |
| npm run build:web | 通过，Vite 打包 1m 19s；exit 0 |
| git diff --check | 通过；exit 0 |

本轮新增 15 项：正式控制 5 项、Chat 7 项、导航 2 项、真实 Shell 1 项；原有断言保留。首次类型检查发现新增导入与既有 conversationBindings 重复，已删除重复导入后再检查。中间测试结果 68/95 项仅属过程记录，最终结果以上表为准。未运行前端全量，未将定向结果表述为全量通过。

最终 frontend 已跟踪源码与配置清单 SHA-256：`1ad5188692f05de4deb84d2d165519e42ff5d9f2249c19a8db2a8a9b944ee3ab`。门禁前后逐文件清单完全一致，sameSource=true；报告和用户并行 Python 工作不在此摘要范围内。证据目录为 `C:/Users/LZX/AppData/Local/Temp/pr-ui-05a`，其中 source-before.json、source-after.json、verification.json 和 final-tests.log/typecheck.log/build.log 保存源码与结果证据。

## 剩余边界

未执行真实浏览器视觉验收或连接外部 Runtime 的手工 Dispatch E2E；本轮证据为组件和真实 Shell 自动化集成、类型及构建门禁。前端成功事件基于既有同步回执协议，不以命令接受证明任务最终交付。sessionStorage 不可用的跨挂载去重限制如上。

完成后仅标记 SELF-TESTED，等待 GPT 独立审计，不宣布 ACCEPT。

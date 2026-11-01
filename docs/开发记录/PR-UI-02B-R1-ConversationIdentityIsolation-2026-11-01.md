# PR-UI-02B-R1｜Conversation Identity Isolation

日期：2026-11-01（Asia/Shanghai）

状态：**SELF-TESTED**

## 1. 起始现场与结论

- 起始 Git HEAD：`f2f211bb2cce6d1bc7e0bd95907e006160672b17`，分支 `master`。
- 起始工作区、暂存区和 untracked 均为空；`ahead 1` 是相对 Gitee 的 `origin/master`，不代表未提交修改。
- 已先阅读 Shell、WorkspaceViewHost、CachedWorkspaceView、ChatView、Chat Store、LaunchAttempt 与既有测试的真实调用链，再建立失败复现。
- 证实存在生产缺口：Store 先完成 B 的历史恢复，再从 `/chat?contextId=A` 切到 `/chat?contextId=B` 时，Host 可复用同一 ChatView；旧代次保护会被路由 watcher 的提前返回绕过。
- 本轮仅修改 ChatView 局部身份检查和既有 Shell 集成测试，另增加本报告。没有引入新的状态管理体系。

## 2. 原始问题与代码证据

以下行号指起始 HEAD 的源码。

| 位置 | 原行为及影响 |
|---|---|
| `WorkspaceViewHost.vue:25` 的 route watcher | 只有 `context && context !== chat.contextId` 等条件成立时才更新 `chatKey`。Store 已是 B 时，路由进入 B 不一定换实例。 |
| `CachedWorkspaceView.ts:14` | 给组件提供独立 route snapshot，但复用同一组件时会把新路由写入该 snapshot；它不负责区分旧异步请求的 Conversation 所有权。 |
| `ChatView.vue:753` | `isConversationVisible()` 只判断 `viewActive` 和路径 `/chat`，无法区分同路径上的 A/B。 |
| `ChatView.vue:2144` 的 context watcher | `chatStore.contextId === targetContextId` 时先返回，跳过后面的 `++composerGeneration` 和 composer 状态清理。 |
| `ChatView.vue:1804`、`:1827` | 启动、待确认提交恢复的迟到结果仅检查 composer 代次，没有显式核对原始 Conversation。 |
| `ChatView.vue:1758` | `activateWorkflowRun` 从响应返回时的 `currentConversationId` 设置 `selectedConversationId`，可能把 A 的 Run 选入 B，并写入 B 的 URL。 |
| `stores/chat.ts:755` 的 `startConversationWorkflow` | 已捕获 `options.conversationId` 并将结果写入该身份的 Binding；消息回写受 `historyGeneration` 保护。这层后台所有权应继续保留。 |

正常切换时，Host 更换缓存键并淘汰旧 ChatView，`onUnmounted` 增加 composer 代次，能够阻断迟到结果。Chat→Workbench 切换还受组件停用和路径检查保护。上述保护不能覆盖 Store 预先持有目标 contextId、ChatView 未卸载的路径，因此需要生产代码修复。

## 3. 实际失败复现

复现位于 `apps/frontend/src/components/app/WorkspaceContinuity.spec.ts`，挂载真实 `AuthenticatedAppShell`、其内部真实 `WorkspaceViewHost` / `CachedWorkspaceView`、真实 ChatView / MissionWorkspaceView，并使用真实 Pinia 和 memory Vue Router。布局叶子组件及外部 API 由测试夹具替代，未 mock Chat Store 或 Mission Launch 内核。

启动通过真实 Agent composer 的发送按钮进入 `sendAgentWorkspaceMessage → upgradeChatToWorkflow → chatStore.startAgentRun → LaunchAttempt → workflowApi.startWorkflowAsync`。在最后一个 API 边界使用 Deferred Promise，明确控制成功或失败的交付时机。

步骤：

1. 路由打开 A，输入并发送 Agent 目标，确认 API 恰好调用一次，原始请求的 `input.conversationId=A`、`source=agent`。
2. 保持启动 Promise 未完成。
3. 对照组直接在 `/chat` 下切到 B；边界组先 `await chat.loadHistory('B')`，再切到 B。
4. 确认 B 的历史请求完成、消息恢复、`isLoadingConversation=false`，并通过组件 UID 验证是否复用。
5. B 写入自己的未发送文本后，再释放 A 的响应，核对 URL、Run 选择、输入、错误、消息和 Binding。

原始生产源码下的结果：

| 场景 | 实测结果 |
|---|---|
| 正常切 B，A 成功 / 失败迟到 | 对照组均通过；UID 改变。 |
| B 已预加载，A 成功迟到 | UID 不变；B 的 URL 被改成 `contextId=B&runId=late-A`，应保留的 `run-B` 被覆盖。 |
| B 已预加载，A 失败迟到 | B 出现 `ACG 任务未能启动`，来自 A 的失败。 |
| B 已预加载后尝试启动自己的任务 | 旧 composer 的 loading/submitting 未退出，API 只有 A 的 1 次调用，B 应有的第 2 次调用没有发生。 |

第一轮双场景运行得到 1 failed / 1 passed；扩展后的 6 项新测试得到 **4 failed / 2 passed，exit 1**。日志与当时测试源码已保留，未改写失败记录。B 的并行启动用例在原实现中先失败于旧 loading 阻止提交；修复后才继续验证 A 的 success/failure finally 不能结束 B 的真实待完成请求。

## 4. 最小修复及边界

仅修改 `apps/frontend/src/views/ChatView.vue`：

1. 增加局部 Conversation 等价判断，复用既有 `conversationBindings` / `belongsToConversation` 识别正式身份及已有 Draft Alias。可见性同时核对组件当前身份与 Router 当前可见身份。
2. 在 Conversation 身份改变时独立使 composer 代次失效，并清理该页面的旧 loading、submitting、输入和启动错误。它不依赖是否需要再次 `loadHistory`，因此 Store 已恢复 B 时也生效。
3. 保留首次 Chat send 的原有 Draft 证明条件：`sendingDraftId`、当前 Draft、Store 新 context、未处于历史恢复、路由尚无 context。这条迁移不会被提前清除；已有 Alias 关系也不会被当作新 Conversation。
4. Agent composer、Workflow 启动和待确认提交恢复均捕获请求发起时的 Conversation。异步完成、catch、finally 和后续滚动同时检查原始身份与代次；当前显示 `/chat` 时还核对可见身份。
5. `activateWorkflowRun` 必须接收原始 Conversation，校验 Binding 归属后设置原始选择身份；URL 写入前再次核对该 Conversation 仍可见。历史恢复的末尾 URL 写入也核对原始 Conversation。
6. 隐藏视图的启动完成保存在原 Store 的原 Conversation Binding 中；没有为切换 Conversation 添加 AbortController 或取消请求，LaunchAttempt 的完成、对账和去重规则保持原实现。

开发中的首轮补丁曾因过早清除 Draft 首次迁移证明、以及阻挡只有 Run ID 的旧历史入口，导致 4 项既有测试失败；这些失败记录保留在 `first-fix.log`。最终补丁保留首次发送证明及既有无 context 的历史恢复语义，原有断言全部通过。

没有修改 WorkspaceViewHost、CachedWorkspaceView、Chat Store、Mission Launch 内核、幂等身份、后端、Runtime、ACG、视觉布局或 CSS。

## 5. 新增集成测试与回归合同

原 Continuity 文件的 11 项测试正文逐字保留，增加 9 项参数化实例，总计 20 项；共享 teardown 增强为每次卸载后检查活动 Runtime SSE 数为 0。

| 新增实例 | 验证结果 |
|---|---|
| 正常 / 预加载切换，A 迟到成功（2 项） | B 的消息、文本、错误、`selectedConversationId`、Run、URL 均保持 B；A Binding 与 workflowRuns reference 仍属于 A。 |
| 正常 / 预加载切换，A 迟到失败（2 项） | B 不接收 A 的错误或恢复输入；A 的 uncertain 提交仍只属于 A，B 没有该待确认身份。 |
| B 自己仍启动中，A 成功 / 失败 finally 迟到（2 项） | 两个真实 Store 提交均进入 API；A 完成后 B 的 loading/submitting 仍为 true，直到 B 自己完成；最终 B 只选择 `own-B`。 |
| 原提交恢复成功 / 失败迟到（2 项） | 真实恢复按钮进入原 LaunchAttempt 对账；沿用同一 operation/clientRequestId。B 不受影响；成功结果落入 A，失败仍保留 A 的原身份。 |
| 合法 Alias 的 Conversation 在 Workbench 中完成真实启动（1 项） | 隐藏完成不覆盖当前 Workbench Run；原 Draft Alias 仍能指向原 Conversation；返回和重复往返可选择新 Binding，创建次数仍为 1。卸载后 SSE 为 0，推进 20 秒不再轮询。 |

成功与恢复测试返回 A 时**不提供 runId**，由 A 自己的 Binding 恢复迟到创建的 Run；随后重复 Chat/Workbench 往返，确认创建仍只有 1 次。恢复路径另确认对账只调用 1 次，没有重复创建。

旧 C/D 等 Continuity 测试继续验证真实延迟 Chat SSE 的 Draft 迁移、同一 Runtime SSE、隐藏增量、停用轮询、未发送文本、EditorGroup、脏文件、图状态、浏览器历史等合同；`ChatView.spec.ts` 原 31 项也全部保留并通过。

## 6. 最终验证与同一源码快照

环境：Windows，Node `v24.19.0`，npm `11.17.0`。命令在 `apps/frontend` 执行，Git 检查在仓库根执行。

| 验证 | 结果 |
|---|---|
| 定向：WorkspaceContinuity、ChatView、chat.session、workspace/session | 4 个文件，75/75，exit 0；18.07s。 |
| `npm test -- --maxWorkers=2 --minWorkers=1` | **136 个文件，989/989，exit 0**；189.54s。 |
| `npx vue-tsc -p tsconfig.json --noEmit` | exit 0。 |
| `npm run build:web` | exit 0；包含原有 vue-tsc 与 Vite Web Build，Vite 构建 16.80s。 |
| `git diff --check` | 通过；新增报告另检查行末空白与文件结尾。 |
| 原测试保留与源码范围 | 原 11 项 Continuity 测试正文逐字比对通过；验证快照的生产修改只有 ChatView，自测完成时暂存区为空。 |

最终定向验证前，对 Git 跟踪及未忽略的前端输入共 **602 个文件**记录路径和 SHA-256。定向、全量、类型检查及构建结束后再取清单，602 个路径及内容均一致，0 差异。

清单文件 SHA-256：`13CEB6D547A3A9C8AF491459B223F29BA2A4407529370056982C3AF93CB5F121`，验证前后相同。报告位于 docs，不是前端测试或构建输入。

没有新增测试排除、skip、Disabled、固定 Sleep 或减弱断言。既有 Vitest `retry: 1` 配置未修改；原始确定性失败在该配置下仍失败。新定向测试没有未处理 Promise rejection；全量输出没有 Vitest Unhandled Errors / Rejection 汇总。全量中既有 MissionWorkspaceView 测试仍输出 jsdom XHR `AggregateError` 的 stderr，该文件测试通过，未修改该夹具来隐藏输出。

## 7. 交付范围、证据与验收建议

修改文件：

- `apps/frontend/src/views/ChatView.vue`：局部身份所有权与代次检查。
- `apps/frontend/src/components/app/WorkspaceContinuity.spec.ts`：9 项真实 Shell 集成实例及 teardown SSE 检查。
- 本报告。

本机原始证据：`C:\Users\LZX\AppData\Local\Temp\pr-ui-02b-r1`。

| 文件 | 用途 |
|---|---|
| `before.log`、`before-expanded.log` | 原生产源码下的真实失败输出。 |
| `WorkspaceContinuity.before-fix.spec.ts`、`ChatView.baseline.vue` | 复现时测试源码及基线组件源码备份。 |
| `first-fix.log`、`second-fix.log`、`expanded-fix.log` | 修复迭代的原始回归记录。 |
| `final-targeted.log`、`full-test.log` | 最终同快照定向与全量结果。 |
| `typecheck.log`、`build-web.log` | 最终类型检查与构建输出。 |
| `source-before.json`、`source-after.json` | 602 项路径与内容校验。 |

边界：这些是使用真实 Vue 组件生命周期、Pinia 和 Router 的 jsdom 集成验证，外部 API 返回由测试控制；本轮未进行真实浏览器、真实后端或跨设备 E2E，也未部署。Windows 构建通过不能替代独立环境复验。

建议独立复验重点重放“B 的历史已恢复、Host UID 不变、A 迟到返回”的边界及 B 同时启动场景，并核对 A/B 的持久 Binding 和 Run reference。现有证据支持 **SELF-TESTED，可提交独立复验**；不自行宣布 ACCEPT。本报告记录的验证快照在报告生成时没有 Commit、Push、Merge 或部署。双视图交互架构在本轮局部补丁范围内收敛，不继续增加抽象层。

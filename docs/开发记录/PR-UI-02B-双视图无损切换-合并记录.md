# PR-UI-02B Conversation / Workbench 双视图：实施与身份隔离修复合并记录

> **文档性质**：阶段证据合并稿——实施记录 1 篇 + R1 会话身份隔离修复 1 篇
>
> **覆盖时间**：2026-10-31 ~ 2026-11-01
>
> **当前定位**：双视图切换的现行实现（Vue KeepAlive 有界缓存 + 局部身份所有权）；两篇均 SELF-TESTED 可提交独立复验
>
> **合并日期**：2026-11-03

## 0. 合并说明与导读

本册把 **PR-UI-02B（2026-10-31 ~ 11-01）** 的 2 篇记录合并为一篇：双视图无损切换实施记录、R1 Conversation Identity Isolation 修复报告。正文逐字保留原文，仅做两类机械处理：标题层级下移一级、指向已合并/已归档文档的相对链接改写（经查本册原文均无站内相对链接，未发生改写）。来源清单见文末附录。

### 0.1 这一阶段在解决什么

02B 按 UI-02 审计「保留两页面、统一恢复入口」的路线实施 Conversation / Workbench 双视图无损切换：KeepAlive 有界缓存（最多一个 Chat 与一个 Mission 槽位）、脏文件确认后替换 Mission 槽位、刷新后按已有 contextId 与历史 API 重建。R1（2026-11-01）修复跨会话身份隔离：A/B 两个 Conversation 交错恢复与同时启动时，迟到响应不得写回对方——ChatView 局部身份所有权与代次检查，配 9 项真实 Shell 集成回归。

### 0.2 一页结论

| 篇目 | 性质 | 结论 | 关键证据 |
|---|---|---|---|
| 02B 实施 | 实施记录 | SELF-TESTED：双视图往返连续、缓存有界、刷新可重建 | 定向 + 全量 136 文件 / 980 用例（与 02A-R2 共用快照）、vue-tsc、build:web |
| 02B-R1 | 修复报告 | SELF-TESTED，可提交独立复验：A 迟到返回不污染 B | WorkspaceContinuity 9 项 Shell 集成；602 项路径与内容校验 0 差异 |

### 0.3 贯穿全阶段的不变量

- KeepAlive 只提供当前进程内的往返连续性；刷新后使用已有 contextId、历史/角色 API 与 Run 路由重建，不承诺未发送文本、Editor 标签与临时光标跨刷新持久化。
- 缓存最多保留一个 Chat 和一个 Mission 槽位；不新增业务 Store、后端 API 或数据库字段。
- 既有确定性失败在 `retry: 1` 配置下仍失败才算失败；没有新增排除、skip、固定 Sleep 或减弱断言。

### 0.4 明确未完成与放行条件

- 两篇均未做真实浏览器视觉验收、真实后端/模型执行或部署；jsdom 集成验证不能替代独立环境复验。
- R1 建议复验重点重放「B 的历史已恢复、Host UID 不变、A 迟到返回」及 A/B 同时启动边界，并核对持久 Binding 与 Run reference。
- R1 明确：双视图交互架构在本轮局部补丁范围内收敛，不继续增加抽象层。

### 0.5 阅读建议

先读 02B 的根因与切换实现（含两个开发期真实缺口的修复记录），再读 R1 的失败复现与局部补丁边界。

## 篇目与阅读顺序

1. **PR-UI-02B｜Conversation / Workbench 双视图无损切换实施记录** — 实施记录，2026-10-31 — 原文件 `PR-UI-02B-双视图无损切换实施记录-2026-10-31.md`
2. **PR-UI-02B-R1｜Conversation Identity Isolation** — 修复报告，2026-11-01 — 原文件 `PR-UI-02B-R1-ConversationIdentityIsolation-2026-11-01.md`

---

## 1. 原文｜PR-UI-02B｜Conversation / Workbench 双视图无损切换实施记录

<!-- 原始记录：PR-UI-02B-双视图无损切换实施记录-2026-10-31.md -->

- 日期：2026-10-31
- 状态：**SELF-TESTED**，等待独立复验
- HEAD / 基线：`ae709af60a0f734b342073a7c94d92396463906e`，分支 `master`
- 前置门禁：起始检查确认 R2 未实现；经用户追加授权先修复请求所有权，再推进本阶段。R2 的实现与验证单独记录在《PR-UI-02A-R2-消息请求代次隔离修复报告-2026-10-31.md》。

### 1. 根因

Shell 原来以 `route.path` 为组件 key 直接切换 RouterView。Chat 与 Mission Workspace 路径不同，因此往返会销毁原组件，丢失 Composer、EditorGroup、选择及阅读位置。仅增加 KeepAlive 也不完整：缓存组件继续读取全局路由，隐藏 Chat 的 watcher 可能响应 Workbench 查询参数；原来只在 unmount 释放的观察器与轮询则会留在后台。

本轮采用三条所有权规则：Conversation 决定消息请求归属，缓存视图决定交互状态归属，既有 Mission/Run 与后端查询决定任务归属。视图隐藏不等于新建 Conversation，也不等于停止任务。

已阅读 PR-UI-00 审计。该审计明确 Runtime SSE 是临时非回放输出，因此最终方案在缓存 Mission 隐藏期间保留唯一 SSE 引用，停用其查询轮询；不能靠返回后重连补回临时输出。

### 2. 最终生命周期架构

Shell 的 RouterView 交给 `WorkspaceViewHost` 渲染：

- Chat 一个 `KeepAlive(max=1)` 槽位。
- Mission Workspace 一个 `KeepAlive(max=1)` 槽位。
- 其他应用页面使用普通路由渲染，不进入上述缓存。
- `CachedWorkspaceView` 为缓存实例提供独立路由快照，防止隐藏视图读取另一个视图的路由。它不保存业务数据，也不是新的 Workspace Store。

继续使用原 Chat Pinia Store、ChatWorkflowBinding、Workbench Registry、EditorGroup、TextDocument、RuntimeEventStore 与 RuntimeObservationAdapter。没有复制另一份编辑器或消息业务状态。

### 3. 缓存身份与路由

| 视图 | 缓存身份 | 生命周期 |
|---|---|---|
| Chat | 以 contextId 或当前 Draft 种子区分当前会话；显式新建使用新槽位序号 | 首次发送产生 contextId 时保持原实例；消费 newConversation 标记后不再重建；切换到另一历史 Conversation 替换旧 Chat 槽位 |
| Mission Workspace | `mission:<missionId>` | runId 查询变化复用当前 Mission 实例；切换 Mission 才替换槽位 |

不以 `route.fullPath` 作为缓存身份。显式新建继续由 ChatView 的 `resetWorkspace()` 生成、持久化 Draft 和清理页面状态，Shell/Host 不生成 Draft，也不重复清消息。

Workbench 补充 runId 查询监听，复用原 `selectRun` 处理前进/后退。Projection 响应同时检查请求 Controller、活跃视图和 Mission/Run 身份；迟到请求不覆盖新选择。返回时刷新 Projection，并重新计算 current Run；用户显式选中的旧 Run 保持选中，不自动跳到外部新建的 Run。

### 4. 双向导航关联规则

既有 Chat / ACG 侧栏入口承担切换，不增加重复按钮：

1. Chat → Workbench：使用当前 Conversation 的非失效 Binding；显式 runId 必须属于该 Conversation，否则失败关闭。没有显式选择时优先活跃关联，再考虑现有历史关联。GET Run 验证 runId、missionId 全部匹配后才进入 Workspace。
2. Workbench → Chat：使用当前 Mission 和 URL 中选中的 Run 精确找 Binding；多个不同 canonical Conversation 竞争同一 Run 时拒绝猜测。GET Run 验证任务归属，GET Conversation 验证 contextId 和访问权限，然后返回原模式与原 contextId。
3. Alias 只用于查找其 canonical Binding，不改写历史格式。Draft 只在仍是同一个本地 Draft、且当前没有别的 context 时允许返回；不把 Mission ID 当 Conversation ID。
4. 关联不存在时保留原导航入口回退，并明确提示没有可恢复关联。回退 Chat 时移除未经验证的任务参数，验证原 Conversation 的访问权；已有候选关联但验证失败时停留当前视图，不借回退打开被拒绝的缓存历史。
5. 所有异步导航比较发起时的路由和导航代次。路由变动后，旧查询不能再次导航。

Binding 始终是本地导航索引，业务身份仍来自已有后端查询。本轮无 Conversation-Mission 后端关联合同。

### 5. SSE、Observation 与 Polling

| 资源 | 隐藏时 | 激活时 | 真正销毁时 |
|---|---|---|---|
| Chat 消息 SSE | 继续原请求，不 abort、不重新发送；R2 保护所有权 | 显示持续累积的消息，恢复阅读位置 | 若切换到其他 Conversation，由新会话操作使旧请求失效 |
| Chat 进度/详情查询 | 停止进度轮询、取消详情请求，保留已有展示数据 | 刷新原 Run 进度和详情 | 原清理逻辑释放 |
| Chat 全局事件/ResizeObserver | 移除页面事件，停用拖拽与动画/观察器 | 重新绑定并测量，恢复原 scrollTop | 全部清理 |
| Mission Runtime SSE | 缓存 Mission 继续持有一个共享引用，累积临时输出 | 复用同一个 Store/连接，不重复 acquire | release 共享引用；最后引用消失时断流 |
| RuntimeObservation / Projection | stop、abort、清除定时器；迟到响应无写入权 | 同一 Adapter 重新观察，GET 刷新投影 | stop 并释放注册资源 |
| Copilot | 停止定时刷新；已授权进行中的交互仍可完成到原组件 | 保留草稿，恢复一个刷新循环 | 保存既有会话缓存并取消请求 |
| 审批 / 运行计时 / CodeMirror 诊断 | 停止相应计时器；内部 lint 重试也检查激活状态 | 恢复一个循环，不重建 CodeMirror | 释放计时器、文档监听与语言服务连接 |

Inspector 的备用 SSE 所有者也具有停用保护，避免父级资源变化时在隐藏状态创建额外订阅。已发出的 Chat 启动结果在隐藏后返回时，只更新原组件/原 Binding；不能改写可见 Workbench 的 URL 或启动隐藏进度轮询。相关 payload、启动身份及幂等合同保持原实现。

返回缓存 Artifact 时，已经保留的前台文档不再重复等待一次不会重新发出的 `content-ready` 事件，Observation 会正常恢复。

### 6. Dirty Buffer 与编辑器保护

EditorGroup、WorkspaceFileEditor 和实际 CodeMirror 实例随 Mission 缓存，仍使用既有 TextDocument；文件缓冲区、光标、标签和活动 Editor 不复制、不清空。Graph 组件实例同样保留，原 renderer 的就地状态更新保持视野。

`confirmFileNavigation()` 保留，并由可覆盖隐藏 Mission 的 Router 全局守卫调用：

- 精确关联的 Chat ↔ 当前 Mission/Run 往返不要求放弃修改。
- 不相关页面、显式新建 Conversation 或切换另一个 Mission 仍检查 dirty 状态。
- 隐藏 Mission 即将被另一个 Mission 淘汰时仍会确认；取消会阻止路由提交。
- 组件销毁注销守卫；现有文件 `beforeunload` 保护继续适用于刷新/关闭。

这不是删除脏状态检查，也不是允许缓存淘汰静默丢弃文件。

### 7. 测试与最终快照

| 覆盖 | 证据 |
|---|---|
| A：Chat 往返 | 实际 Shell + ChatView + MissionWorkspaceView；同一组件 UID、未发文本、消息、文件引用、角色、模型配置、contextId、scrollTop |
| B：Workbench 往返 | 实际 EditorGroup / FileEditor / TextDocument；Graph、Task、Artifact 标签，活动 Editor、脏缓冲区、光标、选择、Graph 缩放、Auxiliary、Bottom Tab、面板宽度/折叠 |
| C：迟到 SSE | 实际 Chat Store 与可控 ReadableStream；响应头在隐藏后到达，Draft 正确迁移，完整消息保留，只发起一次消息请求 |
| D：Runtime | 隐藏时持续接收 Runtime 临时输出，唯一连接和同一 RuntimeStore；停止查询轮询、Adapter 不重建、外部新 Run 刷新、迟到 Projection/启动结果不覆盖当前 Run、销毁释放 |
| E：身份对抗 | 17 个导航用例；不存在、invalidAt、Mission/Run 不匹配、显式历史 Run、多个 Alias、canonical 歧义、403、错误 context、旧 Draft；实际 Shell 拒绝越权回退 |
| F：导航回归 | 实际 Router back/forward、不同 Conversation、历史页进入、新建 Draft、不同 Mission 及取消离开、直接 Mission 深链、新 Shell 从历史恢复 |
| 真实编辑器生命周期 | 实际 CodeMirror EditorView 保留 document/selection；暂停隐藏诊断并在激活后恢复；Graph 使用实际组件与 mocked renderer 验证 renderer 不重建 |

所有实际 Shell 往返测试还断言 AgentOS 命令 POST 为零，切换本身不创建 Mission、Run 或触发规划。

本轮新增或扩展的套件如下，数字为最终套件总用例数，路径前缀均为 `apps/frontend/src/`：

| 套件 | 最终用例数 |
|---|---:|
| `stores/chat.requestOwnership.spec.ts` | 7 |
| `stores/chat.workflow.spec.ts` | 12 |
| `views/ChatView.spec.ts` | 31 |
| `components/app/WorkspaceContinuity.spec.ts` | 11 |
| `features/workspace/navigation.spec.ts` | 17 |
| `components/workbench/WorkspaceCodeEditor.lifecycle.spec.ts` | 1 |
| `components/workspace/FormalToolApprovals.lifecycle.spec.ts` | 1 |
| `components/workbench/AcgCopilotPanel.spec.ts` | 20 |
| `components/agentos/AcgTopologyGraph.spec.ts` | 8 |

另执行 App Shell、MissionWorkspaceView、chat.stream/chat.session、RuntimeEventStore、Observation、WorkbenchLayout、TextDocument、RunProgressEditor 与 LSP 的 10 个回归套件；共计 19 个文件、240 个用例通过。

最终源码快照清单包含前端源文件、测试及配置共 484 个文件；清单 SHA-256：

`DDBBC96B7BBAA25DFFB5742E649F5A1981505429EA8E088E7F814AFF72C93A31`

| 最终检查 | 结果 |
|---|---|
| 定向：R2 + Chat/Shell/Workbench + Runtime/Observation + 编辑器 | 19 个文件 / 240 个用例通过 |
| 全量 Vitest：`npm test -- --maxWorkers=2 --minWorkers=1` | 136 个文件 / 980 个用例通过，退出码 0，201.63 秒 |
| 类型检查：`npx vue-tsc -p tsconfig.json --noEmit` | 通过，退出码 0 |
| Web 生产构建：`npm run build:web` | vue-tsc 与 Vite 均通过，退出码 0；2664 个模块，Vite 22.07 秒 |
| `git diff --check` 与源文件哈希复核 | 通过；484 个文件的哈希变化 0、文件清单变化 0，前后清单 SHA-256 完全一致 |

最终原始日志保留在本机 `$env:TEMP`：`pr-ui-02b-verified-targeted.log`、`pr-ui-02b-verified-full.log`、`pr-ui-02b-verified-types.log`、`pr-ui-02b-verified-build.log`。源文件清单为 `pr-ui-02b-verified-source.json`，构建后复核为 `pr-ui-02b-verified-source-after.json`。

开发期曾发现两个真实缺口：CodeMirror 内部 lint 重试没有随外层定时器停用、缓存 Artifact 返回后继续等待旧 content-ready。均已修复并有回归覆盖。首轮集成测试还曾因格式化 Vue 代理的巨大对象差异导致 Worker OOM，改为比较内部 UID 后通过；未提高堆上限或清缓存制造通过。最终验收表只使用上面同一源码快照的结果。

最终全量日志仍有既有 jsdom XMLHttpRequest `AggregateError` 打印，最终测试汇总全部通过、退出码 0；这些打印不作为后端网络成功或真实服务验收的证据。

### 8. 缓存淘汰、刷新和验证边界

缓存最多保留一个 Chat 和一个 Mission。切换到另一 Conversation 会替换 Chat 槽位，切换到另一 Mission 会在脏文件确认后替换 Mission 槽位；不提供无限会话/任务内存缓存。

KeepAlive 仅提供当前进程内的往返连续性。刷新后使用已有 contextId、历史/角色 API 和 Mission/runId 路由重建；未发送文本、Editor 标签、临时光标和 Graph 视野不承诺跨刷新持久化。RuntimeStore 仍保留既有缓冲区大小限制；它不是审计历史或服务端权威。

测试使用真实 Vue Router、Shell、两种视图、Pinia、ReadableStream、EditorGroup、TextDocument 和 CodeMirror；后端 API、浏览器文本几何及 Graph renderer 使用可控替代。未执行真实浏览器视觉验收、真实后端模型/工具执行或部署，因此这里只报告自测。

### 9. 工作区与未解决问题

起始的用户修改包括 Agent 配置、Electron dev 脚本、前端 router、Settings 及其测试、启动脚本、发行检查记录，以及未跟踪的 Workspace/Session 审计文档。本轮没有暂存、回滚或覆盖这些文件。`components.d.ts` 仅新增本轮 Host 的自动声明。

没有新增业务 Store、后端 API、数据库字段；没有修改 Planner、Runtime、Scheduler、Workbench Registry 或 Mission/Run 身份合同。未解决问题限于上节明确的跨刷新与真实浏览器/后端验证边界，仍待独立复验。

未 Commit、Push、Merge 或部署，HEAD 保持基线。参考：[Vue KeepAlive 生命周期与有界缓存](https://vuejs.org/guide/built-ins/keep-alive.html)。


---

## 2. 原文｜PR-UI-02B-R1｜Conversation Identity Isolation

<!-- 原始记录：PR-UI-02B-R1-ConversationIdentityIsolation-2026-11-01.md -->

日期：2026-11-01（Asia/Shanghai）

状态：**SELF-TESTED**

### 1. 起始现场与结论

- 起始 Git HEAD：`f2f211bb2cce6d1bc7e0bd95907e006160672b17`，分支 `master`。
- 起始工作区、暂存区和 untracked 均为空；`ahead 1` 是相对 Gitee 的 `origin/master`，不代表未提交修改。
- 已先阅读 Shell、WorkspaceViewHost、CachedWorkspaceView、ChatView、Chat Store、LaunchAttempt 与既有测试的真实调用链，再建立失败复现。
- 证实存在生产缺口：Store 先完成 B 的历史恢复，再从 `/chat?contextId=A` 切到 `/chat?contextId=B` 时，Host 可复用同一 ChatView；旧代次保护会被路由 watcher 的提前返回绕过。
- 本轮仅修改 ChatView 局部身份检查和既有 Shell 集成测试，另增加本报告。没有引入新的状态管理体系。

### 2. 原始问题与代码证据

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

### 3. 实际失败复现

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

### 4. 最小修复及边界

仅修改 `apps/frontend/src/views/ChatView.vue`：

1. 增加局部 Conversation 等价判断，复用既有 `conversationBindings` / `belongsToConversation` 识别正式身份及已有 Draft Alias。可见性同时核对组件当前身份与 Router 当前可见身份。
2. 在 Conversation 身份改变时独立使 composer 代次失效，并清理该页面的旧 loading、submitting、输入和启动错误。它不依赖是否需要再次 `loadHistory`，因此 Store 已恢复 B 时也生效。
3. 保留首次 Chat send 的原有 Draft 证明条件：`sendingDraftId`、当前 Draft、Store 新 context、未处于历史恢复、路由尚无 context。这条迁移不会被提前清除；已有 Alias 关系也不会被当作新 Conversation。
4. Agent composer、Workflow 启动和待确认提交恢复均捕获请求发起时的 Conversation。异步完成、catch、finally 和后续滚动同时检查原始身份与代次；当前显示 `/chat` 时还核对可见身份。
5. `activateWorkflowRun` 必须接收原始 Conversation，校验 Binding 归属后设置原始选择身份；URL 写入前再次核对该 Conversation 仍可见。历史恢复的末尾 URL 写入也核对原始 Conversation。
6. 隐藏视图的启动完成保存在原 Store 的原 Conversation Binding 中；没有为切换 Conversation 添加 AbortController 或取消请求，LaunchAttempt 的完成、对账和去重规则保持原实现。

开发中的首轮补丁曾因过早清除 Draft 首次迁移证明、以及阻挡只有 Run ID 的旧历史入口，导致 4 项既有测试失败；这些失败记录保留在 `first-fix.log`。最终补丁保留首次发送证明及既有无 context 的历史恢复语义，原有断言全部通过。

没有修改 WorkspaceViewHost、CachedWorkspaceView、Chat Store、Mission Launch 内核、幂等身份、后端、Runtime、ACG、视觉布局或 CSS。

### 5. 新增集成测试与回归合同

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

### 6. 最终验证与同一源码快照

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

### 7. 交付范围、证据与验收建议

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


---

## 附录：来源清单与合并说明

| # | 原文件 | 日期 | 性质 | 原文大小 |
|---:|---|---|---|---:|
| 1 | `PR-UI-02B-双视图无损切换实施记录-2026-10-31.md` | 2026-10-31 | 实施记录 | 12984 字节 |
| 2 | `PR-UI-02B-R1-ConversationIdentityIsolation-2026-11-01.md` | 2026-11-01 | 修复报告 | 11826 字节 |

> **合并规则**：正文逐字保留，仅做两类机械处理：(1) 标题层级下移一级，原文 H1 由各节「原文｜」标题替代，代码块内的 `#` 行不受影响；(2) 指向已合并 / 已归档文档的相对链接改写为新文件名（本册原文经查无此类链接）。结论、数字、失败记录、命令与代码块未改动。
>
> **完整性校验**：写入后对每篇正文做回读比对（忽略标题层级下移），本册 2 篇全部逐字节一致；校验脚本见整理说明。
>
> **恢复原件**：原文件已从当前目录移除，完整内容保留在 Git 历史中。整理提交前用 `git checkout HEAD -- "docs/开发记录/<原文件名>"`；提交后用 `git checkout HEAD~1 -- "docs/开发记录/<原文件名>"`。

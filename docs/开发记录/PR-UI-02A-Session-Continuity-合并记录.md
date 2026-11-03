# PR-UI-02A Session Continuity：实施与两轮修复合并记录

> **文档性质**：阶段证据合并稿——实施报告 1 篇 + 修复报告 2 篇（R1 Draft 身份、R2 消息请求代次隔离）
>
> **覆盖时间**：2026-10-31
>
> **当前定位**：会话身份与历史恢复的实施主线；R2 的最终门禁与 PR-UI-02B 实施共用同一源码快照
>
> **合并日期**：2026-11-03

## 0. 合并说明与导读

本册把 **PR-UI-02A（2026-10-31）** 的 3 篇记录合并为一篇：Session Continuity 实施报告、R1 Draft 身份修复报告、R2 消息请求代次隔离修复报告。正文逐字保留原文，仅做两类机械处理：标题层级下移一级、指向已合并/已归档文档的相对链接改写（经查本册原文均无站内相对链接，未发生改写）。来源清单见文末附录。

### 0.1 这一阶段在解决什么

UI-02 审计（见 [PR-UI-02](PR-UI-02-Workspace-Session-交互架构审计-2026-10-31.md)）建议 Workspace Session 以「现有数据的派生关系」实现，不新增实体、接口或第二套 Store。本阶段沿该路线推进，并按暴露的缺口补两轮修复：

- **02A 实施**：前端会话身份、历史恢复、本地关联迁移与 Run 展示语义（会话别名匹配、恢复优先级、draft 合冲突保护）；
- **R1**：修复新建空白 Conversation 的 Draft 身份生命周期——两种模式新建均分配新 Draft，消息只清空一次，旧绑定/别名不交叉；
- **R2**：修复消息请求代次隔离。02B 起始门禁发现该缺口后，经用户追加授权单独实施；防止旧请求的响应、finally、清历史回执与迟到 SSE 帧写回新会话。

### 0.2 一页结论

| 篇目 | 性质 | 结论 | 关键证据 |
|---|---|---|---|
| 02A 实施 | 实施报告 | SELF-TESTED：别名、恢复优先级、本地迁移与归属校验落地 | 全量 131 文件 / 936 用例；受保护文件基线 `pr-ui-02a-protected.json` |
| 02A-R1 | 修复报告 | SELF-TESTED：Draft 身份生命周期修复 | 定向 3 文件 48 用例 + 全量 936 用例、vue-tsc、build:web 全通过 |
| 02A-R2 | 修复报告 | SELF-TESTED：代次校验防旧响应写回，覆盖 7 类迟到边界 | 与 02B 共用最终门禁：19 文件 240 用例 + 全量 136 文件 / 980 用例 |

### 0.3 贯穿全阶段的不变量

- 旧 v1 binding/reference 存储保持可读，缺别名字段的旧记录不强制全局迁移；迁移只发生在有当前发送证据的本地索引上。
- 新 Draft 只解析自己的 Run；返回旧 contextId 仍恢复旧 Run；Store 绑定与别名不交叉。
- 传输取消是尽力执行，代次校验才是防止旧响应写回的最终保证；不以传输取消宣称服务端任务已取消。

### 0.4 明确未完成与放行条件

- 全部 SELF-TESTED，无独立 ACCEPT；未验证真实浏览器到真实后端的端到端往返。
- Shell 模式切换 / clearMessages 边界、Workbench 同路径 Run 切换、双视图导航留给 PR-UI-02B（见 [02B 册](PR-UI-02B-双视图无损切换-合并记录.md)）。
- R2 的最终门禁与 02B 实施共用同一快照结果，原文已注明不要以开发期结果替代最终结果。

### 0.5 阅读建议

按 02A → R1 → R2 顺序读。02A 看恢复优先级与归属校验合同，R1 看 Draft 新建/恢复矩阵，R2 看代次所有权规则与对抗用例清单。

## 篇目与阅读顺序

1. **PR-UI-02A｜Session Continuity 实施报告** — 实施报告，2026-10-31 — 原文件 `PR-UI-02A-Session-Continuity-实施报告-2026-10-31.md`
2. **PR-UI-02A-R1｜Draft 身份修复报告** — 修复报告，2026-10-31 — 原文件 `PR-UI-02A-R1-Draft身份修复报告-2026-10-31.md`
3. **PR-UI-02A-R2｜消息请求代次隔离修复报告** — 修复报告，2026-10-31 — 原文件 `PR-UI-02A-R2-消息请求代次隔离修复报告-2026-10-31.md`

---

## 1. 原文｜PR-UI-02A｜Session Continuity 实施报告

<!-- 原始记录：PR-UI-02A-Session-Continuity-实施报告-2026-10-31.md -->

日期：2026-10-31。实施范围：前端会话身份、历史恢复、本地关联迁移和 Run 展示语义。最终状态：**SELF-TESTED**。未进行独立 ACCEPT。

### 1. 现场与保护边界

- 分支 `master`；开始 HEAD `081aa3fd22903d3b73c98d1a25dc750b3f036557`。
- 开始时已有修改：`apps/agent/app/config.py`、两份 `output/release-*` 文档；新增的 PR-UI-02 审计报告。
- 实施中观察到 `SettingsView.vue` 和上述发布文档的并行修改，未写入、恢复或纳入本轮实施。
- 对 Agent 配置、原审计报告、整个 `features/mission/`、`AuthenticatedAppShell.vue` 建立 SHA256 基线。配置、原审计报告、全部 Mission Launch 文件及 Shell 均与基线一致。发布文档在执行期间发生并行变化，原样保留。
- 未执行 Reset、Checkout、Stash、Commit、Push、Merge、部署或后端数据变更。

### 2. 实际发现与问题复现

1. ChatView 原 context watcher 只维护 workspace 索引，新聊天首次获得 contextId 后未写 URL，刷新不能定位原会话。
2. Chat Store 原 loadHistory 只加载消息，未获取 Conversation 元数据，上一会话的 roleId 会残留。
3. 原历史请求没有代次保护，慢 A 请求能覆盖已恢复的 B，包括消息、contextId 和 loading。
4. 旧 Agent 会话的传输模式可能被当前视图模式覆盖；文件发送还省略了 workspaceMode。后端 `ChatStreamPersistenceService.java:37` 起按 contextId 和 workspaceMode 匹配，模式不一致可能创建另一 Conversation。
5. 直接启动任务的 draft binding 未随首次聊天 contextId 迁移，真实上下文和历史任务关联断开。
6. Chat Store、全局 reference 索引和轮询器的终态集合只覆盖 completed/failed/cancelled；部分判断混用了 status 与 phase。
7. 原恢复链虽然优先读取显式 runId，但未验证 URL missionId 与 Run 归属，也未区分已验证选择和最近 binding。
8. 历史页面初始化也会生成新的本地 draft UUID，恢复操作中没有必要。

在修改前新增两条 Store 行为测试并实际运行：均失败，分别观测到 roleId 为 `previous-role`，以及 B 恢复后 contextId 被慢请求回写为 A。日志：`%TEMP%/pr-ui-02a-red.log`。

最小方案：纯函数处理索引和选择；原 Store 局部增加历史请求代次、元数据恢复；仅在当前草稿首次发送得到 contextId 时迁移；复用现有 Run 详情和 Mission workspace GET 验证归属。未建设 Session 实体、Workspace Store 或 Session Manager。

### 3. 修改文件清单

路径均相对于 `apps/frontend/src/`：

| 文件 | 改动 |
|---|---|
| `features/workspace/session.ts`（新增） | 身份关联、别名、draft 合并、URL 增量参数、Run 选择和状态纯函数 |
| `features/workspace/session.spec.ts`（新增） | 索引多重关联、冲突保护、选择与状态行为测试 |
| `stores/chat.ts` | 历史代次保护、角色/传输模式恢复、局部 binding 迁移和别名读取 |
| `stores/chat.session.spec.ts`（新增） | 恢复竞态、模式兼容、迁移、快照与无副作用测试 |
| `stores/chat.stream.spec.ts` | 原历史恢复测试补齐现有元数据 API fixture，保留原断言 |
| `stores/workflowRuns.ts` | 原 reference 索引原位关联更新、别名持久化、共享活动状态判断 |
| `views/ChatView.vue` | context URL 同步、发送过程迁移证明、Run 归属验证与恢复优先级 |
| `views/ChatView.spec.ts` | URL/刷新/归属/历史选择/successor/Mission 恢复测试，原 fixture 补齐真实 missionId |
| `views/MissionWorkspaceView.vue` | 仅替换两处 Run 状态集合引用；未改导航和同路径切换逻辑 |
| `composables/useWorkflowProgress.ts` | 以 Run status 决定终态，保持原轮询实现 |
| `composables/useWorkflowProgress.spec.ts` | 补测所有终态及 status/phase 不一致的行为 |
| `composables/useChatWorkflowPresentation.ts` | 补齐 succeeded 和 superseded 文案 |
| `components/agentos/WorkflowRunPanel.vue` | 补齐同两种已有后端状态文案 |
| `services/api/agentos/types/workflow.ts` | 前端类型补齐已有 succeeded/superseded 状态 |

另新增本报告。未改 Conversation/Chat 后端接口、数据库、Schema、Dispatch、C2、ACG Copilot、启动内核或页面模板/CSS。

### 4. 身份合同

| 身份 | 本轮处理方式 |
|---|---|
| `Conversation.id` | 数据库 UUID，仅元数据；不作为模型历史键或 URL contextId |
| `contextId` | 原聊天历史定位键，原值用于历史 GET、续聊和 URL |
| `chatContextId` / `chatRoleId` | Mission 创建时冻结的输入快照，迁移不回写 |
| `binding.conversationId` | 本地关联主键，可由有证据的 draft 迁往真实 contextId |
| `conversationAliases` | 在现有 binding/reference 内保留历史键；不是新 Session 状态或后端字段 |
| `missionId` | 正式任务身份；必须与读取到的 Run 归属一致 |
| `runId` | 执行实例身份，同时是本地去重键；不代表 Mission 的最新 Run |
| `operationId` / `clientRequestId` | 原启动身份，保留原值及原 LaunchAttempt 存储位置 |

一个 context 的 binding 数组可保留多个 Mission；同一 Mission 可保留多个不同 Run。迁移不会按 Mission 去重。

### 5. Conversation 恢复机制

- `loadHistory(contextId)` 是历史恢复入口，设置本次目标和请求代次，同时读取原消息及现有 `conversationApi.getConversation(contextId)` 元数据。
- 元数据 contextId 必须等于本次目标才恢复 roleId；允许原 roleId 为空。开始恢复时清除上一会话角色，避免跨会话残留。
- 消息、角色、使用量和 loading 的回写均受到请求代次和目标 contextId 保护。切换 B 或清空草稿后，A 的成功/失败/finally 均失效。
- `setContextId(non-null)` 返回 `loadHistory` 的 Promise；null 只清空并使旧请求失效。View 发现目标 context 已在 Store 中时不会再加载一次。
- 历史元数据失败或 contextId 不匹配时，可保留读取到的消息，但记录恢复错误并阻止普通发送，避免带错误角色/模式续聊。恢复请求可通过原 loadHistory 入口重试。
- 传输 workspaceMode 取原 Conversation 元数据，兼容旧索引和 Agent binding。普通及文件/流式发送都尊重已恢复模式；没有将旧 Agent Conversation 强制改为 chat。
- 首次发送取得 contextId 后增量 `router.replace`，保留所有已有 query；不重新加载刚收到的消息。空 context/draft 不发起历史读取，也不自动创建 Conversation。
- 全新空白页面仍可生成本地 draft 键；它不作为新的 LaunchAttempt/clientRequestId。历史恢复页面不生成这一草稿 UUID。

### 6. draft 迁移机制

- 只在当前组件开始首次聊天/文件发送前记录当前 draft；接到 contextId 时，必须仍是无历史 URL 的同一 draft、此前没有 contextId，且不是历史加载过程，才调用迁移。
- 仅本地 binding/reference 索引改变。真实 context 下已有记录与 draft 记录按 runId 合并；保留 draft 别名，删除冗余 draft bucket。
- 如同一 runId 在两侧指向不同 Mission，拒绝整次归并并保留原索引。未知 draft、不匹配的目标 context、历史页面加载不会猜测迁移。
- reference 仍以原 runId 为键，只更新已有记录。已存在于真实 context 的相同 reference 也补充历史别名；不重新 register 或创建 reference。
- binding 的状态更新/失效标记支持旧别名，刷新后可从同一 v1 存储读回别名。
- 不插入消息、不移动或编辑 LaunchAttempt、不重写 operation/client ID、冻结请求或原始 input。测试以真实 `createMissionLaunchAttempt.begin` 建立快照，比较迁移前后的整个 sessionStorage 和完整 pending identity。

### 7. Run 恢复与终态规则

恢复顺序：URL 显式 Run（及指定 Mission）→本会话已验证选择→最近有效的后端确认非终态 binding→已读取验证的历史 Run→空状态。

- 显式 runId 不因绑定中的最新 Run 或 `supersededByRunId` 改变；不会跟随 successor 自动跳转。
- URL 仅指定 missionId 时读取既有 Mission workspace 投影，读取其现有 Run，再验证 Run 的 missionId；将有效选择写入 URL，保留其他参数。
- 后端返回 runId 必须匹配请求 runId；存在预期 Mission 时，还必须匹配 missionId。URL 或 binding 的归属不一致时不选择替代 Run、不伪造 binding。
- 本地历史 binding 只提供候选，不视为最新 Run 事实；候选由 GET Run 验证。最新候选与当前选中实例分别处理。
- 预读取的已验证 Run 只传递一次给原详情加载器，避免恢复时重复 GET；原详情重试和缓存机制保留。
- 显式历史 ID 暂时不可读取时，保留 URL 和原有详情失败/重试展示，不认定其为有效 binding；后续详情成功仍须验证归属。恢复过程中不创建 Mission/Run。
- 活动状态：pending、planning、running、waiting_review、retrying。
- 终态：failed、completed、succeeded、cancelled、superseded。completed/succeeded 展示成功，superseded 展示被替代。
- status 独立于 lifecyclePhase 和 Formal Control；例如 retrying 即使出现旧 failed phase，仍继续轮询。未改变 Runtime 状态机。

### 8. 验证记录

新增 36 项行为测试（新增两个 spec 并扩展既有 spec）。未删除或放宽旧断言。

| 验证 | 结果 |
|---|---|
| 修改前复现：`npm test -- src/stores/chat.session.spec.ts` | 2 条失败，证实角色残留与 A/B 竞态 |
| 首轮定向回归 | 7 文件、69 测试通过 |
| 扩展后的定向复核 | 5 文件、94 测试通过，包含原 MissionWorkspaceView 31 项测试 |
| 初轮完整回归 | 129 文件通过、2 文件失败；921 测试通过、2 失败，另有 1 未处理计时器错误。保留失败证据，不作为最终通过结果 |
| 冻结源码后完整回归：`npm test -- --maxWorkers=2 --minWorkers=1` | **131 文件、923 测试通过，退出码 0，无未处理错误；161.97s** |
| 独立 TypeScript：`npx vue-tsc -p tsconfig.json --noEmit` | 退出码 0 |
| `npm run build:web`（再次包含 TypeScript） | 退出码 0；Vite built in 30.02s |
| `git diff --check` | 退出码 0；仅原有 LF/CRLF 提示 |

补充检查：全部新增文件无行尾空白；ChatView 和 MissionWorkspaceView 的 template/style 块与 HEAD 完全一致。最终 diff 已逐项审查；未暂存修改，结束 HEAD 仍为 `081aa3fd22903d3b73c98d1a25dc750b3f036557`。

初轮全量执行期间源码仍有修订，新增冲突保护断言与已转换模块交错；同时原 Workbench runtime 流测试失败，并在测试环境退出后触发 localStorage 计时器错误。随后冻结源码，以 `--maxWorkers=2 --minWorkers=1` 降低调度负载复核；旧 Workbench 测试不变，定向 31 项已通过。最终完整回归仍执行全部 spec，不屏蔽失败或异常。

无副作用证据：历史恢复测试监视两套 HTTP client 的 POST 及 UUID 生成，均未调用；迁移测试监视任务创建和 Material 创建，均未调用，并断言消息数/reference 数不增加、整个 LaunchAttempt 存储字节串及 identity 不变。View 刷新不调用启动、发送或迁移；错误归属不轮询、不读取拓扑、不创建 binding。完整回归还覆盖原 Launch Safety、幂等、恢复、策略及架构约束测试。

本机日志保留于 `%TEMP%`：`pr-ui-02a-red.log`、`pr-ui-02a-focused.log`、`pr-ui-02a-focused2.log`、`pr-ui-02a-focused-final.log`、`pr-ui-02a-full.log`、`pr-ui-02a-full-final.log`、`pr-ui-02a-type.log`、`pr-ui-02a-build.log`。受保护文件基线为 `pr-ui-02a-protected.json`。

### 9. 兼容性与尚未实施事项

- 原 v1 binding/reference 存储仍可读取；缺少别名字段的旧记录无需全局迁移。迁移仅发生在有当前发送证据的本地索引上。
- 旧 Agent workspaceMode 保留；旧 contextId 未替换成数据库 UUID。
- 未验证真实浏览器到真实后端的端到端往返；当前证据为 Vitest/jsdom 行为测试、源码合同检查、类型检查和实际构建。
- 无可靠关联证据的历史 draft 继续保留；不尝试从冻结 LaunchAttempt 推测或重写历史会话。
- Shell 模式切换/clearMessages 边界、Workbench 同路径 Run 切换、双视图导航仍留给 PR-UI-02B。
- 本轮不提供新的元数据恢复错误 UI 或多任务管理 UI；沿用现有错误提示和历史读取入口。

### 10. 关键源码位置

| 文件与行号 | 内容 |
|---|---|
| `features/workspace/session.ts:2` | 共享 Run 状态 |
| `features/workspace/session.ts:19` | 会话别名匹配与 binding 查找 |
| `features/workspace/session.ts:27` | draft 合并及冲突保护 |
| `features/workspace/session.ts:47` | Run/Mission 验证 |
| `features/workspace/session.ts:51` | 恢复优先级纯函数 |
| `stores/chat.ts:256` | 本地关联迁移 |
| `stores/chat.ts:805` | 历史代次及元数据恢复 |
| `stores/chat.ts:890` | setContextId 调用合同 |
| `stores/workflowRuns.ts:222` | reference 原位迁移 |
| `views/ChatView.vue:1298` | 详情重试时再次验证归属 |
| `views/ChatView.vue:2104` | Run 恢复入口 |
| `views/ChatView.vue:2198` | 当前发送证明及 URL 同步 |
| `composables/useWorkflowProgress.ts:73` | 只按 Run status 判断终态 |
| `views/MissionWorkspaceView.vue:362` | Workbench 复用同一终态判断 |

最终状态：**SELF-TESTED**；不提交、不推送、不部署，修改保留等待独立验收。


---

## 2. 原文｜PR-UI-02A-R1｜Draft 身份修复报告

<!-- 原始记录：PR-UI-02A-R1-Draft身份修复报告-2026-10-31.md -->

- **状态：SELF-TESTED**
- **日期：2026-10-31**
- **基线：** `117a510dbca7077a3937faa42a087b3685f9cbc0`
- **范围：** 修复新建空白 Conversation 的 Draft 身份生命周期；未修改 Mission Launch、LaunchAttemptIdentity、requestSnapshot、operationId/clientRequestId 生成规则、conversationAliases 历史格式、后端、Workspace Store 或视觉布局。

### 实施

1. Shell 的 Chat/Agent 新建入口统一通过 `/chat?...&newConversation=1` 表达一次新建意图，不在 Shell 清消息或生成 Draft。工作区模式切换也发送相同意图，并保留目标模式。
2. ChatView 复用现有 `resetWorkspace()` 消费意图：只清理一次消息、生成并持久化新的 `draft:${createClientRequestId()}`，清除选中 Conversation、Run、Run 详情和进度上下文，并移除路由中的 `contextId`、`missionId`、`runId` 与一次性标记。
3. 新建标记消费期间跳过旧 `contextId` 历史加载和 Run 恢复，避免组件复用时旧任务在清空后被异步恢复；清除标记后，旧 Conversation 仍按自己的 `contextId` 恢复。
4. 旧绑定及其 `conversationAliases` 保持原样；新 Draft 使用独立键，不继承旧会话别名。

### 验收覆盖

- Shell → 实际 ChatView 集成：Chat 与 Agent 两种模式均通过侧栏新建，Draft ID 与旧 ID 不同，消息只清空一次，旧绑定/别名保留。
- ChatView 新建标记：两种模式、同模式路由复用、模式切换均分配新 Draft；移除旧 context/Mission/Run 参数并保留 workspace。
- 任务恢复：新 Draft 只解析自己的 Run；返回旧 `contextId` 后仍恢复旧 Run。
- Store 绑定：迁移后的旧 Alias 保持在旧 Conversation，新 Draft 的 binding 不交叉。

### 验证结果

| 检查 | 结果 |
|---|---|
| 定向测试：`src/App.spec.ts src/views/ChatView.spec.ts src/stores/chat.session.spec.ts` | 通过，3 个文件 / 48 个用例 |
| 前端全量测试：`npm test -- --maxWorkers=2 --minWorkers=1` | 通过，131 个文件 / 936 个用例 |
| 独立 TypeScript 检查：`npx vue-tsc -p tsconfig.json --noEmit` | 通过，退出码 0 |
| Web Build：`npm run build:web` | 通过；vue-tsc 与 Vite build 均成功，2660 个模块转换 |
| `git diff --check` | 通过；无空白错误 |

测试输出中有既有 jsdom `AggregateError` 与 Vue Router 生命周期警告，但全量测试最终退出码为 0，全部用例通过。

### 边界与工作区

- 当前只完成自测，未做独立复验、浏览器 E2E、部署或运行时验收。
- 本轮未 Commit、未 Push、未部署。
- 发现并保留了与本任务无关的既有工作区修改；没有暂存、回滚或覆盖它们。


---

## 3. 原文｜PR-UI-02A-R2｜消息请求代次隔离修复报告

<!-- 原始记录：PR-UI-02A-R2-消息请求代次隔离修复报告-2026-10-31.md -->

- 日期：2026-10-31
- 状态：**SELF-TESTED**，等待独立复验
- 基线：`ae709af60a0f734b342073a7c94d92396463906e`
- 授权：02B 门禁检查发现 R2 未实现后，用户明确要求“根据第一性原理修复缺口然后推进任务”。本记录单独说明 R2；双视图实施另见同日 02B 记录。

### 根因与所有权规则

原来的 `historyGeneration` 只保护历史读取。文件消息响应、SSE 响应头/事件及它们的 `finally` 直接写当前 Pinia 状态；SSE 还用可复用的消息数组下标寻找接收对象。清空数组不能让已发出的请求失去写入权限，AbortController 也不能保证传输没有迟到响应。

现在将两类行为区分为：

- 显式新建、加载其他 Conversation、清空/替换消息：使旧消息请求失去所有权，并尽力取消旧 SSE 传输。
- 同一 Conversation 的视图隐藏/恢复：保留消息请求所有权，允许原 SSE 持续完成。

### 修复

1. `stores/chat.ts` 为消息请求引入内部代次。文件响应、异常及收尾均检查当前所有者；旧错误不再回到新 Composer。
2. SSE 捕获自己的消息对象，停止通过数组下标寻找新会话的消息；迟到响应头、数据帧、错误和收尾均不能更新新会话的 context、usage、请求 ID 或 loading/streaming 状态。
3. `clearMessages`、`loadHistory`、`setContextId(null)`、`setMessages` 使旧消息请求失效。异步清历史的结果同样不能清掉其后开始的新消息请求。
4. 取消操作在等待后端取消回执前捕获原 Controller，回执晚到也只取消原传输。
5. ChatView 的 Composer 持有自己的代次；新建/切换 Conversation 后，旧文件、Chat/Agent 发送及旧启动结果不能恢复旧输入或释放新请求的 UI 锁。
6. 已授权的 Mission 启动结果仍按原 Conversation 和原 operation/clientRequest 身份保存 Binding；消息投影受 Conversation 代次保护，不向新会话插入原任务消息。启动 payload、requestSnapshot、operationId/clientRequestId、LaunchAttemptIdentity 和服务端合同未改变。

### 对抗验证

新增 `stores/chat.requestOwnership.spec.ts` 7 个用例覆盖：

- 旧文件响应与旧 finally 晚于新请求。
- 旧文件错误不回流新输入框。
- 旧清历史回执不清除新消息请求。
- 不配合 abort 的 SSE 在相同消息下标发送迟到帧。
- 新建 Conversation 后迟到的 SSE context 响应头。
- 切换历史 Conversation 后的旧文件响应。
- 等待后端取消回执期间开始了新 SSE。

`ChatView.spec.ts` 对 Chat/Agent 两种 Composer 增加旧失败/旧 finally 对抗；`chat.workflow.spec.ts` 增加启动前微任务及启动响应等待期间切换会话的两个用例，验证原 Binding 保留、原请求身份不变、新消息不受污染。

进入 02B 前，R2 曾单独执行相关 52 个用例通过；随后补充上述边界，并纳入最终统一源码快照回归。最终门禁结果与 02B 记录共用，避免用开发期结果替代最终结果。

| 最终门禁 | 结果 |
|---|---|
| 19 个定向文件（含 R2、Chat/Shell/Workbench、Runtime/编辑器） | 240/240 通过 |
| 全量 Vitest | 136 个文件 / 980 个用例通过，退出码 0 |
| `npx vue-tsc -p tsconfig.json --noEmit` | 通过，退出码 0 |
| `npm run build:web` | 通过，vue-tsc 与 Vite 生产构建退出码 0 |
| `git diff --check` 及统一快照复核 | 通过；484 个文件哈希与文件清单变化均为 0 |

### 边界

本轮没有修改后端、启动身份合同、Alias 存储格式或新增业务 Store。传输取消是尽力执行；代次校验才是防止旧响应写回的保证。前端测试不能证明服务端任务已经取消，也未以此作出取消声明。

未 Commit、Push、Merge 或部署。SELF-TESTED 不代表独立验收通过；最终源码清单 SHA-256 与日志索引见 02B 记录。


---

## 附录：来源清单与合并说明

| # | 原文件 | 日期 | 性质 | 原文大小 |
|---:|---|---|---|---:|
| 1 | `PR-UI-02A-Session-Continuity-实施报告-2026-10-31.md` | 2026-10-31 | 实施报告 | 13741 字节 |
| 2 | `PR-UI-02A-R1-Draft身份修复报告-2026-10-31.md` | 2026-10-31 | 修复报告 | 2756 字节 |
| 3 | `PR-UI-02A-R2-消息请求代次隔离修复报告-2026-10-31.md` | 2026-10-31 | 修复报告 | 3986 字节 |

> **合并规则**：正文逐字保留，仅做两类机械处理：(1) 标题层级下移一级，原文 H1 由各节「原文｜」标题替代，代码块内的 `#` 行不受影响；(2) 指向已合并 / 已归档文档的相对链接改写为新文件名（本册原文经查无此类链接）。结论、数字、失败记录、命令与代码块未改动。
>
> **完整性校验**：写入后对每篇正文做回读比对（忽略标题层级下移），本册 3 篇全部逐字节一致；校验脚本见整理说明。
>
> **恢复原件**：原文件已从当前目录移除，完整内容保留在 Git 历史中。整理提交前用 `git checkout HEAD -- "docs/开发记录/<原文件名>"`；提交后用 `git checkout HEAD~1 -- "docs/开发记录/<原文件名>"`。

# PR-UI-05B 持久任务入口与双向连续性实施记录

日期：2026-11-04。状态：SELF-TESTED。05A 仍未获得独立 ACCEPT。

## 入场

master / HEAD 为 `9ba090b275ae4f01cd927aebff14322fe755f275`，GitHub master 实时核验一致。暂存区为空。保留原有五项 Python 工作：workflow_runtime.py、memory_workflow_store.py、sqlite_workflow_store.py、workflow_store.py、test_workflow_store_contract.py；本轮未编辑、暂存这些文件。Gitee tracking ref 落后一项是上轮仅推送 GitHub 的结果。

## 05A 审计复现

先增加真实 FormalExecutionControls 组件测试和 navigation 竞争测试，再运行原实现：48 项中 11 项失败、37 项通过，退出码 1。日志 `%TEMP%/pr-ui-05b-before.log`。

同 Run 的 graphId、graphVersion、permitId、runtimeRevision、运行状态和能力失效不会使旧 generation 过期，迟到回执仍发 succeeded。修复为同步观察身份、正式来源、版本、状态、能力及只读条件快照；变化使请求代次过期，成功、错误和 finally 均沿用同一代次保护。不改变 prepareFormalCommand、operationId 或重试存储合同。

反向导航原先只在 await 前选 binding，无法发现 readRun/readConversation 期间撤销、替换、跨 Mission owner 或 Alias 冲突。现在在每次查询后重新核验同 Run 的唯一 canonical owner、绑定内容及 Alias 归属。Shell 同时检查路由、导航代次、Store index 和当前 context；原关联在查询中撤销时不能走缓存 fallback。

实施期间一次 Shell guard 编辑误扩到另一个处理器，产生未定义局部变量；中间回归保留失败日志，随后补齐该处理器的请求前快照，最终门禁全部重跑。中间结果不作为最终验证。

## 交互与数据合同

Chat 现有运行摘要下增加“打开所选 Run 的 Workbench”，数据来自已恢复并由后端查询验证的 activeWorkflowRun 与当前 Conversation binding，不依赖 formalControl 或 Dispatch。运行中、待审核、历史终态均可导航。同一 Conversation 多 Run 使用明确选择列表，通过现有 runId 路由恢复合同切换，不创建任务。

一次性 Dispatch 提示继续仅接受正式控制组件的合法 ACCEPTED / IDEMPOTENT_REPLAY 回执，沿用 sessionStorage 去重。“稍后”只关闭提示，持久入口仍在；重新挂载不发 POST。提示与持久入口均调用同一导航函数，使用 conversationWorkbenchTarget 和真实 getWorkflowRun 校验。

查询前捕获 Conversation、Mission、所选 Run、路由与导航代次；查询后核对当前可见身份、同一 Store index 和唯一 canonical binding。403、404、409、网络失败或无法确认归属时保留当前页面。反向导航使用 workbenchConversationTarget，返回 canonical context 及原 workspaceMode。没有用 Mission ID 替代 Conversation ID。

任务状态仍来自 Run / Progress / Observation。入口本身不证明已 Dispatch、运行或完成；没有新增 SSE、轮询、全局导航 Store、执行控制器或 Copilot Session。沿用 Shell 缓存、ACG、编辑器与 Copilot 连续性合同。

## 修改清单

- FormalExecutionControls.vue：同 Run 来源和授权快照失效保护。
- FormalExecutionControls.spec.ts：六项迟到回执反例。
- navigation.ts：双向查询后 binding、canonical owner 与 Alias 校验。
- navigation.spec.ts：五项反向查询竞争反例。
- AuthenticatedAppShell.vue：双向请求前后路由、context 与 index 一致性。
- ChatView.vue：摘要区持久入口、Run 选择、共用验证导航及过期请求保护。
- ChatView.spec.ts：提示关闭及重新挂载后入口存在，无自动 POST。
- WorkspaceContinuity.spec.ts：真实 Shell / Router / Pinia 下九项新增场景；三个状态各三轮往返、四类故障、迟到导航、多个 Run 选择。原有 21 项保留。
- 本实施记录。

## 最终门禁

所有命令在 apps/frontend 执行，日志位于 `%TEMP%/pr-ui-05b-*.log`。

- `npm test -- src/components/workspace/FormalExecutionControls.spec.ts src/features/workspace/navigation.spec.ts src/views/ChatView.spec.ts src/components/app/WorkspaceContinuity.spec.ts --maxWorkers=2 --minWorkers=1`：退出 0；4 文件、116 项通过（Formal 24、navigation 24、Chat 38、Continuity 30）。
- `npx vue-tsc -p tsconfig.json --noEmit`：退出 0。
- `npm test -- --maxWorkers=2 --minWorkers=1`：退出 0；143 文件、1088 项全部通过，429.43 秒；未报告未处理 Promise rejection。
- `npm run build:web`：退出 0，Vite 构建 55.73 秒。
- `git diff --check`：退出 0。

定向、全量、类型检查和构建对应同一最终前端源码，验证后逐文件 SHA-256 复核一致。清单覆盖所有 Git tracked apps/frontend 文件（不含本报告和并行 Python 工作）；按路径排序的 JSON 清单位于 `%TEMP%/pr-ui-05b-source.json`，其 SHA-256 为 `fb86f037033da085ef8ada4b5b05e1bbf1406450e43ea4a43818d208552842b1`。

前端 diff：8 文件，147 行新增、19 行删除，另新增本报告。验证未修改测试 deadline、排除规则或删除原测试；原有 teardown 持续校验 SSE 释放，新增多轮测试最大订阅数不超过 1。现有编辑器/ACG/Copilot Continuity 断言及全量回归保留。

## 风险与审计边界

本轮是组件和真实 Shell 集成验证，未进行真实浏览器视觉验收或远端执行 E2E；不宣称独立 ACCEPT。sessionStorage 不可用时，一次性提示去重继续退化为当前实例内去重。身份查询无法确认时入口拒绝导航，需刷新后重试。原 Shell 无关联工作区返回通用 Chat 的 fallback 仍保留；曾存在关联但在查询中被撤销的请求禁止 fallback。

未提交、推送、合并或部署。等待独立审计。

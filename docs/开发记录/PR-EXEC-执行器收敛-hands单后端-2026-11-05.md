# PR-EXEC 执行器收敛：删除 python Local Runtime，hands 单后端（2026-11-05）

## 结论

- 执行后端收敛为唯一一套：**zhiyi-hands（DSH 基座，`apps/hands` TS 服务）**。python Local Runtime 执行器（`apps/local-runtime`，30 文件 3,863 行 + 自带测试 1,890 行）整体删除。
- `LocalRuntime*` 共享脊柱保留（chat 通道不受影响）：契约 `contracts/local_runtime.py`、客户端 `adapters/local_runtime.py`、传输基类 `adapters/local_runtime_http.py`（`HandsHttpTransport` 的父类）、chat 执行器 `app/tools/local_runtime.py`、资源平面 `components/resource/local_runtime.py`。hands 骑在同一合同/协议上，这些是它的地基。
- chat 与 mission 两条链全部经 hands 执行：wiring 门控无条件化后，chat 借 `runtime.local_runtime_client`（HandsHttpTransport），mission 链恒套 `FormalWorkspaceTools`（正式五步 + 收据闭环）。

## 同日上游工作（切换先行）

1. **chat 切 hands 的传输适配**（`apps/agentOS/src/adapters/hands_http.py` + 新增 `hands_patch.py`）：
   - `cancel` 覆盖：hands 回执无 requestId/invocationId 回显，基类校验必抛；409 `EXECUTION_ALREADY_SETTLED` 幂等回查
   - `events`/`stream_events` 翻译：hands wire（`stdout.delta`/`payload.text`）→ LocalRuntime 契约（`stdout_delta`/`data.delta`）；终态事件 `query_execution` 富化 exitCode/timedOut/error.code，receipt checksum fail-closed
   - `shell.exec` 在 `execute()` 入口早返回 `accepted`（chat run_command 依赖 admission 即返回 + 事件流推进终态；formal 链 `execute_with_identity` 阻塞收据不受影响）
   - chat `patch_file` 的 unified diff → 读-改-写两收据（applier 逐字移植自已删除的 local-runtime `apply_unified_patch`，见 `hands_patch.py`）
   - `overwrite:False`→`createIfAbsent:true`、shell `cwd`→`workdir`、fs.list 条目 `{name,type,target}`→`{path,name,type}`
2. **切换方式**：唯一途径 = 停栈后改 `<home>/environment.json` 顶层 `"backend":"hands"` + `-Recover`（`up --backend` 不生效；`init` 对已有 home 早退）。本次删除后 backend 键与门控全部移除，hands 恒定，无需再改任何配置。

## 删除与无条件化清单

| 位置 | 改动 |
|---|---|
| `apps/local-runtime/` | 整目录删除（git rm，46 文件） |
| `apps/agent/tests/test_chat_local_runtime_http_e2e.py` 等 3 件 | spawn python 服务的子进程 E2E 删除；覆盖由 `test_chat_hands_http_e2e.py`（含新增 DENY 用例：拒绝后不执行、账本无新行）+ `test_chat_permissions.py` 单元承接 |
| `apps/agent/app/execution/wiring.py` | `AGENTOS_EXECUTION_BACKEND` 门控删除：恒 `HandsHttpTransport`、恒 `FormalWorkspaceTools`；`HttpLocalRuntimeTransport` import 移除 |
| `apps/agent/app/execution/workspace_authority.py` | `'python'` 旧 Run 回退分支删除 |
| `ops/.../persistent_runtime.py` | host 启动二选一 → 恒 `start_hands`；env 恒 hands + shell `'true'` + node/npm 探测；`--backend` CLI 参数与 init 写入的 backend 键删除；state_for 的 backend 补注移除 |
| `ops/.../native_runtime.py` | snapshot python 探测分支删除（恒 `/v1/health` + node.exe + `zhiyi-hands` 断言）；死代码 legacy `up()` 整块移除（全仓无调用方，引用已删服务）及 `up` CLI 动作 |
| `ops/.../persistent.ps1` | `-Backend` 参数删除 |
| `ops/scripts/release/assemble_portable.py` | `copy_app("local-runtime")` 删除 |
| `ops/.../README.md` | N01A harness 退役横幅（`up` 动作已移除，唯一入口 persistent.ps1） |

途中修复过的既有缺口（同文件）：`state_for` 原先只在全新分支写 backend 键，已初始化 home 加载时缺失 → 快照按 python 模式找 `python.exe`（node 树）→ 全栈 DOWN「ordinary-user non-elevated tokens」。该问题随本次单轨化一并消亡。

## 验证证据

- 单元：`test_hands_transport_chat.py` 13 用例（先红后绿）；`test_execution_adapter_settlement.py` 16/16（formal 阻塞收据合同不变）
- E2E：`test_chat_hands_http_e2e.py` 2 用例（真 hands 子进程全 chat 链：读写 patch 往返 + 守卫拒覆盖 `FS_NOT_OBSERVED` + 账本收据断言 + run_command 流式/exitCode + 中途取消 `cancel-requested` 行 + 越界拒绝 + DENY）
- 回归：chat 全套 60/60；删除后 chat 全量（排除 8 个既有收集断裂文件，见下）后台复跑
- 真栈：hands 模式 Recover 全 UP（快照 `zhiyi-hands` PASS）→ chat 实发消息 → 账本 `fs.list` 收据（grant `n01a-grant`）+ 模型答真实工作区内容 → fs.list 直调 175ms/次（轮询节奏，结构预期 +150ms 起步）

## 已知边界与遗留

- **无回退能力**：python 执行器删除后不可回退，唯一后端 hands（用户裁决）
- agentOS `pytest tests/adapters` 中 `test_hands_integration` 2 用例为既有红（pytest.ini 不含 `apps/agent` 路径，`import app.*` 必挂），与 hands 无关
- `apps/agent/tests` 有 8 个**既有**收集断裂文件（`test_branch_safe_mission_lifecycle.py` 等 import 从未入库的 `test_planning_loop`），属规划器测试区历史欠账，非本次改动
- chat 写工具审批走 SSE + 前端 UI（chat permission 弹窗）；mission 链正式审批为另一套（`formal_tool_pending`），两套并存如设计
- 延迟代价保留：每次 hands 工具调用 +150ms 轮询起步；UNKNOWN fail-closed 不自动重试

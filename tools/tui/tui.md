# 知弈 AgentOS TUI 开发手册

本文面向后续接手 `tools/tui` 的开发者，说明 TUI 的运行方式、代码结构、数据流、测试方法和常见注意事项。

## 概述

基于 Textual 框架构建的终端 UI，对标 Claude Code 的交互体验，将知弈 AgentOS Web 前端的功能迁移到终端。通过 REST API 与 AgentOS FastAPI 后端（`agent/app/main.py`）通信，提供聊天和工作流控制台两个核心页面。

版本 0.1.0 — 2026-06-04

当前约定：WebUI 和 TUI 统一使用 Docker 中的 AI 后端。默认 API 地址是 `http://127.0.0.1:8000/ai`，由根目录唯一基线 `compose.yaml` 叠加开发和 Windows 覆盖层启动。TUI 默认不再自动启动本地 `uvicorn` 后端，避免出现两套服务、两套数据源或行为不一致。

## 快速开始

推荐从仓库根目录运行：

```powershell
.\tools\tui\start.ps1 -Role lawyer
```

脚本会做三件事：

1. 使用 `compose.yaml` + `compose.dev.yaml` + `compose.windows.yaml` 启动或复用 Docker `ai-service`。
2. 等待 `http://127.0.0.1:8000/health` 可用。
3. 设置 `AGENTOS_API_URL=http://127.0.0.1:8000/ai` 并启动 TUI。

也可以直接运行 CLI：

```powershell
$env:PYTHONPATH = "tools/tui/src"
$env:AGENTOS_API_URL = "http://127.0.0.1:8000/ai"
python -m kinlin_tui.app os --role lawyer
```

安装为可执行命令：

```powershell
python -m pip install -e tools/tui
zhiyi os --role lawyer
zhiyi start --role lawyer
```

如需连接非默认后端，可以显式传入：

```powershell
zhiyi os --api-url http://127.0.0.1:8000/ai
```

## Docker 后端同步

如果修改了 `agent/app`、`agent/packs` 或其他会被 `agent/Dockerfile` 复制进镜像的后端代码，需要重建 Docker AI 服务，WebUI 和 TUI 才会同时生效：

```powershell
docker compose -f compose.yaml -f compose.dev.yaml -f compose.windows.yaml --env-file .env.windows --profile debug-ports build ai-service ai-debug-port
docker compose -f compose.yaml -f compose.dev.yaml -f compose.windows.yaml --env-file .env.windows --profile debug-ports up -d ai-service ai-debug-port
```

验证 Docker 后端是否已使用新代码：

```powershell
@'
import json
import urllib.request

payload = json.dumps({"text": "你好", "sessionId": "probe"}, ensure_ascii=False).encode("utf-8")
request = urllib.request.Request(
    "http://127.0.0.1:8000/ai/agent/lawyer/chat",
    data=payload,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=30) as response:
    data = json.loads(response.read().decode("utf-8"))
print(data["answer"])
print(data["skillsUsed"])
print(data["trace"][0]["action"])
'@ | python -
```

期望结果中 `trace[0]["action"]` 是 `direct_response`，说明“你好”没有被错误送入案件分析工作流。

## 目录结构

```text
tools/tui/
├── pyproject.toml
├── start.ps1
├── tui.md
├── src/kinlin_tui/
│   ├── app.py
│   ├── theme.py
│   ├── mascot.py
│   ├── api/
│   │   └── client.py
│   ├── screens/
│   │   ├── chat.py
│   │   └── dashboard.py
│   └── widgets/
│       ├── command_bar.py
│       ├── header.py
│       ├── mascot_widget.py
│       ├── status_tag.py
│       └── step_list.py
└── tests/
    └── test_app.py
```

核心文件：

- `app.py`：Textual 应用入口和 `zhiyi` CLI。默认连接 Docker API。
- `api/client.py`：`AgentOSClient`，封装 `/ai` 下的 HTTP 接口。
- `screens/chat.py`：主聊天界面，负责角色切换、消息发送、会话 ID 复用。
- `screens/dashboard.py`：工作流控制台，负责运行列表、步骤详情和 Trace 查看。
- `theme.py`：角色主题、中文角色名、图标和 Textual CSS。
- `start.ps1`：Windows PowerShell 一键启动脚本，统一走 Docker 后端。
- `tests/test_app.py`：TUI 回归测试。

## 启动入口

`pyproject.toml` 注册了两个命令：

```text
zhiyi = kinlin_tui.app:main
kinlin-tui = kinlin_tui.app:main
```

支持的常用形式：

```powershell
zhiyi os --role lawyer
zhiyi os --role teacher
zhiyi os --role programmer
zhiyi os --role writer
zhiyi start --role lawyer
```

历史兼容形式也可用：

```powershell
zhiyi --role lawyer
```

`zhiyi start` 会尝试启动 Docker `ai-service`；`zhiyi os` 只启动 TUI，并默认连接 `http://127.0.0.1:8000/ai`。

## 数据流

聊天数据流：

```text
ChatScreen
  -> AgentOSClient.agent_chat(role, text, session_id)
  -> POST /ai/agent/{role}/chat
  -> 读取响应 answer
  -> RichLog 渲染 Markdown 文本
```

Dashboard 数据流：

```text
DashboardScreen
  -> AgentOSClient.list_workflow_runs()
  -> GET /ai/core/workflows/runs
  -> DataTable 展示运行记录
  -> 选中行后 get_workflow_run(run_id)
  -> StepList 展示步骤详情
```

会话逻辑：

- `ChatScreen` 按角色维护 `_session_ids`。
- 第一次发送时不带 `session_id`。
- 后端返回 `sessionId` 或 `session_id` 后，后续同角色消息会复用该会话 ID。
- 切换角色后使用该角色自己的会话 ID，避免不同角色上下文混在一起。

## API 客户端约定

`AgentOSClient` 默认地址：

```text
http://127.0.0.1:8000/ai
```

重要约定：

- 使用 `127.0.0.1`，不要默认使用 `localhost`，减少 Windows IPv4/IPv6 解析差异。
- `httpx.AsyncClient` 设置了 `trust_env=False`，避免本地请求被系统代理转发导致 `502 Bad Gateway`。
- HTTP 错误会尽量解析后端返回的 `detail`、`message` 或 `error` 字段。
- 客户端方法通常返回字典；调用方应检查 `"error"` 字段，而不是假设一定抛异常。

常用接口：

| 方法                     | 后端接口                                  |
| ------------------------ | ----------------------------------------- |
| `agent_chat()`         | `POST /agent/{role}/chat`               |
| `list_workflow_runs()` | `GET /core/workflows/runs`              |
| `get_workflow_run()`   | `GET /core/workflows/runs/{id}`         |
| `get_trace()`          | `GET /core/workflows/runs/{id}/trace`   |
| `cancel_workflow()`    | `POST /core/workflows/runs/{id}/cancel` |
| `create_task()`        | `POST /core/tasks`                      |
| `start_workflow()`     | `POST /core/workflows/start`            |

## 界面说明

### ChatScreen

主聊天界面，默认进入。

| 快捷键     | 功能                         |
| ---------- | ---------------------------- |
| `Esc`    | 聚焦输入框                   |
| `F2`     | 循环切换角色                 |
| `F3`     | 在消息区列出当前工作目录文件 |
| `F5`     | 进入 Dashboard               |
| `Ctrl+Q` | 退出                         |

角色枚举来自 `RoleTheme`：

```text
lawyer -> teacher -> programmer -> writer
```

吉祥物由 `MascotWidget` 挂载在聊天页右侧。形象是纯 ASCII 的圆润小助手，避免 emoji 或宽字符在不同终端里错位：

- 初始状态：`MascotMood.IDLE`
- 发送消息后：`MascotMood.THINKING`
- 收到正常回复后：`MascotMood.HAPPY`
- API 返回错误或异常后：`MascotMood.ERROR`
- 切换角色时同步 `MascotWidget.role`，用于更新主题色

新增角色时至少要同步修改：

- `theme.py` 中的 `RoleTheme`、`ROLE_NAMES`、`ROLE_ICONS`
- `api/client.py` 中的 `ALLOWED_ROLES`
- 后端 `/ai/agent/{role}/chat` 支持的角色配置
- 测试用例中的角色预期

### DashboardScreen

工作流运行控制台。

| 快捷键           | 功能               |
| ---------------- | ------------------ |
| `F1` / `Esc` | 返回聊天界面       |
| `R`            | 手动刷新           |
| `V`            | 查看当前运行 Trace |
| `C`            | 取消当前运行       |

注意：

- 后端可能返回 `runId` 或 `run_id`，当前代码用 `_first_text()` 兼容两种命名。
- Textual 的 `RowKey` 不是普通字符串，读取时要通过 `_row_key_text()` 转换。
- 列表每 3 秒轮询刷新一次。

## 开发流程

推荐工作流：

1. 确认 Docker `ai-service` 已启动：

   ```powershell
   docker compose -f compose.yaml -f compose.dev.yaml -f compose.windows.yaml --env-file .env.windows ps ai-service
   ```
2. 启动 TUI：

   ```powershell
   .\tools\tui\start.ps1 -Role lawyer
   ```
3. 修改 TUI 代码。
4. 运行测试：

   ```powershell
   python -m pytest tools\tui\tests -q
   ```
5. 如果同时修改了后端，重建并重启 Docker `ai-service`。
6. 用真实接口探测关键路径，例如问候语、角色切换、Dashboard 列表。

## 测试

TUI 测试：

```powershell
python -m pytest tools\tui\tests -q
```

后端聊天路由相关测试：

```powershell
python -m pytest agent\tests\test_agentos_core.py::test_legacy_lawyer_agent_chat_greeting_returns_direct_intro agent\tests\test_agentos_core.py::test_legacy_lawyer_agent_chat_vpn_question_is_not_contract_template -q
```

完整相关测试：

```powershell
python -m pytest agent\tests\test_agentos_core.py tools\tui\tests -q
```

测试覆盖重点：

- `zhiyi --role ...` 是否仍兼容并默认进入 `os` 子命令。
- 聊天提交是否调用 `agent_chat()` 并渲染回复。
- 同角色连续对话是否复用后端返回的 `sessionId`。
- Dashboard 是否兼容后端返回的 camelCase `runId`。
- 律师角色的问候语和泛法律问题是否避免进入案件分析模板。

## 常见问题

### TUI 里“你好”仍然返回案件分析

说明当前 `8000` 上的 Docker AI 服务还不是新镜像。重建并重启：

```powershell
docker compose -f compose.yaml -f compose.dev.yaml -f compose.windows.yaml --env-file .env.windows --profile debug-ports build ai-service ai-debug-port
docker compose -f compose.yaml -f compose.dev.yaml -f compose.windows.yaml --env-file .env.windows --profile debug-ports up -d ai-service ai-debug-port
```

然后用真实接口探测 `trace[0]["action"]` 是否为 `direct_response`。

### 出现 `502 Bad Gateway`

优先检查：

- `AGENTOS_API_URL` 是否是 `http://127.0.0.1:8000/ai`
- Docker `ai-service` 是否健康
- 是否误连到代理或旧服务

`AgentOSClient` 已设置 `trust_env=False`，正常情况下本地请求不应被系统代理劫持。

### WebUI 和 TUI 行为不一致

先确认两者是否都连同一个 Docker AI 服务：

```powershell
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

期望看到 `federal-hub-ai-service-prod` 或当前 compose 项目的 `ai-service` 映射到 `0.0.0.0:8000->8000/tcp`。

如果 TUI 设置了自定义 `AGENTOS_API_URL`，先清掉或改回：

```powershell
Remove-Item Env:AGENTOS_API_URL -ErrorAction SilentlyContinue
```

再用 `.\tools\tui\start.ps1` 启动。

### 中文显示异常

优先使用 Windows Terminal，并确保环境变量：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

`start.ps1` 已自动设置这两个变量。

## 提交建议

修改 TUI 文档时单独提交即可：

```powershell
git add tools/tui/tui.md
git commit -m "完善 TUI 开发文档"
```

如果同时改了 TUI 代码和后端代码，建议拆成独立提交，便于回滚和审查。

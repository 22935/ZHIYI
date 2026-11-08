# EX-M1：原生环境选择 Hands 执行后端

> 范围说明：下文 M1 的端口、固定工作区和历史桌面证据仅代表 M1。
> 当前入口的 `-Desktop` 启动 Electron；动态工作区必须在 Electron 中选择候选目录，
> 再由本机身份通过 WorkspaceAuthority 授权。目录选择 IPC 本身不签发 Grant。
> Electron、动态授权、正式 ACG 开发及冷重启的本次证据见
> [M2B 验收记录](../../../../../docs/开发记录/PR-EX-M1-M2B-执行闭环与工作区授权-合并记录.md)。

沿用 [N03 环境](README-N03.md) 的 PostgreSQL、Memurai、DPAPI、Workflow SQLite、TypeScript Backend 和 Python 服务。
Hands 是独立 Node.js 服务，源代码仅从本仓 `apps/agentOS/src/hands` 加载；不读取原 zhi-xing 仓库。
默认使用 Hands 执行后端与同一 ResourcePlane/HMAC/Grant 选择。

## 构建

```powershell
pnpm --dir apps/agentOS/src/hands install --frozen-lockfile
pnpm --dir apps/agentOS/src/hands exec tsc --noEmit
pnpm --dir apps/agentOS/src/hands test
# 构建 TypeScript Backend，不依赖 JVM。
Push-Location apps/backend-ts
npm ci
npm run build
Pop-Location
```

## 独立持久环境

首次初始化需要与 N03 相同的依赖和模型凭据；Home、Workspace 必须独立于已有用户环境。
`PortOffset` 在初始化时固定，不改变 default 的端口。`TestPython` 应指向安装了 pytest 的独立 venv。

```powershell
$profileHome = "$env:LOCALAPPDATA\ZhiyiNative\ex-m1"
$entry = '.\ops\scripts\infra\windows\native\persistent.ps1'
& $entry init -HomeDir $profileHome -PortOffset 200 `
  -TestPython 'C:\test-tools\Scripts\python.exe'
& $entry up -HomeDir $profileHome -Desktop
& $entry status -HomeDir $profileHome
& $entry down -HomeDir $profileHome
# 非正常退出后：沿用已有 N03 recover 入口；不删除数据。
& $entry recover -HomeDir $profileHome -Desktop
```

本轮真实环境为 `%LOCALAPPDATA%\ZhiyiNative\ex-m1-20261029`；测试 Python 位于其 `test-python`。
端口为 PostgreSQL 15632、Memurai 16579、Python 18961、Hands 18965、Node Backend 18280、前端 15400、桌面 CDP 19422。
默认环境不参与这些启停命令。现有桌面入口用于验收，Electron 与 TypeScript Backend 通过同一 LocalIdentity 运行。

## 数据和权限

`hands-ledger/` 与 `data/*.sqlite3` 分离。`credentials.dpapi` 保存密钥；启动时生成的 Hands credentials JSON 在健康检查后删除。
`hands-service.json`、`hands-grants.json` 由可信开发配置生成，模型无法指定 root、Grant 或沙箱档位。
文件 API 对授权工作区执行读写约束。测试命令由系统编译为指定 Python 的 `-m pytest`，每次经现有工具审批；
`confinement=none` 是显式的宿主批准命令模式，不宣称具有 ACL Shell 沙箱。该模式只用于本轮独立测试 Home/Workspace。
不能把测试环境的 shell Grant 或凭据复制到其他用户环境。

## 正式任务

从真实桌面创建 Mission，选择“本机工作区开发与测试”能力包。按正式界面准备、激活任务图、交接、申请 ExecutionPermit、执行。
工作区节点中的 AgentOS 工具循环调用 Hands；修改文件和测试命令在界面逐次确认。
收据校验、执行身份和绑定存入现有 Value Store/Trace/Provenance 路径；最终产物由 AgentOS 生成。
HTTP 202 只表示接收；UNKNOWN 必须停止并对账，不允许将未知结果当成功或自动重新执行。

异常验收复用真实服务与生产 HMAC：

```powershell
& "$env:LOCALAPPDATA\ZhiyiNative\python\Scripts\python.exe" `
  ops/scripts/infra/windows/native/hands_checks.py --home $profileHome `
  --output artifacts/windows/pr-ex-m1/exception-check.json
```

该命令创建新的独立测试 Workspace/Ledger，验证 STARTED 崩溃恢复 UNKNOWN、同请求不重放、真实 Shell 取消、checksum 和清理。

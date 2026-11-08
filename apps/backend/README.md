# 知弈 TypeScript Backend

Node.js 24 + Fastify 5 + pg。平台负责 PostgreSQL 会话/消息/角色/Profile/搜索、文件、Chat 保存及 Python 网关；Python AgentOS 继续负责规划、编译、执行、权限、Checkpoint 与恢复。

```powershell
npm ci
npm run typecheck
npm test
npm run dev
```

`npm run dev` 监控 `src/**/*.ts` 和 TypeScript 配置，完成类型检查后自动重载后端。编译失败时继续运行上一次成功版本，修复错误后自动恢复更新。每次成功构建写入独立的 `.cache/backend-dev/` 临时目录，运行中的请求不会读取到混合版本的模块。关闭时仅清理本监控进程创建的构建目录。

热更新期间若有 SSE/下载等请求，等待处理及清理完成后再切换；聊天客户端断开后仍会等待回复保存完成。长期不断开的流会延迟更新。首次监听到下次监听之间有短暂的服务切换窗口，下一版使用同一个端口。监控进程 PID 保持稳定，子进程 PID 会变化。停止监控进程会关闭子进程及文件监听。

原生开发启动器默认使用该监控入口。已启动的旧环境可以只切换 TS 后端：

```powershell
.\ops\scripts\start-local-desktop.ps1 -HomeDir "$env:LOCALAPPDATA\ZhiyiNative\default-clean-20261106" -WatchBackend -NoPause
```

此操作核验既有进程所有权、Home 和 LocalIdentity；首次只停止旧 TS 后端并启动监控进程，启动失败会回退旧入口。Python、数据库、Hands 和 Electron 不随此操作重启。`watch-backend` 操作可重复执行，已启用且健康时不再重启。

发行包仍运行编译后的固定入口，不启用源码监听：

```powershell
npm run build
npm start
```

正式和开发默认监听 `127.0.0.1:18080`。通过仓库 Windows 原生启动器使用既有 Home；启动器注入以下配置，不需要 JDK/JRE/Maven，也不注册或登录用户：

| 配置 | 用途 |
| --- | --- |
| `ZHIYI_BACKEND_TS_PORT` | Backend 端口，默认 18080 |
| `ZHIYI_DATABASE_URL` | PostgreSQL 应用角色连接串 |
| `AI_SERVICE_URL` | Python 服务地址 |
| `AI_INTERNAL_TOKEN` | 保留的内部服务认证，不能作为用户凭据发送 |
| `APP_UPLOAD_DIR` | Home 内上传文件目录 |
| `ZHIYI_BACKEND_TS_DEV_ORIGIN` | 精确开发页面 origin；产品默认只允许 `kinlin-app://shell` |
| `ZHIYI_BACKEND_TS_IDENTITY_FILE` | 受保护的 LocalIdentity 文件绝对路径 |
| `ZHIYI_BACKEND_TS_EXPECTED_USER_ID` | 启动器独立核对的历史 PostgreSQL owner |
| `ZHIYI_BACKEND_TS_HOME_BINDING` | 可信 Home environment.json 的 SHA-256 |

LocalIdentity 沿用 `zhiyi-local-identity-v1` 格式，保留 actorId/legacyUserId、null tenant 与既有 Home binding。服务不从 HTTP 请求接受身份覆盖。业务请求须携带允许的 Origin；写请求另需 `X-Zhiyi-Local-Request: 1`，前端和 Electron 已接入。拒绝旧 Authorization/JWT 与客户端可信身份头。

`/health/live` 仅反映进程存活；`/health/ready` 同时核对身份与数据库 owner。二者提供 `/api/health/*` 别名。缺配置时 ready=503。Python、Hands、Terminal 的就绪由 Windows 启动器分别检查。

`migrations/` 原样保留 V1–V13 SQL。`platform_database.py` 仅对完全空的 public schema 初始化；已有库只做兼容检查，不执行历史 SQL、不重置数据、不轮换 Grant。旧 Session 表作为历史 Schema 保留，运行不再使用。

测试自动创建随机端口和独立临时 PostgreSQL cluster（发现本机二进制后运行）。可用 `ZHIYI_TEST_POSTGRES_BIN`、`ZHIYI_TEST_PYTHON` 指定测试工具；测试不读取用户 Home 或数据库凭据。Gateway 单测的本地 HTTP 服务仅验证传输合同，跨进程 Runtime SSE 验收另见 `ops/scripts/runtime_streaming_combined_acceptance.py`。

Ctrl+C/SIGTERM 或父进程 Node IPC `shutdown` 均关闭上游流、完成消息落库并关闭数据库连接。Windows supervisor 保留进程所有权核验；端口占用时拒绝启动，不接管陌生进程。

平台 TS 后端的自动重载不替代 Python AI/AgentOS 服务重载。前端由 Vite 更新；压缩 TS worker 是请求级进程，下一次请求会读取最新源码。

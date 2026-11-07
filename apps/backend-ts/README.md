# PR-TS-01-Lite TypeScript Backend

最小独立骨架：Node.js 24、TypeScript、Fastify 5、Vitest。生产代码只有配置、只读身份映射、HTTP 健康/本机访问检查和进程入口四个文件。唯一直接运行依赖是 Fastify。

## 构建与运行

在本目录执行：

```powershell
npm ci --ignore-scripts
npm run typecheck
npm test
npm start
```

`npm test` 先编译，再运行单元、真实 TCP HTTP 和编译入口子进程测试。测试仅使用新建的系统临时目录和 `127.0.0.1:0` 随机端口；测试探针路由仅在测试中注册，不进入生产入口。`node_modules`、`dist` 由仓库现有规则忽略。

默认启动 `http://127.0.0.1:18081`，不会读取 Java 的 `SERVER_PORT` / `SERVER_ADDRESS`。支持专用变量 `ZHIYI_BACKEND_TS_PORT`，`0` 表示操作系统分配端口；明确拒绝当前原生栈默认端口，含 `18080`。遇到占用只退出，不查杀或接管进程。

| 请求 | 身份正常 | 身份未配置/错误 |
| --- | --- | --- |
| `GET /health/live` | 200 `{"status":"UP"}` | 200 `{"status":"UP"}` |
| `GET /health/ready` | 200 `{"status":"UP"}` | 503 `{"status":"DOWN","reason":"LOCAL_IDENTITY_NOT_CONFIGURED"}` 或 `LOCAL_IDENTITY_INVALID` |

健康响应不返回 UUID、路径或映射正文；有效 Host 且没有 Origin 的健康探针可访问。HEAD 由 Fastify 提供。ready 仅代表本骨架的身份配置就绪，不代表数据库、Python、Hands 或整个 AgentOS 就绪。

## LocalIdentity 映射

服务不会读取真实 PostgreSQL、SQLite、审计数据库副本或 N03 Home，也不会自动创建身份文件。本轮未取得/导入真实用户 UUID；**不存在通过数据库核验 UUID 的能力**。保留旧 UUID 的规则以临时合成数据测试，真实身份导入属于后续受控配置步骤。

后续从受信的既有用户映射预置以下三个专用变量，文件必须是绝对路径：

- `ZHIYI_BACKEND_TS_IDENTITY_FILE`：受保护的版本化 JSON 文件。
- `ZHIYI_BACKEND_TS_EXPECTED_USER_ID`：独立预置的旧 `users.id`，不是客户端参数。
- `ZHIYI_BACKEND_TS_HOME_BINDING`：独立预置的稳定 Home 标识；本骨架只比对字符串，不扫描 Home 或验证真实数据库实例。

文件格式如下，占位符不能直接运行，也不要为通过 ready 生成替代 UUID：

```json
{
  "format": "zhiyi-local-identity-v1",
  "version": 1,
  "actorId": "<existing-users.id>",
  "legacyUserId": "<same-existing-users.id>",
  "wireTenantId": null,
  "homeBinding": "<same-trusted-home-binding>"
}
```

只有 ActorId、legacyUserId 与预期旧 UUID 完全一致，版本、字段和 Home 绑定匹配，且 raw tenant 为 null 才就绪。不改为 `__unscoped__`，不合并用户，不生成 UUID，不写回文件。读取后冻结身份，直到重启不重载；修改文件不会改变在途服务的身份。文件缺失、JSON/版本/身份/绑定不符均失败关闭：live 保持可诊断，ready 503，非健康路由在处理前被拒绝。多用户或不同 tenant 的映射暂不支持。

此最小格式落实了 PR-TS-00B 设计的当前校验需求；未加入尚未使用的 generation、数据库指纹或迁移来源字段。后续扩展必须显式升级格式/校验，不把 Lite 的 Home 字符串比对当成完整身份迁移验收。

## 本机访问与关闭

只接受准确的 `Host: 127.0.0.1:<实际监听端口>`；不信任代理转发身份。Origin 默认只允许 `kinlin-app://shell`，拒绝 `null`、未知 Origin 和重复 Host/Origin。开发可显式设置一个精确的 HTTP loopback origin（包含端口）：`ZHIYI_BACKEND_TS_DEV_ORIGIN`。不使用通配 CORS。

拒绝 Authorization、客户端用户/Actor/Tenant 头、`X-Authenticated-*` 和内部服务令牌声明；拒绝 query/JSON body 中的权威身份字段。非健康访问必须有允许的 Origin 和有效服务端身份；写请求还需 `X-Zhiyi-Local-Request: 1`。当前没有业务写路由或通用 CORS preflight/网关。后续业务需按实际路由补充 schema 与 preflight 合同。

Origin/Host 检查防止错误来源和浏览器跨站使用，不是同 Windows 用户下恶意程序的隔离机制。没有变动 Electron IPC Sender、Hands HMAC、审批或 Python 授权；它们也没有接入本包。

终端 Ctrl+C、SIGTERM，或由父进程 Node IPC 发送字符串 `shutdown`，均调用 Fastify `close()`：拒绝新请求，完成在途健康请求，关闭 idle keep-alive、监听 socket、信号/IPC handler，并自然退出。Windows 子进程测试使用明确的父进程 IPC，未假定 Windows 必须支持 POSIX 信号。没有 HTTP 远程关闭端点、后台轮询、文件 watcher 或外部连接池。

## 验证边界和下一步

目前只实现 `/health/live`、`/health/ready`。未接入真实身份、PG、Redis、Python、Hands；未实现 Chat/SSE/CRUD/Artifact、Repository、Migration Runner、ServiceSpec 或发布流程。运行默认配置时 ready 返回 503 是预期行为。

下一阶段先审阅本机准入与身份配置合同，再以独立 fixture 验证真实身份的受控导入；在获得对应授权前不接真库、不占用 18080、不切换现有入口。本轮不提交、不推送。

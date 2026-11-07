# PR-TS-00B-LocalIdentity最终设计

> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

## 冻结决定

**可以冻结单用户LocalIdentity设计（INFERRED规范，依据VERIFIED数据）。** 当前PG/legacy/identity Mission/Grant的唯一actor均U01，raw tenant缺失，Run冻结授权匹配。保留原users.id作为ActorId；不新生成替代UUID、不重写任何历史owner、不自动合并身份。本轮没有创建该配置或改表。

Chroma供应商FK定义问题不进入身份映射判据；外部工作区未备份不妨碍只读设计/骨架，但任何数据写入迁移或外部项目破坏性测试都不得据此放行。

## 稳定Actor来源与Home映射

未来映射文件建议Home内`identity/local-identity.json`，版本化且原子替换、受Home ACL保护，随冷备。形状如下（示意占位符，不包含真实UUID）：

```json
{
  "format": "zhiyi-local-identity-v1",
  "version": 1,
  "actorId": "<existing-users.id>",
  "legacyUserId": "<same-existing-users.id>",
  "wireTenantId": null,
  "workspaceTenantFallback": "__unscoped__",
  "source": "verified-single-legacy-owner",
  "identityGeneration": 1,
  "homeBinding": "<validated-home-and-database-binding>"
}
```

这是服务端权威配置，不是renderer可写偏好，不存JWT/session/密码，不是签发Grant的第二数据库。Home binding应校验受信Home manifest、数据库实例/库身份和映射版本；路径重定位需要显式导入/恢复流程，不因cwd变化自动重建身份。丢失/损坏/未知version、映射UUID不存在、多owner预检失败：ready=false并拒绝业务请求，只开放最小诊断；禁止用首行users或随机UUID自动补齐。

现有单用户：首次显式迁移事务/映射建立时复查U01的一致性，actorId=legacy user UUID；users资料行继续作为Conversation/Role/头像/资料归属锚点。先停用登录/密码端点与读取，不在同PR删除users或历史session表。schema退役独立PR和恢复窗口后再批准。

## Tenant双层语义

wireTenantId保持null/不发送tenant header。新Run输入仍省略authenticatedTenantId；不得全局把header写成字符串__unscoped__。仅在WorkspaceAuthority.owner/resolve和semantic principal原有归一处用`tenant or '__unscoped__'`。已有Grant表字符串sentinel保留；历史Run输入、identity Mission metadata不回填。

原raw null/ABSENT在本机等价条件已验证；EMPTY与显式非空tenant对未来外来历史数据仍要独立检测，不把多个tenant归一后合并。用户/tenant来自后端配置，不来自query/body/header/IPC参数。

## 三场景策略

零用户且无任何owner残留可走显式首次初始化；零用户有残留BLOCKED。单用户须跨PG/SQLite/Grant完整一致才建立映射，本机命中；多个用户或不同历史owner/tenant一律BLOCKED并人工确定隔离保留或另案迁移，不自动选择主用户，不重写Run owner/Artifact关系。

本轮没有需要人工选择哪个历史actor的未决事项；若导入其他Home、备份、数据或创建新的owner，必须重做预检，不能套用本机结论。

## 请求身份与Python可信上下文

LocalIdentityProvider在服务启动装配受信配置，生成不可变ActorContext：UUID actorId、subject、role、nullable wireTenant、generation。REST层只接收业务参数；遇到userId/tenantId/trusted身份头等权威声明拒绝或忽略，所有owner查询与写入使用服务端context。profile/users路径外actor拒绝；不能保留RoleService中null-user绕过模式为公开端口。

PythonTransport从固定upstream配置出站，先剥离所有客户端X-Authenticated*/X-Internal-Service-Token/Authorization，再从服务端重建内部服务认证与actor headers、trace。保留Python InternalServiceAuthMiddleware的恰好一个token/constant-time/非空user-subject-role检查；role不是前端声明的管理员权限。health例外保持最小。

## 无登录HTTP本机准入（冻结合同）

1. 产品只监听127.0.0.1默认18080，使用supervisor分配的明确端口。严格校验Host为当前本机host/port，拒绝陌生Host/DNS重绑定；不信任转发头生成actor或权限。
2. 发行允许Origin仅`kinlin-app://shell`，开发仅实际Vite loopback origin/port白名单；拒绝未知Origin、`null`、不匹配端口。CORS是响应策略，服务端先做准入检查才执行业务。
3. 敏感读/写必须有合法Origin；写请求另要求非简单header（例如`X-Zhiyi-Local-Request: 1`）和受控JSON/multipart。此header不是秘密；它只配合Origin/preflight防止跨站简单表单/no-cors写。GET不得产生业务写入。
4. 无Origin仅开放最小live/ready，不开放PG、Grant、文件或执行；Main需要调用业务时通过受控本地桥接按固定app origin/契约发送，不接受任意URL代理。合法Electron自定义scheme/开发proxy行为用真实socket/桌面测试确认。
5. 401/403表示本机准入/身份就绪/操作授权失败，不跳回登录、不签JWT、不恢复用户session。映射不可用时业务503及稳定诊断码，禁止匿名执行fallback。
6. 同一Windows用户下恶意本地程序能构造HTTP header，属于同OS用户信任边界；不能将Origin或ActorId宣传为OS沙箱。受限Home ACL、IPC sender、工具审批、Grant/Permit/HMAC仍分别保留。

上述是目标合同，**尚无实现和运行测试**。PR-TS-01可建立schema与隔离准入测试，任何接真实数据的放行必须等该合同实测通过；不以无登录为由permitAll。

## Workspace / Hands / IPC不可删除项

WorkspaceAuthority继续唯一签发/选择/撤销PG Grant；Run.freeze清掉客户端binding并冻结快照；resolve核对owner/tenant/grant epoch/resource/root/inode/revoked。重新授权同目录也不能让旧Run借新Grant执行。TS不直接写Grant表、不为旧Run补新binding、不把current workspace代入已冻结Run。

保留Electron sender webContents.id + mainFrame与所有IPC参数校验；保留Hands HMAC/ledger、terminal独立服务token、Python内部认证、工具审批与ACG Permit/Checkpoint/Trace/Provenance。JWT/session bootstrap专属代码退役时，按identity-touchpoint-inventory逐点区分进程token与用户token。

## 后续实现验收门禁

同Home多次启动actor/generation稳定；mapping缺失/错UUID/未知版本拒绝；伪造身份与跨actor路径失败；恶意Origin/Host/null/simple POST/no-cors失败；合法Electron成功；Python直连仍拒绝；Grant撤销/重授权/切目录/旧Run全部按原epoch；备份恢复PG/SQLite/Grant投影/身份配置一致。零/单/多用户均以隔离数据fixture覆盖，不能用本机仅一用户替代负面测试。

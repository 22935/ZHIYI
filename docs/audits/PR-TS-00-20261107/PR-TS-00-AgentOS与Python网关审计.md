# PR-TS-00-AgentOS与Python网关审计

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 权威边界（VERIFIED 源码 / INFERRED 迁移约束）

Java 当前负责平台数据与HTTP安全/投影/传输，不是计划器或执行器。目标TS只能替换该平台边界。Python AgentOS Core保留Mission/Run/Review、生命周期、调度、Checkpoint、Trace、Provenance、Permit、frozen workspace binding权威；Hands保留执行/HMAC/ledger/文件与shell授权执行；terminal-host是用户终端服务，不能变成模型执行器。

`apps/agent/app/main.py:42`（`runtime = build_default_runtime()`）、`apps/agent/app/api/agentos_v2.py:703`（`create_c2_router(runtime, coordinator)`）、`apps/backend/src/main/java/com/kinlin/ai/gateway/AgentOsGatewayService.java:33`（`implements AgentOsClient`） 是现有依赖路径。apps/agentOS为Core实现，apps/agent为HTTP装配和执行接线；本轮均不重写。

## 网关逐组件合同

| 组件 | 已验证源码职责 | TS归属/限制 |
| --- | --- | --- |
| AgentOsClient | JSON typed/untyped、multipart、binary传输接口 | application outbound port；不暴露Fastify reply |
| AgentOsGatewayService | enabled、超时选择、HTTP状态和error envelope转换 | AgentOsGatewayAdapter；保留每族现状，后续统一需版本决策 |
| AiSseGatewayService | GET/POST SSE、idle/total、取消、metrics、sid复核 | 新SseGateway；替换sid gate，保留timeout/abort/流顺序 |
| AiProxyService | 固定upstream；path安全；header允许集；字节request/response | ProxyAdapter；限制body与响应预算，不能任意origin代理 |
| AgentOsPaths | 唯一 /ai/agentos/v2 与segment/query编码 | 路径构造纯函数，禁止业务服务拼url |
| PythonClientFactory | 唯一baseURL/shared auth-filtered transport | 一个PythonTransport实例族；上层不另造fetch客户端 |
| PlatformAiTransport | platform能力失败分类 | 结构化error port；fallback仍由application负责 |
| TrustedUserContextForwarder | 从服务端认证上下文生成可信用户/tenant/trace | LocalIdentityProvider + TrustedContextEncoder，拒绝客户端伪造 |
| PythonServiceAuthentication | 注入内部服务认证header | 保留独立内部服务令牌，不随用户JWT退役 |

## 上游路径与身份

正式平台 `/api/agentos/v2/*` → Python `/ai/agentos/v2/*`；通用 `/ai/*` → Python同路径。各AgentOS Controller的AgentOsPaths表达式、Projection返回类型在route CSV。Artifact/Observation/Review/Mission/Run/Workspace/Event七个Controller覆盖操作、查询、文件与事件；不能把C2五步归为一个“执行”endpoint后在TS实现状态机。

WebClientConfig共享filter统一service auth、trace和trusted identity；SSE显式捕获上下文以免切线程丢失。证据：`apps/backend/src/main/java/com/kinlin/ai/config/WebClientConfig.java:51`（`authentication.apply(headers)`）；`apps/backend/src/main/java/com/kinlin/ai/gateway/AiSseGatewayService.java:104`（`userContextForwarder.requireCurrent()`）。

header名称：`X-Internal-Service-Token`；`X-Authenticated-User-Id/Subject/Role/Tenant-Id`；`X-Trace-Id`（精确大小写不敏感实现见AiGatewayHeaders/TraceContext）。这些是字段名，报告不包含值。Python要求恰好一个有效服务认证header并constant-time比较，再要求非空user/subject/role；公共health路径除外。证据：`apps/agent/app/security/internal_auth.py:100`（`hmac.compare_digest`）、`apps/agent/app/security/internal_auth.py:132`（`def _trusted_identity`）。不能取消登录后开放Python业务直连。

## Error Envelope / TraceId / 超时

AgentOS JSON：2xx解析后附内部HTTP状态元数据；4xx保留稳定code/message/requestId（清理换行、截300字符），格式不符变AGENTOS_REQUEST_REJECTED；上游5xx→502 AGENTOS_UPSTREAM_ERROR；连接/超时等异常当前统一503 AGENTOS_UPSTREAM_UNAVAILABLE。typed成功反序列化失败→502 AGENTOS_CONTRACT_INVALID；launch409特定冲突走对账。证据：`apps/backend/src/main/java/com/kinlin/ai/gateway/AgentOsGatewayService.java:223`（`private Mono<Map<String, Object>> mapResponse`）、`apps/backend/src/main/java/com/kinlin/ai/gateway/AgentOsGatewayService.java:253`（`private <T extends AgentOsApiResponse> Mono<AgentOsClient.TypedResponse<T>> typedResponse`）。

普通proxy：连接失败503、超时504、其他invalid502；path无效400。PlatformAiTransport向application交REJECTED/UPSTREAM_ERROR/TIMEOUT/UNAVAILABLE/INVALID_RESPONSE分类。不能强行统一成一种error envelope而破坏既有前端处理。TraceId从服务端过滤/合法客户端trace生成并随请求传递；不把自由header复制到上游，不把内部HTTP状态元数据泄漏到业务DTO。

配置默认值来自application.yml：connect 15s、platform command/read 240s、health 3s；AgentOS普通query 5s，missions列表240s，mission创建15s，其余post240s；binary/multipart为progress 5s。SSE idle240s，max0表示不限制总长。环境可覆盖，以上不等于当前运行有效值（服务未运行）。

## SSE / Abort / 持久化

SSE建连前可返回JSON HTTP错误；建连后只能发送终止event，不能第二次写HTTP status。event/id/retry/data逐条转发、顺序保持、UTF-8分片与多行data必须测试；HTTP close/disconnect传播AbortController到Python，释放reader、timer和并发配额。取消HTTP流不能由TS擅自等价为取消Run，正式Run取消仍调用Python命令端口。

现实现sid门：openPost/openGet拒绝缺sid；周期3s复核、查询1s、lease5s，失效发auth.invalidated并取消订阅。该**登录合同退役**；替换为LocalIdentity ready/进程关闭与必要执行授权校验，不保留假sid。Grant/Permit撤销仍由Python在执行处检查。`apps/backend/src/main/java/com/kinlin/ai/gateway/AiSseGatewayService.java:105`（`userContext.sid() == null`）、`apps/backend/src/main/java/com/kinlin/ai/gateway/AiSseGatewayService.java:189`（`Flux<ServerSentEvent<String>> withSessionGate`）。

ChatStreamPersistenceService.prepare先事务提交user；流完成/取消再单独提交assistant。断流失败metadata、reasoning上限200000字符、usage/model/source/tool字段均需保留当前基线。capture.persisted为进程内布尔，不保证数据库commit成功、崩溃恢复或客户端重试幂等；目标需定义stream attempt持久幂等/恢复方案，不能长事务跨模型流。`apps/backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java:70`（`capture.persisted = true`）、`apps/backend/src/main/java/com/kinlin/ai/controller/AiServiceProxyController.java:63`（`SignalType.CANCEL`）。

## 上传下载 / 路径 / 资源边界

multipart重建file资源、filename和content-type；binary保留content-type/disposition，5xx屏蔽上游正文。AgentOsPaths.segment使用encodePathSegment，query过滤null/blank并编码value；TS不能用整段URI编码，也不能把query当未校验字符串拼入。proxy拒绝非/ai/、双斜杠、..、反斜杠和控制字符；新实现须覆盖百分号编码/双解码，不能把原始request.url当外部URL。

资源现状：WebClient内存codec上限50MB；proxy request.readAllBytes与binary byte[]是缓冲路径；入站multipart10MB/11MB；RateLimit默认300/min，错误时放行；缓存错误降级PG。这些是VERIFIED实现，不是合理容量承诺。目标要定义全局/actor并发流、body/max-event-size、队列预算、上传下载背压与drain截止时间；阈值实测前为UNKNOWN，不编造吞吐。

## 尚缺证据

BLOCKED运行HTTP/SSE/取消传播；UNKNOWN Last-Event-ID/事件重放语义、WebSocket代理、全部可选Python路由是否实际加载、资源压力边界。python-route-inventory.csv为AST静态声明，main.py有try/except ImportError和feature gate，不能以装饰器数量认定实际注册成功。下一阶段必须用本机隔离fixture上游做字节/事件差分，再做真实服务授权E2E。

# PR-TS-00-HTTP接口与前端依赖矩阵

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 接口统计口径与有效性

VERIFIED 源码：141 个方法级 Mapping 声明，展开为 145 个 method/path 行：140 条显式路由 + 5 条 `/ai/**` 方法族；另有 53 行具 `/api` 兼容别名，不能把别名计成新业务。25 个 Controller 全部在 route-inventory.csv 中。GET 的框架 HEAD、CORS OPTIONS、Actuator/Swagger 自动注册不计入这 145 行。

`route-inventory.csv` 每行含方法、完整路径、别名、Controller/方法/行、请求签名、响应类型、状态行为和源表达式、依赖、Python path 表达式、认证、SSE/Multipart/Binary、前端与测试引用。Java 实体不作为目标 DTO。响应状态字段对无法静态确定的分支标记 dynamic/UNKNOWN；全局异常处理、Security/RateLimit 前置失败也适用，不凭默认200假定所有结果成功。

当前没有服务运行，**确认的只是源码映射，运行注册/可访问性为 BLOCKED**。CSV 的 CONFIRMED_SOURCE_MAPPING 特指这个层级。

## `/api` 规范化与代理

`apps/backend/src/main/java/com/kinlin/ai/filter/LocalApiPathFilter.java:27`（`LEGACY_ROOTS`）：仅集合内 root 去 `/api` 前缀，发生在 Security 之前，并重建 ServletRequestPathUtils 缓存。保留原生 `/api/agentos/v2`、`/api/knowledge-graph`、`/api/role-fusion` 等路径。不能统一给所有路由加/去 api，也不能把 `/api/ai/*` 当另一套身份规则。

`apps/backend/src/main/java/com/kinlin/ai/controller/AiServiceProxyController.java:39`（`public ResponseEntity<byte[]> proxy`）：通用代理承接 GET/POST/PUT/PATCH/DELETE，显式 `/ai/chat/text/stream` 与 `/ai/test/sse` 优先。下游 `/ai/foo` 存在不保证 Python 有该路由；上游条件加载和认证也可能拒绝。Python 上游的 201 个路由声明在 python-route-inventory.csv，包含 UNKNOWN 未挂载与条件挂载；**不能把 201 当确认生效路由数**。`/rag`、`/api/static`、`/performance` 不自动属于 `/ai/**`；WebSocket upgrade 不由 HTTP 字节代理实现。

## 五种路由状态

| 状态 | 本轮判定 |
| --- | --- |
| 确认源码生效候选 | 140 显式 method/path；运行验证 BLOCKED |
| 通用代理承载 | 5方法族；前端18个已展开调用项落入该族，Python 实际挂载需运行证据 |
| 前端调用但无 Java 对应 | 下表5项；其中2项有 Python 实现，仍不能跨过 Java 直接称可用 |
| 已废弃 | 本轮未发现 Controller 上显式 @Deprecated 的已退役路由；Login/Register/Logout/Verify/改密码属于计划退役，当前仍有效源码，不能提前删除 |
| 不明确 | 实时ASR WebSocket传输；动态URL/外部资源；Actuator/Swagger运行注册；可选Python路由，均明确保留 UNKNOWN/BLOCKED |

| 前端证据 | 方法 | 路径 | 结论 |
| --- | --- | --- | --- |
| `apps/frontend/src/components/FileHistoryList.vue:214` | GET | /api/rag/documents/${file.id}/download | VERIFIED 前端存在；Java 路由缺口，运行未测 |
| `apps/frontend/src/services/api/agentos/api/runtime.ts:32` | GET | /api/agentos/v2/runs/{runId}/context-packs | VERIFIED 前端存在；Java 路由缺口，运行未测 |
| `apps/frontend/src/services/api/agentos/api/runtime.ts:68` | POST | /api/agentos/v2/nodes/${encodeURIComponent(nodeId)}/enabled | VERIFIED 前端存在；Java 路由缺口，运行未测 |
| `apps/frontend/src/services/api/chat.ts:116` | GET | /api/chat/history/role/${roleId} | VERIFIED 前端存在；Java 路由缺口，运行未测 |
| `apps/frontend/src/services/api/chat.ts:130` | GET | /api/chat/summary/${roleId} | VERIFIED 前端存在；Java 路由缺口，运行未测 |


context-packs 与 node enabled 在 Python 已有实现：`apps/agent/app/api/agentos_v2.py:2909`（`@router.get("/runs/{run_id}/context-packs")`）、`apps/agent/app/api/agentos_v2.py:1345`（`@router.post("/nodes/{node_id}/enabled")`）。迁移前必须决定补齐正式 Java/TS gateway 合同还是移除前端入口；本轮不改。RAG 下载还缺 bearer 注入，但目标无登录也不能由此自动补齐路由。两条 chat history/summary 的消费是否仍挂在活动UI是 UNKNOWN，不擅自判废弃。

## Frontend / Electron 全量调用关系

frontend-callsite-inventory.csv 包含 152 行（C2 的一个调用展开为五种 action，故不是函数数）；125 项对应显式路由、18 项通用代理；5项缺口、1项ASR upgrade、1项内部terminal、1项外部/Artifact fetch、1项动态helper已追至Settings调用者。递归扫描 src，包括 stores/chat、companion、ModelRuntimeControls、NativeWorkspacePicker、runtimeEvents 和 views，未只看 services/api。

agentosRequest base=`apiUrl('/api/agentos/v2')`；普通 request/多份 axios base=`apiUrl('/api')`；直接 fetch apiUrl 不补 `/api`；backendUrl 专门补 `/api`。runPath 与 revisionPath 按源码辅助展开；路径段 encodeURIComponent、查询 params、AbortSignal 均须保留。来源：`apps/frontend/src/platform/api.ts:38`（`export const apiUrl`）；`apps/frontend/src/services/api/agentos/client.ts:6`（`baseURL:`）；`apps/frontend/src/services/api/agentos/paths.ts:1`（`runPath`）。

独立 axios 实例：file、search、knowledgeGraph、roleFusion、federatedModel、agentos/client，以及 utils/request。前五者自行注入 bearer，不能只删统一拦截器。HTTP client、SSE fetch、ASR WebSocket、terminal内部连接是不同合同；terminal bearer 是进程服务认证，不是用户 JWT，不在退役清单。

## 登录退役触点与目标

identity-touchpoint-inventory.csv 记录224个源码触点，每项含路径/行号、类型、目标和可找到的测试；逐行匹配只能定位，不等于224个独立行为。源码范围包括全部 router/store/service/utils/platform/electron 和 Electron Main/Preload。下表说明责任，CSV 提供逐点落地位置。

| 文件/符号 | 调用关系/依赖 | 目标行为与测试 |
| --- | --- | --- |
| `apps/frontend/src/router/index.ts:34`（`requiresAuth`） | beforeEach → ensureDesktopSession / authApi.verify；meta.requiresAuth | 去登录跳转；身份未就绪显示本机身份诊断；router测试改写 |
| `apps/frontend/src/platform/electron/session.ts:19`（`ensureDesktopSession`） | router/requestAuth → bridge.session.ensure → Main sessionBootstrap | 退役token存储/恢复；替换local identity readiness；session相关测试改写 |
| `apps/frontend/src/utils/requestAuth.ts:29`（`attachAuthToken`） | request和agentosRequest共享；handleUnauthorizedError清状态/重试 | 移除JWT注入与401登录跳转；保持错误/取消处理测试 |
| `apps/frontend/src/stores/user.ts:21`（`localStorage`） | token:userId缓存身份；资料API依赖 | 以backend稳定actor+generation作缓存边界 |
| `apps/frontend/src/stores/chat.ts:212`（`Authorization`） | Chat模型查询、stream fetch；companion另有adapter | 移除用户token，保留SSE事件/取消/历史 |
| `apps/frontend/src/views/SettingsView.vue:712`（`async function serverFetch`） | profiles配置的独立fetch helper | 移除token；保留本地操作准入和服务侧配置密钥边界 |
| `apps/desktop/electron/src/main.ts:80`（`bootstrapLocalSession`） | sessionBootstrap IPC → POST /auth/login；发行启动器注入账号 | 删除登录bootstrap；保留API Origin IPC与Main sender guard |
| `apps/desktop/electron/src/preload.ts:29`（`session:`） | bridge.session.ensure → IPC.sessionBootstrap；frontend bridge.ts手工同构 | 同步更新两端类型与Main测试；保留通道白名单 |
| `apps/desktop/electron/src/main.ts:278`（`const authorized =`） | sender webContents id + mainFrame → guard(event) | KEEP；无登录不移除IPC发送者验证、URL/路径/参数校验 |


LoginView 的登录/注册表单、auth.ts 验证缓存与logout、user/password入口、AuthenticatedAppShell登出、workflowRuns token前置检查都要逐点移除。源码行与测试引用以 identity-touchpoint CSV / source-evidence-index 为准；未发现对应测试的项明确待补，不伪造已覆盖。

## 状态码与特殊行为冻结

GlobalExceptionHandler：415媒体类型、413超大文件、422缺file、400校验/业务/JSON、404资源/接口；Security未认证401；RateLimit429。Gateway的4xx、409冲突、503断连、504通用代理超时及AgentOS超时503不可被一个统一error handler意外抹平。SSE建连前HTTP错误与流中error事件必须区分。依据：`apps/backend/src/main/java/com/kinlin/ai/exception/GlobalExceptionHandler.java:48`（`handleMissingMultipartPart`）；`apps/backend/src/main/java/com/kinlin/ai/interceptor/RateLimitInterceptor.java:44`（`TOO_MANY_REQUESTS`）。

Multipart需保留file字段、filename/content-type、10MB/11MB限额；Binary需保留status/content-type/content-disposition且不得经过JSON DTO序列化。显式SSE保留event/id/retry/data顺序、Last-Event-ID语义需单独核验（UNKNOWN，不能自动承诺重放）。

## 独立语法复核（VERIFIED，仅盘点检查）

使用仓库已安装的TypeScript 5.4.5解析366个TS/JS/Vue script块，没有安装依赖或启动浏览器。152个CSV调用项均定位到真实CallExpression/NewExpression，C2一个调用仍展开五个目标；语法候选中另外4项人工核对为documents.ts的Map get/delete和lsp-host.ts的LSP JSON-RPC request，均不是平台HTTP。排除证据与零未决候选见verification.json；不是运行路由/E2E验证。

identity-touchpoint-inventory.csv补充AST定位的所属函数、导入依赖和调用符号引用候选。跨模块import/IPC/template动态绑定不能由词法证明的调用者保留UNKNOWN；不把同名引用当语义调用图。terminal-client内部Authorization明确KEEP，不属于用户JWT退役。frontend-ast-evidence.json仅含源码符号和位置，不采集运行请求/凭据/正文。

# PR-TS-00B-接口与运行合同补证

> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

## 证据层级

本轮只授权冷备/隔离PG与只读元数据补证，没有启动Java/Python/Hands/Electron/Redis/HTTP fixture或运行完整测试。下述为VERIFIED源码合同+INFERRED迁移决策；HTTP/SSE/原生完整E2E仍UNKNOWN/未执行，不以数据库查询替代运行测试。

## 五处缺口的正式处置

| 编号/路径 | 前端/上游证据 | 当前结论 | 冻结处置 | 迁移门禁 |
| --- | --- | --- | --- | --- |
| G01 GET /api/agentos/v2/runs/{runId}/context-packs | `apps/frontend/src/workbench/runtime/observation.ts:690`（`agentosApi.listRunContextPacks`）<br>`apps/agent/app/api/agentos_v2.py:2909`（`@router.get("/runs/{run_id}/context-packs")`） | VERIFIED 活动Inspector调用；Java缺路由 | TS-05补正式薄查询/闭合投影，保留run/mission owner；不重建ContextPack | P1，可延后到TS-05前；PR-TS-01骨架不依赖该API |
| G02 POST /api/agentos/v2/nodes/{nodeId}/enabled | `apps/frontend/src/components/resource-center/ResourceOverviewPanel.vue:284`（`agentosApi.setNodeEnabled`）<br>`apps/agent/app/api/agentos_v2.py:1345`（`@router.post("/nodes/{node_id}/enabled")`） | VERIFIED 活动资源管理调用；Java缺路由 | TS-05保留Python node-plane owner检查/401/403/404/503和enabled DTO；TS不自行调度 | P1，交付资源管理之前必须补齐 |
| G03 GET /api/chat/history/role/{roleId} | `apps/frontend/src/services/api/chat.ts:114`（`async getConversationHistory`）<br>Java只有/history/{contextId}，多一segment不匹配 | VERIFIED 方法存在；全src文本/AST未发现调用者；catch空数据 | 按未消费legacy wrapper冻结为不新建后端业务；TS-06去除/显式弃用包装，不改当前源码 | P2；未来发现消费者则重新评审 |
| G04 GET /api/chat/summary/{roleId} | `apps/frontend/src/services/api/chat.ts:128`（`async getConversationSummary`）<br>Java无summary路由 | VERIFIED 方法存在；全src文本/AST未发现调用者；catch空文本 | 同G03；不要凭函数名发明摘要服务 | P2；未来恢复入口需新合同 |
| G05 GET /api/rag/documents/{id}/download | `apps/frontend/src/components/FileHistoryList.vue:206`（`const handleDownload`）<br>`apps/frontend/src/views/HistoryView.vue:65`（`<FileHistoryList`） | VERIFIED 活动History文件页；Java /rag无download；fetch未带用户bearer | TS-04/05须先对齐文档元数据/受控文件定位与owner；不能直接传路径给任意读取 | P1；History下载验收之前解决；不沿用当前无保护下载假设 |


context-packs返回runId/items/total，查询identity或legacy run后做mission/run访问检查，仅返回bounded metadata而不是模型输入正文。Node enabled在Python resource_plane上修改调度开关，缺plane503、缺node404、无actor401、非空tenant不匹配403；本机旧tenant缺失语义需保持，不能任意改成sentinel header。两者已有Python实现，不允许TS重建运行语义。

## ASR活动性结论

VERIFIED：RealtimeASRService只由VoiceRecorder导入；VoiceRecorder默认enableRealtime=false，startRecording内启动startRealtimeASR的调用、sendAudio、endSession均被注释；全src的VoiceRecorder组件挂载搜索无消费者，TS AST对startRealtimeASR也无调用。RealtimeASRService.startSession虽有语法引用，但其上层函数不可从当前录音流程到达。

冻结处置（INFERRED）：当前实时ASR为休眠源码，不是TS-01/平台切换必须新增的活动WebSocket合同。不要仅因构造WebSocket代码存在就承诺支持，也不在本轮删除源码。Vite的/ai ws:true只是把upgrade送Java，Java仍没有对应WS端点，不能据此宣称连通。未来重启功能需独立带服务身份/准入的WS设计与测试。证据：`apps/frontend/src/components/VoiceRecorder.vue:90`（`//   await startRealtimeASR()`）；`apps/frontend/vite.config.ts:174`（`Availability still requires a corresponding Java WS endpoint.`）。

## SSE / sid / 取消与落库

`apps/backend/src/main/java/com/kinlin/ai/gateway/AiSseGatewayService.java:105`（`userContext.sid() == null`）：GET/POST受保护流都要求sid，且SessionRecheckGate周期查询PostgreSQL。新无登录模式不保留假sid或session表依赖；替换为稳定ActorContext与本机HTTP准入，保留idle/max timeout、trusted context、取消传播、流事件顺序。Python Grant/Permit撤销仍在原执行权威处检查。

`apps/backend/src/main/java/com/kinlin/ai/controller/AiServiceProxyController.java:63`（`SignalType.CANCEL`）：cancel捕获后异步complete；`apps/backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java:70`（`capture.persisted = true`） 在repository.save之前设置内存标记。同步/流式落库都是短事务而不是跨网络长事务。迁移验收必须覆盖完成/取消竞争、上游错误、保存失败、进程崩溃、重连重试；不得把内存标记当持久exactly-once。HTTP流断开不等于取消Run，正式取消仍由Python命令控制。

隔离测试方案：独立fixture上游与随机端口、匿名请求、临时数据目录/独立测试PG；逐字节UTF8与多行SSE、id/event/data顺序、Abort断连、idle/total区分、两段事务和失败恢复。未实施fixture、未跑业务测试；该P1必须在TS-05 SSE启用前解决。

## JWT / Axios / Electron覆盖

上一轮全部src AST与身份触点清单字节哈希保持一致：route145行、frontend152项、identity224触点。独立Axios为utils/request、agentos/client、file、search、knowledgeGraph、roleFusion、federatedModel；后五者有自己的bearer注入，不能只改request.ts。stores/chat、companion chatStream、model controls、workspace picker、runtimeEvents、copilot SSE、Settings serverFetch也必须按清单移除用户token。

router.requiresAuth与401登录跳转、user store token缓存key、workflowRuns token前置条件、auth.ts验证/登出、LoginView注册登录、ensureDesktopSession、Preload session.ensure、Main bootstrapLocalSession与产品ensure_local_account一起退役。每点源码函数/依赖/调用符号候选/测试在identity-touchpoint-inventory.csv；无测试项需后续补，不伪造覆盖。

**保留**Main IPC sender id+mainFrame guard、通道白名单/参数校验、API Origin动态端口桥接、terminal内部token、Hands HMAC、工具审批、Python内部服务认证与执行授权。无用户登录不等于无进程/能力边界。证据：`apps/desktop/electron/src/main.ts:278`（`const authorized =`）。

## Windows Native合同

VERIFIED：当前实现是函数+process record字典，不存在已实现的通用ServiceSpec类（限定ops/scripts/terminal-host/electron扫描）。ServiceSpec属于目标设计，不把它写成已具备能力。

现链PG/Redis→Java/Vite并行准备→受release-file/nonce/owner-PID/created门控的AI→Hands/terminal→最终health→Electron。Java readiness=`/actuator/health/readiness`，AI=`/health/ready`，Vite=`/api/health/ready`，Hands=`/v1/health`。stop_order=`desktop, frontend, ai, host, terminal, java, redis, postgres`；产品占用端口拒绝，开发有takeover，两者不能混用。

目标把java进程适配成node dist/main.js并默认18080，保留PID+创建时间+可执行身份、Home锁、失败回收和冷备合同；共用描述符但显式profile策略，不将开发takeover带入产品。SSE/Chat drain需在AI停止前完成接收关闭与必要持久化，再沿依赖顺序停机。Windows显式停止协议不能假设POSIX信号必达。

## 测试隔离复核与剩余门禁

NativePostgres创建随机临时cluster/随机端口；PostgresContainerBase动态覆盖datasource URL/user/password；RedisIntegrationTestBase另起临时Redis并动态覆盖端口；LocalApiHttpIntegrationTest为RANDOM_PORT+test/H2。删除清理代码仅以各helper创建的root为目标，但整个suite还包含默认外部URL、文件写入与继承profile，不能仅凭基座认定整套已隔离。

本轮未运行mvn test、Vitest、原生冷启动或其他现有业务测试；没有触发initdb/临时Redis。PR-TS-01只可搭建受限骨架与架构/准入fixture；首次运行任何旧suite前逐suite确认URL、env、目录、随机端口、进程拥有者和清理范围。required gate、PG15 repository、Redis、SSE socket、Windows启动停止恢复分别在03/04/05/07验收，不能用H2或注入测试代替。

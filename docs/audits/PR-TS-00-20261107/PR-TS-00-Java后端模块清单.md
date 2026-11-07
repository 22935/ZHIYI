# PR-TS-00-Java后端模块清单

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 范围与计数（VERIFIED 静态）

生产 Java 文件 299，16993 行；Controller 25；service 包 20 个类；全目录 @Service 23（另三项在 gateway）；projection 包 148 个文件，其中 Mapper 29、其余 DTO 等 119。测试目录 115 个 Java 文件，542 个 `@Test/@ParameterizedTest/@RepeatedTest/@TestFactory` 声明；包括基座/工具文件，**不是 542 次执行结果**。迁移 SQL 13 份。

`java-dependency-inventory.csv` 覆盖全部 299 文件，含行号、SHA-256、内部 imports、字段、事务、缓存、身份和测试引用。`source-evidence-index.csv` 是补充定位索引。扫描包括 package-info.java，未把它计作类。依赖字段提取可能包含嵌套 DTO 字段；导入依赖不等于运行调用。

| 顶级包 | Java文件数 |
| --- | --- |
| KinlinAiApplication.java | 1 |
| annotation | 1 |
| aspect | 2 |
| client | 8 |
| config | 13 |
| controller | 26 |
| dto | 30 |
| entity | 6 |
| exception | 4 |
| filter | 5 |
| gateway | 9 |
| infrastructure | 11 |
| interceptor | 1 |
| observability | 4 |
| projection | 148 |
| repository | 5 |
| security | 3 |
| service | 20 |
| util | 2 |


## Controller 全量范围

| Controller | 首个路由证据 | method/path行数 | 注入依赖 |
| --- | --- | --- | --- |
| AgentOsArtifactController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsArtifactController.java:44` | 21 | AgentOsClient gateway |
| AgentOsEventController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsEventController.java:35` | 2 | AiSseGatewayService sseGateway |
| AgentOsMissionController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsMissionController.java:40` | 21 | AgentOsClient gateway |
| AgentOsObservationController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsObservationController.java:44` | 13 | AgentOsClient gateway |
| AgentOsReviewController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsReviewController.java:40` | 11 | AgentOsClient gateway |
| AgentOsRunController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsRunController.java:41` | 5 | AgentOsClient gateway |
| AgentOsWorkspaceController | `apps/backend/src/main/java/com/kinlin/ai/controller/AgentOsWorkspaceController.java:17` | 4 | AgentOsClient gateway |
| AiServiceProxyController | `apps/backend/src/main/java/com/kinlin/ai/controller/AiServiceProxyController.java:35` | 7 | AiProxyService aiProxyService;AiSseGatewayService aiSseGatewayService;ChatStreamPersistenceService chatStreamPersistenceService |
| AlertController | `apps/backend/src/main/java/com/kinlin/ai/controller/AlertController.java:26` | 4 | AlertService alertService |
| AuthController | `apps/backend/src/main/java/com/kinlin/ai/controller/AuthController.java:46` | 4 | UserService userService;JwtUtil jwtUtil;LoginSessionService loginSessionService |
| ChatController | `apps/backend/src/main/java/com/kinlin/ai/controller/ChatController.java:32` | 3 | ChatService chatService |
| ChatQualityController | `apps/backend/src/main/java/com/kinlin/ai/controller/ChatQualityController.java:29` | 1 | ChatQualityService qualityService;ChatService chatService |
| ConversationController | `apps/backend/src/main/java/com/kinlin/ai/controller/ConversationController.java:31` | 6 | ConversationService conversationService |
| FileController | `apps/backend/src/main/java/com/kinlin/ai/controller/FileController.java:34` | 4 | FileService fileService |
| HealthController | `apps/backend/src/main/java/com/kinlin/ai/controller/HealthController.java:47` | 4 | JdbcTemplate jdbcTemplate;ObjectProvider<RedisConnectionFactory> redisConnectionFactory;AiDependencyHealthClient aiDependencyHealthClient |
| KnowledgeGraphController | `apps/backend/src/main/java/com/kinlin/ai/controller/KnowledgeGraphController.java:40` | 6 | KnowledgeGraphService knowledgeGraphService |
| KylinOSController | `apps/backend/src/main/java/com/kinlin/ai/controller/KylinOSController.java:25` | 3 | KylinOSIntegrationService kylinOSService |
| MetricsController | `apps/backend/src/main/java/com/kinlin/ai/controller/MetricsController.java:30` | 1 | MeterRegistry meterRegistry |
| RagController | `apps/backend/src/main/java/com/kinlin/ai/controller/RagController.java:27` | 4 | RagService ragService |
| RecommendationController | `apps/backend/src/main/java/com/kinlin/ai/controller/RecommendationController.java:29` | 2 | RecommendationService recommendationService |
| RoleController | `apps/backend/src/main/java/com/kinlin/ai/controller/RoleController.java:33` | 7 | RoleService roleService;com.kinlin.ai.service.RoleSwitchOptimizer roleSwitchOptimizer |
| RoleFusionController | `apps/backend/src/main/java/com/kinlin/ai/controller/RoleFusionController.java:30` | 2 | RoleFusionService roleFusionService |
| SearchController | `apps/backend/src/main/java/com/kinlin/ai/controller/SearchController.java:30` | 2 | ChatService chatService;SearchService searchService |
| UserController | `apps/backend/src/main/java/com/kinlin/ai/controller/UserController.java:45` | 6 | UserService userService;com.kinlin.ai.service.FileService fileService |
| UserProfileController | `apps/backend/src/main/java/com/kinlin/ai/controller/UserProfileController.java:28` | 2 | UserProfileService userProfileService |


## Service 全量逐项处置

以下职责/事务/fallback 为 VERIFIED 源码观察；目标拆分与幂等性判断为 INFERRED。每个 Service 的具体依赖、事务行号、测试引用见 CSV；没有注解不代表下游 repository 没有自己的事务。

| 类与证据 | 业务职责 | 持久化/事务 | 异常与Fallback | 幂等性判断 | TS处置 |
| --- | --- | --- | --- | --- | --- |
| AgentConversationPersistenceService<br>`apps/backend/src/main/java/com/kinlin/ai/service/AgentConversationPersistenceService.java:24` | Agent exchange 汇入共同会话历史 | conversations/messages；persistExchange 单事务 | 空 owner/session/text 跳过；遇到其他 owner 跳过，不能合并 | 相同 exchange 重试可重复写，无持久幂等键 | 保留历史投影职责，调用者需另行确认；不重建 Runtime Store |
| AlertService<br>`apps/backend/src/main/java/com/kinlin/ai/service/AlertService.java:18` | 阈值巡检与内存告警历史 | MetricsService + 进程内 Map；无持久 DB/事务 | 巡检逐项 catch；重启丢失历史 | 检查可能追加告警，非幂等 | observability application；内存语义要显式冻结或另案调整 |
| ChatQualityService<br>`apps/backend/src/main/java/com/kinlin/ai/service/ChatQualityService.java:15` | 历史消息质量评分 | 纯计算，无 DB/缓存/Python/事务 | 按输入评分，边界值见 QualityScore 测试 | 读计算 | 并入 chat analytics，若产品退役需单独批准 |
| ChatService<br>`apps/backend/src/main/java/com/kinlin/ai/service/ChatService.java:30` | 同步 Chat 编排、两段短事务、RAG/角色上下文 | conversations/messages；TransactionTemplate 两次短事务，HTTP 位于事务外 | 客户端失败固定文本且 confidence=0；RAG/角色上下文失败继续原查询 | 请求重试会追加消息，非全局幂等 | 迁移 chat application；不复制 Python 生成/工具执行 |
| ChatStreamPersistenceService<br>`apps/backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java:24` | 流前落 user、流后/取消落 assistant、reasoning/usage 捕获 | conversations/messages；prepare/complete 各自 @Transactional | 未完成/空响应/取消保留失败 metadata；capture.persisted 仅内存一次保护 | 非跨进程幂等；persisted 在实际 save 前置位，保存失败不能靠原 capture 重试 | 迁移 chat stream recorder；增加可恢复 attempt 唯一键设计与回滚测试 |
| ConversationService<br>`apps/backend/src/main/java/com/kinlin/ai/service/ConversationService.java:26` | 按 owner/mode 列表、批量预览、标题、删除 | conversations/messages；写方法事务；列表也有 @Transactional | 按 owner 删除失败返回 false；updateTitle 无权为 not-found | 读幂等；create 非幂等；删除多次结果需保留合同 | conversation repository + application；内部无 owner 方法禁止变为公开端口 |
| FileService<br>`apps/backend/src/main/java/com/kinlin/ai/service/FileService.java:25` | 上传、下载路径解析、删除和文件列表 | uploadDir 本地文件系统；无 DB/cache/事务 | 大小限制；IO 异常或列表单条错误；Paths.get 路径边界需专项修订 | 上传生成 UUID 名非幂等；删除存在性合同需保留 | files/storage adapter；显式根路径约束、重解析点与失败补偿 |
| KnowledgeGraphService<br>`apps/backend/src/main/java/com/kinlin/ai/service/KnowledgeGraphService.java:23` | 构图、混合检索、推理和统计 fallback | KnowledgeGraphClient；无平台事务 | PlatformAiClientException 由各方法转既有空结果/error Map | 上游构图幂等 UNKNOWN；只读方法可重放需超时约束 | 保留薄适配器与 DTO，不在 TS 重建图谱引擎 |
| KylinOSIntegrationService<br>`apps/backend/src/main/java/com/kinlin/ai/service/KylinOSIntegrationService.java:17` | 银河麒麟 OS 检测/系统信息等历史接口 | System/Runtime.exec Linux 命令；无 DB/cache | Windows 上探测失败捕获；系统信息含 javaVersion | 读取为主；系统命令副作用必须逐方法审查 | 目标 Windows-only：建议退役/替换明确的 Windows diagnostics，需 API 消费决策 |
| LoginSessionService<br>`apps/backend/src/main/java/com/kinlin/ai/service/LoginSessionService.java:27` | 创建、撤销、检查 PostgreSQL 登录会话 | iam_login_sessions + JwtProperties；create/revoke 事务 | 会话缺失/撤销/过期走失效判断 | 登录创建新 sid；撤销幂等性由测试冻结至退役 | 退役用户 session 服务；不删除历史表作为首步 |
| MetricsService<br>`apps/backend/src/main/java/com/kinlin/ai/service/MetricsService.java:19` | 请求/错误/时延指标 | MeterRegistry；无业务 DB/事务 | 采集行为与 MeterRegistry 实现相关 | 计数副作用，非业务幂等 | 改为 observability port，保留指标意义与低基数 |
| RagService<br>`apps/backend/src/main/java/com/kinlin/ai/service/RagService.java:25` | RAG query/upload/list/delete 的业务 fallback | 仅 RagClient；无平台 DB/cache/事务 | query 失败固定回答/空源/0；list 失败空列表；upload 包装异常；delete 异常吞掉 | 上游写操作幂等 UNKNOWN，不能自动重试 upload/delete | RAG adapter + projections；检索索引仍由 Python 所有 |
| RecommendationService<br>`apps/backend/src/main/java/com/kinlin/ai/service/RecommendationService.java:21` | 关键词/场景规则推荐，去重最多 5 条 | 无 DB/cache/Python/事务 | 输入缺失使用默认推荐 | 同输入纯计算，最多5条 | 迁移轻量 application 纯函数；并非模型或策略执行器 |
| RoleFusionService<br>`apps/backend/src/main/java/com/kinlin/ai/service/RoleFusionService.java:23` | 融合和权重客户端编排 | RoleFusionClient；无平台事务 | 失败返回 error Map，不能统一改成抛 5xx 而无版本决策 | 上游幂等 UNKNOWN | 保留 legacy AI capability adapter；不合入 AgentOS 调度 |
| RoleService<br>`apps/backend/src/main/java/com/kinlin/ai/service/RoleService.java:21` | 自定义角色 CRUD 与配置验证 | roles；create/update/delete 事务；update/delete roles cache 精确逐出 | 校验失败 BusinessException；更新删除允许 userId==null 分支 | create 非幂等；更新相同值语义需合同测试 | roles application；新 ActorContext 必须非空，不保留 null 绕过 |
| RoleSwitchOptimizer<br>`apps/backend/src/main/java/com/kinlin/ai/service/RoleSwitchOptimizer.java:30` | 角色上下文读取与缓存 | RoleService；Spring roles Cacheable，TTL 配置 1h | 缓存异常由 CacheConfig 降级 DB；无新独立缓存权威 | 读幂等，但 Java default typing 与 TS 不兼容 | 并入 roles read/cache adapter；新 namespace，保留失效与降级 |
| RoleValidationService<br>`apps/backend/src/main/java/com/kinlin/ai/service/RoleValidationService.java:16` | 角色配置校验 | 纯校验，无事务/DB/Python | 返回 validation errors/warnings | 同输入确定性需用例冻结 | 并入 roles domain validation |
| SearchService<br>`apps/backend/src/main/java/com/kinlin/ai/service/SearchService.java:20` | 仅搜索 owner 的 conversations 中的 message | ConversationRepository + MessageRepository；PageRequest 0/200；无事务注解 | 没有会话返回空列表 | 只读幂等；结果上限 200、大小写不敏感必须冻结 | 迁移 search application/repository，必须保留 owner 限定 |
| UserProfileService<br>`apps/backend/src/main/java/com/kinlin/ai/service/UserProfileService.java:21` | 聚合资料、会话数、角色使用次数与活跃度 | 经 UserService/ConversationService/RoleRepository 读；无独立事务注解 | 非法 role UUID 捕获；缺资料保持部分字段空值 | 只读派生结果；无独立 UserProfile 表 | 迁移 local profile read model；权威 owner 不从路径任意声明 |
| UserService<br>`apps/backend/src/main/java/com/kinlin/ai/service/UserService.java:20` | 用户资料查询更新；含密码创建验证 | users；create/updatePassword/update/delete 事务 | 重复用户名/邮箱或找不到用户抛 IllegalArgumentException | 查询幂等；创建非幂等；资料更新需验证 owner | 保留 actor/profile repository；删除密码验证与登录创建流程 |


当前用户路径：Controller 的 AuthenticatedUser → Service(userId)；ChatStreamPersistenceService 自行取得 currentUserId；网关经 TrustedUserContextForwarder。UserProfileService/SearchService 依赖参数身份而不是自行认证，必须在新 application 层注入 LocalIdentity。角色读取缓存也不能成为 owner 权威。证据：`apps/backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java:32`（`AuthenticatedUser.currentUserId()`）；`apps/backend/src/main/java/com/kinlin/ai/service/RoleService.java:89`（`userId == null ||`）。

## Projection 全量分类

| Projection域 | 文件数 |
| --- | --- |
| artifact | 5 |
| chatquality | 1 |
| common | 3 |
| conversation | 3 |
| copilot | 2 |
| graph | 5 |
| history | 5 |
| identity | 2 |
| knowledgegraph | 4 |
| material | 3 |
| memory | 4 |
| message | 5 |
| mission | 10 |
| operational | 2 |
| output | 6 |
| provenance | 5 |
| rag | 4 |
| recovery | 3 |
| resource | 9 |
| resourcecatalog | 10 |
| role | 5 |
| rolefusion | 2 |
| run | 19 |
| trace | 8 |
| user | 2 |
| userprofile | 3 |
| workspace | 18 |


保留投影的闭合 DTO、字段允许集、缺失字段/空值、枚举、排序和 wire 命名；不把 Map 原样暴露给 renderer，不共享数据库实体。Architecture Guard 中 MissionProjectionArchitectureTest / QueryProjectionArchitectureTest / StaticQueryRouteArchitectureTest / ArchitectureGuardTest 均需转为 TS 依赖规则与序列化测试。实现可合并 mapper 模板，不能按 148 个文件机械翻译。

## 数据、传输和框架边界

实体：BaseEntity、User、Role、Conversation、Message、LoginSession；repository：User、Role、Conversation、Message、LoginSession 五个接口。Workspace Grant 并非 Java JPA 实体，由 Python WorkspaceAuthority 写 PostgreSQL。所有生产 Java 的精确清单在 dependency CSV，非 Service 的 client/gateway/filter/config/security/observability/exception 等也在范围内。

Spring MVC/Tomcat 是入站 API；WebClient/Reactor 为出站与 SSE。移除 Spring 不意味着复制 Python lifecycle；AgentOsClient 是 application 的端口，AgentOsGatewayService 才是传输实现。证据：`apps/backend/src/main/java/com/kinlin/ai/gateway/AgentOsGatewayService.java:33`（`implements AgentOsClient`）。

## 测试冻结与执行限制

全部测试仅审源码，未运行 mvn test。`test-inventory.csv` 含 profiles、潜在删除/进程调用行号。NativePostgres.start 创建临时 cluster/随机端口；NativeRedis.start 创建临时配置/随机端口，但全套调用链与覆盖配置没有完成隔离证明，因此不借机启动临时数据库。`apps/backend/src/test/java/com/kinlin/ai/integration/NativePostgres.java:87`（`Files.createTempDirectory`）；`apps/backend/src/test/java/com/kinlin/ai/integration/NativeRedis.java:59`（`Files.createTempDirectory`）。

CI：`.github/workflows/backend-ci.yml:60`（`Run backend test gate`） 配置 Ubuntu 24.04/JDK17，安装本机 PostgreSQL15/Redis，mvn test 后 package -DskipTests；本轮未触发 CI。H2 test 的 Flyway=false/create-drop 不能证明 PostgreSQL 迁移成功。性能标签默认排除，不能将静态测试总数当 required gate 的执行数。

## 测试逐文件迁移矩阵

分类为静态词法辅助（多分类），不假定每类测试都已验证对应功能。删除旧登录合同只删除 JWT/session 专属断言；其中共用的 owner/header/SSE/撤销执行许可断言应重写保留。fixture/base 文件标记改写表示保留其隔离能力，不表示有测试方法。

| 测试源码 | 分类（可多选） | 声明数 | 迁移处置 |
| --- | --- | --- | --- |
| `apps/backend/src/test/java/com/kinlin/ai/architecture/ArchitectureGuardTest.java` | 业务行为;Redis;Gateway;SSE;Security;Architecture Guard | 30 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/architecture/MissionProjectionArchitectureTest.java` | Projection;Architecture Guard | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/architecture/QueryProjectionArchitectureTest.java` | Projection;SSE;Security;Architecture Guard | 7 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/architecture/StaticQueryRouteArchitectureTest.java` | REST;Projection;Gateway;Architecture Guard | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/config/AgentPropertiesTest.java` | 待确认 | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/config/JwtPropertiesTest.java` | Security | 6 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsArtifactControllerTest.java` | REST;Projection;Gateway;SSE;Security | 13 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsEventControllerTest.java` | REST;Gateway;SSE;Security | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsMissionControllerTest.java` | REST;Projection;Gateway | 13 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsObservationControllerTest.java` | REST;Projection;Gateway | 10 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsReviewControllerTest.java` | REST;Projection;Gateway | 7 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsRouteCompatibilityTest.java` | REST;Gateway;SSE | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AgentOsRunControllerTest.java` | REST;Projection;Gateway | 7 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/AuthControllerTest.java` | REST;Projection;Security | 18 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/ChatControllerTest.java` | REST;Projection;Security | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/ChatProjectionControllerTest.java` | REST;Projection;Security | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/ConversationProjectionControllerTest.java` | REST;Projection;Security | 9 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/HealthControllerTest.java` | REST;PostgreSQL;Redis | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/MissionProjectionControllerTest.java` | REST;Projection;Gateway | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/RecommendationControllerTest.java` | REST;Projection;Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/RecordingAgentOsGateway.java` | Projection;Gateway | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/RoleProjectionControllerTest.java` | REST;Projection;Security | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/SearchProjectionControllerTest.java` | REST;Projection;Security | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/StrippedIdentityHeaderBoundaryTest.java` | REST;Security | 8 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/controller/UserProjectionControllerTest.java` | REST;Projection;Security | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/dto/agentos/AgentOsContractSerializationTest.java` | Projection;Security | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/filter/LocalApiPathFilterTest.java` | Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/filter/SensitiveIdentityHeaderFilterTest.java` | Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/filter/TraceIdFilterTest.java` | 待确认 | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/AgentOsGatewayServiceTest.java` | 业务行为;Projection;Gateway | 7 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/AiProxyServiceTest.java` | 业务行为;Projection;Gateway;Security | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/AiSseGatewayLifecycleTest.java` | Gateway;SSE;Security | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/AiSseGatewayServiceTest.java` | 业务行为;Gateway;SSE;Security | 8 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/AiSseGatewaySessionRevocationTest.java` | Gateway;SSE;Security | 5 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/PythonServiceAuthenticationTest.java` | Gateway;Security | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/SessionRecheckGateTest.java` | SSE;Security | 7 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/gateway/TrustedUserContextForwarderTest.java` | Gateway;Security | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/infrastructure/http/FakePythonTransport.java` | Gateway | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/infrastructure/http/PlatformAiClientCharacterizationTest.java` | Gateway | 16 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/infrastructure/http/PythonClientFactoryTest.java` | Gateway | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/infrastructure/http/TransportErrorClassifierTest.java` | Gateway | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/infrastructure/http/WebClientAiDependencyHealthClientTest.java` | Gateway | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/ChatIntegrationTest.java` | Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/LegacyTransportRemovalTest.java` | REST;Gateway;SSE | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/NativePostgres.java` | PostgreSQL;SSE;Native Runtime | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/NativePostgresTest.java` | PostgreSQL;Native Runtime | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/NativeRedis.java` | Redis;SSE;Native Runtime | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/PostgresContainerBase.java` | PostgreSQL;Redis;Native Runtime | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/PostgresIntegrationTestBase.java` | PostgreSQL | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/PostgresMigrationIntegrationTest.java` | PostgreSQL | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/PostgresRepositoryIntegrationTest.java` | PostgreSQL | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/RedisIntegrationTestBase.java` | PostgreSQL;Redis;Native Runtime | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/RoleCacheRedisIntegrationTest.java` | Projection;Redis | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/RoleIntegrationTest.java` | Security | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/SessionRevocationPostgresIntegrationTest.java` | REST;Projection;PostgreSQL;Security | 2 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/SseSessionRevocationEndToEndTest.java` | Projection;Gateway;SSE;Security | 4 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/integration/SseSessionRevocationPostgresTest.java` | Projection;PostgreSQL;Gateway;SSE;Security | 1 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/interceptor/RateLimitInterceptorTest.java` | Gateway;Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/observability/LogRedactorTest.java` | Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/observability/ObservabilityExpositionTest.java` | REST;Projection;Redis;SSE;Security | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/observability/OutboundTracePropagationTest.java` | SSE;Architecture Guard | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/performance/KinlinBackendBaselineBenchmark.java` | PostgreSQL;Redis;SSE;Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/performance/QueryDebtMeasurementTest.java` | Security | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/artifact/ArtifactProjectionSerializationTest.java` | Projection | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/conversation/ConversationProjectionSerializationTest.java` | Projection | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/copilot/CopilotProjectionMapperTest.java` | Projection | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/history/HistoryAndResourceCatalogProjectionMapperTest.java` | Projection | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/knowledgegraph/KnowledgeGraphProjectionMapperTest.java` | Projection | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/knowledgegraph/KnowledgeQueryMapperTest.java` | REST;Projection | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/material/MaterialProjectionTest.java` | Projection | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/memory/MemoryEventsProjectionMapperTest.java` | Projection | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/message/MessageProjectionSerializationTest.java` | Projection | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/mission/MissionProjectionSerializationTest.java` | Projection | 7 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/mission/MissionQueryFixture.java` | 待确认 | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/mission/MissionSemanticProjectionSerializationTest.java` | Projection | 8 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/mission/MissionSemanticQueryFixture.java` | 待确认 | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/output/OutputProjectionMapperTest.java` | Projection | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/platform/OperationalProjectionTest.java` | REST;Projection;Security | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/provenance/ProvenanceProjectionMapperTest.java` | Projection | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/rag/RagProjectionMapperTest.java` | Projection | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/recovery/RecoveryAndIdentityProjectionMapperTest.java` | Projection | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/resource/ResourceUsageProjectionMapperTest.java` | Projection | 9 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/resource/ResourceUsageProjectionSerializationTest.java` | Projection | 10 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/resource/ResourceUsageQueryFixture.java` | 待确认 | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/role/RoleQuerySerializationTest.java` | Projection | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/run/RunActionCapabilitiesProjectionTest.java` | Projection | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/run/RunProjectionBoundaryTest.java` | Projection | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/trace/TraceProjectionMapperTest.java` | Projection | 12 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/trace/TraceProjectionSerializationTest.java` | Projection | 8 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/trace/TraceQueryFixture.java` | 待确认 | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/user/UserCredentialOutputGuardTest.java` | Projection;Architecture Guard | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/user/UserQuerySerializationTest.java` | Projection | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/workspace/WorkspaceProjectionMapperTest.java` | Projection | 13 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/workspace/WorkspaceProjectionSerializationTest.java` | Projection | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/projection/workspace/WorkspaceQueryFixture.java` | 待确认 | 0 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/AuthenticatedUserTest.java` | Security | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/LocalApiHttpIntegrationTest.java` | REST;Projection;Gateway;SSE;Security | 1 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/SecurityRouteMatrixTest.java` | REST;Gateway;Security | 3 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/SessionRevocationHttpContractTest.java` | REST;Projection;Security | 6 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/SessionRevocationPersistenceTest.java` | REST;Projection;Security | 4 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/SessionStateUnavailableTest.java` | REST;Projection;Security | 3 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/security/WsEndpointAuthorizationTest.java` | REST;Gateway;Security | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/ChatServiceTest.java` | 业务行为;Gateway | 14 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/ChatStreamPersistenceServiceTest.java` | 业务行为;Projection;SSE;Security | 10 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/ConversationServiceTest.java` | 业务行为 | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/KnowledgeGraphServiceTest.java` | 业务行为;Gateway | 6 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/RagServiceTest.java` | 业务行为;Gateway | 9 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/RecommendationServiceTest.java` | 业务行为 | 2 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/RoleFusionServiceTest.java` | 业务行为;Gateway | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/RoleServiceTest.java` | 业务行为 | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/RoleSwitchOptimizerTest.java` | 业务行为;Redis | 4 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/RoleValidationServiceTest.java` | 业务行为 | 5 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/service/UserServiceTest.java` | 业务行为 | 14 | 保留合同 / 改写测试 |
| `apps/backend/src/test/java/com/kinlin/ai/util/JwtUtilTest.java` | Security | 5 | 删除旧登录合同 + 改写无登录安全测试 |
| `apps/backend/src/test/java/com/kinlin/ai/util/PasswordUtilTest.java` | 待确认 | 10 | 保留合同 / 改写测试 |

# PR-TS-00-风险与迁移执行计划

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 审计决定：BLOCKED；PR-TS-01：NO-GO

已经完成本轮源码遍历、静态接口/依赖盘点、环境检查、风险与目标设计交付。没有完成真实DB/schema版本/owner统计、运行路由/SSE/native行为验证；部分动态/可选上游与测试隔离仍待确认。遵照验收标准，不将UNKNOWN伪造为ACCEPT。此决定不代表已证实当前存在所有风险描述的事故；下表区分**迁移触发风险**与已见源码缺口。

## 分级风险与可验证处置

| 等级/编号 | 问题与证据 | 影响范围 | 触发条件 | 处置 | 阶段 | 验收条件 |
| --- | --- | --- | --- | --- | --- | --- |
| P0/R01 | 身份重建/自动合并将历史数据和执行授权错配<br>`apps/backend/src/main/java/com/kinlin/ai/gateway/TrustedUserContextForwarder.java:22`（`AUTHENTICATED_USER_ID`）；`apps/agent/app/execution/workspace_authority.py:137`（`row['user_id'] != owner`） | PG users/roles/conversations、SQLite Run、Artifact/Grant | 新actor UUID、tenant归一变化或多用户强制合并 | 保留旧owner UUID/wire tenant映射；零/单/多用户按数据库报告分流；多用户人工决策 | 00补证→02身份 | 同Home重启actor不变；旧owner数据仍隔离；未决多用户拒绝启动 |
| P0/R02 | Grant重新签发或替换Run快照会使旧Run越权<br>`apps/agent/app/execution/workspace_authority.py:136`（`row['grant_id'] != binding['grantId']`）；`apps/agent/app/execution/workspace_authority.py:116`（`run_input.pop('workspaceBinding', None)`） | 目录写入、shell执行、历史Run | 移除登录时绕过owner/revoked/epoch校验或复用新grant | Python仍唯一issuer/resolver；不改历史Run；保留grant epoch、inode、resource和owner检查 | 02/05 | 撤销后旧Run失败；重新授权同目录旧Run仍失败，新Run正常；跨owner/tenant拒绝 |
| P0/R03 | 未查真库即迁移可能破坏不可恢复数据<br>`apps/backend/src/main/resources/db/migration/V10__delete_builtin_roles.sql:5`（`DELETE FROM roles`）；`apps/backend/src/main/resources/db/migration/V13__drop_user_feedback.sql:4`（`DROP TABLE`） | 所有持久数据、Flyway lineage、恢复 | 将文件V13当真库V13；并行迁移runner；只回滚二进制 | 真实只读schema/owner审计、全栈冷备和恢复演练；历史SQL冻结；单写runner交接 | 00补证→03/07 | 真实history成功状态/constraints有证据；原Home恢复验证；不丢SQLite/Artifact/Grant |
| P0/R04 | 去JWT后平台请求可伪造actor或由跨站驱动敏感操作<br>`apps/backend/src/main/java/com/kinlin/ai/controller/UserProfileController.java:29`（`@PathVariable UUID userId`）；`apps/desktop/electron/src/main.ts:278`（`const authorized =`） | profile/roles/conversations/Workspace/Hands入口 | 直接permitAll、信任userId或误删IPC sender guard；仅CORS无服务端写准入 | 服务端LocalIdentity生成trusted headers；非空owner；Host/Origin/非简单请求准入；保留IPC校验 | 01/02/06 | 伪造身份头/URL/body无效；陌生Origin/null/恶意Host写拒绝；错误sender IPC拒绝 |
| P0/R05 | 替换进程名或恢复流程会误杀/残留进程或产生不一致冷备<br>`ops/scripts/release/product_runtime.py:151`（`def occupied_ports`）；`ops/scripts/infra/windows/native/persistent_runtime.py:605`（`def require_stopped`） | 用户其他程序、PG/Redis/SQLite一致性 | 仅按PID/端口终止、开发takeover带入产品、流未落库即备份 | 保留身份校验/停栈锁/数据hash；profile策略显式化；Node drain与旧记录兼容 | 01设计→07 | PID复用/端口占用不误杀；失败无受管孤儿；冷备恢复一致且actor不变 |
| P1/R06 | SSE sid gate与无登录actor不兼容；断流落库非持久幂等<br>`apps/backend/src/main/java/com/kinlin/ai/gateway/AiSseGatewayService.java:105`（`userContext.sid() == null`）；`apps/backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java:70`（`capture.persisted = true`） | Chat流、事件、用户历史 | 仅删除JWT过滤器；取消/超时/数据库失败/进程崩溃 | 以本机准入替换sid gate；保留流timeout/abort；定义attempt重放/事务恢复合同 | 04/05 | 无sid可合法建流；失败/取消事件有序；落库失败可诊断和恢复且不重复user/assistant |
| P1/R07 | 前端接口缺口与条件Python路由不能按注解数补齐<br>`apps/frontend/src/services/api/agentos/api/runtime.ts:32`（`/context-packs`）；`apps/agent/app/main.py:144`（`except ImportError as e:`） | 上下文包、node启停、旧chat统计、RAG下载、ASR | 仅迁移140显式路由；假定代理有任意上游 | 逐项确认消费/上游wire；补正式合同或批准退役；WS单独决策 | 01合同→05/06 | 五缺口各有合同测试或退役记录；可选路由加载可观测；ASR升级路径明确 |
| P1/R08 | 错误/序列化/时间/Redis值差异破坏现有合同<br>`apps/backend/src/main/java/com/kinlin/ai/gateway/AgentOsGatewayService.java:249`（`AGENTOS_UPSTREAM_UNAVAILABLE`）；`apps/backend/src/main/java/com/kinlin/ai/config/CacheConfig.java:66`（`roleAwareJsonSerializer()`） | 所有平台API与角色缓存 | 全局统一error、Date隐式时区、读Java类型缓存 | 按族兼容error，显式UUID/time/count/JSONB映射；版本化cache namespace | 03/04/05 | 匿名fixture字段/status/code差分通过；PG JSONB/time roundtrip；Redis停机可降级 |
| P1/R09 | 文件路径与通用代理缓冲需明确安全/容量边界<br>`apps/backend/src/main/java/com/kinlin/ai/service/FileService.java:66`（`Paths.get(uploadDir, filePath)`）；`apps/backend/src/main/java/com/kinlin/ai/gateway/AiProxyService.java:71`（`readAllBytes()`） | 平台文件与网关内存 | 不受控type/filePath或大body并发；迁移只翻译API | 根目录realpath/重解析点/文件名约束与上限背压；先确认调用者校验；不声称已复现越权 | 04/05 | 编码遍历/绝对路径/链接逃逸拒绝；超限413；慢读取消释放资源 |
| P1/R10 | 测试隔离与运行基线未证实，迁移绿色结果不可比较<br>`apps/backend/src/test/resources/application-test.yml:13`（`create-drop`）；`.github/workflows/backend-ci.yml:62`（`mvn -B -ntp test`） | 旧/新合同门禁 | H2代PG、未确认环境即运行测试或直接跳过旧行为 | 确认每个suite的数据目录/URL/端口/清理所有权后隔离执行；保存实际报告 | 00补证→各PR | mvn原基线与TS等价矩阵均有真实输出；无生产数据/服务干扰 |
| P2/R11 | 机械类翻译与遗留平台接口增大维护面<br>`apps/backend/src/main/java/com/kinlin/ai/service/KylinOSIntegrationService.java:31`（`cat /etc/kylin-release`）；`apps/backend/src/main/java/com/kinlin/ai/service/RecommendationService.java:35`（`generateContextualRecommendations`） | 模块边界、Windows-only体验 | 复制JavaService/Map/System.exec而未区分平台职责 | 按application/port/adapter整合；KylinOS等经消费方决策退役，推荐保留纯函数 | 01设计→04 | 架构依赖规则通过；无platform层引入Python计划执行；遗留API有明确处置 |


R01–R05为P0迁移阻断项，均有处置和验收，不宣称已经修复。R04中profile路径接受userId是源码事实，是否可越权读取需结合活动安全上下文进一步验证；R09是边界风险，未进行路径越权利用测试。本轮不利用漏洞、不修业务代码。

## 未来等价测试矩阵

| 测试域 | 场景 | 通过标准 | 阶段 |
| --- | --- | --- | --- |
| REST合同 | route CSV保留项逐method/path；alias规范化/HTTP优先级；HEAD/OPTIONS/actuator单列 | 与旧匿名fixture比字段、status、error code；计划退役auth单列404/410 | 01/04/05 |
| 分页/排序 | page/pageSize边界、空值过滤、cursor、并列时间稳定排序 | 列表items/total/nextCursor与既有合同一致，未知规则先冻结 | 03/05 |
| UUID/时间/JSONB | uuid非法/nullable；TIMESTAMP/TIMESTAMPTZ、UTC/本机时区、计数bigint；对象数组Unicode | PG15往返保持；wire格式逐字段一致，无隐式时区漂移 | 03/04 |
| 事务 | conversation及messages删除；同步chat两段事务；失败回滚；roles commit后cache | 中途异常不半写；HTTP不持有事务；无owner路径不可公开 | 03/04 |
| SSE事件 | 一字节UTF8切分、多行data、event/id/retry、reasoning/tool/usage/done顺序 | socket读取有序；不全量buffer；断连不生成第二响应；bounded内存 | 05 |
| SSE中断 | idle/max分离、客户端Abort、上游4xx/5xx/断连、慢客户端、shutdown | 正确HTTP或terminal event；abort传到Python；无timer/reader/配额泄漏 | 05/07 |
| Chat落库 | complete/cancel同时触发、空响应、DB失败、进程崩溃、重连重试 | 定义attempt语义；不重复历史；失败可恢复；metadata与最后用户消息归属正确 | 04/05 |
| LocalIdentity | 零/一/多用户、配置丢失/篡改、同Home重启、伪造actor/tenant/header | 稳定actor；多用户未决fail closed；无JWT/session/密码；资料隔离 | 02/06 |
| 服务认证 | Python缺token/重复header/假user/正常Backend转发、公共health | Python业务直连拒绝；trusted context由Backend生成；无凭据出现在日志 | 02/05 |
| Workspace Grant | 选择A→新Run、切B→旧Run仍A、撤销A、重授权A、跨tenant/owner、目录身份变更 | 旧Run无新grant权限；missing binding fail closed；Hands JSON只是投影 | 02/05 |
| Mission/Run/Review/Artifact | launch reconcile/409、graph五步、permit/dispatch、cancel/retry、软删终态、文件下载 | Python仍权威，TS不调度；403/404/409/202等逐路由冻结 | 05 |
| 缓存/Redis | 角色hit/miss/evict、Redis中断恢复、旧Java值/new namespace、协调DB不动 | 降级PG；修改删除不读陈旧值；无FLUSHALL/协调协议变更 | 04 |
| 无登录入口安全 | 真实socket Host/Origin/null/简单表单跨站、假userId、未授权IPC sender | 敏感写/读符合本机准入；合法Electron可用；不因无登录开放目录执行 | 01/02/06 |
| Windows native | 冷启/重复启/占端口/PID复用/部分失败/关闭中流/恢复/冷备hash损坏 | 产品不误杀；无受管残留；备份恢复owner/grant/store一致；无JRE/JVM依赖 | 07 |


Java逐文件处置见模块报告和test-inventory.csv。旧JWT签名/登录/session重查的专属断言删除；其中owner、trusted header、SSE取消与Grant/Permit授权不删除。不能要求新后端继续签JWT以满足旧测试。新无登录入口测试替代登录合同；RuntimeEvent/Trace/Provenance/Checkpoint序列化仍保留。测试数量/通过率本轮无运行输出，全部NOT RUN。

## 迁移PR顺序、前置条件和回滚

| 阶段 | 范围 | 前置条件 | 退出门禁 | 回滚机制 |
| --- | --- | --- | --- | --- |
| TS-00补证 | 真实schema/owner/tenant/孤儿与SQLite/Artifact匿名对账；完整套件隔离评审、关键动态路由确认 | 本轮BLOCKED；用户正常环境已运行并可安全只读连接 | 补证报告与正式验收，不执行重写 | 只读失败停止，不改数据；旧栈原样 |
| TS-01 架构/骨架 | 锁Node/Fastify/schema方案；Actor/本机准入/错误/ServiceSpec合同；隔离fixture与architecture guard | TS-00正式ACCEPT且P0处置与身份方案冻结 | 空health/测试在独立端口/目录；无真库修改；逐路由迁移追踪 | 删除新骨架或停止隔离进程；旧入口仍有效 |
| TS-02 LocalIdentity | 无登录owner映射/可信身份；零一多用户预检；保留Python/IPC授权边界 | 真库多owner决策完备；可恢复身份备份 | 稳定actor/tenant、伪造输入拒绝、旧Run/Grant不混淆 | 恢复原映射/配置；未切换前Java仍登录；不合并数据 |
| TS-03 persistence | pg/Kysely repositories/types/短事务；Flyway lineage交接设计与schema验证 | schema fingerprint与备份恢复已验证 | PG15等价JSONB/UUID/time/约束/事务测试；migration单写 | 先保持expand-only兼容；schema不可逆则完整冷还原，禁止仅降二进制 |
| TS-04 平台业务 | conversation/roles/profile/search/chat/recommendation/files及cache | 02/03完成，owner与文件边界明确 | REST/fallback/事务/缓存差分；不改Python生成语义 | 旧Java仍可用；禁止新旧同时写一请求/双发模型 |
| TS-05 Gateway/SSE | 所有保留AgentOS/AI路径、closed projections、binary/multipart、abort/stream recorder | 正式上游wire与五缺口/WS决策完成 | Python服务认证、Mission/Run/Review/Artifact/Grant/流E2E | 流先drain；只读shadow可选；命令/执行禁止双写shadow |
| TS-06 Frontend/Electron | 移除token/login/sessionBootstrap/401跳转，改identity readiness；保留IPC/Origin | TS平台/网关通过；无登录入口安全合同通过 | 桌面启动无需密码；完整调用矩阵回归；无孤立axios/token守卫 | 切回完整旧renderer+Java配套，不混用新无登录UI与旧需JWT后端 |
| TS-07 Native/发行切换 | node dist/main.js/18080、manifest/health/ownership/backup；冷启动停止恢复 | 全部合同绿、备份可恢复、正式切换批准 | 普通Windows用户、无JDK/JVM/Docker、包内Node/PG/Redis/Python/Hands全链实测 | 同Home全栈冷备恢复；完整配套旧发行包与identity兼容；不自动执行 |
| TS-08 Java退役 | 删除Java/JRE/Maven/登录残留、切CI和文档 | 正式发行验收与回滚窗口结束，剩余合同有处置 | 扫描无JVM运行依赖；TS required gates与冷备恢复通过 | 保存旧签名发行包/数据备份；不可逆清理后需完整恢复 |


每阶段不自动获得后续实施/部署授权；本轮仅审计，禁止预建backend-ts。后续实现可以按依赖拆任务，但平台写请求/执行命令不可发给新旧后端各一次。只读影子比较也需匿名化、独立连接池和资源预算，不偷偷接生产流量。

## 本轮验收逐项状态

| 要求 | 状态 | 证据/缺口 |
| --- | --- | --- |
| Git基线/远端关系 | VERIFIED | 干净master/8775130f，参考领先23提交；结束verification |
| Java范围 | VERIFIED | 299源文件哈希/依赖，20 Service逐项，115测试文件 |
| HTTP完整性 | VERIFIED静态 / BLOCKED运行 | 145 method-path行+53别名；五缺口/条件上游/框架生成路由单列 |
| Frontend/Electron关系 | VERIFIED静态 / UNKNOWN运行 | 152调用项、224身份触点；ASR升级链未证实 |
| Python/Hands权威 | VERIFIED源码 | gateway/transport/WorkspaceAuthority/Runtime分工明确 |
| schema与版本 | BLOCKED | 真库未运行，不读DPAPI/不自启动；SQL计划未执行 |
| LocalIdentity风险 | VERIFIED证据 / INFERRED方案 | 零一多用户策略，真实owner数量与决策UNKNOWN |
| Windows链 | VERIFIED静态 / BLOCKED运行 | 524依赖引用、N03/产品差异、备份恢复门禁 |
| TS目标架构 | INFERRED设计完成 | 模块树/依赖/技术评估/安全准入/迁移权威方案 |
| 迁移前置/回滚 | INFERRED设计完成 | 00补证→01–08顺序；schema不可逆需全冷备恢复 |
| P0处置 | 方案完整 / 验收未完成 | R01–R05逐项验收，禁止提前切换 |
| 无业务源码/数据修改 | VERIFIED变更边界 | verification.json；仅本目录新增文件，未启动服务/执行DB写 |

## 最小解阻措施

1. 在用户正常业务环境已经运行时，用明确的只读连接取得真实Flyway/schema/匿名owner/grant/孤儿统计；本轮不能为此启动服务。补充SQLite/Artifact历史身份匿名对账，不输出正文/完整路径。
2. 根据真实零/单/多用户与tenant情况冻结LocalIdentity映射；多用户或多历史owner必须人工决策，不能默认归并。
3. 逐项冻结五处前后端缺口、ASR升级路径、可选Python挂载及本机无登录HTTP准入合同；把运行未验证项作为下一次授权验收的明确范围。
4. 确认现有测试全套的目录/URL/端口/清理隔离后再运行；真实冷启动/停止/恢复/备份演练需要另行明确运行操作范围。本轮没有执行这些动作。
5. 对本报告正式验收后才进入PR-TS-01；没有通过前维持NO-GO。本轮结束停止，不自动迁移/提交/推送。

## 文件变更

本轮只新增 `docs/audits/PR-TS-00-20261107/`。八份主报告、四份要求CSV以及辅助CSV/JSON/只读SQL/审计生成脚本均在同目录；完整列表和SHA-256见 artifact-manifest.csv。无已有报告被覆盖；生成器对报告使用独占创建。CSV细化仅更新本轮自建的中间盘点产物，不触碰审计前文件。未执行任何现有业务测试或DB迁移。

"""Generate this audit's new reports with checked source citations. No app imports."""
from pathlib import Path
import csv,json,re,collections,subprocess
OUT=Path(__file__).parent;ROOT=OUT.parents[2]
def load(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
stats=json.loads((OUT/'inventory-summary.json').read_text(encoding='utf-8'))
env=json.loads((OUT/'environment-evidence.json').read_text(encoding='utf-8'))
deps=load('java-dependency-inventory.csv');routes=load('route-inventory.csv');front=load('frontend-callsite-inventory.csv');tests=load('test-inventory.csv');migs=load('migration-inventory.csv')
J='apps/backend/src/main/java/com/kinlin/ai/'
def ev(p,needle):
 s=(ROOT/p).read_text(encoding='utf-8-sig');at=s.find(needle)
 if at<0:raise ValueError(f'missing citation {p}: {needle}')
 return f'`{p}:{s.count(chr(10),0,at)+1}`（`{needle}`）'
def je(p,needle):return ev(J+p,needle)
def table(headers,rows):
 def cell(v):return str(v).replace('|','\\|').replace('\n','<br>')
 return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(cell(v) for v in row)+' |' for row in rows])+'\n'
legend='''> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

'''
def report(title,body):
 p=OUT/(title+'.md')
 with p.open('x',encoding='utf-8') as f:f.write('# '+title+'\n\n'+legend+body.strip()+'\n')
head=env['git']['head']['output']
report('PR-TS-00-本机基线与环境审计',f'''
## 结论：BLOCKED

源码盘点和迁移方案已经交付；真实数据库、运行 API/SSE 与冷启动验收没有证据，不能宣称全面审计已验收。`PR-TS-01: NO-GO`，先补齐本轮门禁，不自动实施下一阶段。

## Git 冻结

| 项目 | 本轮证据 |
| --- | --- |
| HEAD / branch | `{head}` / `master` |
| 远端 master | `git ls-remote origin refs/heads/master` 返回相同 SHA |
| 参考 SHA | `1f3e37701b4977f452514bafd208092a2ac1d80a` |
| 拓扑关系 | `git rev-list --left-right --count REF...HEAD` = `0 23`，参考为当前 HEAD 的祖先 |
| 开始时 tracked / staged / untracked | 均为空，`git status --short --branch` 仅 `## master...origin/master` |
| 其他未提交 PR | 开始时未发现；本轮新增审计目录不会进入业务基线 |
| diff / cached diff | 开始均为空；结束复查见 `verification.json` |

已执行用户要求的六条初始 Git 命令；另做只读 ls-remote 与拓扑检查，未 fetch、切换、清理、暂存、提交或推送。初始干净状态来自本轮终端输出；`environment-evidence.json` 是随后快照，包含本轮自建目录。

完整参考差异在 `reference-delta.txt`。Java 生产差异集中于 AiSseGatewayService、ChatStreamPersistenceService、MessageMetadataQuery、MessageProjectionMapper 和 application.yml；相关测试也变化。因此 SSE 最大时长、取消落库、usage/上下文压缩字段按当前 HEAD 冻结，不能从旧 SHA 推断。证据：`git diff --numstat REF HEAD -- apps/backend`。

## 本机环境（VERIFIED）

| 项目 | 观测 |
| --- | --- |
| Windows | Windows 11 专业版，10.0.26100，build 26100（Win32_OperatingSystem） |
| Node / npm / pnpm | v24.19.0 / 11.17.0 / 10.14.0 |
| TypeScript | PATH 无全局 tsc；frontend 已安装 5.4.5，hands/electron 已安装 5.9.3；未安装/升级 |
| Java / Maven | Temurin OpenJDK 21.0.11 / Maven 3.9.12；pom 编译目标仍是 17，Spring Boot 3.2.0 |
| Python | 全局与 N03 venv 的解释器观测均为 3.14.5 |
| PostgreSQL | 本地二进制 `postgres --version` = 15.19；服务端版本 UNKNOWN |
| Redis / Memurai | memurai.exe 文件版本 4.1.2.0；运行 Redis 协议版本 UNKNOWN，未连接 INFO |
| Electron | node_modules 元数据 45.1.0；本轮未启动 Electron |

软件证据在 `environment-evidence.json`，npm/pnpm/全局 tsc 的结果来自本轮终端版本命令；不是依赖兼容性测试。pom：{ev('apps/backend/pom.xml','<java.version>17</java.version>')}。

## N03 Home 与当前状态

扫描 `%LOCALAPPDATA%/ZhiyiNative` 下含 environment.json 的目录，发现 Home：`<LOCALAPPDATA>/ZhiyiNative/default-clean-20261106`；不是文档默认值 `default`。未读取/解密 credentials.dpapi。

`environment-evidence.json` 的 `{env['captured_at']}` 快照：environment format=`zhiyi-windows-persistent-v1`，portOffset=0。runtime-state 记录 8 个进程，但 psutil 确认全部 PID 已不存在；八个配置端口 loopback TCP connect 均失败，Get-NetTCPConnection 也未发现监听。因此 VERIFIED 当前观测为停栈/陈旧进程记录，不能凭状态文件声称 UP。实际启动命令、健康路径与所有权检查见原生运行链报告，当前进程健康 UNKNOWN。

对 environment.json、runtime-state.json 和最新日志文件保留 SHA-256。只保存日志名、字节数和 ERROR/WARN 数，不保存正文、完整 Workspace 路径或业务数据。共有 12 个日志会话目录；最新 java.log 含 ERROR 2 / WARN 6，不能由此推断当前故障根因或健康。历史启动回执不代替本轮启动验证。

## 安全边界与未执行事项

未运行业务服务 up/status/recover 命令（status 内部会连接依赖）；未连接或修改数据库；未执行 schema-only dump；未运行 mvn test、前端测试或原生生命周期测试。虽然 NativePostgres/NativeRedis 设计为随机端口临时实例，整个测试套件的文件删除、默认 URL、环境继承尚未逐一证明隔离，故本轮只审阅测试源码。详见模块报告与 `test-inventory.csv`。

## 产物与证据层级

所有写入限定本目录新建审计材料。八份报告和四份必需 CSV 外，增加源码哈希索引、Python 路由声明、身份触点、原生依赖、测试清单及安全环境快照。审计脚本只读源码、输出本目录；数据库 SQL 是未执行计划。机器清单是静态提取，UNKNOWN 字段保留原始表达式供复核，不能将它们当成运行合同证明。
''')
service_design={
'ChatService':('同步 Chat 编排、两段短事务、RAG/角色上下文','conversations/messages；TransactionTemplate 两次短事务，HTTP 位于事务外','客户端失败固定文本且 confidence=0；RAG/角色上下文失败继续原查询','请求重试会追加消息，非全局幂等','迁移 chat application；不复制 Python 生成/工具执行'),
'ChatStreamPersistenceService':('流前落 user、流后/取消落 assistant、reasoning/usage 捕获','conversations/messages；prepare/complete 各自 @Transactional','未完成/空响应/取消保留失败 metadata；capture.persisted 仅内存一次保护','非跨进程幂等；persisted 在实际 save 前置位，保存失败不能靠原 capture 重试','迁移 chat stream recorder；增加可恢复 attempt 唯一键设计与回滚测试'),
'AgentConversationPersistenceService':('Agent exchange 汇入共同会话历史','conversations/messages；persistExchange 单事务','空 owner/session/text 跳过；遇到其他 owner 跳过，不能合并','相同 exchange 重试可重复写，无持久幂等键','保留历史投影职责，调用者需另行确认；不重建 Runtime Store'),
'ConversationService':('按 owner/mode 列表、批量预览、标题、删除','conversations/messages；写方法事务；列表也有 @Transactional','按 owner 删除失败返回 false；updateTitle 无权为 not-found','读幂等；create 非幂等；删除多次结果需保留合同','conversation repository + application；内部无 owner 方法禁止变为公开端口'),
'RoleService':('自定义角色 CRUD 与配置验证','roles；create/update/delete 事务；update/delete roles cache 精确逐出','校验失败 BusinessException；更新删除允许 userId==null 分支','create 非幂等；更新相同值语义需合同测试','roles application；新 ActorContext 必须非空，不保留 null 绕过'),
'UserService':('用户资料查询更新；含密码创建验证','users；create/updatePassword/update/delete 事务','重复用户名/邮箱或找不到用户抛 IllegalArgumentException','查询幂等；创建非幂等；资料更新需验证 owner','保留 actor/profile repository；删除密码验证与登录创建流程'),
'UserProfileService':('聚合资料、会话数、角色使用次数与活跃度','经 UserService/ConversationService/RoleRepository 读；无独立事务注解','非法 role UUID 捕获；缺资料保持部分字段空值','只读派生结果；无独立 UserProfile 表','迁移 local profile read model；权威 owner 不从路径任意声明'),
'SearchService':('仅搜索 owner 的 conversations 中的 message','ConversationRepository + MessageRepository；PageRequest 0/200；无事务注解','没有会话返回空列表','只读幂等；结果上限 200、大小写不敏感必须冻结','迁移 search application/repository，必须保留 owner 限定'),
'RagService':('RAG query/upload/list/delete 的业务 fallback','仅 RagClient；无平台 DB/cache/事务','query 失败固定回答/空源/0；list 失败空列表；upload 包装异常；delete 异常吞掉','上游写操作幂等 UNKNOWN，不能自动重试 upload/delete','RAG adapter + projections；检索索引仍由 Python 所有'),
'KnowledgeGraphService':('构图、混合检索、推理和统计 fallback','KnowledgeGraphClient；无平台事务','PlatformAiClientException 由各方法转既有空结果/error Map','上游构图幂等 UNKNOWN；只读方法可重放需超时约束','保留薄适配器与 DTO，不在 TS 重建图谱引擎'),
'FileService':('上传、下载路径解析、删除和文件列表','uploadDir 本地文件系统；无 DB/cache/事务','大小限制；IO 异常或列表单条错误；Paths.get 路径边界需专项修订','上传生成 UUID 名非幂等；删除存在性合同需保留','files/storage adapter；显式根路径约束、重解析点与失败补偿'),
'RecommendationService':('关键词/场景规则推荐，去重最多 5 条','无 DB/cache/Python/事务','输入缺失使用默认推荐','同输入纯计算，最多5条','迁移轻量 application 纯函数；并非模型或策略执行器'),
'LoginSessionService':('创建、撤销、检查 PostgreSQL 登录会话','iam_login_sessions + JwtProperties；create/revoke 事务','会话缺失/撤销/过期走失效判断','登录创建新 sid；撤销幂等性由测试冻结至退役','退役用户 session 服务；不删除历史表作为首步'),
'RoleSwitchOptimizer':('角色上下文读取与缓存','RoleService；Spring roles Cacheable，TTL 配置 1h','缓存异常由 CacheConfig 降级 DB；无新独立缓存权威','读幂等，但 Java default typing 与 TS 不兼容','并入 roles read/cache adapter；新 namespace，保留失效与降级'),
'RoleValidationService':('角色配置校验','纯校验，无事务/DB/Python','返回 validation errors/warnings','同输入确定性需用例冻结','并入 roles domain validation'),
'ChatQualityService':('历史消息质量评分','纯计算，无 DB/缓存/Python/事务','按输入评分，边界值见 QualityScore 测试','读计算','并入 chat analytics，若产品退役需单独批准'),
'RoleFusionService':('融合和权重客户端编排','RoleFusionClient；无平台事务','失败返回 error Map，不能统一改成抛 5xx 而无版本决策','上游幂等 UNKNOWN','保留 legacy AI capability adapter；不合入 AgentOS 调度'),
'KylinOSIntegrationService':('银河麒麟 OS 检测/系统信息等历史接口','System/Runtime.exec Linux 命令；无 DB/cache','Windows 上探测失败捕获；系统信息含 javaVersion','读取为主；系统命令副作用必须逐方法审查','目标 Windows-only：建议退役/替换明确的 Windows diagnostics，需 API 消费决策'),
'MetricsService':('请求/错误/时延指标','MeterRegistry；无业务 DB/事务','采集行为与 MeterRegistry 实现相关','计数副作用，非业务幂等','改为 observability port，保留指标意义与低基数'),
'AlertService':('阈值巡检与内存告警历史','MetricsService + 进程内 Map；无持久 DB/事务','巡检逐项 catch；重启丢失历史','检查可能追加告警，非幂等','observability application；内存语义要显式冻结或另案调整')}
service_rows=[]
for d in deps:
 if d['layer']!='service':continue
 desc,db,fall,idem,target=service_design[d['symbol']]
 service_rows.append([f"{d['symbol']}<br>`{d['file']}:{d['line']}`",desc,db,fall,idem,target])
layercounts=collections.Counter(d['layer'] for d in deps)
controllers=[]
for name in sorted(set(r['controller'] for r in routes)):
 rs=[r for r in routes if r['controller']==name]
 controllers.append([name,f"`{rs[0]['file']}:{rs[0]['line']}`",len(rs),'; '.join(sorted(set(r['dependencies'] for r in rs)))])
projection=collections.Counter(d['file'].split('/projection/')[1].split('/')[0] for d in deps if '/projection/' in d['file'])
testtable=table(['测试源码','分类（可多选）','声明数','迁移处置'],[[f"`{t['file']}`",t['categories'],t['test_annotations'],t['decision']] for t in tests])
report('PR-TS-00-Java后端模块清单',f'''
## 范围与计数（VERIFIED 静态）

生产 Java 文件 {stats['java_sources']}，{stats['java_lines']} 行；Controller {stats['controllers']}；service 包 {stats['service_package_files']} 个类；全目录 @Service {stats['spring_service_annotations']}（另三项在 gateway）；projection 包 {stats['projection_files']} 个文件，其中 Mapper {stats['projection_mappers']}、其余 DTO 等 119。测试目录 115 个 Java 文件，542 个 `@Test/@ParameterizedTest/@RepeatedTest/@TestFactory` 声明；包括基座/工具文件，**不是 542 次执行结果**。迁移 SQL 13 份。

`java-dependency-inventory.csv` 覆盖全部 299 文件，含行号、SHA-256、内部 imports、字段、事务、缓存、身份和测试引用。`source-evidence-index.csv` 是补充定位索引。扫描包括 package-info.java，未把它计作类。依赖字段提取可能包含嵌套 DTO 字段；导入依赖不等于运行调用。

{table(['顶级包','Java文件数'],sorted(layercounts.items()))}

## Controller 全量范围

{table(['Controller','首个路由证据','method/path行数','注入依赖'],controllers)}

## Service 全量逐项处置

以下职责/事务/fallback 为 VERIFIED 源码观察；目标拆分与幂等性判断为 INFERRED。每个 Service 的具体依赖、事务行号、测试引用见 CSV；没有注解不代表下游 repository 没有自己的事务。

{table(['类与证据','业务职责','持久化/事务','异常与Fallback','幂等性判断','TS处置'],service_rows)}

当前用户路径：Controller 的 AuthenticatedUser → Service(userId)；ChatStreamPersistenceService 自行取得 currentUserId；网关经 TrustedUserContextForwarder。UserProfileService/SearchService 依赖参数身份而不是自行认证，必须在新 application 层注入 LocalIdentity。角色读取缓存也不能成为 owner 权威。证据：{je('service/ChatStreamPersistenceService.java','AuthenticatedUser.currentUserId()')}；{je('service/RoleService.java','userId == null ||')}。

## Projection 全量分类

{table(['Projection域','文件数'],sorted(projection.items()))}

保留投影的闭合 DTO、字段允许集、缺失字段/空值、枚举、排序和 wire 命名；不把 Map 原样暴露给 renderer，不共享数据库实体。Architecture Guard 中 MissionProjectionArchitectureTest / QueryProjectionArchitectureTest / StaticQueryRouteArchitectureTest / ArchitectureGuardTest 均需转为 TS 依赖规则与序列化测试。实现可合并 mapper 模板，不能按 148 个文件机械翻译。

## 数据、传输和框架边界

实体：BaseEntity、User、Role、Conversation、Message、LoginSession；repository：User、Role、Conversation、Message、LoginSession 五个接口。Workspace Grant 并非 Java JPA 实体，由 Python WorkspaceAuthority 写 PostgreSQL。所有生产 Java 的精确清单在 dependency CSV，非 Service 的 client/gateway/filter/config/security/observability/exception 等也在范围内。

Spring MVC/Tomcat 是入站 API；WebClient/Reactor 为出站与 SSE。移除 Spring 不意味着复制 Python lifecycle；AgentOsClient 是 application 的端口，AgentOsGatewayService 才是传输实现。证据：{je('gateway/AgentOsGatewayService.java','implements AgentOsClient')}。

## 测试冻结与执行限制

全部测试仅审源码，未运行 mvn test。`test-inventory.csv` 含 profiles、潜在删除/进程调用行号。NativePostgres.start 创建临时 cluster/随机端口；NativeRedis.start 创建临时配置/随机端口，但全套调用链与覆盖配置没有完成隔离证明，因此不借机启动临时数据库。{ev('apps/backend/src/test/java/com/kinlin/ai/integration/NativePostgres.java','Files.createTempDirectory')}；{ev('apps/backend/src/test/java/com/kinlin/ai/integration/NativeRedis.java','Files.createTempDirectory')}。

CI：{ev('.github/workflows/backend-ci.yml','Run backend test gate')} 配置 Ubuntu 24.04/JDK17，安装本机 PostgreSQL15/Redis，mvn test 后 package -DskipTests；本轮未触发 CI。H2 test 的 Flyway=false/create-drop 不能证明 PostgreSQL 迁移成功。性能标签默认排除，不能将静态测试总数当 required gate 的执行数。

## 测试逐文件迁移矩阵

分类为静态词法辅助（多分类），不假定每类测试都已验证对应功能。删除旧登录合同只删除 JWT/session 专属断言；其中共用的 owner/header/SSE/撤销执行许可断言应重写保留。fixture/base 文件标记改写表示保留其隔离能力，不表示有测试方法。

{testtable}
''')
gaprows=[[f"`{f['file']}:{f['line']}`",f['method'],f['normalized_path'],'VERIFIED 前端存在；Java 路由缺口，运行未测'] for f in front if f['classification']=='FRONTEND_ONLY']
report('PR-TS-00-HTTP接口与前端依赖矩阵',f'''
## 接口统计口径与有效性

VERIFIED 源码：141 个方法级 Mapping 声明，展开为 145 个 method/path 行：140 条显式路由 + 5 条 `/ai/**` 方法族；另有 53 行具 `/api` 兼容别名，不能把别名计成新业务。25 个 Controller 全部在 route-inventory.csv 中。GET 的框架 HEAD、CORS OPTIONS、Actuator/Swagger 自动注册不计入这 145 行。

`route-inventory.csv` 每行含方法、完整路径、别名、Controller/方法/行、请求签名、响应类型、状态行为和源表达式、依赖、Python path 表达式、认证、SSE/Multipart/Binary、前端与测试引用。Java 实体不作为目标 DTO。响应状态字段对无法静态确定的分支标记 dynamic/UNKNOWN；全局异常处理、Security/RateLimit 前置失败也适用，不凭默认200假定所有结果成功。

当前没有服务运行，**确认的只是源码映射，运行注册/可访问性为 BLOCKED**。CSV 的 CONFIRMED_SOURCE_MAPPING 特指这个层级。

## `/api` 规范化与代理

{je('filter/LocalApiPathFilter.java','LEGACY_ROOTS')}：仅集合内 root 去 `/api` 前缀，发生在 Security 之前，并重建 ServletRequestPathUtils 缓存。保留原生 `/api/agentos/v2`、`/api/knowledge-graph`、`/api/role-fusion` 等路径。不能统一给所有路由加/去 api，也不能把 `/api/ai/*` 当另一套身份规则。

{je('controller/AiServiceProxyController.java','public ResponseEntity<byte[]> proxy')}：通用代理承接 GET/POST/PUT/PATCH/DELETE，显式 `/ai/chat/text/stream` 与 `/ai/test/sse` 优先。下游 `/ai/foo` 存在不保证 Python 有该路由；上游条件加载和认证也可能拒绝。Python 上游的 201 个路由声明在 python-route-inventory.csv，包含 UNKNOWN 未挂载与条件挂载；**不能把 201 当确认生效路由数**。`/rag`、`/api/static`、`/performance` 不自动属于 `/ai/**`；WebSocket upgrade 不由 HTTP 字节代理实现。

## 五种路由状态

| 状态 | 本轮判定 |
| --- | --- |
| 确认源码生效候选 | 140 显式 method/path；运行验证 BLOCKED |
| 通用代理承载 | 5方法族；前端18个已展开调用项落入该族，Python 实际挂载需运行证据 |
| 前端调用但无 Java 对应 | 下表5项；其中2项有 Python 实现，仍不能跨过 Java 直接称可用 |
| 已废弃 | 本轮未发现 Controller 上显式 @Deprecated 的已退役路由；Login/Register/Logout/Verify/改密码属于计划退役，当前仍有效源码，不能提前删除 |
| 不明确 | 实时ASR WebSocket传输；动态URL/外部资源；Actuator/Swagger运行注册；可选Python路由，均明确保留 UNKNOWN/BLOCKED |

{table(['前端证据','方法','路径','结论'],gaprows)}

context-packs 与 node enabled 在 Python 已有实现：{ev('apps/agent/app/api/agentos_v2.py','@router.get("/runs/{run_id}/context-packs")')}、{ev('apps/agent/app/api/agentos_v2.py','@router.post("/nodes/{node_id}/enabled")')}。迁移前必须决定补齐正式 Java/TS gateway 合同还是移除前端入口；本轮不改。RAG 下载还缺 bearer 注入，但目标无登录也不能由此自动补齐路由。两条 chat history/summary 的消费是否仍挂在活动UI是 UNKNOWN，不擅自判废弃。

## Frontend / Electron 全量调用关系

frontend-callsite-inventory.csv 包含 {stats['frontend_callsites']} 行（C2 的一个调用展开为五种 action，故不是函数数）；125 项对应显式路由、18 项通用代理；5项缺口、1项ASR upgrade、1项内部terminal、1项外部/Artifact fetch、1项动态helper已追至Settings调用者。递归扫描 src，包括 stores/chat、companion、ModelRuntimeControls、NativeWorkspacePicker、runtimeEvents 和 views，未只看 services/api。

agentosRequest base=`apiUrl('/api/agentos/v2')`；普通 request/多份 axios base=`apiUrl('/api')`；直接 fetch apiUrl 不补 `/api`；backendUrl 专门补 `/api`。runPath 与 revisionPath 按源码辅助展开；路径段 encodeURIComponent、查询 params、AbortSignal 均须保留。来源：{ev('apps/frontend/src/platform/api.ts','export const apiUrl')}；{ev('apps/frontend/src/services/api/agentos/client.ts','baseURL:')}；{ev('apps/frontend/src/services/api/agentos/paths.ts','runPath')}。

独立 axios 实例：file、search、knowledgeGraph、roleFusion、federatedModel、agentos/client，以及 utils/request。前五者自行注入 bearer，不能只删统一拦截器。HTTP client、SSE fetch、ASR WebSocket、terminal内部连接是不同合同；terminal bearer 是进程服务认证，不是用户 JWT，不在退役清单。

## 登录退役触点与目标

identity-touchpoint-inventory.csv 记录224个源码触点，每项含路径/行号、类型、目标和可找到的测试；逐行匹配只能定位，不等于224个独立行为。源码范围包括全部 router/store/service/utils/platform/electron 和 Electron Main/Preload。下表说明责任，CSV 提供逐点落地位置。

{table(['文件/符号','调用关系/依赖','目标行为与测试'],[
[ev('apps/frontend/src/router/index.ts','requiresAuth'),'beforeEach → ensureDesktopSession / authApi.verify；meta.requiresAuth','去登录跳转；身份未就绪显示本机身份诊断；router测试改写'],
[ev('apps/frontend/src/platform/electron/session.ts','ensureDesktopSession'),'router/requestAuth → bridge.session.ensure → Main sessionBootstrap','退役token存储/恢复；替换local identity readiness；session相关测试改写'],
[ev('apps/frontend/src/utils/requestAuth.ts','attachAuthToken'),'request和agentosRequest共享；handleUnauthorizedError清状态/重试','移除JWT注入与401登录跳转；保持错误/取消处理测试'],
[ev('apps/frontend/src/stores/user.ts','localStorage'),'token:userId缓存身份；资料API依赖','以backend稳定actor+generation作缓存边界'],
[ev('apps/frontend/src/stores/chat.ts','Authorization'),'Chat模型查询、stream fetch；companion另有adapter','移除用户token，保留SSE事件/取消/历史'],
[ev('apps/frontend/src/views/SettingsView.vue','async function serverFetch'),'profiles配置的独立fetch helper','移除token；保留本地操作准入和服务侧配置密钥边界'],
[ev('apps/desktop/electron/src/main.ts','bootstrapLocalSession'),'sessionBootstrap IPC → POST /auth/login；发行启动器注入账号','删除登录bootstrap；保留API Origin IPC与Main sender guard'],
[ev('apps/desktop/electron/src/preload.ts','session:'),'bridge.session.ensure → IPC.sessionBootstrap；frontend bridge.ts手工同构','同步更新两端类型与Main测试；保留通道白名单'],
[ev('apps/desktop/electron/src/main.ts','const authorized ='),'sender webContents id + mainFrame → guard(event)','KEEP；无登录不移除IPC发送者验证、URL/路径/参数校验']])}

LoginView 的登录/注册表单、auth.ts 验证缓存与logout、user/password入口、AuthenticatedAppShell登出、workflowRuns token前置检查都要逐点移除。源码行与测试引用以 identity-touchpoint CSV / source-evidence-index 为准；未发现对应测试的项明确待补，不伪造已覆盖。

## 状态码与特殊行为冻结

GlobalExceptionHandler：415媒体类型、413超大文件、422缺file、400校验/业务/JSON、404资源/接口；Security未认证401；RateLimit429。Gateway的4xx、409冲突、503断连、504通用代理超时及AgentOS超时503不可被一个统一error handler意外抹平。SSE建连前HTTP错误与流中error事件必须区分。依据：{je('exception/GlobalExceptionHandler.java','handleMissingMultipartPart')}；{je('interceptor/RateLimitInterceptor.java','TOO_MANY_REQUESTS')}。

Multipart需保留file字段、filename/content-type、10MB/11MB限额；Binary需保留status/content-type/content-disposition且不得经过JSON DTO序列化。显式SSE保留event/id/retry/data顺序、Last-Event-ID语义需单独核验（UNKNOWN，不能自动承诺重放）。
''')
report('PR-TS-00-数据库与身份迁移审计',f'''
## 数据库实测结论：BLOCKED

真实 Home 的 PostgreSQL 15432 未监听，记录PID不存在。未启动数据库，未解密凭据，未运行 SELECT/pg_dump/迁移。`flyway_schema_history` 的实际版本、校验和、成功状态、实际schema、用户数、每用户Conversation/Role数、Grant/Tenant归属、selected/revoked与孤儿数量全部 **UNKNOWN/BLOCKED**。不能报告“真实库已V13”，不能以临时库、SQL文件或旧java.log替代实测。

`database-readonly-plan.sql` 为后续补证的只读事务查询计划，**本轮未执行**。只输出结构、版本、匿名U/T编号、汇总计数；不输出用户UUID、私有对话、Workspace路径或JSON正文。安全连接需在已有真实服务运行且凭据取得方式获授权后单独执行；认证失败时停止，不自动重置角色/密码。

## Flyway SQL 全量审计（VERIFIED 源码）

{table(['版本','文件/行数','涉及表','变更位置（源码）'],[[m['version'],f"`{m['file']}` ({m['lines']}行)",m['tables'],m['operations']] for m in migs])}

V1建立 users/roles/conversations/messages；V2索引；V3兼容密码列；V4反馈表；V5 legacy title/file_url/stable_key与unique；V6内置角色upsert；V7 workspace_mode数据归一；V8 avatar；V9预览索引；V10删除内置角色；V11 session权威；V12 WorkspaceAuthority；V13删除反馈。所有SQL均读取并记录SHA-256；没有执行其DML/DDL。迁移不可逆操作（V10/V13）不能通过回滚应用二进制自动恢复。

## 结构与关系（源码事实不等于真实库约束）

| 表 | 源码结构/约束 | 迁移关注 |
| --- | --- | --- |
| users | UUID主键；username/email唯一；password_hash；无时区TIMESTAMP | 保留id承接旧归属；密码字段退役不等于删除所有者 |
| roles | UUID主键；user_id可空；role_type；stable_key unique；3个JSONB配置 | 内置/自定义owner差异；不能把null自动归为本机actor |
| conversations | UUID主键；user_id/role_id可空；context_id全局unique；workspace_mode/title | context与actor不可冲突合并；列表按mode/更新时间 |
| messages | conversation_id非空；metadata JSONB；role/type/content/file_url | 不输出正文；按conversation保存关系，事务一致性 |
| iam_login_sessions | sid UUID；user_id REFERENCES users；过期/撤销timestamp | 无登录后不读写签发；先保留归档以便回滚，不充当LocalIdentity真源 |
| local_workspace_authorizations | string user/tenant；workspace_id PK；grant_id unique；root_identity/canonical_root；TIMESTAMPTZ | selected且非revoked的(user,tenant)部分unique；无users外键 |
| flyway_schema_history | Flyway运行时创建维护 | 只能真实SELECT确定，不由SQL文件数推断 |

证据：{ev('apps/backend/src/main/resources/db/migration/V1__init_schema.sql','CREATE TABLE conversations')}；{ev('apps/backend/src/main/resources/db/migration/V11__create_iam_login_sessions.sql','REFERENCES users(id)')}；{ev('apps/backend/src/main/resources/db/migration/V12__local_workspace_authorizations.sql','CREATE UNIQUE INDEX')}。

V1对 roles.user_id/conversations.user_id/conversations.role_id/messages.conversation_id 没有声明外键；静态后续SQL未找到补齐这些关系外键的语句。故“JPA能关联”不等于不存在孤儿。V10删除内置角色可能留下历史role_id引用，真实数量 UNKNOWN。不得在迁移时自动补约束或清理这些数据。

`UserProfile` 是UserProfileService内嵌聚合对象，没有发现独立UserProfile JPA表。应迁移其userId派生关系，不能虚构一张待搬迁的profile表。JSONB必须测试对象/数组/null、Unicode和数值；uuid保持字符串；TIMESTAMP无时区不可由JS Date默认套本机时区，TIMESTAMPTZ需明确UTC偏移，逐字段冻结序列化。bigint计数转换需防精度丢失。

## LocalIdentityProvider 设计（INFERRED，未实施）

输入仅受保护的N03 Home身份配置和数据库映射；输出不可变 `ActorContext {{actorId, tenantId?, subject, role, identityGeneration}}`。actorId用UUID以兼容现有平台表；subject/role保持Python可信头非空，不从renderer body/header指定。不生成JWT、不读用户session、不需要密码。身份首次解析失败、配置丢失或多用户未决均fail closed，不能每次启动生成新actor或选“第一个用户”。

现有身份链：AuthenticatedUserContext → TrustedUserContextForwarder → Python InternalServiceAuthMiddleware → current_trusted_user → `_trusted_run_input` / WorkspaceAuthority.owner。证据：{je('gateway/TrustedUserContextForwarder.java','public void apply')}；{ev('apps/agent/app/api/agentos_v2.py','"authenticatedUserId": actor.user_id')}；{ev('apps/agent/app/execution/workspace_authority.py','def owner(actor)')}。

Tenant需区分缺失与显式值。WorkspaceAuthority.owner将空tenant归为 `__unscoped__`，但Run所有权检查保存/比较的是原始可空tenant；不要全局把header改为 `__unscoped__` 而改变历史Run比较结果。LocalIdentity必须同时冻结wire tenant值与Grant查表归一规则。

| 真库场景 | 未来迁移策略 | 阻断/回滚 |
| --- | --- | --- |
| 0用户 | 先验证没有Conversation/customRole/Grant/SQLite Run遗留owner；全空才在受控迁移事务中建立UUID actor与兼容owner记录 | 有遗留owner即BLOCKED；初始化前后冷备份；本轮不创建 |
| 1用户 | 仅在PG与SQLite/Artifact owner/tenant核对一致后，映射到原users.id作为稳定actor；不批量改历史数据 | Grant或Run有额外owner/tenant则转人工；保持原grant epoch与所有id |
| 多用户 | 输出匿名归属统计，人工选择保留隔离的多本机身份方案、指定主actor并保留其他owner档案、或另案迁移 | **不自动合并、不取首行、不重写Run owner**；需要书面决策、冲突映射、备份和验收 |

Actor映射可先在受限Home配置中保存版本、actor UUID、旧owner映射引用与database identity；映射写入/备份采用原子替换和校验，不接受请求指定路径。是否需要额外actor表留给后续显式schema PR；本轮无新schema。失去配置不能静默重建，应从受信备份恢复映射。

## Workspace Grant / Run 历史不变量

{ev('apps/agent/app/execution/workspace_authority.py','def freeze')} 清掉客户端workspaceBinding后由权威current生成快照；{ev('apps/agent/app/execution/workspace_authority.py','def _resolve')} 校验revoked、grantId、owner、tenant、resource、root以及目录inode身份。select遇已撤销row会生成新grant_id，使旧Run永远不能借新授权复活。TS保留Python权威，不直接写Grant表、不生成伪Grant、不把所有历史owner改成本机新UUID。

canonical_directory解析真实目录并接受当前Windows用户可访问目录，这不是OS沙箱。无登录不扩大可选目录、不绕过批准、不把旧Run绑定到当前选择。恢复过程中必须同时恢复PG权威表、Hands JSON投影、SQLite Run快照、Artifact和同一身份映射；投影不充当第二权威。

## 真库补证清单与快照条件

执行read-only plan前检查server身份/数据库名称/readonly配置；BEGIN READ ONLY内完成schema history/列/索引/外键/unique/JSONB/匿名owner/grant/孤儿/跨owner角色/多selected/多owner根统计，ROLLBACK结束。先查真实表存在性再分段执行，旧版缺表直接记录版本阻断，不能创建表补绿。

可选 `pg_dump --schema-only --no-owner --no-privileges` 仅在确认已有只读连接与安全输出目录后写系统临时目录并记SHA-256；不进Git、不含业务数据、命令行不放密码。本轮条件不满足，dump为BLOCKED。PG统计仍不足以证明SQLite/Artifact历史owner一致，后者需独立只读匿名聚合核对，不能查询或导出正文。
''')
report('PR-TS-00-AgentOS与Python网关审计',f'''
## 权威边界（VERIFIED 源码 / INFERRED 迁移约束）

Java 当前负责平台数据与HTTP安全/投影/传输，不是计划器或执行器。目标TS只能替换该平台边界。Python AgentOS Core保留Mission/Run/Review、生命周期、调度、Checkpoint、Trace、Provenance、Permit、frozen workspace binding权威；Hands保留执行/HMAC/ledger/文件与shell授权执行；terminal-host是用户终端服务，不能变成模型执行器。

{ev('apps/agent/app/main.py','runtime = build_default_runtime()')}、{ev('apps/agent/app/api/agentos_v2.py','create_c2_router(runtime, coordinator)')}、{je('gateway/AgentOsGatewayService.java','implements AgentOsClient')} 是现有依赖路径。apps/agentOS为Core实现，apps/agent为HTTP装配和执行接线；本轮均不重写。

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

WebClientConfig共享filter统一service auth、trace和trusted identity；SSE显式捕获上下文以免切线程丢失。证据：{je('config/WebClientConfig.java','authentication.apply(headers)')}；{je('gateway/AiSseGatewayService.java','userContextForwarder.requireCurrent()')}。

header名称：`X-Internal-Service-Token`；`X-Authenticated-User-Id/Subject/Role/Tenant-Id`；`X-Trace-Id`（精确大小写不敏感实现见AiGatewayHeaders/TraceContext）。这些是字段名，报告不包含值。Python要求恰好一个有效服务认证header并constant-time比较，再要求非空user/subject/role；公共health路径除外。证据：{ev('apps/agent/app/security/internal_auth.py','hmac.compare_digest')}、{ev('apps/agent/app/security/internal_auth.py','def _trusted_identity')}。不能取消登录后开放Python业务直连。

## Error Envelope / TraceId / 超时

AgentOS JSON：2xx解析后附内部HTTP状态元数据；4xx保留稳定code/message/requestId（清理换行、截300字符），格式不符变AGENTOS_REQUEST_REJECTED；上游5xx→502 AGENTOS_UPSTREAM_ERROR；连接/超时等异常当前统一503 AGENTOS_UPSTREAM_UNAVAILABLE。typed成功反序列化失败→502 AGENTOS_CONTRACT_INVALID；launch409特定冲突走对账。证据：{je('gateway/AgentOsGatewayService.java','private Mono<Map<String, Object>> mapResponse')}、{je('gateway/AgentOsGatewayService.java','private <T extends AgentOsApiResponse> Mono<AgentOsClient.TypedResponse<T>> typedResponse')}。

普通proxy：连接失败503、超时504、其他invalid502；path无效400。PlatformAiTransport向application交REJECTED/UPSTREAM_ERROR/TIMEOUT/UNAVAILABLE/INVALID_RESPONSE分类。不能强行统一成一种error envelope而破坏既有前端处理。TraceId从服务端过滤/合法客户端trace生成并随请求传递；不把自由header复制到上游，不把内部HTTP状态元数据泄漏到业务DTO。

配置默认值来自application.yml：connect 15s、platform command/read 240s、health 3s；AgentOS普通query 5s，missions列表240s，mission创建15s，其余post240s；binary/multipart为progress 5s。SSE idle240s，max0表示不限制总长。环境可覆盖，以上不等于当前运行有效值（服务未运行）。

## SSE / Abort / 持久化

SSE建连前可返回JSON HTTP错误；建连后只能发送终止event，不能第二次写HTTP status。event/id/retry/data逐条转发、顺序保持、UTF-8分片与多行data必须测试；HTTP close/disconnect传播AbortController到Python，释放reader、timer和并发配额。取消HTTP流不能由TS擅自等价为取消Run，正式Run取消仍调用Python命令端口。

现实现sid门：openPost/openGet拒绝缺sid；周期3s复核、查询1s、lease5s，失效发auth.invalidated并取消订阅。该**登录合同退役**；替换为LocalIdentity ready/进程关闭与必要执行授权校验，不保留假sid。Grant/Permit撤销仍由Python在执行处检查。{je('gateway/AiSseGatewayService.java','userContext.sid() == null')}、{je('gateway/AiSseGatewayService.java','Flux<ServerSentEvent<String>> withSessionGate')}。

ChatStreamPersistenceService.prepare先事务提交user；流完成/取消再单独提交assistant。断流失败metadata、reasoning上限200000字符、usage/model/source/tool字段均需保留当前基线。capture.persisted为进程内布尔，不保证数据库commit成功、崩溃恢复或客户端重试幂等；目标需定义stream attempt持久幂等/恢复方案，不能长事务跨模型流。{je('service/ChatStreamPersistenceService.java','capture.persisted = true')}、{je('controller/AiServiceProxyController.java','SignalType.CANCEL')}。

## 上传下载 / 路径 / 资源边界

multipart重建file资源、filename和content-type；binary保留content-type/disposition，5xx屏蔽上游正文。AgentOsPaths.segment使用encodePathSegment，query过滤null/blank并编码value；TS不能用整段URI编码，也不能把query当未校验字符串拼入。proxy拒绝非/ai/、双斜杠、..、反斜杠和控制字符；新实现须覆盖百分号编码/双解码，不能把原始request.url当外部URL。

资源现状：WebClient内存codec上限50MB；proxy request.readAllBytes与binary byte[]是缓冲路径；入站multipart10MB/11MB；RateLimit默认300/min，错误时放行；缓存错误降级PG。这些是VERIFIED实现，不是合理容量承诺。目标要定义全局/actor并发流、body/max-event-size、队列预算、上传下载背压与drain截止时间；阈值实测前为UNKNOWN，不编造吞吐。

## 尚缺证据

BLOCKED运行HTTP/SSE/取消传播；UNKNOWN Last-Event-ID/事件重放语义、WebSocket代理、全部可选Python路由是否实际加载、资源压力边界。python-route-inventory.csv为AST静态声明，main.py有try/except ImportError和feature gate，不能以装饰器数量认定实际注册成功。下一阶段必须用本机隔离fixture上游做字节/事件差分，再做真实服务授权E2E。
''')
native_rows=[]
for p,needle,contract in [
('ops/scripts/infra/windows/native/persistent_runtime.py','def java_environment','现有DB/Redis/JWT/内部auth/CORS环境映射；TS只退役用户JWT部分'),
('ops/scripts/infra/windows/native/persistent_runtime.py',"java = start('java'",'java -jar → 平台backend描述符 node dist/main.js'),
('ops/scripts/infra/windows/native/persistent_runtime.py','def prepare_workspace_grants','PG权威表存在后投影；禁止TS另建授权真源'),
('ops/scripts/infra/windows/native/persistent_runtime.py','def down','显式服务顺序停机；保留创建时间/用户/可执行文件身份检查'),
('ops/scripts/infra/windows/native/persistent_runtime.py','def backup','停栈、全冷备、路径/哈希/reparse检查'),
('ops/scripts/infra/windows/native/persistent_runtime.py','def restore','原Home/PG版本/DPAPI检查、保留pre-restore'),
('ops/scripts/release/product_runtime.py','def ensure_local_account','产品自动注册/登录与账户凭据持久化→LocalIdentity准备'),
('ops/scripts/release/product_runtime.py','java = start_service','发行版bundled JRE/JAR→bundled Node24和dist'),
('ops/scripts/release/product_runtime.py','def occupied_ports','产品端口占用报错；不能继承开发takeover杀进程'),
('ops/scripts/release/assemble_portable.py','def build_jre','jlink/JRE组装退役；检查Node24二进制签名/hash与许可证'),
('ops/scripts/release/assemble_portable.py','def copy_backend_jar','JAR拷贝退役；dist+生产依赖+配置schema+版本manifest'),
('.github/workflows/backend-ci.yml','Package production jar','Maven/JDK gate在等价TS gate通过和最终切换前保留')]:native_rows.append([ev(p,needle),contract])
report('PR-TS-00-Windows原生运行链审计',f'''
## 当前链（静态VERIFIED；运行BLOCKED）

N03 Home与所有服务观测见环境报告。端口组postgres15432 / redis16379 / ai18761 / host18765 / java18080 / frontend15200 / terminal18766 / debug19222，统一portOffset。不能把静态默认当运行监听；本轮均未监听。native-dependency-inventory.csv记录524处源码依赖引用（不是524个缺陷）。

{table(['源码证据','职责和迁移点'],native_rows)}

## N03 开发启动

persistent_runtime.up核对Home/普通用户/非reparse、锁/陈旧进程/端口；PG与Redis准备完成后启动Java和Vite；Python native_startup预加载只读定义，release-file/nonce/launcher PID/creation-time门约束其正式装配。SQLite schema检查与PG权威表可用后的Grant准备并行，join后才放行AI；terminal、Hands按依赖就绪；最终AI/Java/frontend健康门通过才打开Electron。参考：{ev('ops/scripts/infra/windows/native/persistent_runtime.py','with ThreadPoolExecutor(max_workers=2')}、{ev('ops/scripts/infra/windows/native/persistent_runtime.py','--owner-created')}。

Java命令为PATH java -jar backendJar，Vite是node vite.js --mode electron，AI为venv python -m app.native_startup，Hands使用现有tsx service-main.ts路径，terminal为node src/main.mjs，Electron通过desktop_shell描述符启动。实际cwd/env参数以函数源码为准，敏感env不复制到报告；运行进程当前不存在，因此没有本轮实际cmdline可核实。

健康门：Java `/actuator/health/readiness`，AI `/health/ready`，Vite后端代理readiness；PG通过SQL SELECT1，Redis ping，Hands/terminal按自身检查。不要删除Actuator路径后忘记更新supervisor；可先由TS提供兼容readiness和live/ready路径，等描述符切换再明确退役别名。

## 产品发行链

assemble_portable组装Python/JRE/Node/PG/Memurai、Java JAR、Hands及Electron renderer壳；build_jre用jlink，包校验与version manifest仍列JRE/JAR。product_runtime使用包内解释器；AI直接uvicorn单worker，Java用bundled java -jar。产品无Vite/CDP，桌面进程存活+窗口出现作为就绪；ensure_local_account注册/登录后Main再bootstrap会话。产品端口被占用仅拒绝，不杀用户程序。

开发stack现有takeover与产品fail-on-occupied是已存在差异，不能把其整个生命周期实现互换。TS迁移需共用一个ServiceSpec/进程身份/备份/停止合同，以profile显式选择开发热更新与发行静态资源、端口冲突策略；产品拒绝占用的策略必须保留。开发是否继续takeover由后续明确决策，不以新增Node后端为由扩大杀进程范围。

## JVM/Maven/JRE退役闭包

变更范围不止一行java.exe：persistent ports键/java_environment/backendJar、product PATH/required paths、assemble build_jre/copy_backend_jar/--jar/manifest/包自检、CI JDK/Maven/test/package、健康脚本、状态回执/停止顺序和相关测试均须同步。`native-dependency-inventory.csv` 可按java_jar筛选；只删apps/backend会让现有Windows入口直接失败。

Node24编译产物入口设计为固定包内 `runtime/node/node.exe apps/backend-ts/dist/main.js`（仅设计路径，本轮未创建backend-ts）。开发也运行dist同一入口，由单独构建watch更新产物；不以tsx/watch进程替代正式服务所有者。进程记录从java迁移到backend，legacy记录只做有版本的兼容读取，必须校验PID+创建时间+可执行身份后才能停机，不能只按端口/PID终止。

## 数据/恢复约束

保持PG cluster与受限应用角色、Redis DB0缓存/DB1协调/DB2 provider state、Python SQLite/Checkpoint、Artifact、uploads、环境和DPAPI不变；用户JWT字段最终退役但内部token/HMAC/数据库凭据不能轮换或删除。产品内存储Redis授权限制未进行运行核验，不把Memurai开发版当已验证无限期发行方案。

backup要求所有受管业务进程停止、PG/Redis正常退出，sqlite句柄/OS锁释放后做完整冷拷贝；禁跟reparse，逐文件哈希。restore核对同Home/PG版本和DPAPI后保留pre-restore，再恢复数据。TS新增LocalIdentity映射与版本化schema状态需加入同一冷备清单；恢复不能只还原PG遗漏Artifact/SQLite/Grant epoch。依据：{ev('ops/scripts/infra/windows/native/persistent_runtime.py','def require_stopped')}、{ev('ops/scripts/infra/windows/native/persistent_runtime.py','previous = home.with_name')}。

## Node graceful shutdown 与验收

Windows控制台/桌面关闭、supervisor协议、SIGINT/SIGTERM可达性要实际测试；不能假定Windows会像Linux一样传SIGTERM。先拒绝新请求、ready=false、停止接收新流，给在途流bounded drain；截止时Abort上游、执行已定义的Chat失败落库，再关PG/Redis连接，最后报告退出。supervisor只在正常退出超时后按已验证身份回收。停止顺序保持Desktop→Frontend→AI→Host→Terminal→Backend→Redis→PostgreSQL；调整应用层drain需与Python可用窗口协调，不能仅改名称。

验收矩阵：冷启动、重复up拒绝、端口冲突、PID复用拒绝、部分启动失败回收、关闭中SSE、PG未就绪、AI失败、Hands失败、同Home恢复、冷备/损坏hash/旧身份映射恢复。现有 test_persistent_startup/test_native_stop/test_native_ai_preload/test_desktop_open/test_desktop_shell/test_terminal_service 属合同基线；本轮未运行，不宣称已通过。运行服务与发行包实测均BLOCKED。
''')
report('PR-TS-00-TypeScript目标架构设计',f'''
## 设计状态

INFERRED / PROPOSED：面向PR-TS-01的正式架构草案，未创建TypeScript后端、未安装依赖、未改业务源码。PR-TS-01须先通过风险报告准入门禁。范围仅Java平台重写；Python Core/ACG/Hands继续是原权威。

```mermaid
flowchart TD
  UI[Electron + Vue] --> API[Fastify REST / SSE]
  API --> APP[Platform Application Services]
  API --> ID[LocalIdentityProvider]
  APP --> PORTS[Repository / AgentOS / Storage Ports]
  PORTS --> PG[PostgreSQL + Redis Cache]
  PORTS --> GW[Gateway Adapters + Projections]
  GW --> HTTP[Python Transport]
  HTTP --> CORE[Python AgentOS Core]
  CORE --> HANDS[Hands Native Execution]
  CORE --> DATA[SQLite / Checkpoint / Artifact]
  SUP[Windows Native Supervisor] --> API
  SUP --> CORE
  SUP --> HANDS
```

## 候选技术评估

| 技术 | 项目中的用途/依据 | 结论与准入验证 |
| --- | --- | --- |
| Node.js 24 | 本机v24.19.0已存在，Hands engines>=24.9.0；目标需要Windows native streams/abort | 采用24系列，后续锁定patch/包hash；不依赖开发机全局PATH的产品运行时 |
| TypeScript | 现有Hands/Electron为TS，前端5.4.5而其他5.9.3 | 新包独立锁版本/strict；不连带升级前端或Hands |
| Fastify 5 | REST插件边界、schema、Pino、可测试inject；适合薄平台网关 | 推荐；需验证wildcard优先级、multipart/SSE、Windows close；不靠框架自动复制Spring安全 |
| Zod | trusted input/config/上游wire验证与闭合DTO | 推荐；Fastify默认JSON Schema与Zod的桥接需明确；不声称可直接塞Zod对象作为默认schema |
| pg + Kysely | 保留现有SQL/JSONB/partial unique/事务；不用JPA懒加载 | 推荐；types不是runtime schema，pg UUID/time/count/JSONB映射需单测和真实PG验收 |
| Redis client | roles缓存 + 现有Python协调继续保留 | 客户端候选需小型连接/重试/关闭验证；TS只负责自己的缓存，不改Lua lease协议 |
| Pino | requestId、结构化日志、redaction | 推荐，密钥/正文/完整路径默认不记录；trace和低基数metric独立于日志 |
| Vitest | 已有TS测试惯例；adapter/mapping单元与HTTP合同 | 推荐；注入测试之外必须真实socket SSE、PG15、Redis和Windows supervisor验收 |
| Node Stream / AbortController | 背压、上游取消、idle/max deadline | 推荐；不同超时reason必须区分，避免把timeout全算用户取消 |

本轮通过Context7核对官方Fastify与Kysely文档：Fastify5默认校验需要完整JSON Schema，close生命周期需明确释放资源；Kysely提供pg Pool方言与托管事务callback提交/异常回滚。这是文档能力证据，**不是本项目兼容性实测**。来源：[Fastify v5迁移指南](https://github.com/fastify/fastify/blob/main/docs/Guides/Migration-Guide-V5.md)、[Fastify Server](https://github.com/fastify/fastify/blob/main/docs/Reference/Server.md)、[Kysely事务实现](https://github.com/kysely-org/kysely/blob/master/src/kysely.ts)、[Kysely PostgresDialect](https://github.com/kysely-org/kysely/blob/master/src/dialect/postgres/postgres-dialect.ts)。依赖版本锁定、第三方插件兼容与许可证验证留在获准的PR-TS-01，不在本轮安装。

## 目录树（文档设计，不创建）

```text
apps/backend-ts/
  package.json / tsconfig.json / vitest.config.ts
  src/
    main.ts                         # 启动/停止，只有装配
    bootstrap/{{container,server,lifecycle}}.ts
    config/{{schema,load}}.ts
    domain/{{identity,conversation,role,errors}}/
    application/
      ports/{{repositories,agentos,ai,storage,clock,identity,telemetry}}.ts
      chat/{{send-message,prepare-stream,record-stream-result}}.ts
      conversations/{{list,detail,rename,delete}}.ts
      roles/{{query,create,update,delete}}.ts
      profile/ / search/ / recommendation/
    api/
      plugins/{{request-context,local-access,trace,rate-limit,errors}}.ts
      routes/{{health,chat,conversations,roles,profile,files}}.ts
      routes/agentos/{{missions,runs,reviews,artifacts,observations,workspaces,events}}.ts
      routes/ai-proxy.ts
      schemas/                      # 请求/响应wire schema，版本化
    adapters/
      identity/local-identity-provider.ts
      postgres/{{pool,types,transaction,repositories}}/
      redis/{{client,role-cache}}.ts
      storage/local-upload-store.ts
      python/{{transport,paths,trusted-context,error-classifier}}.ts
      agentos/{{gateway,sse,projection-mappers}}/
      platform-ai/{{chat,rag,knowledge-graph,role-fusion}}/
    projections/{{mission,run,workspace,artifact,trace,provenance,chat}}/
    observability/{{logger,metrics,redaction}}.ts
  test/{{unit,contract,integration,sse,architecture,windows-native}}/
  migrations/                       # 后续独立schema PR才允许新增SQL
  dist/main.js                      # 构建产物，产品入口
```

## 模块依赖方向与职责

1. REST routes只解析/验证、取服务端ActorContext、调用application、serialize DTO/status；不得直接import pg、拼Python URL或执行任务。
2. Application只依赖domain和ports；控制短事务/缓存失效/业务fallback，不能import Fastify、pg、Python运行内部实现。
3. Gateway adapter实现AgentOsPort；构造编码路径、传输、闭合projection、上游错误；无计划/调度/Permit决策。可以直接作为查询/命令薄application的实现，不额外复制空壳service。
4. PythonTransport是唯一出站owner：固定base origin、service auth、server trusted identity、trace、deadline、取消、byte/JSON/SSE边界和metrics。health可无actor，业务必须有actor；不能提供任意URL转发入口。
5. Repository负责SQL、owner过滤、显式事务连接与DB row映射；projection负责公开wire，不返回数据库row/entity给renderer。Domain纯类型/规则不依赖adapter。
6. LocalIdentityProvider只消费受信Home映射，提供稳定actor和wire tenant；Controller不读请求userId作为权威。bootstrap唯一允许同时import所有adapter与application的composition root。
7. SSE gateway只做流合同；StreamRecorder负责chat持久化，RuntimeEvent仍由Python产生。Storage port只处理平台uploads，不接管Python ArtifactStore/Checkpoint。

依赖Architecture Guard：application→api/adapters、domain→framework、route→SQL、非transport→外部HTTP、platform→Python runtime internals 均禁止；无JWT/session/密码模块；共享contracts只共享wire，不共享运行权威。

## REST / DTO / Error兼容策略

逐行实现route-inventory.csv的需要保留项，保留/api规范化和原生/api族；原有登录接口/改密码最终明确返回410或移除404并同步消费端，不为它们保留伪token。缺口五项不能凭空按前端类型实现业务：先与Python合同对齐/批准退役。

AgentOS command支持409对账、typed错误、binary与multipart；query投影保持白名单字段、枚举/nullable、UUID/time/count。迁移时冻结输入/输出匿名fixture，Fastify/Zod默认未知字段处理须与当前合同逐项核对，不能将校验加严自动当兼容修复。错误转换保留现有族差异，统一日志但不一刀切改变status/code/envelope。

## Database Repository / 事务 / 迁移权威

同步Chat保持“事务A：owner会话+user消息 → 提交 → HTTP → 事务B：assistant消息”，SSE同样不跨流占用PG事务。conversation删除先message再conversation在一个事务；roles更新commit后精确逐出缓存；repository必须接受非空ActorContext。stream attempt幂等需要独立schema与失败恢复设计，不能仅复制内存persisted布尔后宣称exactly-once。

V1–V13冻结不改写。TS初始仅校验真实Flyway状态及schema fingerprint，启动时不自动baseline/repair。正式不再依赖JVM后，以后续独立PR引入唯一TS migration runner：先对照历史Flyway checksum/成功状态完成一次有版本交接，旧Flyway history保留只读，新版本ledger记录来源baseline和SQL hash，在PG advisory lock下单写；严禁Java Flyway与TS runner并行变更schema。不能把SHA-256误当Flyway原checksum算法。交接、失败事务、旧版本拒绝启动与回滚都需PG15测试。

Redis roles旧值包含Java default typing元数据，TS使用新版本namespace，不全库FLUSH，不触碰DB1协调key；miss/断连仍回PG，更新删除失效有测试。TTL1h是当前合同候选，变更需单独批准；缓存不保存LocalIdentity或Grant权威。

## 无登录安全与LocalIdentity

无用户JWT/session，但保留服务认证、路径/IPC sender/执行批准。绑定loopback，严格校验Host和允许Origin（发行kinlin-app://shell、开发固定Vite origin）；不能只配置CORS后就放行跨站写。mutation要求JSON或受控multipart、自定义非简单请求header与服务端Origin检查，拒绝null/未知Origin；无Origin的外部请求只开放最小health，若需Main/CLI操作则设计受控本地桥接/独立进程服务认证，不将其伪装用户session。确切本机准入合同须在PR-TS-01前冻结并做真实socket测试。

renderer传入userId/tenantId/trusted headers一律忽略或拒绝；当前actor外owner的URL返回明确拒绝，不用“单机”理由绕过查询约束。Main IPC保留sender id+mainFrame+参数校验；terminal/Hands内部凭据保持独立，不因名字叫token误删。相同Windows用户下恶意进程不是靠ActorId解决的边界，发行设计只承诺受限Home ACL与应用入口校验，不虚称OS沙箱。

## SSE / Configuration / Logging / Native接入

SSE专门的parse/forward预算、UTF-8分片、多行data、heartbeat、idle/total时钟和Abort reason；新事件不得重排/伪造；Runtime cancel通过Python命令而非断流隐式执行。配置启动即验证required DB/service auth/Home identity，并支持原环境迁移映射；日志默认屏蔽Authorization、内部令牌、HMAC、API密钥、密码、请求正文和完整workspace路径，TraceId长度/格式验证，metrics禁高基数run/user标签。

Supervisor保持Node24服务描述符、18080默认端口/整体offset、健康别名、PID+creation-time身份、启动锁、失败回收、受限env与冷备清单；开发和发行共用描述符合同、显式profile策略，产品绝不接管陌生进程。shutdown由受控本机协议触发drain，不依赖Windows一定传POSIX信号；Chat drain与Python关闭次序需验收。发行包Node运行时是必需组件；无JVM/Hyper-V不等于无运行时。

## PR-TS-01应交付的可审结果

正式验收PR-TS-00后才可建立骨架、锁定依赖、冻结Actor/准入/错误schema、空health和Supervisor adapter、Architecture Guard与合同fixture；不得同时迁移所有CRUD、改变Python runtime或自动升级真库。真正业务切换需后续PR、备份和等价测试门禁。当前结论仍为NO-GO，不能因本设计明确而跳过数据库/身份补证。
''')
risks=[
('P0','R01','身份重建/自动合并将历史数据和执行授权错配',je('gateway/TrustedUserContextForwarder.java','AUTHENTICATED_USER_ID')+'；'+ev('apps/agent/app/execution/workspace_authority.py',"row['user_id'] != owner"),'PG users/roles/conversations、SQLite Run、Artifact/Grant','新actor UUID、tenant归一变化或多用户强制合并','保留旧owner UUID/wire tenant映射；零/单/多用户按数据库报告分流；多用户人工决策','00补证→02身份','同Home重启actor不变；旧owner数据仍隔离；未决多用户拒绝启动'),
('P0','R02','Grant重新签发或替换Run快照会使旧Run越权',ev('apps/agent/app/execution/workspace_authority.py',"row['grant_id'] != binding['grantId']")+'；'+ev('apps/agent/app/execution/workspace_authority.py',"run_input.pop('workspaceBinding', None)"),'目录写入、shell执行、历史Run','移除登录时绕过owner/revoked/epoch校验或复用新grant','Python仍唯一issuer/resolver；不改历史Run；保留grant epoch、inode、resource和owner检查','02/05','撤销后旧Run失败；重新授权同目录旧Run仍失败，新Run正常；跨owner/tenant拒绝'),
('P0','R03','未查真库即迁移可能破坏不可恢复数据',ev('apps/backend/src/main/resources/db/migration/V10__delete_builtin_roles.sql','DELETE FROM roles')+'；'+ev('apps/backend/src/main/resources/db/migration/V13__drop_user_feedback.sql','DROP TABLE'),'所有持久数据、Flyway lineage、恢复','将文件V13当真库V13；并行迁移runner；只回滚二进制','真实只读schema/owner审计、全栈冷备和恢复演练；历史SQL冻结；单写runner交接','00补证→03/07','真实history成功状态/constraints有证据；原Home恢复验证；不丢SQLite/Artifact/Grant'),
('P0','R04','去JWT后平台请求可伪造actor或由跨站驱动敏感操作',je('controller/UserProfileController.java','@PathVariable UUID userId')+'；'+ev('apps/desktop/electron/src/main.ts','const authorized ='),'profile/roles/conversations/Workspace/Hands入口','直接permitAll、信任userId或误删IPC sender guard；仅CORS无服务端写准入','服务端LocalIdentity生成trusted headers；非空owner；Host/Origin/非简单请求准入；保留IPC校验','01/02/06','伪造身份头/URL/body无效；陌生Origin/null/恶意Host写拒绝；错误sender IPC拒绝'),
('P0','R05','替换进程名或恢复流程会误杀/残留进程或产生不一致冷备',ev('ops/scripts/release/product_runtime.py','def occupied_ports')+'；'+ev('ops/scripts/infra/windows/native/persistent_runtime.py','def require_stopped'),'用户其他程序、PG/Redis/SQLite一致性','仅按PID/端口终止、开发takeover带入产品、流未落库即备份','保留身份校验/停栈锁/数据hash；profile策略显式化；Node drain与旧记录兼容','01设计→07','PID复用/端口占用不误杀；失败无受管孤儿；冷备恢复一致且actor不变'),
('P1','R06','SSE sid gate与无登录actor不兼容；断流落库非持久幂等',je('gateway/AiSseGatewayService.java','userContext.sid() == null')+'；'+je('service/ChatStreamPersistenceService.java','capture.persisted = true'),'Chat流、事件、用户历史','仅删除JWT过滤器；取消/超时/数据库失败/进程崩溃','以本机准入替换sid gate；保留流timeout/abort；定义attempt重放/事务恢复合同','04/05','无sid可合法建流；失败/取消事件有序；落库失败可诊断和恢复且不重复user/assistant'),
('P1','R07','前端接口缺口与条件Python路由不能按注解数补齐',ev('apps/frontend/src/services/api/agentos/api/runtime.ts','/context-packs')+'；'+ev('apps/agent/app/main.py','except ImportError as e:'),'上下文包、node启停、旧chat统计、RAG下载、ASR','仅迁移140显式路由；假定代理有任意上游','逐项确认消费/上游wire；补正式合同或批准退役；WS单独决策','01合同→05/06','五缺口各有合同测试或退役记录；可选路由加载可观测；ASR升级路径明确'),
('P1','R08','错误/序列化/时间/Redis值差异破坏现有合同',je('gateway/AgentOsGatewayService.java','AGENTOS_UPSTREAM_UNAVAILABLE')+'；'+je('config/CacheConfig.java','roleAwareJsonSerializer()'),'所有平台API与角色缓存','全局统一error、Date隐式时区、读Java类型缓存','按族兼容error，显式UUID/time/count/JSONB映射；版本化cache namespace','03/04/05','匿名fixture字段/status/code差分通过；PG JSONB/time roundtrip；Redis停机可降级'),
('P1','R09','文件路径与通用代理缓冲需明确安全/容量边界',je('service/FileService.java','Paths.get(uploadDir, filePath)')+'；'+je('gateway/AiProxyService.java','readAllBytes()'),'平台文件与网关内存','不受控type/filePath或大body并发；迁移只翻译API','根目录realpath/重解析点/文件名约束与上限背压；先确认调用者校验；不声称已复现越权','04/05','编码遍历/绝对路径/链接逃逸拒绝；超限413；慢读取消释放资源'),
('P1','R10','测试隔离与运行基线未证实，迁移绿色结果不可比较',ev('apps/backend/src/test/resources/application-test.yml','create-drop')+'；'+ev('.github/workflows/backend-ci.yml','mvn -B -ntp test'),'旧/新合同门禁','H2代PG、未确认环境即运行测试或直接跳过旧行为','确认每个suite的数据目录/URL/端口/清理所有权后隔离执行；保存实际报告','00补证→各PR','mvn原基线与TS等价矩阵均有真实输出；无生产数据/服务干扰'),
('P2','R11','机械类翻译与遗留平台接口增大维护面',je('service/KylinOSIntegrationService.java','cat /etc/kylin-release')+'；'+je('service/RecommendationService.java','generateContextualRecommendations'),'模块边界、Windows-only体验','复制JavaService/Map/System.exec而未区分平台职责','按application/port/adapter整合；KylinOS等经消费方决策退役，推荐保留纯函数','01设计→04','架构依赖规则通过；无platform层引入Python计划执行；遗留API有明确处置')]
riskcsv=[dict(severity=r[0],id=r[1],description=r[2],evidence=r[3],scope=r[4],trigger=r[5],remediation=r[6],phase=r[7],acceptance=r[8]) for r in risks]
with (OUT/'risk-inventory.csv').open('x',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(riskcsv[0]));w.writeheader();w.writerows(riskcsv)
matrix=[
('REST合同','route CSV保留项逐method/path；alias规范化/HTTP优先级；HEAD/OPTIONS/actuator单列','与旧匿名fixture比字段、status、error code；计划退役auth单列404/410','01/04/05'),
('分页/排序','page/pageSize边界、空值过滤、cursor、并列时间稳定排序','列表items/total/nextCursor与既有合同一致，未知规则先冻结','03/05'),
('UUID/时间/JSONB','uuid非法/nullable；TIMESTAMP/TIMESTAMPTZ、UTC/本机时区、计数bigint；对象数组Unicode','PG15往返保持；wire格式逐字段一致，无隐式时区漂移','03/04'),
('事务','conversation及messages删除；同步chat两段事务；失败回滚；roles commit后cache','中途异常不半写；HTTP不持有事务；无owner路径不可公开','03/04'),
('SSE事件','一字节UTF8切分、多行data、event/id/retry、reasoning/tool/usage/done顺序','socket读取有序；不全量buffer；断连不生成第二响应；bounded内存','05'),
('SSE中断','idle/max分离、客户端Abort、上游4xx/5xx/断连、慢客户端、shutdown','正确HTTP或terminal event；abort传到Python；无timer/reader/配额泄漏','05/07'),
('Chat落库','complete/cancel同时触发、空响应、DB失败、进程崩溃、重连重试','定义attempt语义；不重复历史；失败可恢复；metadata与最后用户消息归属正确','04/05'),
('LocalIdentity','零/一/多用户、配置丢失/篡改、同Home重启、伪造actor/tenant/header','稳定actor；多用户未决fail closed；无JWT/session/密码；资料隔离','02/06'),
('服务认证','Python缺token/重复header/假user/正常Backend转发、公共health','Python业务直连拒绝；trusted context由Backend生成；无凭据出现在日志','02/05'),
('Workspace Grant','选择A→新Run、切B→旧Run仍A、撤销A、重授权A、跨tenant/owner、目录身份变更','旧Run无新grant权限；missing binding fail closed；Hands JSON只是投影','02/05'),
('Mission/Run/Review/Artifact','launch reconcile/409、graph五步、permit/dispatch、cancel/retry、软删终态、文件下载','Python仍权威，TS不调度；403/404/409/202等逐路由冻结','05'),
('缓存/Redis','角色hit/miss/evict、Redis中断恢复、旧Java值/new namespace、协调DB不动','降级PG；修改删除不读陈旧值；无FLUSHALL/协调协议变更','04'),
('无登录入口安全','真实socket Host/Origin/null/简单表单跨站、假userId、未授权IPC sender','敏感写/读符合本机准入；合法Electron可用；不因无登录开放目录执行','01/02/06'),
('Windows native','冷启/重复启/占端口/PID复用/部分失败/关闭中流/恢复/冷备hash损坏','产品不误杀；无受管残留；备份恢复owner/grant/store一致；无JRE/JVM依赖','07')]
phases=[
('TS-00补证','真实schema/owner/tenant/孤儿与SQLite/Artifact匿名对账；完整套件隔离评审、关键动态路由确认','本轮BLOCKED；用户正常环境已运行并可安全只读连接','补证报告与正式验收，不执行重写','只读失败停止，不改数据；旧栈原样'),
('TS-01 架构/骨架','锁Node/Fastify/schema方案；Actor/本机准入/错误/ServiceSpec合同；隔离fixture与architecture guard','TS-00正式ACCEPT且P0处置与身份方案冻结','空health/测试在独立端口/目录；无真库修改；逐路由迁移追踪','删除新骨架或停止隔离进程；旧入口仍有效'),
('TS-02 LocalIdentity','无登录owner映射/可信身份；零一多用户预检；保留Python/IPC授权边界','真库多owner决策完备；可恢复身份备份','稳定actor/tenant、伪造输入拒绝、旧Run/Grant不混淆','恢复原映射/配置；未切换前Java仍登录；不合并数据'),
('TS-03 persistence','pg/Kysely repositories/types/短事务；Flyway lineage交接设计与schema验证','schema fingerprint与备份恢复已验证','PG15等价JSONB/UUID/time/约束/事务测试；migration单写','先保持expand-only兼容；schema不可逆则完整冷还原，禁止仅降二进制'),
('TS-04 平台业务','conversation/roles/profile/search/chat/recommendation/files及cache','02/03完成，owner与文件边界明确','REST/fallback/事务/缓存差分；不改Python生成语义','旧Java仍可用；禁止新旧同时写一请求/双发模型'),
('TS-05 Gateway/SSE','所有保留AgentOS/AI路径、closed projections、binary/multipart、abort/stream recorder','正式上游wire与五缺口/WS决策完成','Python服务认证、Mission/Run/Review/Artifact/Grant/流E2E','流先drain；只读shadow可选；命令/执行禁止双写shadow'),
('TS-06 Frontend/Electron','移除token/login/sessionBootstrap/401跳转，改identity readiness；保留IPC/Origin','TS平台/网关通过；无登录入口安全合同通过','桌面启动无需密码；完整调用矩阵回归；无孤立axios/token守卫','切回完整旧renderer+Java配套，不混用新无登录UI与旧需JWT后端'),
('TS-07 Native/发行切换','node dist/main.js/18080、manifest/health/ownership/backup；冷启动停止恢复','全部合同绿、备份可恢复、正式切换批准','普通Windows用户、无JDK/JVM/Docker、包内Node/PG/Redis/Python/Hands全链实测','同Home全栈冷备恢复；完整配套旧发行包与identity兼容；不自动执行'),
('TS-08 Java退役','删除Java/JRE/Maven/登录残留、切CI和文档','正式发行验收与回滚窗口结束，剩余合同有处置','扫描无JVM运行依赖；TS required gates与冷备恢复通过','保存旧签名发行包/数据备份；不可逆清理后需完整恢复')]
report('PR-TS-00-风险与迁移执行计划',f'''
## 审计决定：BLOCKED；PR-TS-01：NO-GO

已经完成本轮源码遍历、静态接口/依赖盘点、环境检查、风险与目标设计交付。没有完成真实DB/schema版本/owner统计、运行路由/SSE/native行为验证；部分动态/可选上游与测试隔离仍待确认。遵照验收标准，不将UNKNOWN伪造为ACCEPT。此决定不代表已证实当前存在所有风险描述的事故；下表区分**迁移触发风险**与已见源码缺口。

## 分级风险与可验证处置

{table(['等级/编号','问题与证据','影响范围','触发条件','处置','阶段','验收条件'],[[r[0]+'/'+r[1],r[2]+'<br>'+r[3],*r[4:]] for r in risks])}

R01–R05为P0迁移阻断项，均有处置和验收，不宣称已经修复。R04中profile路径接受userId是源码事实，是否可越权读取需结合活动安全上下文进一步验证；R09是边界风险，未进行路径越权利用测试。本轮不利用漏洞、不修业务代码。

## 未来等价测试矩阵

{table(['测试域','场景','通过标准','阶段'],matrix)}

Java逐文件处置见模块报告和test-inventory.csv。旧JWT签名/登录/session重查的专属断言删除；其中owner、trusted header、SSE取消与Grant/Permit授权不删除。不能要求新后端继续签JWT以满足旧测试。新无登录入口测试替代登录合同；RuntimeEvent/Trace/Provenance/Checkpoint序列化仍保留。测试数量/通过率本轮无运行输出，全部NOT RUN。

## 迁移PR顺序、前置条件和回滚

{table(['阶段','范围','前置条件','退出门禁','回滚机制'],phases)}

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
''')
with (OUT/'README.md').open('x',encoding='utf-8') as f:
 f.write('# PR-TS-00 审计交付索引\n\n结论：**BLOCKED**；**PR-TS-01: NO-GO**。真实数据库停栈，Flyway/owner/Grant实测未取得；没有启动服务或实施重写。\n\n')
 for p in sorted(OUT.glob('PR-TS-00-*.md')):f.write(f'- [{p.stem}]({p.name})\n')
 f.write('\n四份主机器清单：route-inventory.csv、migration-inventory.csv、frontend-callsite-inventory.csv、java-dependency-inventory.csv。统计口径见inventory-summary.json；变更校验见verification.json；产物哈希见artifact-manifest.csv。所有测试均未执行。\n')
print('Generated 8 reports + README and risk-inventory.csv; source citations checked.')

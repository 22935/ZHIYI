"""Build new PR-TS-00B reports and additive links; never rewrite PR-TS-00 artifacts."""
from pathlib import Path
import json,csv,hashlib,collections,subprocess
OUT=Path(__file__).parent;ROOT=OUT.parents[2]
def js(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def rows(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8-sig')))
pg=js('PR-TS-00B-database-evidence.json');ident=js('PR-TS-00B-identity-evidence.json');first=js('PR-TS-00B-isolation-evidence.json');second=js('PR-TS-00B-isolation-attempt2-evidence.json');done=js('PR-TS-00B-isolation-final-evidence.json');extra=js('PR-TS-00B-supplement-evidence.json');review=js('PR-TS-00B-schema-review-evidence.json')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ev(p,needle):
 s=(ROOT/p).read_text(encoding='utf-8-sig');i=s.find(needle)
 if i<0:raise ValueError('citation missing '+p+' '+needle)
 return f'`{p}:{s.count(chr(10),0,i)+1}`（`{needle}`）'
def table(headers,records):
 def esc(v):return str(v).replace('|','\\|').replace('\n','<br>')
 return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(esc(x) for x in r)+' |' for r in records])+'\n'
legend='''> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

'''
def report(name,body):
 with (OUT/(name+'.md')).open('x',encoding='utf-8') as f:f.write('# '+name+'\n\n'+legend+body.strip()+'\n')
report('PR-TS-00B-数据库实际证据',f'''
## 结论与证据范围

VERIFIED：真实N03 Home的受支持冷快照已创建，原PostgreSQL cluster没有启动；PostgreSQL15.19在隔离副本恢复、查询、正常停止。Flyway V1–V13逐条成功，script与按Flyway规则计算的CRC32全部匹配当前源码。此证据来自真实数据的副本，不是新建临时空库，不是由“存在表”推断迁移成功。

有效数据库连接：`{pg['connection'][0]['database']}`，server=`{pg['connection'][0]['server_version']}`，`127.0.0.1:25432`，effective role=`pg_read_all_data`，transaction_read_only=`on`。用原DPAPI密文在内存中取得连接凭据，只在BEGIN READ ONLY后SET LOCAL ROLE；业务SELECT全部由只读有效角色执行，已验证其public表INSERT/UPDATE/DELETE/TRUNCATE权限计数为0。查询后ROLLBACK；未新建角色、未执行DDL/DML、未运行应用/Flyway。

详见 `PR-TS-00B-database-evidence.json`、`PR-TS-00B-isolation-final-evidence.json` 和审计脚本的query允许集。role/schema配置检查不读取用户密码列；未输出username、UUID、正文、完整Workspace路径。

## 预检查和快照

HEAD与上一轮一致。tracked/staged diff为空；上一轮审计目录原本未跟踪，完整保留。manifest Home匹配 `default-clean-20261106`，format=zhiyi-windows-persistent-v1；PG_VERSION=15，本地二进制15.19。8个记录PID不存在、配置端口无监听，未发现其他postgres/pg_ctl进程；SQLite与OS锁文件用GENERIC_READ/OPEN_EXISTING/share=0检查，未写锁文件或重命名原目录。

源cluster的pg_controldata为`in production`且陈旧postmaster.pid存在。该状态明确为“离线、非正常关闭的恢复候选”，不是干净关闭；用户获知后授权本轮方案。未删除原PID文件、未启动原cluster、未运行pg_resetwal。副本日志证实interrupted/redo starts/redo done/ready，最终shut down；恢复写入只发生在pg-query-copy。

| 位置/范围 | 结果 |
| --- | --- |
| 真实Home | `C:\\Users\\LZX\\AppData\\Local\\ZhiyiNative\\default-clean-20261106` |
| 快照 | `E:\\ZhiyiAudit\\PR-TS-00B-20261107-r01\\snapshot` |
| PG副本 | 同级 `pg-query-copy`；SQLite查询副本为 `sqlite-query-copy` |
| 私有证据 | 同级 `private-evidence`，不进桌面ZIP |
| 空间 | 预检Home约106MiB；E盘空闲约794GiB，检查至少2GiB余量 |
| 快照文件 | {first['snapshot']['files']}，{first['snapshot']['bytes']}字节；全部SHA-256匹配源集合 |
| snapshot.json SHA-256 | `{first['snapshot']['receipt_sha256']}` |
| 原Home校验 | {done['original_home_files_checked']}文件，字节哈希变化{done['original_home_hash_changes']} |
| 原PR-TS-00证据 | 34个既有manifest条目匹配；全部历史报告/清单保持原字节 |

调用现有persistent_runtime.backup函数，而非会以a+b改写控制文件的CLI入口；包装器持有已有控制文件的只读独占句柄。复用protect仅收紧新E盘目录ACL。工具排除logs/temp/webview/lifecycle.lock，备份包含其余Home数据、PG/Redis/SQLite/Checkpoint/Artifact存储、Hands ledger、uploads、environment与DPAPI密文。

**范围限制：完整性仅针对受支持Home payload，不是整机或全部项目冷备。** 两个历史外部Workspace（只标P02/P03）未被此工具包含；未复制、未修改。当前默认Home内工作区P01为空且已包含；P02顶层41项，P03顶层0项。禁止据此快照对外部项目作破坏性迁移；未来涉及外部文件写入/全产品恢复演练时必须另行纳入备份范围。本轮不涉及这些写入。

## 实际启动/查询/停止的过程

1. `python -B .../PR-TS-00B-run-isolated-audit.py` 创建并验证快照，第一次pg_ctl返回1：Windows把`''`空值参数解释成字面动态库名。该进程退出，未查询、未恢复原库。失败证据独立保留。
2. `python -B .../PR-TS-00B-run-copy-retry.py` 用`-c name=`空值重试。PostgreSQL副本已ready并完成redo；pg_ctl进程退出后，Python capture_output等待继承管道，最终TimeoutExpired。此启动器回执失败不等于数据库未启动；没有改用原库。
3. `python -B .../PR-TS-00B-complete-owned-copy.py` 验证postmaster.pid、PID创建时间、postgres.exe、命令行copy数据目录及loopback端口归属，接管**本轮已启动的同一副本**进行只读补证；随后pg_ctl fast stop返回0，端口释放，pg_controldata为shut down。原Home哈希与snapshot哈希再次通过。

这三段证据分别为isolation-evidence、isolation-attempt2-evidence、isolation-final-evidence.json，旧失败记录未覆盖。所有pg_ctl argv见这些JSON及 `PR-TS-00B-运行命令与隔离结果.md`；credentials只在进程内存，命令无密码。没有整套up/recover、没有新建cluster、没有发HTTP执行命令。

## Flyway真实history与源码比对

{table(['version','script','真实checksum','success','源码CRC32匹配'],[[r['version'],r['script'],r['checksum'],r['success'],next(x['checksum_matches'] for x in pg['migration_comparison'] if x['version']==r['version'])] for r in pg['flyway']])}

计算基于UTF-8逐行、去BOM、不计换行、CRC32有符号32位；不把SHA-256当Flyway checksum。算法核对官方[ChecksumCalculator变更源](https://github.com/flyway/flyway/pull/3764/files)。本轮独立比对成功，不等价于运行Flyway validate或完整schema validator；没有调用repair/baseline。

## 实际schema与结构证据

真实public表：conversations、flyway_schema_history、iam_login_sessions、local_workspace_authorizations、messages、roles、users；user_feedback确已不存在。取得{len(pg['columns'])}列、{len(pg['indexes'])}索引、{len(pg['constraints'])}约束定义；完整结构在database-evidence.json，未导出业务数据或schema-only dump。

V5 title/file_url/stable_key、V7 workspace_mode、V8 **avatar_url**均匹配；V12 grant unique与selected/nonrevoked部分unique存在；V11 session.user_id→users外键存在。JSONB为messages.metadata及roles的dialogue_style/personality/avatar_config。TIMESTAMP与TIMESTAMPTZ保留差异。早期辅助检查误写avatar_path而false，schema-review-evidence已按V8源码纠正；没有真实schema错配。

当前roles/conversations/messages多数关系并无数据库FK强制，与迁移SQL一致；数据孤儿计数另行查询，不能因为没有约束而假定安全。索引和约束逐定义为VERIFIED，完整等价重建/执行计划/性能仍UNKNOWN，留在repository迁移门禁。

## 匿名数据与关系完整性

{table(['表','行数'],[[r['table'],r['n']] for r in pg['table_counts']])}

{table(['关系异常检查','数量'],[[r['finding'],r['n']] for r in pg['orphans']+pg['grant_anomalies']])}

所有四个Conversation属于U01；Role数0；两条Grant均属U01/UNSCOPED_SENTINEL，一条selected、一条未selected，均未revoked。Session数2只作为历史统计，不读取或输出JWT。跨SQLite身份对账见独立报告。
''')
dbrows=[[d['alias'],d['logical_file'],sum(t['rows'] for t in d['tables']),d['integrity_ok'],d['foreign_key_violations']] for d in ident['databases']]
report('PR-TS-00B-历史身份对账',f'''
## 当前真实场景：单用户、单历史owner（VERIFIED）

所有存储用同一个内存匿名映射表：PostgreSQL唯一用户=U01；Conversation、两个Grant、legacy Mission/Run、identity.sqlite3 Mission的owner全部为U01。没有其他历史owner，没有自动归并、没有修改userId/tenant/Grant/Run。匿名表只输出U01，原UUID映射不写入报告或ZIP。

| 对账项 | 结果 |
| --- | --- |
| PG users | 1，U01 |
| Conversation / Role | U01的Conversation=4；Role=0 |
| Legacy tasks / runs | 各1；R01 owner=U01 |
| identity missions / workflow_runs_v2 | 1 / 0；Mission owner=U01，与legacy Mission ID/owner/tenant匹配 |
| Run payload vs indexed owner | 匹配；indexed tenant为NULL |
| Run原始tenant | input没有authenticatedTenantId字段（ABSENT），不是字符串__unscoped__ |
| identity Mission原始tenant | metadata没有tenantId字段（ABSENT）；与legacy一致 |
| Grant tenant | 存储字符串__unscoped__；owner=U01 |
| 冻结binding | 唯一Run的workspaceId/grant epoch/owner/归一tenant/resource/root/rootIdentity全部匹配PG；目录当前inode身份匹配 |
| Hands grants投影 | 3条：2条动态PG授权+1条operator启动授权；动态缺失/不一致/多余均0 |
| Checkpoint | 已查checkpoint表0行，不伪造恢复历史 |
| Artifact / Content manifest / Attachment | 0 / 0 / 0，不声称已验证非空Artifact完整生命周期 |

identity v2 Run为0而legacy Run为1是现有存储分层的观测，不能直接当孤儿；本轮仅确认对应Mission存在和owner一致，未启动Runtime推进/物化该Run。非空Artifact/Checkpoint的运行恢复属于后续等价测试。

## SQLite读取方法与完整性

从冷快照复制data到独立sqlite-query-copy，保留WAL/SHM；以mode=ro打开并PRAGMA query_only=ON。未用应用Store构造函数，以免其自动DDL/backfill。只提取schema、计数、身份/引用字段和workspaceBinding元数据；未查询消息/goal/fragment正文。SQLite可能创建/使用SHM仅在查询副本，快照和原Home哈希均保持不变。

{table(['匿名库','逻辑文件','表行数之和（非业务实体数）','integrity_check','foreign_key_check计数'],dbrows)}

关键identity/workflows/checkpoints/content/provenance/values库integrity与FK检查通过。`PR-TS-00B-identity-evidence.json` 中通用single_identity_candidate=false是因为最初把**所有库**FK问题一并纳入该布尔门；不能解释为“发现多个用户”。schema-review-evidence明确分离关键身份库后，single_owner_identity_freeze_eligible=true。保留原始结果和复核过程，不覆盖证据。

## Chroma两条FK诊断的解释

VERIFIED：segments两行；PRAGMA显示父表为单数`collection`，实际存在的是复数`collections`，单数表不存在；用真实collections.id核对，缺失关联计数0。已安装chromadb的00002-segments.sqlite.sql和00009-segment-collection-not-null.sqlite.sql第6行同样写REFERENCES collection(id)。详情和安装源码SHA-256在schema-review-evidence。

INFERRED：这是既有供应商schema引用兼容问题，现有证据不支持认定两条segment业务数据丢失，更不支持认定actor混淆。按P2跟踪，禁止本轮修库或运行Chroma迁移；RAG迁移前须在隔离环境确认目标依赖与FK启用行为。没有直接修正外键、删除segment或重建向量库。

## Workspace / Ledger / Artifact边界

已核对两个动态授权的外部目录存在、当前目录身份匹配；只输出匿名W/P编号。它们未进入受支持Home快照，未进行文件内容读取/修改。投影含一个Home内部operator根，已包含且为空。Hands ledger一文件、386422字节按SHA-256保留；不解析或输出HMAC/事件正文。

PG是动态Grant唯一权威，hands-grants.json只是投影；撤销后重授权会改变grant epoch，旧Run不能继承新Grant。源码：{ev('apps/agent/app/execution/workspace_authority.py','def freeze')}、{ev('apps/agent/app/execution/workspace_authority.py','def _resolve')}。

## 零/单/多用户最终规则

| 场景 | 冻结判定 |
| --- | --- |
| 零users且所有PG/SQLite历史owner为空 | 可走未来首次初始化专用事务；建立一个UUID actor并记录Home映射；本轮未执行 |
| 零users但有历史owner | BLOCKED；不得生成新UUID覆盖遗留owner |
| 单用户且所有owner/tenant对账一致 | **本机当前命中**；ActorId保留旧users.id，raw tenant保持缺失/null，Grant查询沿用__unscoped__ |
| 单用户但有不同历史owner/tenant或Grant错配 | BLOCKED；不能仅按users行数自动选择 |
| 多用户/多历史owner | BLOCKED直到人工决定隔离保留方案；不取首行、不自动合并；任何单机身份映射不得重写历史执行身份 |

这些规则为INFERRED规范设计，当前命中条件为VERIFIED。现有数据允许冻结U01映射方案，不等于已经写入LocalIdentity配置或可跳过后续迁移事务/恢复测试。
''')
contracts=[
('G01','GET /api/agentos/v2/runs/{runId}/context-packs',ev('apps/frontend/src/workbench/runtime/observation.ts','agentosApi.listRunContextPacks'),ev('apps/agent/app/api/agentos_v2.py','@router.get("/runs/{run_id}/context-packs")'),'VERIFIED 活动Inspector调用；Java缺路由','TS-05补正式薄查询/闭合投影，保留run/mission owner；不重建ContextPack','P1，可延后到TS-05前；PR-TS-01骨架不依赖该API'),
('G02','POST /api/agentos/v2/nodes/{nodeId}/enabled',ev('apps/frontend/src/components/resource-center/ResourceOverviewPanel.vue','agentosApi.setNodeEnabled'),ev('apps/agent/app/api/agentos_v2.py','@router.post("/nodes/{node_id}/enabled")'),'VERIFIED 活动资源管理调用；Java缺路由','TS-05保留Python node-plane owner检查/401/403/404/503和enabled DTO；TS不自行调度','P1，交付资源管理之前必须补齐'),
('G03','GET /api/chat/history/role/{roleId}',ev('apps/frontend/src/services/api/chat.ts','async getConversationHistory'),'Java只有/history/{contextId}，多一segment不匹配','VERIFIED 方法存在；全src文本/AST未发现调用者；catch空数据','按未消费legacy wrapper冻结为不新建后端业务；TS-06去除/显式弃用包装，不改当前源码','P2；未来发现消费者则重新评审'),
('G04','GET /api/chat/summary/{roleId}',ev('apps/frontend/src/services/api/chat.ts','async getConversationSummary'),'Java无summary路由','VERIFIED 方法存在；全src文本/AST未发现调用者；catch空文本','同G03；不要凭函数名发明摘要服务','P2；未来恢复入口需新合同'),
('G05','GET /api/rag/documents/{id}/download',ev('apps/frontend/src/components/FileHistoryList.vue','const handleDownload'),ev('apps/frontend/src/views/HistoryView.vue','<FileHistoryList'),'VERIFIED 活动History文件页；Java /rag无download；fetch未带用户bearer','TS-04/05须先对齐文档元数据/受控文件定位与owner；不能直接传路径给任意读取','P1；History下载验收之前解决；不沿用当前无保护下载假设')]
with (OUT/'PR-TS-00B-route-supplement.csv').open('x',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['id','method_path','frontend_evidence','upstream_or_consumer','source_status','frozen_disposition','phase_risk']);w.writerows(contracts)
report('PR-TS-00B-接口与运行合同补证',f'''
## 证据层级

本轮只授权冷备/隔离PG与只读元数据补证，没有启动Java/Python/Hands/Electron/Redis/HTTP fixture或运行完整测试。下述为VERIFIED源码合同+INFERRED迁移决策；HTTP/SSE/原生完整E2E仍UNKNOWN/未执行，不以数据库查询替代运行测试。

## 五处缺口的正式处置

{table(['编号/路径','前端/上游证据','当前结论','冻结处置','迁移门禁'],[[r[0]+' '+r[1],r[2]+'<br>'+r[3],r[4],r[5],r[6]] for r in contracts])}

context-packs返回runId/items/total，查询identity或legacy run后做mission/run访问检查，仅返回bounded metadata而不是模型输入正文。Node enabled在Python resource_plane上修改调度开关，缺plane503、缺node404、无actor401、非空tenant不匹配403；本机旧tenant缺失语义需保持，不能任意改成sentinel header。两者已有Python实现，不允许TS重建运行语义。

## ASR活动性结论

VERIFIED：RealtimeASRService只由VoiceRecorder导入；VoiceRecorder默认enableRealtime=false，startRecording内启动startRealtimeASR的调用、sendAudio、endSession均被注释；全src的VoiceRecorder组件挂载搜索无消费者，TS AST对startRealtimeASR也无调用。RealtimeASRService.startSession虽有语法引用，但其上层函数不可从当前录音流程到达。

冻结处置（INFERRED）：当前实时ASR为休眠源码，不是TS-01/平台切换必须新增的活动WebSocket合同。不要仅因构造WebSocket代码存在就承诺支持，也不在本轮删除源码。Vite的/ai ws:true只是把upgrade送Java，Java仍没有对应WS端点，不能据此宣称连通。未来重启功能需独立带服务身份/准入的WS设计与测试。证据：{ev('apps/frontend/src/components/VoiceRecorder.vue','//   await startRealtimeASR()')}；{ev('apps/frontend/vite.config.ts','Availability still requires a corresponding Java WS endpoint.')}。

## SSE / sid / 取消与落库

{ev('apps/backend/src/main/java/com/kinlin/ai/gateway/AiSseGatewayService.java','userContext.sid() == null')}：GET/POST受保护流都要求sid，且SessionRecheckGate周期查询PostgreSQL。新无登录模式不保留假sid或session表依赖；替换为稳定ActorContext与本机HTTP准入，保留idle/max timeout、trusted context、取消传播、流事件顺序。Python Grant/Permit撤销仍在原执行权威处检查。

{ev('apps/backend/src/main/java/com/kinlin/ai/controller/AiServiceProxyController.java','SignalType.CANCEL')}：cancel捕获后异步complete；{ev('apps/backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java','capture.persisted = true')} 在repository.save之前设置内存标记。同步/流式落库都是短事务而不是跨网络长事务。迁移验收必须覆盖完成/取消竞争、上游错误、保存失败、进程崩溃、重连重试；不得把内存标记当持久exactly-once。HTTP流断开不等于取消Run，正式取消仍由Python命令控制。

隔离测试方案：独立fixture上游与随机端口、匿名请求、临时数据目录/独立测试PG；逐字节UTF8与多行SSE、id/event/data顺序、Abort断连、idle/total区分、两段事务和失败恢复。未实施fixture、未跑业务测试；该P1必须在TS-05 SSE启用前解决。

## JWT / Axios / Electron覆盖

上一轮全部src AST与身份触点清单字节哈希保持一致：route145行、frontend152项、identity224触点。独立Axios为utils/request、agentos/client、file、search、knowledgeGraph、roleFusion、federatedModel；后五者有自己的bearer注入，不能只改request.ts。stores/chat、companion chatStream、model controls、workspace picker、runtimeEvents、copilot SSE、Settings serverFetch也必须按清单移除用户token。

router.requiresAuth与401登录跳转、user store token缓存key、workflowRuns token前置条件、auth.ts验证/登出、LoginView注册登录、ensureDesktopSession、Preload session.ensure、Main bootstrapLocalSession与产品ensure_local_account一起退役。每点源码函数/依赖/调用符号候选/测试在identity-touchpoint-inventory.csv；无测试项需后续补，不伪造覆盖。

**保留**Main IPC sender id+mainFrame guard、通道白名单/参数校验、API Origin动态端口桥接、terminal内部token、Hands HMAC、工具审批、Python内部服务认证与执行授权。无用户登录不等于无进程/能力边界。证据：{ev('apps/desktop/electron/src/main.ts','const authorized =')}。

## Windows Native合同

VERIFIED：当前实现是函数+process record字典，不存在已实现的通用ServiceSpec类（限定ops/scripts/terminal-host/electron扫描）。ServiceSpec属于目标设计，不把它写成已具备能力。

现链PG/Redis→Java/Vite并行准备→受release-file/nonce/owner-PID/created门控的AI→Hands/terminal→最终health→Electron。Java readiness=`/actuator/health/readiness`，AI=`/health/ready`，Vite=`/api/health/ready`，Hands=`/v1/health`。stop_order=`desktop, frontend, ai, host, terminal, java, redis, postgres`；产品占用端口拒绝，开发有takeover，两者不能混用。

目标把java进程适配成node dist/main.js并默认18080，保留PID+创建时间+可执行身份、Home锁、失败回收和冷备合同；共用描述符但显式profile策略，不将开发takeover带入产品。SSE/Chat drain需在AI停止前完成接收关闭与必要持久化，再沿依赖顺序停机。Windows显式停止协议不能假设POSIX信号必达。

## 测试隔离复核与剩余门禁

NativePostgres创建随机临时cluster/随机端口；PostgresContainerBase动态覆盖datasource URL/user/password；RedisIntegrationTestBase另起临时Redis并动态覆盖端口；LocalApiHttpIntegrationTest为RANDOM_PORT+test/H2。删除清理代码仅以各helper创建的root为目标，但整个suite还包含默认外部URL、文件写入与继承profile，不能仅凭基座认定整套已隔离。

本轮未运行mvn test、Vitest、原生冷启动或其他现有业务测试；没有触发initdb/临时Redis。PR-TS-01只可搭建受限骨架与架构/准入fixture；首次运行任何旧suite前逐suite确认URL、env、目录、随机端口、进程拥有者和清理范围。required gate、PG15 repository、Redis、SSE socket、Windows启动停止恢复分别在03/04/05/07验收，不能用H2或注入测试代替。
''')
report('PR-TS-00B-LocalIdentity最终设计',f'''
## 冻结决定

**可以冻结单用户LocalIdentity设计（INFERRED规范，依据VERIFIED数据）。** 当前PG/legacy/identity Mission/Grant的唯一actor均U01，raw tenant缺失，Run冻结授权匹配。保留原users.id作为ActorId；不新生成替代UUID、不重写任何历史owner、不自动合并身份。本轮没有创建该配置或改表。

Chroma供应商FK定义问题不进入身份映射判据；外部工作区未备份不妨碍只读设计/骨架，但任何数据写入迁移或外部项目破坏性测试都不得据此放行。

## 稳定Actor来源与Home映射

未来映射文件建议Home内`identity/local-identity.json`，版本化且原子替换、受Home ACL保护，随冷备。形状如下（示意占位符，不包含真实UUID）：

```json
{{
  "format": "zhiyi-local-identity-v1",
  "version": 1,
  "actorId": "<existing-users.id>",
  "legacyUserId": "<same-existing-users.id>",
  "wireTenantId": null,
  "workspaceTenantFallback": "__unscoped__",
  "source": "verified-single-legacy-owner",
  "identityGeneration": 1,
  "homeBinding": "<validated-home-and-database-binding>"
}}
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
''')
report('PR-TS-00B-准入验收结论',f'''
## PR-TS-00B：CONDITIONAL ACCEPT

真实数据补证成功，先前“数据库不可用、历史owner未知”的阻断已解除。**PR-TS-00可作为迁移准入审计有条件关闭，PR-TS-01：GO（仅架构/受限骨架）**。这不是TypeScript业务切换、真库迁移、旧Java删除或发行部署许可。本轮结束停止，等待正式验收，不继续实现。

## 判定依据

| 项目 | 状态/结果 |
| --- | --- |
| 当前Git | VERIFIED master/8775130f；tracked/staged diff为空；原审计未跟踪文件全部保留 |
| 冷快照与副本 | VERIFIED 2276文件、109592569字节、SHA-256一致；PG副本redo、查询、fast stop成功；原2533文件哈希0变化 |
| 真Flyway | VERIFIED V1–V13成功、script/checksum逐条匹配，不靠表存在推断 |
| 真实身份 | VERIFIED PG唯一U01，与所有非空历史owner一致；tenant原始缺失、Grant归一sentinel；唯一冻结Run授权一致 |
| LocalIdentity | INFERRED规范可冻结：保留旧users.id，raw tenant缺失，Home版本映射，失配fail closed；未实施 |
| 未解决P0实际不一致 | 本轮未发现阻断**只搭骨架**的owner/Grant/schema/恢复副本P0不一致；未来P0控制仍为强制门禁，未实现不称已修复 |
| 原快照完整性限制 | 外部Workspace两处未包含；只读审计无写影响；涉及外部项目写入/产品恢复前另补备份和演练 |
| Chroma | VERIFIED供应商FK指向不存在的单数collection；实际collections关联0缺失；P2单列，未修库 |
| HTTP/SSE/应用E2E | UNKNOWN/NOT RUN；未取得整套应用启动或业务测试执行证据，本轮仅源码合同与隔离计划 |

## PR-TS-01的明确允许范围

可在随后正式授权的PR中创建TS骨架、锁定候选依赖、定义ports/DTO/error/LocalIdentity/本机准入/ServiceSpec、建立纯架构与独立fixture测试；使用独立临时目录与端口，不连接本机真库，不写用户数据，不打开真实Workspace，不替换18080，不修改Python/Hands执行语义。

此GO是阶段范围判定，不代表本轮已开始PR-TS-01。任何真库/外部Workspace写入、旧数据迁移、产品切换均需对应前置条件和正式审批/验收，不能由本结论自动继承。

## 剩余P1/P2及延后条件

| 事项 | 等级 | 可延后至 | 不可跨过的门禁 |
| --- | --- | --- | --- |
| context-packs/node enabled活动Java缺口 | P1 | TS-05 | 正式gateway+closed projection+owner/status合同测试，不复制Python逻辑 |
| History RAG下载缺口 | P1 | TS-04/05 | 受控文档定位/owner/二进制下载合同，不能直接开放路径 |
| SSE sid替换/取消落库恢复 | P1 | TS-05 | 无登录准入、timeout/Abort/事务/幂等负面测试通过 |
| 旧suite全套隔离证明与等价测试 | P1 | 首次运行各suite及对应迁移PR | 不碰真实数据/固定生产端口；PG15/Redis/真实SSE不能用H2代替 |
| 全产品冷启动/停止/恢复/外部项目备份 | P1 | TS-07及任何外部文件写入测试前 | 无误杀、进程身份正确、全恢复一致；目前只是PG副本恢复验证 |
| 无登录Host/Origin/IPC联动 | P1 | TS-01合同/TS-02接真数据前 | 实测否定伪造身份和跨站操作；不能只删JWT |
| 两条无消费者Chat wrapper/休眠ASR | P2 | TS-06 | 显式弃用记录；未来恢复入口重审合同，不本轮删源码 |
| Chroma供应商FK定义 | P2 | RAG依赖/存储迁移前 | 隔离验证FK行为；禁止顺手改原库或重建索引 |

所有P0迁移风险（Actor/Grant错配、服务身份/本机准入、进程所有权、schema单写与备份）仍在目标设计/各阶段强制验收，不以当前只有一用户免除隔离、安全与恢复测试。

## 停止边界与命令证据

所有有运行/写入效果的操作只在新审计文件、E盘快照/查询副本/私有证据、桌面ZIP及其摘要。初始/失败/重试/最终停止证据独立保留；首次错误与管道超时如实记录，不挑选绿色结果覆盖失败。原cluster没有启动，原Home/业务源码没有修改，未安装依赖、未建backend-ts、未删除Java、未提交或推送。

未运行任何现有业务测试；本轮通过的是备份哈希、副本PG查询、SQLite元数据完整性与引用检查、主清单完整性和产物脱敏检查，不能报告成mvn/Vitest/E2E通过。最终命令/进程/端口/哈希与ZIP验证见 `PR-TS-00B-final-verification.json`、运行命令报告和交付manifest。

## PR-TS-00主清单的增量引用

不改旧报告、旧README或四个主CSV。新增 `PR-TS-00B-主清单引用与完整性核对.csv` 将四个原CSV的行数/SHA-256与本轮补证关联，`PR-TS-00B-route-supplement.csv` 对五缺口逐项补充处置；`PR-TS-00B-交付索引.md` 链接全部历史和本轮报告。这是在“不覆盖历史报告”约束下的增量补齐。
''')
command_records=[]
for name,d in [('attempt1',first),('attempt2',second),('final',done)]:
 for c in d['commands']:command_records.append(dict(stage=name,**c))
with (OUT/'PR-TS-00B-command-log.json').open('x',encoding='utf-8') as f:json.dump(command_records,f,ensure_ascii=False,indent=2)
report('PR-TS-00B-运行命令与隔离结果',f'''
## 预检查（只读）

执行Git status/rev-parse/branch/log/diff/cached diff、rg/Get-Content源码审查；Get-PSDrive空间检查；N03 Python -B读取manifest/PID、psutil进程创建时间/端口、只读Win32独占句柄、postgres --version与pg_controldata。未调用persistent up/status/down/recover，不用native.down作为“锁探针”，因为该函数会停止进程/重命名目录/写回执。

## 获准后的操作入口与结果

| 实际入口 | 结果 |
| --- | --- |
| N03 python -B PR-TS-00B-run-isolated-audit.py | 工具进程非零；快照验证PASS；第一次PG启动返回1，未遗留服务；isolation-evidence保留 |
| N03 python -B PR-TS-00B-run-copy-retry.py | 工具进程非零，pg_ctl回执TimeoutExpired；同一副本实际ready/redo成功；attempt2独立保留 |
| N03 python -B PR-TS-00B-complete-owned-copy.py | exit0；只读业务SELECT、身份元数据对账成功；验证所属PG fast stop exit0 |
| N03 python -B PR-TS-00B-supplement.py | exit0；副本SQLite/Grant投影/恢复日志/旧manifest核对；不重启PG |
| N03 python -B PR-TS-00B-review-schema.py | exit0；确认avatar_url与Chroma FK兼容问题；不写库 |
| python -B PR-TS-00B-build-reports.py | 新增报告与增量清单；原报告不覆盖 |
| N03 python -B PR-TS-00B-package.py | 校验原Home/源码/既有证据/脱敏；桌面ZIP和SHA-256，结果另存final-verification |

入口均位于本审计目录；完整pg_ctl可执行路径和参数见command-log.json。参数绑定127.0.0.1:25432、显式copy data/hba/ident目录、default_transaction_read_only=on、archive/preload/ssl关闭；start日志只保存在受限private-evidence。所有SQL源码在run-isolated-audit.collect_pg与reconcile脚本中，使用SELECT允许集；BEGIN READ ONLY→SET LOCAL ROLE pg_read_all_data→SET LOCAL row_security=on→SELECT→ROLLBACK，不创建角色、不DML/DDL。

副本可能进行WAL重放和正常shutdown checkpoint；SQLite查询副本可能使用WAL/SHM。快照只读保留，原Home2533文件哈希0变化，快照2276文件查询后SHA仍匹配。无schema-only dump：已有足够结构查询证据，不额外暴露原始dump。无全产品恢复/业务HTTP/SSE测试，不把这些标PASS。

失败参数`''`仅存在第一轮的历史启动argv；第二轮改为Windows实际空值。后续接管仅针对核对过PID/created/exe/copy cmdline/loopback端口的13508进程，停止后端口释放。没有对原PID38832或其他用户进程发信号。
''')
crossrefs=[]
for name,refs in [
 ('route-inventory.csv','PR-TS-00B-route-supplement.csv;PR-TS-00B-接口与运行合同补证.md'),
 ('migration-inventory.csv','PR-TS-00B-database-evidence.json;PR-TS-00B-数据库实际证据.md'),
 ('frontend-callsite-inventory.csv','PR-TS-00B-route-supplement.csv;PR-TS-00B-接口与运行合同补证.md'),
 ('java-dependency-inventory.csv','PR-TS-00B-LocalIdentity最终设计.md;PR-TS-00B-接口与运行合同补证.md')]:
 crossrefs.append(dict(original_file=name,rows=len(rows(name)),sha256=sha(OUT/name),unchanged_since_PR_TS_00=True,new_evidence=refs,status='VERIFIED byte preservation; additive evidence, no original row rewrite'))
with (OUT/'PR-TS-00B-主清单引用与完整性核对.csv').open('x',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(crossrefs[0]));w.writeheader();w.writerows(crossrefs)
with (OUT/'PR-TS-00B-交付索引.md').open('x',encoding='utf-8') as f:
 f.write('# PR-TS-00B 交付索引\n\n结论：**CONDITIONAL ACCEPT；PR-TS-01 GO，仅限架构/受限骨架**。业务数据迁移、外部工作区写入、产品切换仍有阶段门禁；本轮停止等待正式验收。\n\n')
 for p in sorted(OUT.glob('PR-TS-00B-*.md')):
  if p.name!='PR-TS-00B-交付索引.md':f.write(f'- [{p.stem}]({p.name})\n')
 f.write('\n历史PR-TS-00报告（原字节保留）：\n\n')
 for p in sorted(OUT.glob('PR-TS-00-*.md')):f.write(f'- [{p.stem}]({p.name})\n')
 f.write('\n机器清单以PR-TS-00B-主清单引用与完整性核对.csv增量关联。失败/重试证据都保留；最终状态以isolation-final-evidence及准入验收报告为准。\n\n桌面ZIP仅含本目录脱敏审计产物；E盘snapshot/pg-query-copy/sqlite-query-copy/private-evidence不打包。原Home字节不变；最后验证见PR-TS-00B-final-verification.json。\n')
print(json.dumps({'new_reports':7,'decision':'CONDITIONAL ACCEPT','PR_TS_01':'GO restricted scaffold only','legacy_reports_overwritten':False},ensure_ascii=False))

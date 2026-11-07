# PR-TS-00B-历史身份对账

> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

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

| 匿名库 | 逻辑文件 | 表行数之和（非业务实体数） | integrity_check | foreign_key_check计数 |
| --- | --- | --- | --- | --- |
| S01 | audit.sqlite3 | 0 | True | 0 |
| S02 | checkpoints.sqlite3 | 0 | True | 0 |
| S03 | communication.sqlite3 | 0 | True | 0 |
| S04 | content.sqlite3 | 0 | True | 0 |
| S05 | evolution.sqlite3 | 2 | True | 0 |
| S06 | health.sqlite3 | 52 | True | 0 |
| S07 | identity.sqlite3 | 5 | True | 0 |
| S08 | memory.sqlite3 | 0 | True | 0 |
| S09 | nodes.sqlite3 | 1 | True | 0 |
| S10 | provenance.sqlite3 | 0 | True | 0 |
| S11 | chroma.sqlite3 | 40 | True | 2 |
| S12 | resources.sqlite3 | 3 | True | 0 |
| S13 | values.sqlite3 | 0 | True | 0 |
| S14 | workflows.sqlite3 | 15 | True | 0 |


关键identity/workflows/checkpoints/content/provenance/values库integrity与FK检查通过。`PR-TS-00B-identity-evidence.json` 中通用single_identity_candidate=false是因为最初把**所有库**FK问题一并纳入该布尔门；不能解释为“发现多个用户”。schema-review-evidence明确分离关键身份库后，single_owner_identity_freeze_eligible=true。保留原始结果和复核过程，不覆盖证据。

## Chroma两条FK诊断的解释

VERIFIED：segments两行；PRAGMA显示父表为单数`collection`，实际存在的是复数`collections`，单数表不存在；用真实collections.id核对，缺失关联计数0。已安装chromadb的00002-segments.sqlite.sql和00009-segment-collection-not-null.sqlite.sql第6行同样写REFERENCES collection(id)。详情和安装源码SHA-256在schema-review-evidence。

INFERRED：这是既有供应商schema引用兼容问题，现有证据不支持认定两条segment业务数据丢失，更不支持认定actor混淆。按P2跟踪，禁止本轮修库或运行Chroma迁移；RAG迁移前须在隔离环境确认目标依赖与FK启用行为。没有直接修正外键、删除segment或重建向量库。

## Workspace / Ledger / Artifact边界

已核对两个动态授权的外部目录存在、当前目录身份匹配；只输出匿名W/P编号。它们未进入受支持Home快照，未进行文件内容读取/修改。投影含一个Home内部operator根，已包含且为空。Hands ledger一文件、386422字节按SHA-256保留；不解析或输出HMAC/事件正文。

PG是动态Grant唯一权威，hands-grants.json只是投影；撤销后重授权会改变grant epoch，旧Run不能继承新Grant。源码：`apps/agent/app/execution/workspace_authority.py:113`（`def freeze`）、`apps/agent/app/execution/workspace_authority.py:131`（`def _resolve`）。

## 零/单/多用户最终规则

| 场景 | 冻结判定 |
| --- | --- |
| 零users且所有PG/SQLite历史owner为空 | 可走未来首次初始化专用事务；建立一个UUID actor并记录Home映射；本轮未执行 |
| 零users但有历史owner | BLOCKED；不得生成新UUID覆盖遗留owner |
| 单用户且所有owner/tenant对账一致 | **本机当前命中**；ActorId保留旧users.id，raw tenant保持缺失/null，Grant查询沿用__unscoped__ |
| 单用户但有不同历史owner/tenant或Grant错配 | BLOCKED；不能仅按users行数自动选择 |
| 多用户/多历史owner | BLOCKED直到人工决定隔离保留方案；不取首行、不自动合并；任何单机身份映射不得重写历史执行身份 |

这些规则为INFERRED规范设计，当前命中条件为VERIFIED。现有数据允许冻结U01映射方案，不等于已经写入LocalIdentity配置或可跳过后续迁移事务/恢复测试。

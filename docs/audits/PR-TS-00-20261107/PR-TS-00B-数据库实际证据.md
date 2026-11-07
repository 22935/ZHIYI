# PR-TS-00B-数据库实际证据

> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

## 结论与证据范围

VERIFIED：真实N03 Home的受支持冷快照已创建，原PostgreSQL cluster没有启动；PostgreSQL15.19在隔离副本恢复、查询、正常停止。Flyway V1–V13逐条成功，script与按Flyway规则计算的CRC32全部匹配当前源码。此证据来自真实数据的副本，不是新建临时空库，不是由“存在表”推断迁移成功。

有效数据库连接：`zhiyi`，server=`15.19`，`127.0.0.1:25432`，effective role=`pg_read_all_data`，transaction_read_only=`on`。用原DPAPI密文在内存中取得连接凭据，只在BEGIN READ ONLY后SET LOCAL ROLE；业务SELECT全部由只读有效角色执行，已验证其public表INSERT/UPDATE/DELETE/TRUNCATE权限计数为0。查询后ROLLBACK；未新建角色、未执行DDL/DML、未运行应用/Flyway。

详见 `PR-TS-00B-database-evidence.json`、`PR-TS-00B-isolation-final-evidence.json` 和审计脚本的query允许集。role/schema配置检查不读取用户密码列；未输出username、UUID、正文、完整Workspace路径。

## 预检查和快照

HEAD与上一轮一致。tracked/staged diff为空；上一轮审计目录原本未跟踪，完整保留。manifest Home匹配 `default-clean-20261106`，format=zhiyi-windows-persistent-v1；PG_VERSION=15，本地二进制15.19。8个记录PID不存在、配置端口无监听，未发现其他postgres/pg_ctl进程；SQLite与OS锁文件用GENERIC_READ/OPEN_EXISTING/share=0检查，未写锁文件或重命名原目录。

源cluster的pg_controldata为`in production`且陈旧postmaster.pid存在。该状态明确为“离线、非正常关闭的恢复候选”，不是干净关闭；用户获知后授权本轮方案。未删除原PID文件、未启动原cluster、未运行pg_resetwal。副本日志证实interrupted/redo starts/redo done/ready，最终shut down；恢复写入只发生在pg-query-copy。

| 位置/范围 | 结果 |
| --- | --- |
| 真实Home | `C:\Users\LZX\AppData\Local\ZhiyiNative\default-clean-20261106` |
| 快照 | `E:\ZhiyiAudit\PR-TS-00B-20261107-r01\snapshot` |
| PG副本 | 同级 `pg-query-copy`；SQLite查询副本为 `sqlite-query-copy` |
| 私有证据 | 同级 `private-evidence`，不进桌面ZIP |
| 空间 | 预检Home约106MiB；E盘空闲约794GiB，检查至少2GiB余量 |
| 快照文件 | 2276，109592569字节；全部SHA-256匹配源集合 |
| snapshot.json SHA-256 | `9aa346a2141f5881405079eef436f1eab834aa3d6f056eb1a298904244230841` |
| 原Home校验 | 2533文件，字节哈希变化0 |
| 原PR-TS-00证据 | 34个既有manifest条目匹配；全部历史报告/清单保持原字节 |

调用现有persistent_runtime.backup函数，而非会以a+b改写控制文件的CLI入口；包装器持有已有控制文件的只读独占句柄。复用protect仅收紧新E盘目录ACL。工具排除logs/temp/webview/lifecycle.lock，备份包含其余Home数据、PG/Redis/SQLite/Checkpoint/Artifact存储、Hands ledger、uploads、environment与DPAPI密文。

**范围限制：完整性仅针对受支持Home payload，不是整机或全部项目冷备。** 两个历史外部Workspace（只标P02/P03）未被此工具包含；未复制、未修改。当前默认Home内工作区P01为空且已包含；P02顶层41项，P03顶层0项。禁止据此快照对外部项目作破坏性迁移；未来涉及外部文件写入/全产品恢复演练时必须另行纳入备份范围。本轮不涉及这些写入。

## 实际启动/查询/停止的过程

1. `python -B .../PR-TS-00B-run-isolated-audit.py` 创建并验证快照，第一次pg_ctl返回1：Windows把`''`空值参数解释成字面动态库名。该进程退出，未查询、未恢复原库。失败证据独立保留。
2. `python -B .../PR-TS-00B-run-copy-retry.py` 用`-c name=`空值重试。PostgreSQL副本已ready并完成redo；pg_ctl进程退出后，Python capture_output等待继承管道，最终TimeoutExpired。此启动器回执失败不等于数据库未启动；没有改用原库。
3. `python -B .../PR-TS-00B-complete-owned-copy.py` 验证postmaster.pid、PID创建时间、postgres.exe、命令行copy数据目录及loopback端口归属，接管**本轮已启动的同一副本**进行只读补证；随后pg_ctl fast stop返回0，端口释放，pg_controldata为shut down。原Home哈希与snapshot哈希再次通过。

这三段证据分别为isolation-evidence、isolation-attempt2-evidence、isolation-final-evidence.json，旧失败记录未覆盖。所有pg_ctl argv见这些JSON及 `PR-TS-00B-运行命令与隔离结果.md`；credentials只在进程内存，命令无密码。没有整套up/recover、没有新建cluster、没有发HTTP执行命令。

## Flyway真实history与源码比对

| version | script | 真实checksum | success | 源码CRC32匹配 |
| --- | --- | --- | --- | --- |
| 1 | V1__init_schema.sql | 172574542 | True | True |
| 2 | V2__optimize_indexes.sql | -2036900921 | True | True |
| 3 | V3__add_password_hash.sql | -666480988 | True | True |
| 4 | V4__create_user_feedback_table.sql | -1613665344 | True | True |
| 5 | V5__reconcile_legacy_schema.sql | -1846433067 | True | True |
| 6 | V6__upsert_builtin_roles.sql | -1754184888 | True | True |
| 7 | V7__add_conversation_workspace_mode.sql | 439076636 | True | True |
| 8 | V8__add_user_avatar.sql | 35128799 | True | True |
| 9 | V9__optimize_conversation_preview.sql | 938060099 | True | True |
| 10 | V10__delete_builtin_roles.sql | -872460111 | True | True |
| 11 | V11__create_iam_login_sessions.sql | -866868083 | True | True |
| 12 | V12__local_workspace_authorizations.sql | 1189611711 | True | True |
| 13 | V13__drop_user_feedback.sql | 1819505150 | True | True |


计算基于UTF-8逐行、去BOM、不计换行、CRC32有符号32位；不把SHA-256当Flyway checksum。算法核对官方[ChecksumCalculator变更源](https://github.com/flyway/flyway/pull/3764/files)。本轮独立比对成功，不等价于运行Flyway validate或完整schema validator；没有调用repair/baseline。

## 实际schema与结构证据

真实public表：conversations、flyway_schema_history、iam_login_sessions、local_workspace_authorizations、messages、roles、users；user_feedback确已不存在。取得61列、37索引、15约束定义；完整结构在database-evidence.json，未导出业务数据或schema-only dump。

V5 title/file_url/stable_key、V7 workspace_mode、V8 **avatar_url**均匹配；V12 grant unique与selected/nonrevoked部分unique存在；V11 session.user_id→users外键存在。JSONB为messages.metadata及roles的dialogue_style/personality/avatar_config。TIMESTAMP与TIMESTAMPTZ保留差异。早期辅助检查误写avatar_path而false，schema-review-evidence已按V8源码纠正；没有真实schema错配。

当前roles/conversations/messages多数关系并无数据库FK强制，与迁移SQL一致；数据孤儿计数另行查询，不能因为没有约束而假定安全。索引和约束逐定义为VERIFIED，完整等价重建/执行计划/性能仍UNKNOWN，留在repository迁移门禁。

## 匿名数据与关系完整性

| 表 | 行数 |
| --- | --- |
| users | 1 |
| roles | 0 |
| conversations | 4 |
| messages | 24 |
| iam_login_sessions | 2 |
| local_workspace_authorizations | 2 |


| 关系异常检查 | 数量 |
| --- | --- |
| conversation_owner_missing | 0 |
| conversation_owner_null | 0 |
| custom_role_owner_missing | 0 |
| custom_role_owner_null | 0 |
| conversation_role_missing | 0 |
| message_conversation_missing | 0 |
| workspace_owner_missing | 0 |
| cross_owner_custom_role | 0 |
| multiple_selected_live | 0 |
| duplicate_grant_id | 0 |
| roots_multiple_owners | 0 |
| selected_and_revoked | 0 |


所有四个Conversation属于U01；Role数0；两条Grant均属U01/UNSCOPED_SENTINEL，一条selected、一条未selected，均未revoked。Session数2只作为历史统计，不读取或输出JWT。跨SQLite身份对账见独立报告。

## 打包前结束状态补充（VERIFIED）

打包校验发现4个并发tracked删除，HEAD未变，staged为空；本轮未执行这些删除，原样保留。开始时tracked干净、结束时Dirty。详见[并发工作区变更记录](PR-TS-00B-并发工作区变更记录.md)和final-verification.json；此结束状态优先于前文生成时的Git观察。审计引用源码与旧产物哈希仍一致。

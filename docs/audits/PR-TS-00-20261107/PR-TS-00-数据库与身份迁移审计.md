# PR-TS-00-数据库与身份迁移审计

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 数据库实测结论：BLOCKED

真实 Home 的 PostgreSQL 15432 未监听，记录PID不存在。未启动数据库，未解密凭据，未运行 SELECT/pg_dump/迁移。`flyway_schema_history` 的实际版本、校验和、成功状态、实际schema、用户数、每用户Conversation/Role数、Grant/Tenant归属、selected/revoked与孤儿数量全部 **UNKNOWN/BLOCKED**。不能报告“真实库已V13”，不能以临时库、SQL文件或旧java.log替代实测。

`database-readonly-plan.sql` 为后续补证的只读事务查询计划，**本轮未执行**。只输出结构、版本、匿名U/T编号、汇总计数；不输出用户UUID、私有对话、Workspace路径或JSON正文。安全连接需在已有真实服务运行且凭据取得方式获授权后单独执行；认证失败时停止，不自动重置角色/密码。

## Flyway SQL 全量审计（VERIFIED 源码）

| 版本 | 文件/行数 | 涉及表 | 变更位置（源码） |
| --- | --- | --- | --- |
| 1 | `apps/backend/src/main/resources/db/migration/V1__init_schema.sql` (47行) | conversations;messages;roles;users | 1:CREATE TABLE;10:CREATE TABLE;24:CREATE TABLE;33:CREATE TABLE;43:CREATE INDEX;44:CREATE INDEX;45:CREATE INDEX;46:CREATE INDEX;47:CREATE INDEX |
| 2 | `apps/backend/src/main/resources/db/migration/V2__optimize_indexes.sql` (18行) |  | 1:CREATE INDEX;2:CREATE INDEX;3:CREATE INDEX;4:CREATE INDEX;5:CREATE INDEX;6:CREATE INDEX;7:CREATE INDEX;8:CREATE INDEX;9:CREATE INDEX;10:CREATE INDEX;11:CREATE INDEX;12:CREATE INDEX;13:CREATE INDEX |
| 3 | `apps/backend/src/main/resources/db/migration/V3__add_password_hash.sql` (16行) | users | 12:ALTER TABLE |
| 4 | `apps/backend/src/main/resources/db/migration/V4__create_user_feedback_table.sql` (20行) | user_feedback | 1:CREATE TABLE;14:CREATE INDEX;15:CREATE INDEX;16:CREATE INDEX;17:CREATE INDEX;18:CREATE INDEX;19:CREATE INDEX;20:CREATE INDEX |
| 5 | `apps/backend/src/main/resources/db/migration/V5__reconcile_legacy_schema.sql` (53行) | conversations;messages;roles | 11:ALTER TABLE;21:ALTER TABLE;31:ALTER TABLE;49:ALTER TABLE |
| 6 | `apps/backend/src/main/resources/db/migration/V6__upsert_builtin_roles.sql` (23行) | SET;roles | 1:UPDATE;9:INSERT INTO;15:UPDATE |
| 7 | `apps/backend/src/main/resources/db/migration/V7__add_conversation_workspace_mode.sql` (13行) | conversations | 1:ALTER TABLE;4:UPDATE;8:ALTER TABLE;12:CREATE INDEX |
| 8 | `apps/backend/src/main/resources/db/migration/V8__add_user_avatar.sql` (2行) | users | 1:ALTER TABLE |
| 9 | `apps/backend/src/main/resources/db/migration/V9__optimize_conversation_preview.sql` (2行) |  | 1:CREATE INDEX |
| 10 | `apps/backend/src/main/resources/db/migration/V10__delete_builtin_roles.sql` (5行) | roles | 5:DELETE FROM |
| 11 | `apps/backend/src/main/resources/db/migration/V11__create_iam_login_sessions.sql` (12行) | iam_login_sessions | 3:CREATE TABLE;11:CREATE INDEX;12:CREATE INDEX |
| 12 | `apps/backend/src/main/resources/db/migration/V12__local_workspace_authorizations.sql` (17行) | local_workspace_authorizations | 2:CREATE TABLE;16:CREATE UNIQUE INDEX |
| 13 | `apps/backend/src/main/resources/db/migration/V13__drop_user_feedback.sql` (4行) | user_feedback | 4:DROP TABLE |


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

证据：`apps/backend/src/main/resources/db/migration/V1__init_schema.sql:24`（`CREATE TABLE conversations`）；`apps/backend/src/main/resources/db/migration/V11__create_iam_login_sessions.sql:5`（`REFERENCES users(id)`）；`apps/backend/src/main/resources/db/migration/V12__local_workspace_authorizations.sql:16`（`CREATE UNIQUE INDEX`）。

V1对 roles.user_id/conversations.user_id/conversations.role_id/messages.conversation_id 没有声明外键；静态后续SQL未找到补齐这些关系外键的语句。故“JPA能关联”不等于不存在孤儿。V10删除内置角色可能留下历史role_id引用，真实数量 UNKNOWN。不得在迁移时自动补约束或清理这些数据。

`UserProfile` 是UserProfileService内嵌聚合对象，没有发现独立UserProfile JPA表。应迁移其userId派生关系，不能虚构一张待搬迁的profile表。JSONB必须测试对象/数组/null、Unicode和数值；uuid保持字符串；TIMESTAMP无时区不可由JS Date默认套本机时区，TIMESTAMPTZ需明确UTC偏移，逐字段冻结序列化。bigint计数转换需防精度丢失。

## LocalIdentityProvider 设计（INFERRED，未实施）

输入仅受保护的N03 Home身份配置和数据库映射；输出不可变 `ActorContext {actorId, tenantId?, subject, role, identityGeneration}`。actorId用UUID以兼容现有平台表；subject/role保持Python可信头非空，不从renderer body/header指定。不生成JWT、不读用户session、不需要密码。身份首次解析失败、配置丢失或多用户未决均fail closed，不能每次启动生成新actor或选“第一个用户”。

现有身份链：AuthenticatedUserContext → TrustedUserContextForwarder → Python InternalServiceAuthMiddleware → current_trusted_user → `_trusted_run_input` / WorkspaceAuthority.owner。证据：`apps/backend/src/main/java/com/kinlin/ai/gateway/TrustedUserContextForwarder.java:12`（`public void apply`）；`apps/agent/app/api/agentos_v2.py:251`（`"authenticatedUserId": actor.user_id`）；`apps/agent/app/execution/workspace_authority.py:46`（`def owner(actor)`）。

Tenant需区分缺失与显式值。WorkspaceAuthority.owner将空tenant归为 `__unscoped__`，但Run所有权检查保存/比较的是原始可空tenant；不要全局把header改为 `__unscoped__` 而改变历史Run比较结果。LocalIdentity必须同时冻结wire tenant值与Grant查表归一规则。

| 真库场景 | 未来迁移策略 | 阻断/回滚 |
| --- | --- | --- |
| 0用户 | 先验证没有Conversation/customRole/Grant/SQLite Run遗留owner；全空才在受控迁移事务中建立UUID actor与兼容owner记录 | 有遗留owner即BLOCKED；初始化前后冷备份；本轮不创建 |
| 1用户 | 仅在PG与SQLite/Artifact owner/tenant核对一致后，映射到原users.id作为稳定actor；不批量改历史数据 | Grant或Run有额外owner/tenant则转人工；保持原grant epoch与所有id |
| 多用户 | 输出匿名归属统计，人工选择保留隔离的多本机身份方案、指定主actor并保留其他owner档案、或另案迁移 | **不自动合并、不取首行、不重写Run owner**；需要书面决策、冲突映射、备份和验收 |

Actor映射可先在受限Home配置中保存版本、actor UUID、旧owner映射引用与database identity；映射写入/备份采用原子替换和校验，不接受请求指定路径。是否需要额外actor表留给后续显式schema PR；本轮无新schema。失去配置不能静默重建，应从受信备份恢复映射。

## Workspace Grant / Run 历史不变量

`apps/agent/app/execution/workspace_authority.py:113`（`def freeze`） 清掉客户端workspaceBinding后由权威current生成快照；`apps/agent/app/execution/workspace_authority.py:131`（`def _resolve`） 校验revoked、grantId、owner、tenant、resource、root以及目录inode身份。select遇已撤销row会生成新grant_id，使旧Run永远不能借新授权复活。TS保留Python权威，不直接写Grant表、不生成伪Grant、不把所有历史owner改成本机新UUID。

canonical_directory解析真实目录并接受当前Windows用户可访问目录，这不是OS沙箱。无登录不扩大可选目录、不绕过批准、不把旧Run绑定到当前选择。恢复过程中必须同时恢复PG权威表、Hands JSON投影、SQLite Run快照、Artifact和同一身份映射；投影不充当第二权威。

## 真库补证清单与快照条件

执行read-only plan前检查server身份/数据库名称/readonly配置；BEGIN READ ONLY内完成schema history/列/索引/外键/unique/JSONB/匿名owner/grant/孤儿/跨owner角色/多selected/多owner根统计，ROLLBACK结束。先查真实表存在性再分段执行，旧版缺表直接记录版本阻断，不能创建表补绿。

可选 `pg_dump --schema-only --no-owner --no-privileges` 仅在确认已有只读连接与安全输出目录后写系统临时目录并记SHA-256；不进Git、不含业务数据、命令行不放密码。本轮条件不满足，dump为BLOCKED。PG统计仍不足以证明SQLite/Artifact历史owner一致，后者需独立只读匿名聚合核对，不能查询或导出正文。

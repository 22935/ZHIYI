# 知弈 AgentOS Docker 基础设施重构 RFC v1.1

# Zhiyi AgentOS Docker Infrastructure Refactoring RFC v1.1

状态：冻结实施基线。当前实施范围仅为 P0/P1，不再扩展架构。

## 1. 目标与边界

以 Docker Compose 建立可审计、可迁移、可恢复的单机部署底座。明确排除 Kubernetes、MinIO、Prometheus、Grafana、Loki 和新任务队列。旧容器、旧卷、旧 Compose 与唯一数据在新架构完成迁移验证前不得删除。

阶段顺序：P0 数据备份、迁移、持久化与回滚；P1 Canonical Compose、网络、卷和环境；P2 Java AI 网关、JWT、内部令牌、SSE、Trace ID；P3 非 root、安全限制、多架构与发布；P4 迁移演练、重启、回滚和完整验收。

## 2. 数据库迁移门禁

- 全新空数据库由 Flyway 从 V1 顺序迁移，不执行 baseline。
- 已有数据库必须先生成只读 Schema 快照和 SHA-256 指纹，分类为 `legacy` 后由操作者显式提交报告 ID、指纹和识别版本进行 baseline。
- 禁止 baseline 到版本 0；生产配置永久保持 `baselineOnMigrate=false`。
- 无法确定版本、部分迁移或出现未知表/列时分类为 `drift` 并停止。
- 迁移不得用大范围 `IF NOT EXISTS` 掩盖漂移；兼容迁移必须验证既有对象定义，不匹配即失败。
- 固定内置角色使用 `stable_key` 和固定 UUID，采用受控 UPSERT。

## 3. 网络与入口

| 网络 | 属性 | 成员 |
| --- | --- | --- |
| `web-network` | internal | Frontend、Backend |
| `agent-network` | 允许外部出站，不发布 FastAPI 端口 | Backend、FastAPI |
| `data-network` | internal | Backend、PostgreSQL、Redis、迁移工具 |

Frontend 只能访问 Backend；FastAPI 不得加入 `web-network` 或 `data-network`，也不直接依赖 PostgreSQL/Redis。Backend 是唯一可同时访问 Frontend、FastAPI 和数据服务的业务服务。由于 `agent-network` 允许出站，Backend 与 FastAPI 都可能具备出站能力；P0/P1 只保证入站和容器横向访问隔离，不实现域名级出站控制。

Frontend 默认绑定 `127.0.0.1`。远程 HTTPS 网关只能绑定指定私有管理地址，防火墙变更必须先预览、备份原规则、执行验证，验证失败自动回滚，并保留人工恢复状态文件；禁止无控制绑定 `0.0.0.0`。

## 4. 持久化与实例隔离

所有环境使用不同的 `KINLIN_DEPLOYMENT_ID`。卷名固定为：

```text
${KINLIN_DEPLOYMENT_ID}_postgres_data_v11
${KINLIN_DEPLOYMENT_ID}_redis_data_v11
${KINLIN_DEPLOYMENT_ID}_agentos_data_v11
${KINLIN_DEPLOYMENT_ID}_backend_uploads_v11
${KINLIN_DEPLOYMENT_ID}_ai_cache_v11
```

卷同时写入实例标签；启动、备份、恢复检查名称、标签和数据目录 marker，禁止跨实例复用。

AgentOS Workflow Store 本阶段固定单 FastAPI 实例、单 Uvicorn worker。SQLite 启用 WAL、`busy_timeout`、`synchronous=FULL`，使用 SQLite Backup API 生成一致性副本；完成 PostgreSQL Workflow Store 前禁止水平扩容。

## 5. Secret 与运行用户

生产基线为 rootful Docker Engine；预检发现 rootless 或 userns-remap 必须拒绝。Compose 文件 Secret 是 bind mount，不依赖 Compose 的 `uid/gid/mode` 映射。Backend UID/GID 10001、FastAPI 10002、Frontend 10003、Flyway 10004。需要入口预处理的容器由最小 root 入口复制 Secret 到 tmpfs，设为目标 UID 独占读权限，验证未授权 UID 不可读后立即降权；不得回退到明文环境变量、宽松权限或 root 常驻。

PostgreSQL 使用 `POSTGRES_PASSWORD_FILE`；Redis 由入口从 `/run/secrets` 生成 tmpfs 配置后以 `redis` 用户运行；Spring Boot 读取 configtree；FastAPI 读取 `*_FILE`。

## 6. 完整备份与恢复

备份是维护窗口内的最终全量备份，不称为增量备份。写服务必须停止，范围包括：

- PostgreSQL 业务库自定义格式 dump；
- `pg_dumpall --globals-only --no-role-passwords` 全局对象；
- Backend 上传文件、AgentOS 数据、AI 缓存；
- 由 SQLite Backup API 生成的 Workflow DB 一致性副本；
- Redis 在确认 BGSAVE 成功后的 RDB；
- Schema 审计、Git/镜像/Compose 版本清单和 `SHA256SUMS`。

清单不得包含密码、角色密码哈希或可认证连接串。全局对象恢复后，必须从 Compose Secret 重设应用数据库角色密码。恢复只能进入新的实例 ID 和不存在的卷。

Redis 当前归类为可重建缓存。恢复必须核对 RDB 载入、键数量、关键键抽样读取和持久化状态；恢复失败不直接破坏源备份，可在保留失败证据后以空缓存重新预热，因此不阻断业务数据上线。

## 7. 健康与后续 P2 契约

Liveness 只检查进程自身，不依赖 PostgreSQL、Redis 或模型服务。Readiness 检查业务必要的本地持久化和数据依赖。模型 Provider 使用独立依赖检查，故障只标记 degraded，不使整个系统不可用。

P2 必须把 SSE 的 240 秒解释为空闲超时而非总时长，并实现心跳间隔、可配置最大时长、客户端取消传播，以及 Nginx—Java—Python 全链路非缓冲实测；这些不属于本轮 P0/P1 完成声明。

# 知弈 AgentOS Docker 基础设施重构完整流程

> 整合日期：2026-07-23
>
> 整合来源：`04-` 至 `09-` 共六份原始报告
>
> 冻结基线：《知弈 AgentOS Docker 基础设施重构 RFC v1.1》

---

## 概述

本次 Docker 基础设施重构自 2026-07-18 启动，至 2026-07-22 完成 Windows 开发与部署收口，历时约 4 天。重构按 P0 → P1 → P2 → P3 四个阶段依次推进，每个阶段有独立的实施、验收和门禁。

| 阶段 | 日期 | 主题 | 验收状态 |
| --- | --- | --- | --- |
| P0/P1 | 2026-07-18 | 核心基础设施：Compose、网络、卷、Secret、备份恢复、Flyway | 通过 |
| P1-Windows | 2026-07-18 | Windows Docker Desktop 本地开发环境 | 通过 |
| P2 | 2026-07-19 | AI 网关安全、SSE、Trace ID、结构化日志 | `P2_ACCEPTED_WINDOWS` |
| P3 | 2026-07-19 | 多架构容器、只读根、镜像最小化、在线/离线发布 | 实现完成，发布门禁未通过 |
| 收口 | 2026-07-19 ~ 2026-07-22 | Windows 开发优化与部署包 | `DOCKER_WINDOWS_DEVELOPMENT/DEPLOYMENT: ACCEPTED` |

---

## 1. 起点：仓库现状审计

实施起点 Git `9b34b1a`，审计发现以下核心问题：

- **Compose 定义分散**：根目录和 `docker/` 各有一套，开发/生产重复维护，网络边界和卷命名不统一。
- **Schema 漂移风险**：Flyway SQL 使用宽泛 `IF NOT EXISTS`，无法可靠暴露漂移；已有数据库无指纹审计和显式 baseline 门禁。
- **SQLite 脆弱**：AgentOS SQLite 缺少固定 WAL/busy timeout、进程级单实例门禁和可验证的一致性备份。
- **Secret 不规范**：依赖环境变量或只声明挂载，缺少运行用户实际读取验证、来源文件隔离和负向权限验证。
- **恢复闭环缺失**：未覆盖 PostgreSQL 全局对象、Redis RDB、上传文件、AgentOS 数据、版本清单和校验文件的一体化恢复。
- **Redis 定位模糊**：用于 Spring Cache、会话辅助等可重新生成数据，但未明确归类为 `rebuildable-cache`。
- **Docker Engine 安全**：rootful `/var/lib/docker`，SecurityOptions 只有 seccomp/cgroupns，无 rootless 或 userns-remap。

---

## 2. P0/P1：核心基础设施重构（2026-07-18）

### 2.1 Canonical Compose

建立唯一结构源 `compose.yaml`，消除开发/生产重复维护：

```
Frontend -- web-network(internal) -- Backend
                                        |
                                        +-- agent-network(egress) -- FastAPI
                                        |
                                        +-- data-network(internal) -- PostgreSQL / Redis / schema-tool
```

- Frontend 只加入 `web-network`，仅访问 Backend。
- FastAPI 只加入 `agent-network`，不发布端口，不解析 PostgreSQL/Redis。
- PostgreSQL 和 Redis 只加入 `data-network`，不发布宿主机端口。
- Backend 加入三个网络，是唯一可访问 FastAPI 的业务入口。

Compose 文件矩阵：

| 文件 | 用途 |
| --- | --- |
| `compose.yaml` | Canonical 基础定义 |
| `compose.dev.yaml` | 开发覆盖（源码挂载、热更新、调试端口） |
| `compose.prod.yaml` | 生产覆盖（只读根、capability 最小化） |
| `compose.observability.yaml` | 可观测性组件 |
| `docker/docker-compose.yml` | 兼容入口 → 转向 Canonical Compose |

### 2.2 卷命名与实例隔离

卷名均包含实例 ID，启动/备份/恢复均核验实例 ID、卷标签和数据 marker：

```
kinlin-test-rfc11_postgres_data_v11
kinlin-test-rfc11_redis_data_v11
kinlin-test-rfc11_agentos_data_v11
kinlin-test-rfc11_backend_uploads_v11
kinlin-test-rfc11_ai_cache_v11
```

### 2.3 Schema 指纹与 Flyway 双路径

实现 `schema_audit.py` 只读审计，将数据库分类为 `empty`、`managed`、`legacy` 或 `drift`：

- **全新数据库**：空库审计后 Flyway 从 V1 顺序执行到 V6。
- **已有数据库**：只读提取表、列、索引和 Flyway 历史，只有确定的 `legacy` 版本可进入 `baseline_existing.py`。

迁移 SQL 不再用 `IF NOT EXISTS` 掩盖漂移；生产配置固定 `baselineOnMigrate=false`。

### 2.4 Secret 权限

Compose Secret 是 bind mount。Backend、FastAPI、Flyway、PostgreSQL 和 Redis 的最小 root 入口先复制 Secret 到 tmpfs、设置独占权限、封闭来源目录，再降权：

| 服务 | 运行 UID | Secret 验证 |
| --- | --- | --- |
| Backend | 10001 | source denied, target readable, mode=0400 |
| FastAPI | 10002 | source denied, target readable, mode=0400 |
| Frontend | 10003 | — |
| Flyway | 10004 | target mode=0400 |
| PostgreSQL | 70 | source denied, target readable |
| Redis | 999 | tmpfs config readable |

### 2.5 SQLite 一致性

- `journal_mode=wal`、`busy_timeout=5000`、`synchronous=2(FULL)`、`integrity_check=ok`
- FastAPI 固定 `--workers 1`，进程锁阻止第二实例共享同一 Workflow Store
- 在线 Backup API 生成一致性副本

### 2.6 备份恢复闭环

维护窗口内生成全量备份，包含：PostgreSQL 自定义格式数据库、`pg_dumpall --globals-only` 全局对象、Backend 上传卷、AgentOS 数据卷、AI 缓存卷、SQLite Backup API 副本、Redis RDB、Schema 审计、Git/镜像/Compose 清单和 `SHA256SUMS`。

恢复经历 5 次演练迭代，分别修复了 SQLite WAL 只读挂载、PostgreSQL bootstrap 角色、Redis AOF 优先级等问题。第 6 次恢复使用全新实例 ID 和 Secret/卷完成隔离恢复，全部校验通过。

### 2.7 测试结果

| 验收项 | 结果 |
| --- | --- |
| Python/基础设施测试 | 19 passed |
| Backend Maven | 109 tests, 0 failures |
| Frontend | vue-tsc + vite build 通过 |
| Compose | 四组 config --quiet 通过 |
| 五服务启动 | 全部 healthy |
| 网络负向测试 | Frontend 仅有 web; FastAPI 仅有 agent; FastAPI→Backend TCP 拒绝 |
| 备份恢复 | 第六个全新实例完整恢复成功 |
| Secret 负向测试 | 所有运行 UID 均不能读取 `/run/secrets` 原文件 |

---

## 3. P1-Windows：Docker Desktop 本地开发环境（2026-07-18）

### 3.1 Windows Compose 合并结构

```
docker compose -f compose.yaml -f compose.dev.yaml -f compose.windows.yaml --env-file .env.windows up -d --build
```

等价包装脚本：`.\scripts\infra\windows\up.ps1`

网络拓扑新增 Windows 专用 ingress：

```
Host 127.0.0.1:18088
  └─ windows-ingress-network (non-internal)
       └─ Frontend
            └─ web-network (internal) ─ Backend
                 Backend ─ agent-network (egress) ─ FastAPI
                 Backend ─ data-network (internal) ─ PostgreSQL / Redis
```

`debug-ports` profile 通过独立代理临时发布调试端口，关闭 profile 后不可达。

### 3.2 热更新与构建缓存

Docker Desktop bind mount 存在文件事件丢失问题，改为可配置 polling：

| 项目 | 实测结果 |
| --- | --- |
| Vue/Vite 修改感知 | 408 ms |
| FastAPI 自动 reload | 365 ms |
| Spring Boot 重启 | 优化后约 67.3 s（应用启动 4.834 s），跳过 test compile |
| 无源码变更暖构建 | 4.8 s |
| 普通源码变更构建 | 10.1 s |

缓存策略：Frontend 依赖目录用 Docker named volume；Maven repo、Backend target、Python venv、pip cache 均使用实例命名卷。

### 3.3 PowerShell 脚本清单

| 脚本 | 用途 |
| --- | --- |
| `preflight.ps1` | 环境预检 |
| `up.ps1` | 启动五服务 |
| `down.ps1` | 停止并移除容器/网络，默认不删卷 |
| `restart-service.ps1` | 重启指定服务 |
| `logs.ps1` | 查看服务日志 |
| `status.ps1` | 显示实例和服务状态 |
| `clean-build-cache.ps1` | 清理构建缓存（不清理数据卷） |
| `diagnose.ps1` | 生成脱敏诊断包 |
| `remove-data-volumes.ps1` | 独立危险操作，需二次确认 |

### 3.4 数据卷隔离验证

第二实例 `kinlin-win-p1-002` 的 PostgreSQL 探针用户数为 0，而主验收实例中探针用户存在，证明数据卷没有共享。

---

## 4. P2：AI 网关安全与可观测性（2026-07-19）

### 4.1 现状审计发现

1. Java 曾对 `/ai/core/**` 匿名放行
2. Java 到 Python 内部令牌、用户头和 Trace 注入未统一
3. Python 可读内部令牌配置但业务路由未强制验证
4. 普通代理错误被包装为 HTTP 200
5. SSE 的 240 秒总时长可能丢弃心跳，客户端取消未完整传播
6. Trace ID、MDC/ContextVar 和生产 JSON 日志未形成全链路

### 4.2 安全设计

**统一鉴权链**：

```
Client → Nginx/Vite → Spring Boot (JWT 认证) → FastAPI (内部令牌)
```

- 所有 `/ai/**` 在 Java 要求合法 JWT；匿名请求返回 401
- Java 从 `Authentication` 构造 `AuthenticatedUserContext`，不从客户端身份头生成
- `SensitiveIdentityHeaderFilter` 删除客户端身份头和内部令牌
- Java 到 Python 统一使用 `X-Internal-Service-Token`，从 configtree Secret 读取
- Python 使用常量时间比较验证内部令牌；缺失 401，错误/空值/重复头 403
- Python 健康端点例外，业务端点同时要求内部令牌和完整可信用户上下文
- Java 只转发受控请求头，目标基址固定，避免 SSRF

**实测 HTTP 证据**：

```
unauth_ai_status=401
proxy_upstream_200=200
proxy_upstream_401=401 / 403=403 / 500=502
trusted_user_matches_jwt=True
forged_role_rejected=True
direct Python business endpoint=401
direct Python health endpoint=200
```

### 4.3 SSE 网关

- 事件格式：`text/event-stream`、`data:`、空行分隔、`[DONE]` 结束
- Python 默认心跳间隔 15 秒；Java 和 Nginx 不缓冲、不吞心跳
- `SSE_IDLE_TIMEOUT=240000ms` 空闲超时，事件或心跳重置计时
- `SSE_MAX_DURATION=1800000ms` 可配置总时长上限
- 客户端关闭 → Java Reactor 取消上游 → Python `request.is_disconnected()` → 任务状态清理

**实测证据**：

```
短时正常流：HTTP 200，首包约 629ms，[DONE]=true
默认心跳：15 秒间隔通过
客户端取消：Python state=cancelled
生产 Nginx 长流：267.4 秒，49 个心跳，[DONE]=true
```

### 4.4 Trace ID 与结构化日志

**全链路 Trace ID 贯穿 Nginx → Java → Python**：

- Nginx 接受合法 UUID/32 hex，否则生成受控 `$request_id`
- Java 写 MDC，响应及 Python 请求使用同一值，finally 清理
- Python ASGI Middleware 用 ContextVar 覆盖整个请求和 SSE 生成器生命周期
- 16 路并发单元测试无串号

**结构化日志固定字段**：`timestamp`、`level`、`service`、`trace_id`、`workflow_id`、`task_id`、`message`、`exception`

**脱敏**：Authorization、Cookie、JWT、内部令牌、模型 Key、数据库/Redis 密码不记录。

### 4.5 测试结果

| 范围 | 结果 |
| --- | --- |
| Python 全量 | 134 passed, 1 skipped |
| Backend Maven | 129 tests, 0 failures |
| Frontend | 3469 modules transformed |
| 基础设施 | 20 passed |
| 泄漏扫描 | 已知 Secret/JWT 命中均为 0 |

### 4.6 关键修复

1. 全局 RestTemplate Customizer 错误注入内部令牌到 `TestRestTemplate`，修复为仅在 `AgentGatewayService` 的 Python RestTemplate 上注入后，129/129 通过。
2. Chroma 测试隔离：`agentos.adapters.retrieval.chroma_client` 在模块导入阶段创建全局 `PersistentClient`，默认打开仓库 tracked 数据库。修复为测试收集前将 `AGENT_CHROMA_PATH` 指向独立临时目录。

---

## 5. P3 实施前只读审计（2026-07-19）

### 5.1 镜像现状

| 服务 | 生产基础镜像 | 阶段 | 当前架构 |
| --- | --- | --- | --- |
| Frontend | build=`node:24-alpine` / runtime=`nginx:alpine` | 多阶段 | linux/amd64 |
| Backend | build=`maven:3.9-eclipse-temurin-17` / runtime=`eclipse-temurin:17-jre-alpine` | 多阶段 | linux/amd64 |
| FastAPI | `python:3.14-slim` | 单阶段 | linux/amd64 |

### 5.2 跨架构阻断项

| 问题 | 影响 | 解决方案 |
| --- | --- | --- |
| Temurin Alpine JRE 17 只有 amd64 | ARM64 阻断 | 换 `17.0.19_10-jre-jammy` |
| Flyway Alpine 9.22.3 只有 amd64 | ARM64 阻断 | 换同版本非 Alpine 多架构标签 |
| Netty native epoll x86_64 classifier | ARM64 加载失败 | 排除 native classifier，回退 NIO |
| Python 无 lock/哈希 | 跨平台不可重复 | 新增跨平台 hash lock |
| 构建依赖 Docker Hub/npm/Maven/PyPI | 离线不可用 | 固定版本+digest |

### 5.3 Python 3.14 双架构 wheel 审计

PyPI 审计确认：NumPy、Pandas、lxml、psutil、PyYAML、uvicorn 原生链、Pydantic core、ONNX Runtime、tokenizers、grpcio、orjson 等关键依赖均在 CP314 amd64 和 aarch64 wheel。当前 3.14 依赖链存在双架构 wheel，不需要降到 3.13。

### 5.4 镜像安全门禁设计

- 默认门禁：Critical=0；High 必须有版本化豁免
- 生成 SPDX SBOM
- 记录镜像 digest
- 已知 Secret 和模式扫描=0
- 扫描器不可用或数据库更新失败时发布失败

### 5.5 构建可重复性

- Frontend：`package-lock.json` lockfileVersion=3，含 386 个 integrity
- Python：需新增跨平台 hash lock，安装固定 `--require-hashes --only-binary=:all:`
- Maven：由 Spring Boot 3.2.0 BOM 管理，无 SNAPSHOT/动态版本
- 基础镜像：采用可读精确版本标签 + manifest digest 双重记录

### 5.6 离线发布设计

```
kinlin-ai-<version>-linux-<arch>/
  VERSION
  manifest.json
  SHA256SUMS
  compose/compose.yaml
  compose/compose.prod.yaml
  config/.env.prod.example
  config/secrets/README.md
  images/<service>.tar.gz
  sbom/<service>.spdx.json
  scripts/{preflight,install,upgrade,rollback,backup,restore,diagnose}.sh
  docs/DEPLOYMENT.md
```

- amd64/arm64 独立包
- 每镜像独立 `docker save` tar 后 gzip
- preflight 同时比较 `uname -m`、Docker architecture 和 manifest architecture
- 安装固定 `docker compose --pull never --no-build up -d`
- 打包 allowlist 扫描，拒绝 `.env`、`.secrets`、数据库文件等

---

## 6. P3：多架构容器与发布实施（2026-07-19）

### 6.1 最终状态

```
P3_ACCEPTED_WINDOWS_AMD64: NOT_ACCEPTED
P3_MULTIARCH_BUILD_ACCEPTED: NOT_ACCEPTED
P3_PRODUCTION_ACCEPTED: NOT_ACCEPTED
P3_ARM64_NATIVE_RUNTIME: BLOCKED_EXTERNAL_ENVIRONMENT
P1.5-Linux: BLOCKED_EXTERNAL_ENVIRONMENT
```

未接受原因（fail-closed 门禁按预期生效）：
1. Trivy 发现 Backend 7 个、AI 4 个、PostgreSQL 1 个 Critical；High 存在且豁免文件为空
2. P3 Flyway 多架构基线无法从 Docker Hub 完成构建（IPv6 网络不可达）
3. 当前 Buildx builder 仅报告 `linux/amd64`，无 QEMU arm64 或原生 arm64 node
4. 无远程原生 arm64 Linux/麒麟环境

### 6.2 实施内容

**镜像和依赖基线**：
- `VERSION` 为发布语义版本权威来源
- 六个基础镜像记录可读精确版本和 manifest digest
- Docker Official Images 改用可达的 Public ECR 镜像源
- Python 使用 `requirements.in` 加 3548 行全哈希 `requirements.lock`，安装固定 `--require-hashes --only-binary=:all:`
- Maven 排除 x86_64/macOS Netty native classifier

**只读根和权限最小化**：
- 六个服务生产覆盖均启用 `read_only: true`、`no-new-privileges: true` 和 `cap_drop: ALL`
- Frontend 无额外 capability；五个 Secret/降权入口只临时加入 `CHOWN,DAC_OVERRIDE,FOWNER,SETGID,SETUID`
- Nginx 只写 `/tmp`；Backend 保留 uploads volume 和 `/tmp`；AI 保留 data/cache volumes 和 `/tmp`

**Buildx Bake**：
- 单一 `docker-bake.hcl` 是发布构建定义
- 目标：`frontend`、`backend`、`ai-service`、`postgres`、`redis`、`flyway`、`all`、`release-amd64`、`release-arm64`、`release-multiarch`
- 三种架构组继承同一服务 Dockerfile
- 发布目标启用 SBOM 和 provenance attestation，禁止 `latest`

**在线发布流程**：
1. 先推不可变 `sha-<12>` 多架构标签，取得 digest
2. 逐平台生成 SBOM/漏洞报告并执行 Secret 门禁
3. 全部通过后 `imagetools create` 提升语义版本标签
4. `manifest.json` 最后生成，只有 complete manifest 表示版本可用

**离线发布**：
- amd64/arm64 独立包，默认每镜像独立 gzip tar
- release Compose 用 `!reset null` 删除 build 段，只接受六个显式镜像引用
- 安装/升级固定使用 `up --pull never --no-build`
- 回滚只在 manifest 声明 Schema 兼容时切旧镜像，不反向迁移、不删除卷
- 备份/恢复 helper 复用包内镜像，不依赖浮动公网镜像

**已退役**：四个旧发布入口（使用浮动版本、在线安装 Docker 或生成破坏性流程）。

### 6.3 漏洞门禁结果

| 镜像 | Critical | High | 主要 Critical |
| --- | ---: | ---: | --- |
| Frontend | 0 | 9 | 无 |
| Backend | 7 | 42 | Tomcat 10.1.16、PostgreSQL JDBC 42.6.0、Spring Security Web 6.2.0 |
| AI | 4 | 9 | Debian perl-base 3 项、ChromaDB 1.5.9 1 项 |
| PostgreSQL | 1 | 16 | 镜像内 gosu Go stdlib |
| Redis | 0 | 0 | 无 |

这些 Critical/High 正确阻止了发布通过，不在容器重构内静默升级。

### 6.4 Windows amd64 运行证据

隔离 deployment `p3-hardening-001` 验证：
- 五服务 healthy；PID 1 UID 分别为 10003、10001、10002、70、999
- 五个进程 `CapEff=0`，根文件系统均只读
- Backend/AI 业务 UID 无法读 `/run/secrets` 源文件
- AI 网关 smoke HTTP 200；生产 OpenAPI 无测试端点

---

## 7. Windows 开发与部署收口（2026-07-19 ~ 2026-07-22）

### 7.1 最终结论

```
DOCKER_WINDOWS_DEVELOPMENT: ACCEPTED
DOCKER_WINDOWS_DEPLOYMENT: ACCEPTED
LINUX_KYLIN_SUPPORT: DEFERRED
ARM64_SUPPORT: DEFERRED
ENTERPRISE_SECURITY_GATE: DEFERRED
```

范围限定 Windows 11 + Docker Desktop + `linux/amd64`，不涵盖 Linux、麒麟、ARM64 或企业正式安全审批。

### 7.2 Windows 开发优化（2026-07-22）

**关键性能提升**：将 Backend 源码从 Windows bind mount javac 全量编译，改为 rsync 到 Linux named volume 后编译：

| 阶段 | 优化前 | 优化后 |
| --- | --- | --- |
| Backend javac（139 文件） | 约 64.4 秒（bind mount） | 4.61 秒（named volume） |
| Spring Boot started | 约 88.6 秒 | 19.64 秒 |
| 五服务 Compose readiness | 约 99.5 秒 | 19.94 秒 |

**源码同步机制**：
- 宿主 `backend/src` 只读挂载到 `/kinlin-host/backend-src`
- `/app/src` 是 deployment 独立、`nocopy` 的 named volume
- 容器启动与 `restart-service.ps1` 调用同一个加锁 rsync 脚本（`rsync -rltc --delete`）
- 无变化时跳过 Maven；新增/修改时增量编译；删除时先清理再编译

**五个规定场景实测**：

| 场景 | 结果 |
| --- | --- |
| 空缓存首次启动 | 19.94 秒 ready |
| 无修改重启 | 跳过 Maven，2.64 秒完成 |
| 单 Java 文件修改 | 10.81 秒恢复 ready |
| 新增 Java 文件 | 12.56 秒恢复 ready |
| 删除 Java 文件 | 12.83 秒恢复 ready |

### 7.3 简易部署包

```
artifacts/windows/kinlin-ai-windows-amd64/
  compose.yaml
  compose.windows.prod.yaml
  .env.example
  images.tar (809,601,536 bytes)
  migrations/
  .kinlin/
  start/stop/status/logs/backup/restore scripts
  README.md
```

**包安全扫描**：真实 `.env`、Secret、数据库/SQLite/RDB、上传、测试数据、`node_modules`、Maven `target`、Python venv 命中数均为 0。

### 7.4 部署验收

| 验收项 | 结果 |
| --- | --- |
| 包启动（`--pull never --no-build`） | 通过 |
| 五服务 healthy | 源/恢复实例均通过 |
| AI 网关 smoke | HTTP 200 |
| SSE 短流 | 6 个事件 + `[DONE]` |
| 容器重启持久化 | 数据完整保留 |
| 备份 | Schema managed, SHA256SUMS 生成 |
| 恢复 | 校验和通过，数据完整恢复到新 ID |
| 泄漏扫描 | 已知 Secret/JWT 0 |

### 7.5 保留边界

- Secret、JWT、内部令牌、模型 Key、数据库/Redis 密码只通过 Secret 文件进入运行时
- Java 仍是客户端可见 AI 请求的统一鉴权边界
- 普通停止和备份脚本不删除卷
- 恢复拒绝覆盖已有 target volume，要求新 deployment ID
- `KINLIN_DEPLOYMENT_ID` 决定独立容器、网络和数据卷
- 未修改冻结的数据迁移语义、Workflow Store 架构或数据库权威数据

---

## 8. 关键文件修改汇总

### Compose & 基础设施
`compose.yaml`、`compose.dev.yaml`、`compose.prod.yaml`、`compose.windows.yaml`、`compose.windows.prod.yaml`、`compose.observability.yaml`、`.env.example`、`.env.windows.example`、`.dockerignore`

### AgentOS / FastAPI
`agentOS/src/agentos/stores/sqlite_workflow_store.py`、`agent/app/execution/instance_lock.py`、`agent/app/execution/runtime.py`、`agent/app/operations/workflow_backup.py`、`agent/app/security/internal_auth.py`、`agent/app/middleware/trace.py`、`agent/app/observability/context.py`、`agent/app/config.py`、`agent/app/main.py`、`agent/Dockerfile`、`agent/Dockerfile.dev`、`agent/docker-entrypoint.sh`

### Backend
`backend/pom.xml`、`backend/src/main/resources/application*.yml`、`HealthController.java`、`SecurityConfig.java`、`JwtAuthenticationFilter.java`、`FilterConfig.java`、`InterceptorConfig.java`、`WebClientConfig.java`、`SensitiveIdentityHeaderFilter.java`、`TraceIdFilter.java`、`AiGatewayHeaders.java`、`AiInternalServiceToken.java`、`PythonServiceAuthentication.java`、`TrustedUserContextForwarder.java`、`AiProxyService.java`、`AiSseGatewayService.java`、`AiServiceProxyController.java`、`AgentOsGatewayService.java`、`GlobalExceptionHandler.java`、`TraceContext.java`、`LogRedactor.java`、`logback-spring.xml`、`backend/Dockerfile`、`backend/Dockerfile.dev`、`backend/docker-entrypoint.sh`

### Frontend / Nginx
`frontend/Dockerfile`、`frontend/Dockerfile.dev`、`frontend/nginx.conf`、`frontend/nginx-main.conf`、`frontend/vite.config.ts`、`frontend/src/services/api/agentos.ts`、`frontend/src/services/api/conversation.ts`、`frontend/src/stores/chat.ts`、`frontend/src/utils/request.ts`

### 数据库迁移
`V1__init_schema.sql` ~ `V6__upsert_builtin_roles.sql`、`docker/flyway/Dockerfile`、`docker/flyway/entrypoint.sh`

### Docker 辅助镜像
`docker/postgres/Dockerfile`、`docker/postgres/secret-entrypoint.sh`、`docker/postgres/init-app-role.sh`、`docker/redis/Dockerfile`、`docker/redis/entrypoint.sh`、`docker/redis/healthcheck.sh`、`docker/debug-proxy/Dockerfile`

### 发布构建
`docker-bake.hcl`、`VERSION`、`requirements.lock`、`check_builder.py`

### 运维脚本
`scripts/infra/`：`common.py`、`init_secrets.py`、`preflight.py`、`schema_audit.py`、`baseline_existing.py`、`backup.py`、`restore.py`、`firewall.py`
`scripts/infra/windows/`：`_common.ps1`、`preflight.ps1`、`up.ps1`、`down.ps1`、`restart-service.ps1`、`logs.ps1`、`status.ps1`、`clean-build-cache.ps1`、`diagnose.ps1`、`remove-data-volumes.ps1`、`clear-backend-source-cache.ps1`
`scripts/release/`：打包、preflight、安装、升级、回滚、备份、恢复、诊断

---

## 9. 测试门禁汇总

| 门禁 | 最终结果 |
| --- | --- |
| Python Agent 全量 | 134 passed, 1 skipped |
| Backend Maven 全量 | 129 passed |
| Frontend 类型检查和构建 | vue-tsc + Vite build 通过 |
| 基础设施测试 | 35 passed |
| 发布脚本测试 | 14 passed |
| Compose config --quiet | 5 组全部通过 |
| 五服务健康 | 全部 healthy |
| 泄漏扫描 | 已知 Secret/JWT/Internal Token/模型 Key 命中均为 0 |
| Bake --print | 5 个 group 通过 |

---

## 10. 持续阻塞项

| 阻塞项 | 状态 | 说明 |
| --- | --- | --- |
| P1.5-Linux | `BLOCKED_EXTERNAL_ENVIRONMENT` | 缺少麒麟/Linux 目标主机、SSH、真实网关来源 |
| P3 ARM64 Native | `BLOCKED_EXTERNAL_ENVIRONMENT` | 无远程原生 ARM64 Linux/麒麟环境 |
| P3 发布门禁 | 未通过 | Critical/High 漏洞待修复或豁免；Flyway 多架构不可达 |
| 企业安全审批 | DEFERRED | 不在当前范围 |
| P4 生产迁移 | 未开始 | 真实旧数据副本迁移、生产级故障注入、回滚时限和完整验收 |

---

## 11. 提交历史

| Commit | Message |
| --- | --- |
| P0/P1 系列 | Docker 基础设施重构：Canonical Compose、网络、卷、Secret、Flyway、备份恢复等 |
| `011c93a` | `feat(ai-security): 建立 Java 与 Python 内部服务认证` |
| `c2b9480` | `fix(auth-gateway): 统一 AI 请求身份与可信用户上下文` |
| `cc55249` | `feat(ai-proxy): 统一普通 AI 请求网关和错误传播` |
| `ca89fa4` | `feat(sse-gateway): 实现 Java SSE 心跳超时与取消传播` |
| `49dc899` | `feat(observability): 增加 Trace ID 和结构化日志` |
| `5378dfc` | `fix(ai-security): 限定内部令牌注入到 Python 客户端` |
| `60a5a0d` | `test(ai-gateway): 完成 AI 网关端到端安全验收` |
| `8285fe5` | `test(agent-storage): 隔离 Chroma 测试数据写入` |
| `70555d3` | `docs(infrastructure): 完成 P3 实施前只读审计` |
| `190856d` | `build(containers): 固定多架构镜像与依赖基线` |
| `5078a49` | `security(containers): 启用只读根与最小权限运行` |
| `4b938c9` | `build(release): 增加多架构 Buildx Bake 目标` |
| `81a173c` | `feat(release): 增加在线发布与镜像安全门禁` |
| `4b7c66d` | `feat(release): 增加离线发布与升级回滚工具` |
| `a5edc2e` | `security(ai-image): 排除运行数据与历史签名 URL` |
| 收口系列 | Windows 开发优化（rsync 源码缓存）、部署包生成与验收 |

# Resource Plane

资源器把执行需求转换为一个可审计、已确认容量的资源绑定。它维护 Node、Runtime、模型端点、健康、凭据与观测事实；调度器负责资格判断、端边云放置、租约申请和绑定冻结；实际执行由 Runtime 与 adapter 完成。

## 目录结构

```text
components/resource/
├── __init__.py                         # 稳定公共 API 聚合
├── errors.py                           # 资源应用用例异常
├── README.md
├── application/
│   ├── __init__.py
│   └── resource_plane.py               # 资源事实与登记/观测用例
├── contracts/
│   ├── __init__.py
│   ├── resource.py                     # 跨组件资源合同的本地入口
├── domain/
│   ├── __init__.py
│   ├── algorithms.py                   # EMA、健康/可用性纯算法
│   ├── credentials.py                  # 凭据记录值对象
│   ├── models.py                       # 带版本快照、健康/候选投影
│   ├── node_health.py                  # Node 健康推导
│   └── runtime_health.py               # Runtime 健康与可靠性投影
├── ports/
│   ├── __init__.py
│   ├── health_store.py                 # 健康状态持久化接口
│   ├── node_store.py                   # Node 持久化接口
│   ├── runtime_store.py                # Runtime/模型/凭据持久化接口
│   └── secret_box.py                   # 密钥加解密接口
├── infrastructure/
│   ├── __init__.py
│   ├── health_store.py                 # 健康状态内存/SQLite 实现
│   ├── node_store.py                   # Node 内存/SQLite 实现
│   ├── runtime_store.py                # Runtime 内存/SQLite 实现
│   ├── crypto/
│   │   └── fernet_secret_box.py        # Fernet 密钥盒
│   ├── signing/
│   │   ├── __init__.py
│   │   └── request_authenticator.py    # HMAC、新鲜度和 nonce 校验
│   └── sqlite/
│       ├── __init__.py
│       └── connection.py               # SQLite 连接配置
├── runtime/
│   ├── __init__.py
│   ├── embedded_runtime.py             # 进程内 Agent 能力投影
│   └── local_runtime.py                 # 本机 Runtime 注册与健康投影
└── scheduler/
    ├── __init__.py
    ├── binder.py                        # 候选评估、租约确认、绑定冻结
    ├── leases.py                        # 租约协调器与容量视图
    ├── models.py                        # 调度决策、拒绝原因和结果模型
    └── placement_policy.py              # Device/Edge/Cloud 软偏好

../contracts/resource/                  # 仓库级权威资源合同定义
../contracts/resource_signing.py        # 仓库级权威签名规范
../adapters/resource_execution.py       # 执行适配器，不属于资源器目录
../runtime/binding.py                   # 需求生成，不属于资源器目录
```

`components/resource/contracts/` 是方便资源部件内部使用的合同入口；跨组件合同的权威定义位于 `contracts/resource/` 和 `contracts/resource_signing.py`（均相对 `src/`）。不要在两处复制模型定义。

## 分层职责与依赖

| 层 | 应承载的内容 | 本目录中的主要文件 | 不应承载的内容 |
|---|---|---|---|
| `contracts` | 稳定的跨层/跨组件数据形状和协议入口 | `resource.py`、`resource_signing.py` | 存储、业务流程和具体调度算法 |
| `application` | 资源登记、凭据生命周期、状态观测等用例编排和资源事实查询 | `resource_plane.py` | SQL 语句、HTTP 处理、候选排序 |
| `domain` | 值对象、内部投影、健康推导及可独立验证的业务计算 | `credentials.py`、`models.py`、健康与算法模块 | 网络、数据库连接及框架生命周期 |
| `ports` | 应用层需要的存储和密钥能力接口 | `*_store.py`、`secret_box.py` | 内存/SQLite/Fernet 实现 |
| `infrastructure` | 端口实现、SQLite 访问、加密、请求身份验证 | `*_store.py`、`sqlite/`、`crypto/`、`signing/` | 资源优先级裁决、工作流状态推进 |
| `runtime` | 把本机或进程内可执行对象登记/投影为 Runtime 资源 | `local_runtime.py`、`embedded_runtime.py` | 为某次任务最终选定资源 |
| `scheduler` | 资格检查、候选评分、容量租约、执行绑定和续租 | `binder.py`、`leases.py`、`placement_policy.py` | 持久化资源事实、实际执行任务 |

依赖原则：

```text
runtime / scheduler / adapters -> application -> ports
                                      |             ^
                                      v             |
                                    domain <- infrastructure
```

基础设施实现端口并可使用领域值对象；领域规则不依赖具体存储。调度器通过应用层读取资源事实，通过租约协调器原子确认容量。`__init__.py` 只聚合公开 API；旧的顶层转发模块已移除，新代码和测试应使用明确的分层路径。

## 调度核心

一次调度遵循不可颠倒的四阶段：

1. **硬约束准入**：`ResourceBinder.evaluate()` 对每个 Runtime 检查启用状态、健康状态、能力、Runtime 类型、允许/排除列表、placement、trust、数据域/区域、Owner Scope、标签、成本/延迟边界、Node 算力和远程执行策略。任一硬约束失败即拒绝，不允许评分或路由提示将其翻盘。
2. **软排序**：只给合格候选计算确定性分数。当前因子包括可靠性、可用槽位比例、空闲度、延迟、成本、显式偏好、端边云层级和受限 routing prior。排序最终以资源 ID 稳定打破平分。
3. **租约确认**：`bind_ready()` 按排序结果逐个申请容量租约。RuntimeSnapshot 的 available slots 是遥测，不是并发容量的权威账本；并发占用由 LeaseCoordinator 决定。冲突时继续尝试下一候选。
4. **复核并冻结**：取得租约后重新读取 Runtime 快照，版本未变化才建立 `ExecutionBinding`，绑定中固定资源、Node、快照版本和租约版本；快照已变化则释放租约并尝试其他候选。

没有合格 Runtime 或没有满足需求的模型端点属于永久配置缺口，`bind_ready()` 返回 `rejected`，执行流程立即报错；只有暂时没有租约容量才返回 `queued` 并进入有界等待。

默认 placement 软偏好定义于 `scheduler/placement_policy.py`：Device `1.0`、Edge `0.5`、Cloud `0.0`，评分权重 `0.15`。因此默认是“端优先、边缘次选、云端兜底”，但这不是硬路由：硬约束只剩 Cloud 时仍可选 Cloud；端资源无租约容量时可继续尝试 Edge/Cloud。

资源接入时，`placement` 描述物理/信任位置，`provider`、`sourceType` 和 `adapter` 描述厂家、来源与协议适配器；三者正交。厂家扩展参数放在 `metadata`，不得把厂商字符串直接解释成能力、信任或准入许可。远程 Node 可登记为 Device、Edge 或 Cloud，但远程 Device 不得自称 `host_trusted`；是否属于远程执行由 Runtime endpoint 决定，不能由 Device placement 绕过远程执行策略。当前远程 Agent 步骤执行 adapter 仅实现 HTTP(S) `agentos_http`，模型推理 adapter 实现了签名 OpenAI Compatible `agentos_model_http`（固定调用 `/v1/chat/completions`）；gRPC、MCP、Kubernetes 等来源可以登记为元数据，但要实际调度执行仍需对应协议 adapter，未知协议不可被当成已可调用资源。

模型路由可通过 `ModelDemand` 的 endpoint/provider/model allowlist 与 denylist 约束候选；供应商匹配不区分大小写，`provider/model` 与模型短名均可用于模型筛选。任意已登记的 `MODEL_SERVER`（本机或远程）只要声明 `provider` 和 `modelId`，资源器就会为每个模型创建绑定到该 Runtime 的 `ModelEndpointProfile`；Runtime、宿主 Node 停用或健康未知/离线时，这些承载端点不会参与路由。Runtime 承载端点从宿主继承 `ownerScope`，带 `ExecutionRequirement.ownerScope` 的请求只能使用同一归属范围的端点；没有归属范围的模型注册表端点表示显式共享服务。模型注册表同步必须显式传入 `placement`，不允许依据厂商名称推断端、边或云位置。

## 一次完整请求的数据变化

```text
BindingManifest
  -> runtime/binding.py
  -> ExecutionRequirement（声明能力与边界，不指定资源）
  -> ResourceBinder.evaluate()
  -> CandidateDecision[]（硬约束拒绝原因 / 合格候选分数）
  -> LeaseCoordinator.acquire()
  -> 复核 RuntimeSnapshot.version
  -> ExecutionBinding（资源、Node、快照版本、租约版本被冻结）
  -> adapters/resource_execution.py
  -> 本地 Runtime 或签名远程请求
  -> AgentOutput / ResourceExecutionError
  -> ResourcePlane.observe_execution()
  -> RuntimeHealth 与 RuntimeSnapshot 更新
  -> Lease release 或到期
```

已绑定的远程模型端点不会再按同名 `provider/model` 回查全局模型注册表，实际推理路径如下：

```text
ExecutionBinding.modelBinding.endpointId
  -> ACGExecutionService._resource_model_runtime()
  -> ResourcePlane（读取冻结端点与承载 Runtime）
  -> adapters/resource_model_execution.py
  -> 签名 POST <Runtime endpoint>/v1/chat/completions
  -> StructuredGenerationResult / ModelInvocationError
  -> ResourcePlane.observe_execution(runtimeId, success, latencyMs)
```

`agentos_model_http` 仅适用于 `MODEL_SERVER`。适配器固定目标路径、忽略登记地址中的查询与片段，并对直接登记为 `/v1` 或完整 `/v1/chat/completions` 的 OpenAI Compatible 地址归一化，防止路径重复拼接。观测只写成功状态和时延，不记录提示词、请求体或模型响应。其他协议（例如 gRPC、MCP、厂商 SDK）必须各自实现 adapter 后，才可作为实际推理目标。

## 资源商店边界

平台本地资源商店位于相邻的 `components/marketplace/`，它是安装控制面，不属于 Resource Plane 的领域模型。商店负责受控目录、安装任务、包校验、受控进程生命周期和用户已有本地服务的接入；资源器只接收已启动的 Runtime，维护其健康、容量和调度事实。

```text
CatalogItem / CustomResourceRequest
  -> InstallationJob
  -> checksum validation / loopback endpoint validation
  -> LocalLauncher (only catalog-managed packages)
  -> ResourcePlane Runtime registration
  -> health check
  -> ResourceBinder candidate
```

`CatalogItem`、处于 `queued`、`installing`、`registering`、`uninstalling` 或 `failed` 的 `InstallationJob` 都不是调度候选。只有任务进入 `running`，且 Runtime 已成功登记并通过健康检查，`ResourceBinder` 才会将其纳入资格判断。停止或卸载会先撤销 Runtime 和模型端点，使其立即退出候选集合；目录任务本身不能绕过 Resource Plane 直接被调度。

首期目录仅从平台维护的本地 JSON 目录和受控 ZIP 包读取，包路径必须落在配置的本地包根目录，并由 SHA-256 校验。自定义资源不接受 shell command：用户只能登记已在本机运行的 `localhost`、`127.0.0.1` 或 IPv6 回环 HTTP(S) 服务。模型服务使用 `agentos_model_http` 时，登记成功后可进入模型端点资源目录；其他协议仍需对应执行 adapter 才能实际调用。

几个关键对象不可混用：

| 对象 | 代表什么 | 生命周期/权威性 |
|---|---|---|
| `RuntimeProfile` | 资源静态身份、能力、位置、来源/厂商/适配器、端点和容量声明 | 登记后持续存在；静态资源事实 |
| `RuntimeSnapshot` | 可用槽位、利用率、心跳等动态观测 | 有观测序号与存储版本；遥测，不负责并发占位 |
| `CandidateDecision` | 一次需求下的资格结果、原因和分数 | 单次评估结果，不是预留 |
| `ResourceLease` | 某次执行尝试占用的容量 | 并发容量权威；需要释放或到期 |
| `ExecutionBinding` | 本次尝试被冻结的执行目标 | 执行侧依据，不应在执行中重新路由 |

远程执行使用 credential ID、时间戳、nonce 和 HMAC-SHA256 请求体签名。接收侧依序校验身份、时间窗、签名，最后原子消费 nonce；校验失败不消费 nonce。明文密钥仅在签发/轮换时返回，持久化保存摘要与加密密文。

## 观测反馈

执行结果经 `ResourcePlane.observe_execution()` 回写：成功/失败和延迟通过 EMA 更新可靠性与延迟估计；RuntimeSnapshot 的观测序号和版本递增，供后续健康判断与排序使用。存储使用版本比较避免并发覆盖。持久化实现可替换，但必须满足 `ports/` 接口及资源存储合同测试。

### 生命周期审计（已实现）

`domain/audit.py` 定义 `ResourceAuditEvent`；`ports/audit_store.py` 定义写入、资源过滤查询和分类计数接口；`infrastructure/audit_store.py` 提供内存与 SQLite 实现。平台装配将 SQLite 审计表放在 `AGENTOS_RESOURCE_DB` 指定的数据库中，并随 Runtime 关闭连接。默认嵌入式测试使用内存仓储。

事件包括 `node_registered`、`runtime_registered`、`credential_rotated`、`observation_rejected`、`snapshot_conflict` 和模型适配器的 `execution_observation_write_failed`。使用 `plane.audit_events(resource_id, limit=100)` 查询最近事件，使用 `plane.audit_counts(resource_id)` 读取按类型聚合的计数。幂等重复登记不重复生成创建事件。

审计仅记录资源 ID、时间和异常类型等分类信息，不写密钥、提示词或文档正文。模型观测旁路故障不覆盖原模型响应；审计仓储本身不可用时记录服务日志，不把已提交登记改报失败。这是单机可观测性，不等同于事务性审计 outbox 或跨主机指标中心。

## 平台本地文档工具

资源器只负责资源事实与调度；工具代码、包构建和安装生命周期位于 `components/marketplace`，不放入资源领域层：

| 位置 | 职责 |
| --- | --- |
| `marketplace/builtins/contracts.py` | 路径、页码、文件大小和格式白名单 |
| `marketplace/builtins/pdf_parser.py` | pypdf 提取文字、页码和受限元数据 |
| `marketplace/builtins/file_converter.py` | 文本/表格转换和随机任务输出目录 |
| `marketplace/builtins/server.py`、`worker.py` | loopback HMAC 服务、单任务执行和 30 秒超时 |
| `marketplace/builtins/catalog.py` | 两个受控目录项、确定性 ZIP 和 SHA-256 |
| `marketplace/application/service.py` | 安装、登记、文件传入/结果读取与健康巡检 |
| `marketplace/infrastructure.py` | 无 shell 启动、独立端口/凭据、任务持久化 |

| 商店工具 | 目录 ID / 能力 | 实际支持 |
| --- | --- | --- |
| PDF 解析 | `tool.pdf-parser` / `pdf.parse` | 文字层 PDF，页范围，按页文本、页数、提取器版本及受限标题/作者/主题 |
| 文件格式转换 | `tool.file-converter` / `file.convert` | `txt → md/html`；`md → txt/html`；`html → txt/md`；`csv ↔ json`；`docx → txt/md/html`；`xlsx → csv/json`；`pdf → txt/md` |

DOCX 转换为文字及表格内容，XLSX 读取活动工作表和公式缓存值，不执行公式；转换为 Markdown 时采用纯文本转义，HTML 转 Markdown 不保留原页面版式。转换不是高保真 Office 排版引擎。扫描 PDF 返回 `OCR_NOT_AVAILABLE`，加密 PDF 被拒绝；不生成 PDF、DOCX 或 XLSX，不隐式下载 OCR、Pandoc 或 LibreOffice。

平台部署时，在运行 AgentOS 的同一 Python 环境安装 `apps/agentOS/requirements-local-tools.txt`（pypdf、python-docx、openpyxl、Markdown）。目录 ZIP 包含平台工具代码，**不包含 Python 解释器和第三方依赖**；缺依赖时安装失败，不在安装请求中执行 pip 或联网下载。平台默认装配会生成本地目录和包，可通过 `AGENTOS_MARKETPLACE_CATALOG_DIR`、`AGENTOS_MARKETPLACE_PACKAGE_DIR`、`AGENTOS_MARKETPLACE_INSTALL_DIR` 覆盖数据目录。当前为平台维护的本地分发，尚未接外部仓库。

### 一次工具请求的数据变化

```text
资源商店 → 安装目录项
  → SHA-256 / ZIP 路径校验 → 固定 Python 模块（shell=False）
  → 独立安装目录、随机 loopback 端口和一次性凭据
  → /health 通过 → Runtime 登记为 device / tool_service / agentos_http
  → 安装任务 running → 已安装列表中的“使用工具”
  → 上传文件 → inputs/<随机 ID>.<扩展名>（sourcePath，不返回宿主绝对路径）
  → sourcePath + 页码/目标格式 → 后端签名 POST /execute
  → 子进程执行白名单能力（最多 30 秒）
  → PDF: AgentOutput.output.text / extractedPages
  → 转换: AgentOutput.output.outputPath = outputs/<任务 UUID>/result.<格式>
  → 受控下载 → ResourcePlane.observe_execution 回写真实成功/失败与时延
```

HTTP `/execute` 成功返回 200 + `AgentOutput`；处理失败返回 422 + 稳定错误码，防止 ACG 将工具失败当成成功。商店便捷接口将工具错误码投影给前端。单文件最多 20 MiB、PDF 最多 200 页、文本最多 100 万字符、表格最多 5 万数据行；Office ZIP 在解析前限制展开大小和压缩比。

文件接口位于 `/agentos/v2/marketplace/installations/{job_id}` 下：`POST /files` 上传、`POST /execute` 执行、`GET /files?path=outputs/...` 下载。接口要求可信租户上下文及资源操作权限，并复核任务归属；只处理运行中的平台文档工具。前端不读取密钥、启动参数或安装路径。

每次安装生成独立 Runtime ID、工作目录和凭据；内置服务凭据绑定进程生命周期，通用凭据轮换接口会明确拒绝单独修改，更新凭据需卸载后重装。健康巡检只刷新心跳，不伪造成功执行。停止后禁用调度，异常退出在下一轮巡检中收敛；平台正常关闭会停止自有服务，重启时旧运行任务收敛为 stopped，需要卸载后重新安装。卸载删除安装工作目录及其输入/结果文件，重要结果应提前下载。当前没有断点续装、跨主机进程接管或自动恢复。

ACG 可以通过现有 `agentos_http` 执行适配器调用这些具体能力，但仍需明确的能力需求、允许的远程执行策略、同租户归属和工作区输入。商店安装不会自动编写业务 Agent、扩展 Planner 业务模板，也不会把其他任务的任意附件路径直接暴露给工具；附件需先进入该安装的受控工作区。

### TODO 复核结论

已完成并移除 `resource-plane-observability` 和 `resource-observability` 两处 TODO，补充事件、持久化、计数和失败隔离测试。其余 TODO 保留真实前提：集中式数据库/nonce 协调、KMS/HSM、密钥宽限期双验、配额及计费权威源、负载恢复策略、Agent 热迁移、shell 细粒度授权及公共 API 弃用策略。`scheduling-policy` 注释已更新，区分已有的成本/地域准入与尚缺的配额/计费数据，避免将已支持约束误写为完全未实现。

## 维护约束

- 新业务流程放在 `application/`，纯业务计算放在 `domain/`，并发分配流程放在 `scheduler/`。
- 新存储后端放入 `infrastructure/` 并实现既有 port，不让上层导入后端实现类作为接口。
- 对外数据形状改动在权威 `contracts/` 中完成，并检查 adapters、runtime 和调度的调用方。
- 测试按层导入权威模块路径，避免重新引入已删除的旧顶层别名。
- 改变 placement 权重时同时更新排序测试；硬约束必须保持高于任何软偏好的否决权。

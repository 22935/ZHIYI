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

资源接入时，`placement` 描述物理/信任位置，`provider`、`sourceType` 和 `adapter` 描述厂家、来源与协议适配器；三者正交。厂家扩展参数放在 `metadata`，不得把厂商字符串直接解释成能力、信任或准入许可。远程 Node 可登记为 Device、Edge 或 Cloud，但远程 Device 不得自称 `host_trusted`；是否属于远程执行由 Runtime endpoint 决定，不能由 Device placement 绕过远程执行策略。当前远程 Agent 执行 adapter 仅实现 HTTP(S)；gRPC、MCP、Kubernetes 等来源可以登记为元数据，但要实际调度执行仍需对应协议 adapter，未知协议不可被当成已可调用资源。

模型路由可通过 `ModelDemand` 的 endpoint/provider/model allowlist 与 denylist 约束候选；供应商匹配不区分大小写，`provider/model` 与模型短名均可用于模型筛选。远程 `MODEL_SERVER` 登记必须带 `provider` 和至少一个 `modelId`，资源器会为每个模型创建绑定到该 Runtime 的 `ModelEndpointProfile`；Runtime 停用时这些端点也不可参与路由。模型注册表同步则必须显式传入 `placement`，不允许依据厂商名称推断端、边或云位置。

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

## 维护约束

- 新业务流程放在 `application/`，纯业务计算放在 `domain/`，并发分配流程放在 `scheduler/`。
- 新存储后端放入 `infrastructure/` 并实现既有 port，不让上层导入后端实现类作为接口。
- 对外数据形状改动在权威 `contracts/` 中完成，并检查 adapters、runtime 和调度的调用方。
- 测试按层导入权威模块路径，避免重新引入已删除的旧顶层别名。
- 改变 placement 权重时同时更新排序测试；硬约束必须保持高于任何软偏好的否决权。

# AgentOS 部件化统一设计

模型兼容端点的 registry 复用、生命周期、SSE 与外部框架边界见
[模型运行时装配](docs/model-runtime.md)。Gitee 分叉提交的迁移判定见
[Gitee 模型运行时迁移检查](docs/gitee-model-runtime-migration.md)。

```text
AgentOS
│
├─ 设计规则（目标，非全部已落地；标注 ⚠ 为当前已违反）
│  ├─ 一个业务部件 = components/ 下的一个文件夹
│  ├─ 部件内部自包含：models / service / algorithms / store
│  ├─ 跨部件共享资料应收敛到 src/contracts/；现存内部导入列入迁移 TODO
│  ├─ runtime/ 只负责装配与编排，不承载领域算法           ⚠ 已违反（runtime 44 文件）
│  ├─ adapters/ 只承载外部系统实现与注入协议
│  ├─ tools/ 只承载 ACG 导出、序列化与绘图
│  └─ support/ 只承载历史运行时配套；不得新增跨部件合同   ⚠ 已违反（support/acg）
│
├─ src/
│  │
│  ├─ contracts/                        跨部件类型/数据合同（38 模块，已膨胀，见分析）
│  │
│  ├─ components/                        业务部件层（设计 9 → 现状 12）
│  │  ├─ mission_manager/                任务管理器（原 task_manager 改名；无本地 models.py，类型在 contracts/mission_semantic|revision）
│  │  ├─ planner/                        规划器（29 文件，含 topology/ 子编译器；最膨胀部件）
│  │  ├─ resource/                       资源器：画像、健康、版本化快照
│  │  ├─ scheduler/                      调度器：Blueprint → ExecutionPackage
│  │  ├─ executor/                       执行器：RuntimeGraph 确定性执行
│  │  ├─ communicator/                   通信器：受控低熵信息流
│  │  ├─ memory/                         记忆器：唯一记忆读写入口
│  │  ├─ auditor/                        审计器：治理判定
│  │  ├─ recovery/                       恢复器：受控自愈与局部重规划
│  │  ├─ attachments/                    新增：附件抽取/存储/服务
│  │  ├─ content/                        新增：内容工作集/存储
│  │  ├─ evolution/                      新增：技能/图自进化
│  │  └─ model_partition/                新增：模型分区
│  │
│  ├─ runtime/                           编排层（44 文件；已承载 identity/workspace/planning 子系统，见分析）
│  │
│  ├─ adapters/                          外部 Adapter 层（29 文件：模型/Agent/工具/检索/LocalRuntime）
│  │
│  ├─ domain/                            新增：领域实体（Mission/SemanticTask/Run/Attempt/Step）+ 仓储接口
│  │
│  ├─ storage/v2/                        新增：Identity V2 / New ACG 存储层（与 support/stores 隔离，勿合并）
│  │
│  ├─ tools/                             ACG 导出与绘图层（7 文件，符合设计，最干净）
│  │
│  └─ support/                           历史运行时配套层
│     ├─ acg/                            ⚠ 规划期 ACG schema/校验/能力目录（事实上的 ACG 合同层，应迁 contracts）
│     ├─ packs/                          Pack Manifest 发现与注册
│     ├─ skills/                         BaseSkill、NoOpSkill、注册表
│     ├─ stores/                         Memory/SQLite WorkflowStore Adapter（服务主执行引擎）
│     ├─ async_tasks.py  run_execution_fence.py
│     └─ （原 support/domain 已迁至 src/domain）
│
├─ service/agents/                       运行期服务层（实际在仓库根，非 src/service）
├─ hands/                                ⚠ TypeScript 项目（node_modules/package.json），不应置于 Python src/
├─ oscode-context/                       ⚠ TypeScript 项目，不应置于 Python src/
│
├─ tests/                                已按 components/contracts/domain/storage/runtime 镜像扩展
│
└─ （config/ 设计列出但当前仓库不存在）

依赖方向
├─ runtime → components → contracts
├─ runtime → components / service / support（运行时装配与历史兼容）
├─ adapters → contracts / service / support（外部实现注入）
├─ tools → components.planner / contracts（只读导出）
├─ domain → contracts（实体实现引用合同接口）
├─ components → contracts（目标）；恢复/执行/规划的现存内部导入待收敛
└─ ⚠ support/acg → 应改为 contracts/acg_schema（当前越权为共享合同层）

核心算法
├─ 任务复杂度：目标长度、文件数、模态、风险、Step 估计、跨域与可选路径加权
├─ 规划：模板相似度阈值 → 能力依赖展开 → 熵预算约束 → ACG 构建
├─ ACG 导出：Canonical JSON → 节点/边映射 → Mermaid 或 DOT
├─ 资源调度：硬过滤 → 加权评分 → 租约
├─ 执行：拓扑就绪集 → 并发限制 → 屏障原子提交 → 条件补丁
├─ 低熵通信：字段契约 → 去重 → Token 压缩 → 血缘
├─ 记忆：权限过滤 → 混合召回 → 冲突保留 → 重排 → 预算选择
├─ 审计：结构/证据/风险/质量 → 规则优先级合并 → PolicyDecision
└─ 恢复：故障分类 → 安全检查点 → 恢复动作 → 重新审计

TODO 实现边界
├─ 模型/工具/远程 Agent：真实 SDK、鉴权、超时、重试、限流、熔断、审计
├─ 存储/检索：SQLite、对象存储、向量库、事务、加密、持久化索引
├─ 通信：消息总线可靠投递、可溯源模型压缩
├─ 恢复：检查点 CAS/互斥、持久化、版本校验、加密
├─ 资源：真实跨进程心跳鉴权、资源快照持久化、服务发现与生产级故障演练
├─ 审计：证据存储、组织级策略引擎
├─ 工具：Graphviz PNG/SVG 二进制渲染
├─ 合同：完整 JSON Schema（oneOf、引用、格式）
└─ 架构：support/acg 规划契约迁至 contracts/acg_schema；support/stores 维持隔离；恢复/执行/规划的跨部件内部导入收敛到 contracts 或公开门面

已知结构问题与收敛建议
详见 docs/架构冗余与错位分析.md（2026-11-09）。要点：
├─ 放错位置：support/acg 越权为 ACG 合同层；src/hands、src/oscode-context 两个 TS 项目混入 Python src/；service/ 在根非 src/service；config/ 不存在
├─ 重复：两个同名 contract_repair.py（语义不同）；ACG 类型在 support/acg 与 contracts 分裂
├─ 膨胀：runtime 44 文件违反薄编排；planner 29 文件（含 topology 子编译器）；contracts 38 文件粒度偏细
└─ 收敛优先级：P0 迁出 TS 项目 / 冻结 support/acg / 重命名 contract_repair → P1 抽离 runtime 子系统 / 明确 contracts 准入 → P2 文档对齐
```

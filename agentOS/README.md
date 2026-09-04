# AgentOS 部件化统一设计

模型兼容端点的 registry 复用、生命周期、SSE 与外部框架边界见
[模型运行时装配](docs/model-runtime.md)。Gitee 分叉提交的迁移判定见
[Gitee 模型运行时迁移检查](docs/gitee-model-runtime-migration.md)。

```text
AgentOS
│
├─ 设计规则
│  ├─ 一个业务部件 = components/ 下的一个文件夹
│  ├─ 部件内部自包含：models / service / algorithms / store
│  ├─ 跨部件共享资料应收敛到 src/contracts/；现存内部导入列入迁移 TODO
│  ├─ runtime/ 只负责装配与编排，不承载领域算法
│  ├─ adapters/ 只承载外部系统实现与注入协议
│  ├─ tools/ 只承载 ACG 导出、序列化与绘图
│  └─ support/ 只承载历史运行时配套；不得新增跨部件合同
│
├─ config/                              运行配置
│
├─ src/
│  │
│  ├─ contracts/                        跨部件唯一共享合同
│  │  ├─ task.py                        Task、约束、生命周期事件
│  │  ├─ workflow.py                    Blueprint、RuntimeGraph、节点与边
│  │  ├─ execution.py                   ExecutionPackage、Outcome、执行状态
│  │  ├─ communication.py               Message、ContextPack、字段/版本契约
│  │  ├─ memory.py                      MemoryRecord、Query、Policy、WriteBatch
│  │  ├─ resource.py                    ResourceProfile、Snapshot、Lease、Decision
│  │  ├─ governance.py                  Trace、Checkpoint、AuditRequest、PolicyDecision
│  │  └─ recovery.py                    FailureEvent、RecoveryPlan、GraphPatch
│  │
│  ├─ components/                       业务部件层
│  │  │
│  │  ├─ task_manager/                  任务管理器
│  │  │  ├─ models.py                   Task、配额、优先级、进度
│  │  │  ├─ state_machine.py            任务/运行合法状态迁移
│  │  │  ├─ service.py                  创建、绑定、取消、恢复、进度查询
│  │  │  ├─ scheduler.py                多任务排队、优先级、并发配额
│  │  │  ├─ algorithms.py               复杂度评分、排序、配额分配
│  │  │  └─ store.py                    WorkflowRegistry、任务存储选择
│  │  │
│  │  ├─ planner/                       规划器：Task → 静态 ACG Blueprint
│  │  │  ├─ models.py                   Intent、Capability、Blueprint、变体
│  │  │  ├─ intent_analyzer.py          LLM/启发式意图理解
│  │  │  ├─ task_structurer.py          目标、约束、风险、预算结构化
│  │  │  ├─ cognitive_router.py         能力 → Agent/角色候选路由
│  │  │  ├─ template_matcher.py         模板评分、相似度、静态优选
│  │  │  ├─ acg_builder.py              Step/Agent/Memory/Evidence/Control 图构建
│  │  │  ├─ algorithms.py               依赖展开、熵预算、多样性选择
│  │  │  └─ service.py                  PlannerService 门面
│  │  │
│  │  ├─ resource/                      资源器：画像、健康、版本化快照
│  │  │  ├─ models.py                   Profile、Snapshot、Metric
│  │  │  ├─ registry.py                 Agent/模型/工具/知识源注册
│  │  │  ├─ health.py                   心跳、负载、时延、可靠性 EMA
│  │  │  ├─ algorithms.py               健康评分、可用性硬过滤
│  │  │  ├─ store.py                    ResourceStore、乐观版本、进程锁
│  │  │  └─ service.py                  资源候选与实时快照
│  │  │
│  │  ├─ scheduler/                     调度器：Blueprint → ExecutionPackage
│  │  │  ├─ models.py                   Binding、Request、Decision、Lease
│  │  │  ├─ binder.py                   抽象能力绑定资源候选
│  │  │  ├─ scorer.py                   标准化评分、稳定并列决策
│  │  │  ├─ leases.py                   原子预留、回收、并发槽位
│  │  │  ├─ package_builder.py          无状态执行包组装
│  │  │  ├─ algorithms.py               多目标评分、退避、候选切换
│  │  │  └─ service.py                  调度审计与反馈
│  │  │
│  │  ├─ executor/                      执行器：RuntimeGraph 确定性执行
│  │  │  ├─ graph.py                    图版本、就绪集、条件分支
│  │  │  ├─ dispatcher.py               并发批次、调用、超时、取消
│  │  │  ├─ barrier.py                  原子提交、迟到结果拒绝、投影
│  │  │  ├─ service.py                  执行、续跑、审核后继续
│  │  │  ├─ algorithms.py               拓扑排序、就绪选择、限流
│  │  │  └─ fault_injection.py          可控故障注入
│  │  │
│  │  ├─ communicator/                  通信器：受控低熵信息流
│  │  │  ├─ models.py                   Message、ContextPack、Provenance
│  │  │  ├─ contracts.py                Schema 版本、字段投递规则
│  │  │  ├─ assembler.py                上游/记忆/证据最小上下文装配
│  │  │  ├─ compressor.py               裁剪、去重、Token 预算压缩
│  │  │  ├─ provenance.py               生产/消费/路由血缘与完整性
│  │  │  ├─ algorithms.py               低熵选择、Token 估算、幂等
│  │  │  └─ service.py                  投递、确认、异常上报
│  │  │
│  │  ├─ memory/                        记忆器：唯一记忆读写入口
│  │  │  ├─ models.py                   MemoryRecord、Query、Policy、WriteBatch
│  │  │  ├─ store.py                    进程内 Store 与存储 Interface
│  │  │  ├─ admission.py                权限、证据、风险、版本、幂等准入
│  │  │  ├─ retrieval.py                过滤、关键词召回、重排、冲突保留
│  │  │  ├─ compression.py              Token 预算选择、类型化压缩
│  │  │  ├─ lifecycle.py                工作/情节/语义记忆生命周期
│  │  │  ├─ algorithms.py               混合评分、背包式预算选择
│  │  │  └─ service.py                  ContextPack、原子写入、快照恢复
│  │  │
│  │  ├─ auditor/                       审计器：治理判定
│  │  │  ├─ models.py                   AuditRequest、Finding、PolicyDecision
│  │  │  ├─ structural.py               图/状态/契约/版本校验
│  │  │  ├─ evidence.py                 结论—证据—来源—过程校验
│  │  │  ├─ risk.py                     风险事实、规则、冲突消解
│  │  │  ├─ quality.py                  完整性、一致性、质量阈值
│  │  │  ├─ policy.py                   规则版本、自动动作、人工审核
│  │  │  ├─ algorithms.py               综合评分、优先级、决策合并
│  │  │  ├─ governance/                Trace、Checkpoint、Review、Evaluation
│  │  │  └─ service.py                  AuditorService 门面
│  │  │
│  │  └─ recovery/                      恢复器：受控自愈与局部重规划
│  │     ├─ models.py                   FailureEvent、RecoveryPlan、GraphPatch
│  │     ├─ classifier.py               故障分类与可恢复性
│  │     ├─ checkpoint.py               进程内检查点 Interface
│  │     ├─ planner.py                  重试、换资源、补证、审核、补丁决策
│  │     ├─ validator.py                补丁身份、预算、能力、连通性校验
│  │     ├─ algorithms.py               最近安全点、动作优先级
│  │     ├─ runtime_recovery/           补丁、绑定、策略、配方、控制器
│  │     └─ service.py                  RecoveryService 门面
│  │
│  ├─ runtime/                          薄编排层
│  │  ├─ bootstrap.py                   组件/原生能力/Pack 注册
│  │  ├─ workflow_runtime.py            Task → Planner → Scheduler → Executor
│  │  ├─ dependencies.py                依赖注入、插件作用域、生命周期
│  │  └─ compatibility.py               运行实例进程内锁兼容层
│  │
│  ├─ adapters/                         外部 Adapter 层
│  │  ├─ model/                         原生提示词、模型运行时注册
│  │  ├─ tool/                          工具运行时协议与注入
│  │  ├─ storage/                       持久化/对象存储协议与注入
│  │  ├─ remote_agent/                  HTTP/gRPC Agent 协议与注入
│  │  ├─ model_adapter.py               文本/结构化模型统一 Adapter
│  │  ├─ tool_adapter.py                工具运行时工厂
│  │  ├─ federated_adapter.py           联邦增强失败开放 Adapter
│  │  └─ retrieval_adapter.py           检索 Adapter 迁移中（引用待同步）
│  │
│  ├─ service/                          运行期服务层
│  │  └─ agents/                        Agent 基础模型、调用上下文、注册表与运行范围
│  │
│  ├─ tools/                            ACG 导出与绘图层
│  │  ├─ models.py                      图模型导出引用
│  │  ├─ serializer.py                  Canonical JSON 序列化
│  │  ├─ exporter.py                    稳定 JSON/格式导出
│  │  ├─ labels.py                      节点/边显示标签映射
│  │  ├─ mermaid.py                     Mermaid flowchart 文本
│  │  ├─ graphviz.py                    Graphviz DOT 文本
│  │  └─ service.py                     ACGToolsService 统一入口
│  │
│  ├─ support/                          历史运行时配套层（非新业务合同）
│  │  ├─ domain/                        线性 Task/Workflow 兼容模型
│  │  ├─ packs/                         Pack Manifest 发现与注册
│  │  ├─ skills/                        BaseSkill、NoOpSkill、注册表
│  │  └─ stores/                        Memory/SQLite WorkflowStore Adapter
│  │
│  └─ README.md                         源码分层与依赖方向
│
└─ tests/
   ├─ resource/                         资源健康、候选、并发版本
   ├─ contracts/                        合同模型
   ├─ test_architecture_layout.py       分层、目录、公开门面
   └─ test_comment_todo_policy.py       中文说明、TODO 边界

依赖方向
├─ runtime → components → contracts
├─ runtime → components / service / support（运行时装配与历史兼容）
├─ adapters → contracts / service / support（外部实现注入）
├─ tools → components.planner / contracts（只读导出）
└─ components → contracts（目标）；恢复/执行/规划的现存内部导入待收敛

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
└─ 架构：support/domain 与 contracts 模型归并；support/stores 下沉；恢复/执行/规划的跨部件内部导入收敛到 contracts 或公开门面
```

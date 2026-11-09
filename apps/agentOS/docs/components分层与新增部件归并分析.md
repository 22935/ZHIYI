# AgentOS components 分层说明与新增部件归并分析（2026-11-09）

> 配套 `docs/架构冗余与错位分析.md`。本文做两件事：① 把 `src/components/` 下 12 个部件的文件按「分层」讲清楚；② 判断 4 个新增部件（attachments / content / evolution / model_partition）是应保留、合并还是并入其它部件。

## 0. 先统一"分层"口径

设计规则写的是「部件内部自包含：models / service / algorithms / store」四层。对照实际代码，文件明显多于这四类，因此把「层」扩展为 5 类便于归类：

| 层 | 角色 | 典型文件名 |
| --- | --- | --- |
| **Facade（门面）** | 部件对外唯一入口，编排内部子能力 | `service.py`（及 `*_service.py`） |
| **Models/Contracts（模型/合同）** | 本部件的类型、共享结构、字段契约 | `models.py`、`contracts.py`、`manifest.py` |
| **Algorithms（纯算法）** | 无 I/O、无副作用、可单测的纯函数 | `algorithms.py` 及 `complexity.py`、`template_matcher.py` 等 |
| **Store/Persistence（存储）** | 可替换的持久化端口与实现（内存/SQLite） | `store.py` 及 `*_store.py` |
| **Domain engines（领域引擎）** | 有具体业务逻辑/流程的模块（路由、编译、校验、抽取等） | 其余：router/compiler/validator/extractor/health… |

> 规律：凡是 `Service` 结尾 = Facade；`Store` 结尾 = 存储；`*er`/`*or`/`*ar` 结尾且带领域动词 = 引擎；`models/contracts/manifest` = 类型层；`algorithms` 及纯函数 = 算法层。

---

## 1. 逐部件文件分层说明（12 个）

### 1.1 mission_manager（任务/任务生命周期；原 task_manager）
> 注意：**本部件没有本地 `models.py`**，领域类型放在 `contracts/mission_semantic.py` 与 `contracts/mission_revision.py`（见架构冗余分析 3.3）。

| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `MissionManager`：任务创建、工作流绑定、生命周期流转 |
| `state_machine.py` | Domain engine | `StateMachine`：合法状态迁移（来自 Core 状态机模块） |
| `scheduler.py` | Domain engine | `WorkflowProgress`/`ProgressAssembler`：进度投影读模型（保留进度投影使本部件有完整生命周期读视图） |
| `semantic_service.py` | Domain engine | `MissionSemanticService`：受权的显式语义操作（无自动 legacy 提升） |
| `semantic_resolver.py` | Algorithms(纯) | `MissionSemanticResolver`：纯语义投影与 Run-basis 捕获，不持久化、无权威 |
| `algorithms.py` | Algorithms | `task_complexity`：确定性复杂度评分 |
| `store.py` | Store | `WorkflowRegistry`/`ScopedWorkflowRegistry`：行业 Pack 工作流定义注册与推荐 |

### 1.2 planner（规划引擎；最大部件，29 文件含 topology 子包）
> 超出四层最严重：除标准层外，塞了 intent/semantic/react/htn/horizon 多种规划范式 + topology 子编译器。

| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `PlanningEngine`：认知规划主入口（`PlanResult`/`apply_task_plan_patch`） |
| `models.py` | — | 部件公开入口（`__getattr__` 转发） |
| `intent_analyzer.py` | Domain engine | `IntentLLM`/`IntentParser`：原始意图→领域无关语义画像 |
| `task_structurer.py` | Domain engine | `structure_tasks`：意图事实→最小任务骨架 |
| `task_decomposer.py` | Domain engine | `TaskDecomposer`：版本化语义任务分解（不引入第二运行时） |
| `cognitive_router.py` | Domain engine | `CognitiveRouter`：按共享能力目录确定性绑定与协作路由 |
| `template_matcher.py` | Algorithms | `TemplateMatcher`：模板相似度（Dice/bigram）匹配 |
| `semantic_planner.py` | Domain engine | `SemanticPlanner`：产出执行无关的 TaskPlan 合同 |
| `acg_lowerer.py` | Domain engine | `ACGLowerer`：frozen 规划决策→ACG 蓝图（确定性 lowering） |
| `lowering_input.py` | Domain engine | 为 `ACGLowerer` 准备冻结输入 |
| `acg_semantic_validator.py` | Domain engine | ACG 语义保持校验 |
| `algorithms.py` | Algorithms | `PlanningVariantGenerator`：可审计带种子变体 |
| `complexity.py` | Algorithms | `assess_complexity`：领域无关复杂度评分 + 模型调用 |
| `horizon.py` | Domain engine | `AdaptiveHorizonSelector`：受信任 TaskPlan 上的有界前沿选择 |
| `htn.py` | Domain engine | `HTNMethodSelector`/`Catalog`：有界 HTN 选择/展开 |
| `react_loop.py` | Domain engine | `BoundedReActPlanningLoop`（默认关闭，opt-in） |
| `runtime_decision.py` | Domain engine | `decide_runtime`：规划器 fresh-state 运行决策（无变更权威） |
| `semantic_patch_planning.py` | Domain engine | TaskPlan 语义修订的规划侧实现 |
| `planning_commit.py` | Domain engine | `PlanningCommitService`：供应商驱动的规划接纳 + 可插拔记录存储 |
| `unified_actions.py` | Domain engine | `PlannerActionGateway`：统一类型化动作网关（S01-02/03 opt-in） |
| `topology/`（9 文件） | **独立子编译器** | `compiler`/`validator`/`binding_solver`/`gate`/`repair`/`model`/`audit`/`errors`/`__init__`：TaskPlan→拓扑编译、能力绑定求解、冲突修复与校验。**规模已接近一个部件** |

### 1.3 resource（资源平面：Node / Runtime / ModelEndpoint；15 文件）
> 一个部件内实际含三个子平面（节点、运行时、模型端点），靠子模块区分。

| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `ResourcePlane`：登记/观测/候选查询，签发资源凭据 |
| `models.py` | Models | 只读投影模型：`RuntimeCandidate`/`ModelEndpointCandidate`/`NodeHealth` 等 |
| `algorithms.py` | Algorithms | `health_score`/`ema`/`is_runtime_available`：健康与候选纯计算 |
| `store.py` | Store | `RuntimeStore`：Runtime 画像/快照、模型端点目录、远程凭据 |
| `health.py` | Domain engine | `ResourceHealthMonitor`：心跳+结果→健康投影 |
| `health_store.py` | Store | `ResourceHealthStore`：跨进程共享 Runtime 健康 |
| `node_health.py` | Domain engine | `NodeHealthMonitor`：心跳分级 |
| `node_store.py` | Store | `NodeStore`：节点资源表存储 |
| `auth.py` | Domain engine | `ResourceRequestAuthenticator`：远程节点请求签名鉴权 |
| `crypto.py` | Domain engine | `ResourceSecretBox`：签名密钥静态保护 |
| `local_runtime.py` | Domain engine | 本地 Runtime 的资源平面注册与健康投影 |
| `embedded_runtime.py` | Domain engine | 进程内逻辑 Agent 运行时注册为 EXECUTION_BACKEND |
| `errors.py` | Models | 资源平面写入路径领域错误 |
| `sqlite_support.py` | Store(辅助) | 各 SQLite 存储共享的耐久/锁设置 |

### 1.4 scheduler（调度；最小部件，4 文件）
> 最贴合四层理想：Facade + Models + 两个引擎（binder/leases）。

| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | 部件公开入口（注：实际调度权威在 `binder.py` 的 `ResourceBinder`） |
| `models.py` | Models | 类型化调度决策（`CandidateDecision`/`RequirementReadiness` 等，无 DAG 状态） |
| `binder.py` | Domain engine | `ResourceBinder`：需求→执行绑定的**唯一选择权威** |
| `leases.py` | Domain engine/Store | `LeaseCoordinator`/`RedisLeaseCoordinator`：原子租约协调（含 `issue_lease`） |

### 1.5 executor（ACG 确定性执行；8 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` → 见 `graph.py`/`node_runner.py` | Facade | 执行入口分散在图与节点运行器（无独立 `service.py`，`__init__` 为公开边界） |
| `compiler.py` | Domain engine | `ACGGraphCompiler`：蓝图→不可变穷举执行包 |
| `graph.py` | Domain engine | `ACGExecutionGraph`：融合 StateGraph/Pregel 的执行核心 |
| `state_graph.py` | Domain engine | `ACGStateGraph`：StateGraph 构建器 |
| `node_runner.py` | Domain engine | `ACGNodeRunner`：单节点固定执行管线 |
| `value_store.py` | Store | `ExecutionValueStore`：运行期受控数据引用仓库（内存/SQLite） |
| `graph_patch.py` | Models | 语义图修订边界共享错误 |
| `orphan_cleaner.py` | Domain engine | `ExecutionOrphanCleaner`：执行正文孤儿延迟清理 |

### 1.6 communicator（受控低熵通信；13 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `CommunicatorService` |
| `models.py` | Models | 公开的消息/上下文/血缘模型 |
| `contracts.py` | Models | 内部低熵上下文合同（`ContextPack`/`estimate_tokens`） |
| `manifest.py` | Models | `CommunicationManifest`：通信拓扑/字段许可/预算声明 |
| `algorithms.py` | Algorithms | `select_fields`/`low_entropy_choice`：内容选择纯函数 |
| `assembler.py` | Domain engine | `ContextAssembler`：字段白名单上下文装配 |
| `compressor.py` | Domain engine | `compress_text`：保守本地压缩 |
| `broker.py` | Domain engine | `CommunicationBroker`：运行期受控按需读取 |
| `reader.py` | Domain engine | `CommunicationReader`：Agent 补读已授权上游引用 |
| `provenance.py` | Domain engine | `ProvenanceLedger`：生产/消费/交互可验证血缘账本 |
| `provenance_store.py` | Store | `SQLiteProvenanceStore`：血缘账本持久化 |
| `reliable.py` | Domain engine/Store | `ReliableCommunicationStore`/`DebateCoordinator`：高级模式的持久引用通信（黑板/辩论） |

### 1.7 memory（记忆；10 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `MemoryService` |
| `models.py` | Models | 共享数据合同与运行期工作记忆（`WorkingMemory` 等） |
| `admission.py` | Domain engine | `admitted`：准入规则（权限/证据/风险/幂等） |
| `retrieval.py` | Domain engine | `retrieve`：SQLite 权威的词典/向量召回 |
| `algorithms.py` | Algorithms | `rerank_memories`：混合排序 |
| `compression.py` | Domain engine | `compact_record`：类型化压缩 |
| `lifecycle.py` | Domain engine | `is_expired`：生命周期判断 |
| `events.py` | Domain engine | `StructuredMemoryEventBuilder`：从节点结果投影记忆事件 |
| `store.py` | Store | `MemoryStore`/`SQLiteMemoryStore`：可替换记忆仓库 |

### 1.8 auditor（治理判定；17 文件含 governance 子包）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `AuditorService` |
| `models.py` | Models | 共享治理合同 |
| `structural.py` | Domain engine | `missing_required_fields`：结构校验 |
| `evidence.py` | Domain engine | `evidence_complete`：证据引用检查 |
| `risk.py` | Algorithms | `classify_risk`：风险归一化 |
| `quality.py` | Algorithms | `quality_passed`：质量阈值 |
| `policy.py` | Domain engine | `policy_outcome`：局部政策规则 |
| `algorithms.py` | Algorithms | `audit_score`：审计结果纯评分 |
| `execution_audit.py` | Domain engine | `ExecutionAuditService`：节点结果纯规则审计 |
| `artifact_acceptance.py` | Domain engine | `inspect_artifact`：提交产物的独立内容检查 |
| `task_acceptance.py` | Domain engine | `evaluate_task_acceptance`：冻结文档要求 vs 已授权产物 |
| `decision_store.py` | Store | `DecisionStore`/`SQLiteDecisionStore`：审计决定持久化 |
| `governance/`（4 文件） | **治理子包** | `trace`(`TraceStore` 投影导出)/`review`(`ReviewManager`)/`evaluation`(`WorkflowEvaluator`)：追踪/评审/评估三件套 |

### 1.9 recovery（受控自愈；11 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `RecoveryService` |
| `models.py` | Models | 共享合同 |
| `classifier.py` | Algorithms | `classify_failure`：确定性失败分类 |
| `algorithms.py` | Algorithms | `recovery_priority`：恢复排序纯函数 |
| `planner.py` | Domain engine | `plan_recovery`：恢复计划创建 |
| `validator.py` | Domain engine | `valid_recovery_plan`：运行前校验 |
| `recipes.py` | Domain engine | `RecoveryRecipeRegistry`：声明式恢复配方注册 |
| `failure.py` | Domain engine | `failure_event_from_exception`：边界失败分类 |
| `checkpoint.py` | Store | `ACGCheckpointStore`：SQLite 执行检查点 |
| `contract_repair.py` | Domain engine | `repair_payload`：JSON 合同载荷无损修复（⚠ 与 `adapters/model/contract_repair.py` 同名不同义） |

### 1.10 attachments（新增；4 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `InputAttachmentService`：联接附件身份、字节与抽取物料 |
| `extractors.py` | Domain engine | `DocumentTextExtractor` 注册表：PDF/DOCX/纯文本抽取 |
| `storage.py` | Store | `AttachmentStorage`/`LocalAttachmentStorage`：上传字节可替换存储端口 |
| `__init__.py` | — | 包边界 |

### 1.11 content（新增；3 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `store.py` | Store | `ContentManifestStore`：不可变内容清单/片段 SQLite 持久化（确定性装配） |
| `workset.py` | Domain engine | `ContentWorksetSession`：单次语义 ACG 步骤内的游标式 workset |
| `__init__.py` | — | 包边界（不可变内容 manifest） |

### 1.12 evolution（新增；6 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade | `EvolutionService`：从已完成 General 轨迹派生受控策略演化 |
| `graph_service.py` | Facade | `GraphEvolutionService`：图演化提案/验证/受控应用 |
| `skill_service.py` | Facade | `SkillEvolutionService`：Skills 自进化闭环（评估/抽象/治理/调度） |
| `store.py` | Store | `EvolutionStore`：不可变演化策略版本的 CAS 存储 |
| `models.py` | Models | 内部模型别名与未来策略扩展位 |
| `__init__.py` | — | 公共服务入口 |

### 1.13 model_partition（新增；2 文件）
| 文件 | 层 | 职责 |
| --- | --- | --- |
| `service.py` | Facade(stub) | `ModelPartitionService` + `ModelPartitionUnavailableError`：明确标注为 **not-yet-implemented model layer executor** 的边界 |
| `__init__.py` | — | 包边界 |

---

## 2. 新增 4 部件：保留 / 合并 / 并入？

判断标准：① 是否已有同质职责落在别的部件；② 是否自包含且边界清晰；③ 是否当前仅为占位（stub）；④ 生命周期是否相邻。

### 2.1 model_partition → **建议并入 `resource/`**（或 `executor/`）
- 依据：全部件只有 1 个有效文件 `service.py`，且明确是 **not-yet-implemented** 的占位边界。
- 概念重叠：`resource/` 已经管理 `ModelEndpointCandidate` 与模型端点目录（"在多个模型端点间分配"本质就是资源平面的分区/分片职责）；若理解为"模型层执行"，则归 `executor/` 也合理。
- 结论：**不必单独立部件**。并入 `resource/`（推荐，作模型分区子能力）最自然；若实现时确属执行侧，再并入 `executor/`。当前可先删除该部件、留一个 `resource/model_partition.py` 占位即可。

### 2.2 attachments + content → **建议合并为一个 `content`（或 `materials`）部件**
- 依据：二者都是"物料/内容"管理，生命周期相邻——
  - `attachments` = **摄取期**（上传字节存储 + 文本抽取）；
  - `content` = **消费期**（不可变清单 + 执行期 workset 游标）。
- 二者都自带 SQLite 存储、都服务"把外部材料喂给 ACG 步骤"，分开只是把同一关注点拆成两个顶层部件 + 两套存储。
- 合并后 `content/` 可含：`extractors.py`(原 attachments)、`storage.py`(字节/清单持久化)、`workset.py`、`service.py`。减少一个顶层部件与一套存储。
- 风险：若未来 attachments 膨胀（多种格式/大文件管线）再拆回不迟。
- 结论：**短期合并、长期可拆**。比保留两个独立部件更清晰。

### 2.3 evolution → **建议保留独立**
- 依据：它是"从已完成轨迹中演化 Skills / 图"的**元能力**，与主执行链路解耦，是明确的架构分层（自进化）。
- 虽当前多为 TODO（按 `当前系统实现审查.md`，`SkillEvolutionService` 方法全为显式 TODO），但其职责边界清晰、不应污染主链路。
- 结论：**保留 `evolution/` 独立**，不要为了减文件数而并入 planner/executor。

### 2.4 归并结论表
| 新增部件 | 建议 | 理由 |
| --- | --- | --- |
| model_partition | **并入 resource/**（或 executor） | 2 文件 stub，与资源/执行概念重叠，未实现 |
| attachments | **并入 content** | 与 content 同属物料管理，生命周期相邻 |
| content | **吸收 attachments**（合并为 `content`） | 同上 |
| evolution | **保留独立** | 自进化元能力，边界清晰，与主链路解耦 |

---

## 3. 一句话总建议

新增部件里**只有 `evolution` 真正需要独立**；`model_partition` 是未实现的占位应并入 `resource/`；`attachments` 与 `content` 应合并为一个 `content`（物料）部件。这样 12 个部件可收敛到 **10 个**（mission_manager、planner、resource、scheduler、executor、communicator、memory、auditor、recovery、content、evolution——其中 content 由 attachments+content 合并、model_partition 并入 resource）。

> 备注：真正让层次"不清"的并非这 4 个新部件，而是 **planner（29 文件 + topology 子编译器）、resource（3 个子平面挤一个部件）、communicator（broker/reader/reliable 多子关注点）** 的膨胀。若要做层次治理，优先级是：先抽出 `planner/topology` 为独立编译器，再把 `resource` 的子平面理清边界。

# 知弈 AgentOS · ACG 动态群体智能引擎技术设计

# Zhiyi AgentOS · ACG Dynamic Swarm Intelligence Engine Technical Design

> 面向超长程复杂任务的动态异构群体智能架构 —— Core Native 自研引擎

## 0. 文档定位

本文档系统阐述知弈 AgentOS 已经落地的
**规划器（Cognitive Planning Engine）**与**执行器（ACG Executor）**两大核心，
并给出核心算法伪代码与复杂度分析。本阶段创新集中在**架构与 harness 设计**，
以「合同审查 + 跨领域投研」验证一套领域无关的动态群体智能内核。

与赛题能力维度的对应：

| 赛题能力维度            | 本引擎实现抓手                              | 可见性证据                      |
| ----------------------- | ------------------------------------------- | ------------------------------- |
| 感知-规划-执行-反馈闭环 | 意图解析→规划器→ACG→就绪集执行→自愈反馈 | 端到端测试、Trace 全链路        |
| 动态异构拓扑            | ACG 计算图 + 就绪集并行调度（超越线性）     | `/acg` 拓扑视图、并行分支     |
| 低熵通信                | 引擎做唯一中介，按 input_spec 精准投递      | Token 节省率、数据血缘图        |
| 自愈闭环                | 故障注入→检查点→局部重规划                | 恢复轨迹、recoveryCount         |
| 兼容多模型/可扩展       | LLM 网关回落映射 + ACG Adapter 扩展协议     | DeepSeek 真实接入、ACG 统一调度 |

## 1. 总体架构

系统遵循「运行时内核（agentOS）/ 应用服务层（agent）/ 领域能力包（packs）」三层
分离。本阶段新增的能力**全部落在 Core 内核**，保持领域无关：

```text
agentOS/src/agentos/core/
├── acg/              # ★新增 ACG 脊椎：节点/边/蓝图/图算法/线性升格
├── planning/         # ★新增 规划器：意图解析/模板匹配/认知路由/ACG构建/引擎
├── communication/    # ★新增 低熵通信：上下文装配/数据血缘/Token估算
├── execution/        # 扩展：ACG执行器/故障注入/Step wrapper/适配器
├── governance/       # 既有：trace/checkpoint/review/evaluation
├── workflow/         # 既有：task_manager/orchestrator/registry/state_machine
└── runtime.py        # 扩展：接入规划器 + ACG 执行路径
```

**执行引擎三态并存**（通过 `WorkflowDefinition.runtimeEngine` 路由）：

- 线性 YAML：加载阶段提升为 ACG DEPENDENCY DAG 后统一调度
- `acg`：★本阶段自研的就绪集并行调度引擎

两条执行路径共享同一套治理设施（Task/Trace/Checkpoint/Review），互不干扰。标准合同审查由 ACG 执行。

### 1.1 端到端数据流

```text
用户意图(自然语言)
   ↓  IntentParser（真实 DeepSeek / 启发式回退）
TaskSemanticProfile（语义画像：目标/能力/复杂度/熵预算）
   ↓  TemplateMatcher（role+task 索引 + 相似度，≥85% 命中）
   ├─ 命中 → 复用模板 → 线性升格为 ACG（静态优选，零规划开销）
   └─ 未命中 → CognitiveRouter（能力→Agent）→ ACGBuilder（动态生成）
ACGBlueprint（节点+边+约束的统一计算图）
   ↓  ACGExecutor（就绪集并行调度）
   ├─ ContextAssembler（低熵：按 input_spec 精准投递 + 血缘）
   ├─ FaultInjector → 自愈（检查点 + 局部重规划）
   └─ 人审中断 → approve 续跑
最终交付物 + 全链路 Trace + 数据血缘 + 恢复轨迹
```

## 2. ACG 计算图模型（脊椎）

`ACGBlueprint` 是规划器的产物、执行器的输入，统一描述任务步骤依赖、智能体
协作、记忆流动与证据传播。严格对应设计书附件一字段。

**节点（6 类）**：`StepNode`（最小执行单元）、`AgentNode`（智能体）、
`SkillNode`（技能）、`MemoryNode`（记忆）、`EvidenceNode`（证据）、
`ControlNode`（START/END/IF/LOOP/PARALLEL/CONSENSUS）。

**边（7 类）**：`DEPENDENCY`（任务依赖，执行器据此算就绪集）、`COMMUNICATION`
（数据流）、`CONTROL_FLOW`、`EXECUTION`（Agent→Step）、`WRITE`/`READ`（Step↔Memory）、
`SUPPORT`（Evidence→Step）。

设计关键：**只有 DEPENDENCY 边参与执行 DAG 构建**，其余边由通信器/记忆器/
审计器分别消费。这使「执行先后」与「数据/记忆/证据关系」解耦——同一张图既是
执行计划，又是数据血缘图谱。

### 2.1 线性工作流自动升格（向下兼容基石）

一条线性 Step 链就是一张最简单的 DAG。`promote_workflow_to_acg()` 把存量
`WorkflowDefinition` 无损升格：每个 step→StepNode，相邻 step 连 DEPENDENCY 边。
升格后由 ACG 执行器调度，行为与原线性执行完全一致——**存量工作流零改动接入
新架构**，这是「静态优选」一侧的落地基础。

## 3. 规划器（Cognitive Planning Engine）

采用「**静态优选，动态补位**」混合策略。综合资源利用与响应速度：简单/已知任务
复用验证过的模板（零规划开销、质量有保障），复杂/未知任务才动态生成认知网络。

### 3.1 意图解析

`IntentParser` 把自然语言意图解析为 `TaskSemanticProfile`（核心目标、关键约束、
所需认知能力、复杂度、领域、隐含需求、风险等级、熵预算）。

分层设计遵守 Core 不依赖 app 层 LLM 的架构铁律：Core 定义最小 `IntentLLM`
协议，app 层装配时注入真实 DeepSeek 网关；未注入或调用失败时回落确定性
启发式，保证 Core 离线可测、规划不被 LLM 故障阻断。

```python
def parse(intent, domain, task_type) -> TaskSemanticProfile:
    if llm is not None:
        try:
            return parse_with_llm(intent, domain, task_type)  # DeepSeek 结构化输出
        except Exception:
            pass  # 不阻断规划
    return heuristic(intent, domain, task_type)  # 关键词→能力映射 + 长度→复杂度
```

### 3.2 模板匹配（静态优选）

`TemplateMatcher` 以 role_type(domain)+task_type(intent) 为一级索引筛候选，再用
字符级 bigram Dice 相似度对 description/tags 打分；intent 精确命中保底 0.9，
达阈值（默认 0.85）即复用模板。预留 `embed` 钩子，后续可平滑接入向量模型。

```python
def match(profile) -> TemplateMatch:
    candidates = [wf for wf in registry.all() if wf.domain == profile.domain_hint]
    if not candidates: return MISS
    exact = [wf for wf in candidates if wf.intent == profile.task_type_hint]
    if exact:
        return TemplateMatch(exact[0], score=max(0.9, similarity), hit=True)
    best = argmax(candidates, key=similarity)
    return TemplateMatch(best, score, hit = score >= 0.85)
```

### 3.3 认知路由（核心创新）

`CognitiveRouter` 调度的是「认知能力」而非任务节点。对画像中每项 required
capability，在 Agent 注册中心做能力标签语义匹配 + 多维效用评分，绑定最优 Agent；
无候选时触发**动态角色生成**（合成临时 Agent 描述符，标记 Ephemeral）。同时按
协作边数 × 单边熵耗估算总熵，与画像 `entropy_budget` 比较，超预算则记录告警
（完整实现会触发模板替换/消息合并）。

### 3.4 ACG 构建器（动态补位）

`ACGBuilder` 把协作网络物化为可执行 ACG：①按能力顺序分解步骤并实例化 StepNode
绑定 Agent；②建立依赖主干；③**赋能节点注入**——产出结论性内容的步骤后注入
Memory 节点（write 边），需外部依据的步骤注入 Evidence 节点（support 边）；
④图级验证（环检测 + 悬空依赖检查）。

## 4. 执行器（ACG Executor）

借鉴操作系统进程调度思想，以 Step 为基本调度单元。把执行模型从「线性
nextStepId 单指针」升级为「**按 DEPENDENCY 边计算就绪集，并行驱动无依赖
Step**」。执行器自身不承载业务逻辑，是高可靠的状态协调与资源中继器。

### 4.1 就绪集并行调度（核心算法）

```python
def drive(run, blueprint):
    completed = set(run.completed_step_ids)
    while True:
        resolve_control_nodes(blueprint, completed)        # 放行 START/PARALLEL/CONSENSUS
        ready = [s for s in step_nodes
                 if s not in completed
                 and all(dep in completed for dep in deps(s))   # 前驱全完成
                 and status(s) in {PENDING, RETRYING}]
        if not ready:
            if all_done(): complete_run(); return
            return run                                     # 等待人审
        batch = ready[:max_parallelism]
        results = await gather(*[execute_step(n) for n in batch])  # ★并行
        for n, outcome in zip(batch, results):
            if isinstance(outcome, InjectedFault):
                if self_heal(n, outcome): continue         # 自愈续跑
                mark_failed(n); return
            elif outcome == WAITING_REVIEW: waiting = True
            elif outcome == COMPLETED: completed.add(n)
        if waiting: return
```

线性工作流的就绪集每轮恰好一个节点 = 退化为原线性行为（兼容性保证）；菱形
图 `A→{B,C}→D` 则在 A 完成后让 B、C 并发执行——动态拓扑由此「可见」。

### 4.2 节点执行 wrapper（统一可观测性）

每个 Step 产生统一事件序列：`STEP_SCHEDULED`（就绪集调度，带 readySet）→
`STEP_STARTED`（带 inputSummary）→ `DATA_CONSUMED`（低熵装配度量）→
`AGENT_CALLED`（带 durationMs）→ `DATA_PRODUCED` → `STEP_SUCCEEDED`
（带 outputSummary）。durationMs 真实计时，输入输出摘要有界（避免日志膨胀）。

`StepNode↔WorkflowStep` 桥接复用既有 `Orchestrator.dispatch_agent` 与 Agent
注册中心，使新引擎无缝复用所有 Pack 智能体、治理与前端展示。

## 5. 低熵通信中介

工作流引擎是所有 Step 间通信的**唯一可信中介**：节点间不传自然语言对话，只沿
依赖边传结构化数据；引擎按下游 `input_spec` 这份「数据采购清单」精准投递。

### 5.1 按需投递与节省率

```python
def assemble(blueprint, step_node, upstream_outputs) -> ContextPack:
    sources = dependency_sources(step_node) or all_upstream
    tokens_available = sum(estimate_tokens(upstream_outputs[s]) for s in sources)
    spec = step_node.input_spec
    if spec.get("from"):    delivered = pick_by_source_map(spec["from"])   # 定向提取
    elif spec.get("fields"):delivered = pick_fields(spec["fields"])        # 字段清单
    else:                   delivered = passthrough(sources)               # 回退兼容
    evidence_refs = aggregate_evidence(sources)                            # 证据链聚合
    tokens_delivered = estimate_tokens(delivered)
    saving_ratio = 1 - tokens_delivered / tokens_available
    ledger.record_consumption(step_node, sources, consumed_fields)         # 血缘记账
    return ContextPack(data=delivered, evidence_refs=..., saving_ratio=...)
```

实测：菱形图中下游仅取 2 个字段、不倾倒上游全文，**节省率达 99.65%**
（3157→11 token）。这是赛题「Token 资源利用率」「降噪信噪比」的硬指标。

### 5.2 数据血缘与双向追溯

`ProvenanceLedger` 记录 `DataProductionEvent`（数据诞生 + checksum）与
`DataConsumptionEvent`（谁消费了谁的哪些字段）：

- **前向追溯**「这个结论从何而来」：递归回溯消费链至原始输入。
- **后向影响**「这个数据用在了何处」：定位所有下游消费者。

血缘图持久化到 `run.provenance`，经 `/acg` 端点供前端渲染。

## 6. 自愈闭环

`FaultInjector` 按任务输入声明在指定节点注入 timeout/crash/empty_evidence
故障（有限次触发后自愈，模拟瞬时异常），不污染生产逻辑。执行器捕获可恢复
故障后：

```python
def self_heal(run, step, fault):
    if step.retry_count >= 3: return False          # 循环保护
    trace(STEP_FAILED, recoverable=True)            # 故障入轨
    checkpoint = checkpoint_store.create(run, step) # 检查点（保存现场）
    step.status = PENDING; step.retry_count += 1    # 局部重规划：复位子图
    trace(RUN_RECOVERED, strategy="local_replan")   # 恢复轨迹入轨
    return True                                     # 下一轮就绪集重新调度该节点
```

实现赛题「接受动态注入异常、无人工干预自主完成闭环」：注入→检查点→局部
重规划→续跑至完成，全程留下可审计恢复轨迹（recoveryCount、local_replan）。

## 7. 复杂度分析

记 ACG 节点数 N、依赖边数 E、最大并行度 P、关键路径长度 L。

| 操作               | 时间复杂度 | 说明                                   |
| ------------------ | ---------- | -------------------------------------- |
| 环检测（DFS 三色） | O(N+E)     | 规划交付前一次性验证                   |
| 拓扑排序（Kahn）   | O(N+E)     | 同上                                   |
| 单轮就绪集计算     | O(N·d̄)  | d̄ 为平均入度，遍历未完成 Step        |
| 全程调度轮数       | O(L)       | 每轮推进至少一层；线性图 L=N           |
| 上下文装配（每步） | O(F)       | F 为下游 input_spec 字段数，非上游全量 |
| 血缘前向追溯       | O(C)       | C 为消费事件数                         |

**并行收益**：线性执行总时长 ≈ Σ 各步耗时；就绪集并行后 ≈ 关键路径耗时，
理论加速比上界为「总工作量 / 关键路径」，受 P 截断。

**低熵收益**：传统全量拼接下游上下文规模随步数线性膨胀 O(ΣSᵢ)；按需投递后
每步仅 O(F) ≪ O(ΣSᵢ)，避免长程任务的 Token 冗余爆炸。

## 8. 测试与验证

| 套件    | 数量         | 覆盖                                          |
| ------- | ------------ | --------------------------------------------- |
| agentOS | 48           | ACG 模型/升格/图算法、通信、规划器、既有核心  |
| agent   | 113(+1 skip) | ACG 执行器/低熵/自愈/API 集成、合同审查、既有 |

关键端到端验证：①菱形图并行执行；②人审中断 approve 续跑；③低熵节省率；
④三类故障自愈至完成；⑤`/acg` 暴露拓扑+血缘+恢复+低熵指标；⑥**真实
DeepSeek 意图解析 → 跨领域（投研）动态生成 ACG**。

## 9. 后续演进

- 认知路由：效用评分接入历史成功率/负载/成本真实信号；熵预算超限的模板替换闭环
- ACG 构建器：依赖分析自动识别可并行子图（当前动态图为线性主干）
- 通信压缩：上游长文本按需调摘要技能（动态上下文压缩）
- 向量检索：模板匹配与记忆唤醒接入向量库（已预留钩子）
- 前端：ACG 拓扑图/数据血缘/恢复轨迹可视化面板（数据源 `/acg` 已就绪）

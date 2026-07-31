# ACG认知规划引擎（Cognitive Planning Engine）与 ACG 就绪集并行执行器（ACG Executor）技术报告

> 日期： 2026-07-20
> 面向超长程复杂任务的动态异构群体智能架构与深度协同推理
> 核心引擎完全自研（Core Native）

---

## 一、摘要

本阶段在既有「治理完备但执行模型为线性单 Agent」的工作流引擎之上，落地了
设计书最核心的两大模块——**认知规划引擎（Cognitive Planning Engine）**与
**ACG 就绪集并行执行器（ACG Executor）**，并配套**低熵通信中介**、**自愈恢复**
与**可视化面板**，打通了从**高维模糊的自然语言意图**到**动态非确定性环境下
自主闭环交付**的完整链路：

```TypeScript
自然语言意图 → 意图解析 → 规划器(静态优选/动态补位) → ACG 计算图
            → 就绪集并行执行 → 低熵通信(按需投递+数据血缘) → 自愈恢复
            → 交付物 + 全链路审计 + 可视化
```

整个引擎以 **ACG（Agentic Computation Graph）** 为统一计算模型，作为
`runtimeEngine=acg` 是生产工作流的统一执行路径；线性 YAML 在加载阶段提升为
带 DEPENDENCY 边的 ACG DAG，并共享 Task / Trace / Checkpoint / Review 治理设施。

---

## 二、赛题能力维度对照

| 赛题能力维度            | 本引擎实现                                   | 验证证据                           |
| ----------------------- | -------------------------------------------- | ---------------------------------- |
| 感知-规划-执行-反馈闭环 | 意图解析→规划器→ACG→就绪集执行→自愈反馈  | 端到端测试 + Trace 全链路          |
| 动态异构拓扑与稀疏路由  | ACG 计算图 + 就绪集并行调度（超越线性）      | 菱形图 B/C 并行、`/acg` 拓扑视图 |
| 低熵通信                | 引擎作唯一中介，按 input_spec 精准投递       | Token 节省率 21.7%、数据血缘图     |
| 超长程上下文连续性      | Memory 节点注入 + 证据链聚合 + 检查点        | 赋能节点注入、证据回填             |
| 端云异构/可扩展         | LLM 网关回落映射 + ExecutionAdapter 扩展协议 | DeepSeek 真实接入、ACG 统一调度    |
| 自愈闭环（异常注入）    | 故障注入→检查点→局部重规划                 | 三类故障自愈、recoveryCount        |
| 可视化与可解释          | ACG 拓扑/血缘/恢复轨迹/低熵指标面板          | 前端面板 +`/acg` 聚合端点        |

---

## 三、四大创新点

**创新一：ACG 统一计算模型 + 就绪集并行调度。**

把执行从「线性 nextStepId单指针」升级为「按 DEPENDENCY 边计算就绪集、并发驱动无依赖 Step」。同一张ACG 既是执行计划（DEPENDENCY 边），又是数据血缘图谱（COMMUNICATION/WRITE/SUPPORT 边）——执行先后与数据/记忆/证据关系解耦。

**创新二：静态优选 + 动态补位的混合规划。**
 简单/已知任务复用验证过的模板（零规划开销、质量有保障），复杂/未知任务由认知路由 + ACG 构建器动态生成认知协作网络。认知路由调度的是「认知能力」而非任务节点，这是与传统 DAG
编排的本质区别。

**创新三：工作流引擎作唯一通信中介的低熵协议。**
 智能体间不传自然语言对话，只沿依赖边传结构化数据；引擎按下游 `input_spec` 这份「数据采购清单」精准投递，避免长程任务的 Token 冗余爆炸。每次数据生产/消费均留痕，构成可双向
追溯的数据血缘图谱。

**创新四：故障可规划的自愈闭环。**
把模型超时、Agent 崩溃、证据为空视为可规划事件，通过检查点 + 局部重规划实现无人工干预的自主纠错，全程留下可审计恢复轨迹。

---

## 四、分阶段实施记录

每阶段保持测试全绿、独立提交，从基线 117 项增至 161 项。

| 阶段 | 内容                                               | 提交    | 测试增量     |
| ---- | -------------------------------------------------- | ------- | ------------ |
| 0    | LLM 变量映射修复 + 测试隔离 + 真实 DeepSeek 验证   | —      | 基线 117 绿  |
| 1    | ACG 数据模型 + 线性工作流自动升格 + 图算法         | db2c027 | +14          |
| 2    | 就绪集并行调度执行器 + 节点 wrapper + Step Trace   | db2c027 | +4           |
| 3    | 低熵通信中介（按需投递 + 数据血缘 + 节省率）       | 04a4af4 | +7           |
| 4    | 认知规划引擎（意图解析/模板匹配/认知路由/ACG构建） | 8fdbe25 | +10          |
| 5    | 自愈恢复（故障注入 + 检查点 + 局部重规划）         | a9ad56c | +6           |
| 6    | ACG 引擎接入 API + 真实 LLM 意图解析注入           | a9428a4 | +4           |
| 7    | 前端可视化面板（拓扑/血缘/恢复/低熵指标）          | 已提交  | 前端构建通过 |

### 阶段 0：地基修复

发现并修复关键缺陷：`.env` 配置为 `DEEPSEEK_*`，而 LLM 网关读 `AGENTOS_LLM_*`，
变量名错位导致即便配了真实 key 也静默回落 mock。修复方案：`from_env()` 增加
回落映射（未显式设 `AGENTOS_LLM_*` 时自动探测 `DEEPSEEK_*`/`DASHSCOPE_*`），
并在 conftest 加 autouse fixture 强制测试走 mock（稳定、零成本、零网络）。
真实 DeepSeek 端到端验证通过（latency ~2.5s）。

### 阶段 1：ACG 脊椎数据模型

- 6 类节点（Step/Agent/Skill/Memory/Evidence/Control）、7 类边，严格对应设计书附件一
- 图算法：环检测（DFS 三色）、拓扑排序（Kahn）、悬空依赖检查、**就绪集计算**
- `promote_workflow_to_acg()`：线性工作流无损升格为 ACG，向下兼容存量工作流

### 阶段 2：就绪集并行执行器

- 主循环：每轮算就绪集 → `asyncio.gather` 并发执行 → 更新完成集
- 菱形图 `A→{B,C}→D` 中 B、C 真实并发；线性图退化为原行为（兼容）
- StepNode↔WorkflowStep 桥接，复用既有 Agent 注册与 dispatch
- 节点级统一 Trace：scheduled→started→data_consumed→agent_called→data_produced→succeeded

### 阶段 3：低熵通信中介

- `ContextAssembler`：按 `input_spec.fields`/`from` 精准提取上游字段，证据链聚合
- `ProvenanceLedger`：数据生产/消费事件，前向追溯「从何而来」+ 后向影响「用在何处」
- Token 节省率量化，血缘图持久化到 `run.provenance`

### 阶段 4：认知规划引擎

- `IntentParser`：真实 LLM（注入式）+ 启发式回退双路径，Core 保持领域无关
- `TemplateMatcher`：role+task 索引 + 字符 bigram Dice 相似度，阈值 0.85
- `CognitiveRouter`：能力→Agent 绑定 + 动态角色生成桩 + 熵预算记账
- `ACGBuilder`：动态生成 ACG + 赋能节点注入（Memory/Evidence）+ 图验证
- `PlanningEngine`：四组件编排，接入 runtime（`usePlanner` 触发，决策入 Trace）

### 阶段 5：自愈恢复

- `FaultInjector`：按任务输入声明注入 timeout/crash/empty_evidence，有限次后自愈
- 自愈机制：捕获可恢复故障 → 检查点 → 复位子图重跑 → 续跑至完成
- 单节点自愈上限防死循环；完整恢复轨迹入 Trace（local_replan 策略）

### 阶段 6：API 接入 + 真实 LLM

- app 层装配时 `set_intent_llm` 注入 DeepSeek 网关（多层兜底）
- 新增 `GET /core/workflows/runs/{id}/acg` 聚合视图端点
- 真实验证：跨领域投研需求 → DeepSeek 意图解析 → 动态生成 ACG（非模板）

### 阶段 7：可视化面板

- `AcgTopologyGraph`（vis-network 拓扑图，节点按类型着色、完成态高亮）
- `AcgLowEntropyMetrics`（节省率/累计节省/恢复次数指标卡）
- `AcgProvenancePanel`（数据血缘 + 恢复轨迹 tab）
- `AcgVisualizationView`（主页面，含故障注入开关、就绪集批次可视化）
- 数据源 `/acg` 端点；`npm run build` 编译通过

---

## 五、核心算法与复杂度

记 ACG 节点数 N、依赖边数 E、最大并行度 P、关键路径长度 L。

| 操作               | 复杂度    | 说明                       |
| ------------------ | --------- | -------------------------- |
| 环检测 / 拓扑排序  | O(N+E)    | 规划交付前一次性验证       |
| 单轮就绪集计算     | O(N·d̄) | d̄ 平均入度               |
| 全程调度轮数       | O(L)      | 线性图 L=N                 |
| 上下文装配（每步） | O(F)      | F 为下游字段数，非上游全量 |
| 血缘前向追溯       | O(C)      | C 为消费事件数             |

**就绪集调度核心算法（伪代码）：**

```python
def drive(run, blueprint):
    completed = set(run.completed_step_ids)
    while True:
        resolve_control_nodes(blueprint, completed)
        ready = [s for s in step_nodes
                 if s not in completed
                 and all(dep in completed for dep in deps(s))
                 and status(s) in {PENDING, RETRYING}]
        if not ready:
            if all_done(): complete_run(); return
            return run                              # 等待人审
        batch = ready[:max_parallelism]
        results = await gather(*[execute_step(n) for n in batch])
        for n, outcome in zip(batch, results):
            if isinstance(outcome, InjectedFault):
                if self_heal(n, outcome): continue  # 自愈续跑
                mark_failed(n); return
            elif outcome == COMPLETED: completed.add(n)
```

**并行收益**：线性执行总时长 ≈ Σ 各步耗时；就绪集并行后 ≈ 关键路径耗时。
**低熵收益**：传统全量拼接上下文 O(ΣSᵢ) 随步数线性膨胀；按需投递每步仅 O(F) ≪ O(ΣSᵢ)。

---

## 六、验证证据

### 测试基线

| 套件    | 数量         | 覆盖                                          |
| ------- | ------------ | --------------------------------------------- |
| agentOS | 48           | ACG 模型/升格/图算法、通信、规划器、既有核心  |
| agent   | 113(+1 skip) | ACG 执行器/低熵/自愈/API 集成、合同审查、既有 |

### 真实运行验证（合同审查 ACG 工作流）

以 `legal_contract_review_v1` 工作流（复用 legal pack 真实 Agent）实测：

- **正常执行**：6 节点全完成，5 次数据消费血缘，状态 completed
- **低熵通信**：下游步骤按 `input.fields` 精准投递，平均 Token 节省率 **21.7%**
  （累计省 193 / 1192 token）；`clause_classify` 仅取 contract_type/scope/payment_terms
  三字段，而非上游全部 9 字段
- **故障自愈**：在 `risk_detect` 注入超时故障 → 检查点恢复 + 局部重规划 →
  仍 completed，recoveryCount=1，恢复轨迹含 step_failed + run_recovered 两条事件
- **跨领域动态规划**：投研需求经真实 DeepSeek 意图解析 → 无模板命中 →
  动态生成 7 节点 ACG（含注入的 Evidence/Memory 节点）

---

## 七、演示指南

**入口**：前端 `/agentos/acg` 页面（ACG 动态群体智能引擎）。

**演示步骤**：

1. 输入合同文本（默认已填示例）
2. 可勾选「启用认知规划器」（意图解析 + ACG 构建）
3. 可勾选「注入故障演示自愈」，选择节点与故障类型
4. 点「启动 ACG 引擎」

**观察点**：

- **ACG 拓扑图**：节点按类型着色（步骤/智能体/记忆/证据/控制），已完成节点绿框高亮
- **就绪集调度轨迹**：每轮就绪批次，体现动态拓扑（非预设链表）
- **低熵通信指标**：平均节省率、累计节省 Token、投递/可获取进度条
- **数据血缘**：每条数据流转（producer→consumer + 消费字段）
- **恢复轨迹**：故障注入 → 检查点恢复 → local_replan 策略

**后端 API**：`GET /ai/core/workflows/runs/{runId}/acg` 返回拓扑+血缘+恢复+低熵指标聚合视图。

---

## 八、已知边界与后续演进

**本阶段简化项（诚实标注）**：

- 认知路由效用评分为简化版（语义匹配为主），历史成功率/负载/成本信号待接入
- ACG 构建器动态图当前为线性主干，依赖分析自动识别并行子图待补
- 熵预算目前为记账告警，超限触发模板替换/消息合并的闭环待实现
- 上下文压缩（上游长文本按需调摘要技能）已设计未落地
- 向量检索已预留钩子，模板匹配与记忆唤醒当前用关键词相似度

---

## 九、结论

本阶段以完全自研的 Core Native 引擎，将设计书最核心的规划器与执行器从纸面
落地为可运行、可验证、可视化的系统，打通了**「意图→规划→ACG→并行执行→
低熵通信→自愈」**完整闭环，并以合同审查 + 跨领域投研双场景验证了一套
**领域无关**的动态异构群体智能内核。所有能力以测试与真实运行证据支撑，
引擎作为新执行路径与既有引擎并存，治理设施共享，为后续多场景扩展与深度协同推理奠定了架构基础。

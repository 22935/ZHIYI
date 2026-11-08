# 记忆器架构与实现

本目录实现 AgentOS 的记忆读写、检索和运行期工作记忆投影。对外统一通过
`MemoryService` 访问记录；记忆合同定义在 `contracts.memory`，执行器负责决定
何时读取、何时提交写入。存储层不负责策略或权限判断，调用链应保持为：

```text
WorkflowRuntime
  └─ SQLiteMemoryStore（运行时持久化；可注入其它 store）
       └─ MemoryService（准入、检索、预算、引用校验）
            ├─ admission / retrieval / algorithms
            ├─ executor.ACGNodeRunner（按步骤策略召回与提交后发布）
            └─ review（审核通过后发布待审核记忆）
```

## 模块职责

| 模块 | 职责 |
| --- | --- |
| `contracts/memory.py` | 跨组件合同：`MemoryType`、`MemoryRecord`、`MemoryQuery`、`MemoryPolicy` 和批量写入合同。记录包含 ID、类型、JSON 内容、scope、重要度、标签和创建/过期时间。 |
| `models.py` | 记忆组件的投影/事件类型：`WorkingMemory`、混合检索命中及检索事件、结构化提交事件、阶段压缩包 `PhaseCapsule`。 |
| `service.py` | 唯一的读写 Facade。执行准入、过期与范围过滤、混合排序、Token 预算、步骤记忆引用校验、阶段 capsule 创建和运行期工作记忆构造。 |
| `store.py` | 存储适配。`MemoryStore` 是进程内字典；`SQLiteMemoryStore` 把合同 JSON 存进独立 SQLite 表并支持重启后恢复。两者提供 `put/get/values`。 |
| `admission.py` | 按策略允许的 `memory_type` 做写入准入；无策略时允许写入。 |
| `retrieval.py` | 元数据过滤、BM25 词法评分及可选的 embedding/vector adapter。内置确定性哈希 embedding 和内存向量索引主要用于离线测试。 |
| `algorithms.py` | 传统 `search` 的确定性重排：重要度降序，ID 升序打破平局。 |
| `lifecycle.py` | 记忆过期判断。混合检索会在评分前排除已过期记录。 |
| `compression.py` | 输出包含 ID、类型和重要度的可审计最小摘要；不是语义压缩，也不修改或删除原记录。 |
| `events.py` | 从已提交步骤结果构建确定性、引用安全的结构化记忆事件，不复制 prompt 或完整输出正文。 |

## 写入与提交

1. `ACGNodeRunner` 解析 Blueprint 步骤上的 `memoryPolicy`，确定是否读/写、读写类型、条数、Token 预算及审核要求。策略在执行时被校验并传给记忆服务。
2. 读取只发生在启用 read 时。`recall_for_step` 强制将 `scope` 设为当前 `run_id`，避免步骤借查询读取其它运行的记忆。
3. 写入内容来自通过输出合同校验及字段白名单控制后的结果；节点不会把 Agent 原始响应或完整 `WorkflowRun` 直接灌入记忆。`StructuredMemoryEventBuilder` 还会生成由 run/step/commit 确定的事件 ID，并限制摘要和证据引用长度。
4. 节点先把 `pendingMemory` 意图放入待提交结果。普通成功结果在执行结果提交后由 `_publish_committed_memory` 发布；需要审核的内容在审核通过后由 Review 流程发布，审核前不会进入正式存储或变成可读引用。策略拒绝写入时返回空结果，不产生有效 `memoryRef`。
5. `remember_step_output` 使用 `memory:{run_id}:{step_id}` 作为幂等 ID。同一 ID、类型、scope、标签和内容的重试会复用记录；同 ID 内容不同则报错，避免恢复重放覆盖已提交事实。
6. `assert_step_ref` 校验 checkpoint 中的引用确实存在，并核对它属于当前 run 与指定来源步骤；不能仅凭可预测的 ID 字符串信任引用。

通用 `remember` 会先调用 `admitted`，获准后交给 store 保存；若配置了 embedding 和向量索引，再更新派生索引。底层存储错误会向上抛出。当前 `MemoryPolicy` 的准入只检查允许类型；保留天数、审计要求等字段由执行/审核编排处理，不应误认为 store 自动执行了这些约束。

## 检索流程

### 混合检索

`hybrid_search` 从权威 store 读取记录，依次执行：

1. 按当前 UTC 时间排除过期记录。
2. 依据 `MemoryQuery` 过滤类型、scope 和标签。步骤召回固定使用当前 run 的 scope。
3. 对候选内容计算 BM25 词法分数；文本由 JSON 内容生成，tokenizer 支持英文/数字 token 和中文字符/二元组。
4. 若同时注入 embedding adapter 与 vector index，则查询向量索引，并仅保留元数据过滤后仍允许的 ID。两个排名用常数 `60` 的 Reciprocal Rank Fusion (RRF) 融合，分数相同时按 ID 稳定排序。
5. 按候选记录内容估算 Token 成本，跳过放不进预算的完整记录，不截断正文；最多返回 query limit 条。
6. 返回记录、命中分数和 `MemoryRetrievalEvent`（scope、模式、引用、预算及降级原因），并保存为 `last_retrieval_event` 供执行器审计投影使用。

默认 `MemoryService()` 不启用语义向量检索，只执行 BM25；若配置了 adapter 但搜索索引抛错，会退化为词法排序并记录 `VECTOR_INDEX_UNAVAILABLE`。缺少语义模型时记录 `SEMANTIC_MODEL_NOT_CONFIGURED`。内置哈希 embedding 不是语义模型，不能把它当作生产语义召回质量保证。向量索引是派生数据；service 初始化时可从权威 store 重建。

另有简化的 `search(query)`：按类型/scope/tag 做本地过滤，再按重要度重排；它不执行 BM25、向量召回或预算控制。不要将其与 `hybrid_search` 混为一谈。

### 预算与阶段 capsule

`recall_for_step` 将 `run_id` 固定为 scope，可选类型、limit 和非负 Token 预算，并记录检索事件。`create_phase_capsule` 只接受当前 run 内存在的源记忆引用，按预算选取完整记录，汇总摘要、证据、决策、风险和关键事实；capsule 以语义记忆保存，固定 ID 重放时内容相同则复用、不同则拒绝。

## 工作记忆与记忆类型

`WorkingMemory` 是一次运行给 Agent 使用的轻量上下文投影，包含任务输入与已完成/等待审核步骤的观察，不是持久化 store，也不替代 executor 图状态。`from_context_pack` 只读取通信器已过滤的 `source_data`，避免旁路读取上游完整输出。

合同枚举支持 `episodic`、`semantic`、`procedural`、`working`、`evidence`。类型是分类元数据；如何构造内容以及是否允许读取/写入由步骤策略和调用方决定。

## 持久化、边界与当前限制

- `WorkflowRuntime` 默认使用 `SQLiteMemoryStore`，数据库路径由 `AGENTOS_EXECUTION_MEMORY_DB` 指定，默认 `data/execution_memory.sqlite3`；运行/部署方负责管理该文件和生命周期。独立创建的 `MemoryService()` 默认使用易失的 `MemoryStore`。
- SQLite 表以 `memory_id` 为主键保存合同 JSON；`put` 是覆盖写入并逐条提交。store 不执行策略、scope、过期和检索排序，这些必须经 `MemoryService`。
- 当前 SQLite 适配器没有向量索引、全文索引、加密配置或显式事务批次；`close()` 负责关闭连接。默认进程内 store 与内存向量索引也没有并发锁。多进程/并发一致性需由替换的存储适配器提供。
- 检索的 scope 是数据隔离过滤，不等同于完整授权系统。新增外部检索器或存储时必须保持 `MemoryService` 为唯一读写入口，并确保在评分前执行准入边界，避免跨 scope 结果进入排名。
- `compact_record` 只生成元数据摘要；真正的阶段压缩由 capsule 逻辑负责，且保留源引用。记忆系统不会自动推断、合并或遗忘语义记忆。

## 常用入口

```python
from components.memory import MemoryService
from components.memory.store import SQLiteMemoryStore

store = SQLiteMemoryStore(db_path="data/execution_memory.sqlite3")
memory = MemoryService(store=store)

# 执行器内部按 run 隔离召回；生产写入应使用受控输出与冻结策略。
records = memory.recall_for_step(
    run_id="run-123",
    step_id="summarize",
    query="已确认的关键事实",
    limit=5,
    token_budget=1200,
)
```

组件级测试位于 `tests/components/memory/`；执行器与恢复/持久化集成覆盖在
`tests/runtime/` 及 `tests/components/executor/`。

# Memory Decoupling Design

## Goal

将 AgentOS 记忆能力从当前集中式 `MemoryService` 演进为可替换、可审计、可渐进迁移的控制平面，同时保持现有执行器、审核恢复和 SQLite 使用方式兼容。

## Scope

本设计采用低风险 MVP 路线，先落地三个边界：

```text
recall != assemble
staging != active
authoritative store != derived index
```

第一阶段不实现图召回、跨机事务、复杂 ANN、自动语义合并和无限长度自治。它们保留为后续扩展点。

## Target Architecture

```text
Executor / Runtime
        |
        v
MemoryFacade
  |-- RequestGate / ScopeGuard
  |-- RecallOrchestrator
  |     |-- DirectRefRetriever
  |     |-- LexicalRetriever
  |     `-- Optional VectorRetriever
  |-- ContextAssembler
  `-- CommitCoordinator
        |-- AdmissionGate
        |-- StagingStore
        |-- AuthoritativeStore
        `-- DerivedIndexManager
```

`MemoryFacade` 是应用层唯一入口。检索器只返回候选和分数，装配器只负责预算与上下文结构，存储只负责持久化，审核器只返回决策，执行器不直接访问 store。

## MVP Contracts

新增三组运行期模型：

- `MemoryContextRequest`：包含 request/run/step 身份、scope、步骤意图、显式引用、允许的记忆类型、预算和策略版本。
- `CandidateSet`：包含候选、拒绝原因和检索事件；拒绝原因至少区分 scope、过期、未命中、排名淘汰、预算超限。
- `ContextPack`：包含不可变 pack ID、内容 hash、分区 sections、source refs、omitted 信息和策略/合同版本。
- `MemoryWriteBatch` / `CommitReceipt`：封装幂等键、受控事件、审核引用、暂存状态和最终 memory refs。

现有 `recall_for_step()`、`hybrid_search()` 和 `remember_step_output()` 保留为兼容包装器，内部委托新组件，不立即删除旧调用方。

## Read Flow

1. `RequestGate` 校验身份、预算、策略和版本。
2. `ScopeGuard` 在召回前过滤 scope、过期和 active 状态。
3. `RecallOrchestrator` 调度显式引用、BM25 和可选向量检索。
4. `FusionRanker` 合并候选，保持确定性排序。
5. `ContextAssembler` 按 L0/L1/L2/L3 和 Token 预算选择完整记录。
6. 生成不可变 `ContextPack`，保留 omitted/rejected 归因。

MVP 的 L0 只支持显式引用和现有受控字段，不引入新的自动硬约束推断。L0 装不下时返回结构化错误，不静默丢弃。

## Write Flow

1. 执行器提交 `MemoryWriteBatch`，内容必须是已生成的结构化事件。
2. `CommitCoordinator` 校验幂等键、scope、策略和审核状态。
3. MVP 先写入 staging/intent 记录，允许当前 `pendingMemory` 兼容。
4. 审核通过或普通 allow 后统一调用 promote 流程。
5. promote 在单个 SQLite 事务内写 active 记录、更新索引、记录提交状态。
6. 重试返回同一 receipt；相同逻辑 ID 内容不一致时拒绝覆盖。

完整的异步审计队列、大对象两阶段上传和跨分片事务属于后续阶段。

## Data Rules

`MemoryRecord` 增加但保持默认兼容的治理字段：`status`、`version`、`contentHash`、`sourceRefs`、`evidenceRefs`、`policyVersion`、`supersedes`。状态至少支持 `ACTIVE`、`CANDIDATE`、`PENDING_REVIEW`、`REJECTED`、`SUPERSEDED`。

权威记录追加写入；旧版本不删除，新的版本通过 `supersedes` 关联。向量索引是派生数据，初始化和运维时可从权威记录重建，不能成为唯一事实源。

## Compatibility and Migration

迁移顺序固定为：

1. 合同和端口，不改变现有调用结果。
2. 拆分召回与装配，旧 API 做 facade wrapper。
3. 执行器切换到 `ContextPack` 和 `MemoryFacade`。
4. 统一普通提交与审核提交。
5. SQLite 升级为权威记录 + staging + 版本追加。
6. 增加 FTS5、真实 embedding、图关联和完整治理。

每一步必须有单元测试、组件测试和受影响的 runtime 回归；任何阶段不得同时修改公共合同、存储格式和执行器时序而没有兼容迁移。

## Non-Goals

- 不在 MVP 中让 Agent 自由指定任意 query、top-k 或相似度阈值。
- 不将原始 prompt、完整 Agent 响应或完整 WorkflowRun 写入记忆。
- 不把 `access_count` 当作 authority 晋升依据。
- 不承诺 SQLite 多进程或多机强一致。


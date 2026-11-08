# Memory Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** 在保持现有 AgentOS 运行时兼容的前提下，将记忆器拆成独立的请求校验、召回、装配和提交边界，并为 staging、版本追加和派生索引留下稳定扩展点。

**Architecture:** 以 `MemoryFacade` 作为唯一应用入口；`RecallOrchestrator` 负责候选召回，`ContextAssembler` 负责预算装配，`CommitCoordinator` 负责幂等提交和晋升。当前旧 API 保留为兼容包装器，SQLite 仍是 MVP 权威存储。

**Tech Stack:** Python, Pydantic, SQLite, pytest, 现有 AgentOS runtime/executor contracts。

---

## 文件职责地图

- Modify: `apps/agentOS/src/contracts/memory.py`，增加兼容治理字段和提交状态合同。
- Create: `apps/agentOS/src/components/memory/contracts.py`，定义读请求、候选集、ContextPack、写批次和回执。
- Create: `apps/agentOS/src/components/memory/ports.py`，定义 store、retriever、index、audit 端口协议。
- Create: `apps/agentOS/src/components/memory/gating.py`，实现请求校验、scope/expiry/status 硬门控。
- Create: `apps/agentOS/src/components/memory/recall.py`，实现召回编排、显式引用、BM25/vector 适配。
- Create: `apps/agentOS/src/components/memory/assembly.py`，实现 L0-L3 分区、预算选择和 pack hash。
- Create: `apps/agentOS/src/components/memory/commit.py`，实现 staging、幂等、promote 和版本策略。
- Modify: `apps/agentOS/src/components/memory/service.py`，收敛为 facade 和旧 API 兼容层。
- Modify: `apps/agentOS/src/components/memory/store.py`，增加状态/版本/staging 操作，保留旧 store 方法。
- Modify: `apps/agentOS/src/components/memory/lifecycle.py`，修复导入并统一过期判断入口。
- Modify: `apps/agentOS/src/components/memory/__init__.py`，暴露新入口和读写模型。
- Modify: `apps/agentOS/src/components/executor/node_runner.py`，从 facade 获取 pack、提交 write batch。
- Modify: `apps/agentOS/src/runtime/review.py`，只产生/校验审计决策，调用 promote。
- Modify: `apps/agentOS/src/runtime/workflow_runtime.py`，保持 store 注入和恢复路径兼容。
- Create/Modify: `apps/agentOS/tests/components/memory/test_gating.py`、`test_recall_pipeline.py`、`test_context_assembly.py`、`test_commit_coordinator.py`。
- Modify: `apps/agentOS/tests/components/memory/test_execution_memory.py`、`test_hybrid_capsule.py` 及受影响 runtime 测试。
- Modify: `apps/agentOS/src/components/memory/README.md`，同步目标架构与迁移状态。

## Phase 0: Baseline and Safety Net

### Task 1: 固化当前行为基线

**Files:**
- Test: `apps/agentOS/tests/components/memory/test_execution_memory.py`
- Test: `apps/agentOS/tests/components/memory/test_hybrid_capsule.py`
- Test: `apps/agentOS/tests/runtime/test_golden_memory.py`

- [ ] 运行记忆组件和相关 runtime 测试，记录当前通过集。
- [ ] 为 SQLite 重启恢复、跨 run 隔离、过期过滤、预算选择、审核后写入各补一个回归测试。
- [ ] 运行：`pytest apps/agentOS/tests/components/memory apps/agentOS/tests/runtime/test_golden_memory.py -q`。
- [ ] 预期：新增测试在未改代码时全部通过；若失败，先修复基线测试假设，不进入重构。

## Phase 1: Contracts and Ports

### Task 2: 增加治理字段并保持旧数据可读

**Files:**
- Modify: `apps/agentOS/src/contracts/memory.py`
- Test: `apps/agentOS/tests/components/memory/test_memory_contracts.py`

- [ ] 为 `MemoryRecord` 增加 `status`、`version`、`contentHash`、`sourceRefs`、`evidenceRefs`、`policyVersion`、`supersedes`，全部提供旧数据可用的默认值。
- [ ] 为状态定义 `MemoryStatus` 枚举，默认新记录为 `ACTIVE`，暂存记录显式传入其它状态。
- [ ] 保持 `model_validate()` 能读取当前 SQLite 中没有新字段的 JSON。
- [ ] 测试：旧字段 JSON 恢复、新字段 alias 序列化、非法版本/状态拒绝。
- [ ] 运行：`pytest apps/agentOS/tests/components/memory/test_memory_contracts.py -q`。

### Task 3: 定义三条读写合同

**Files:**
- Create: `apps/agentOS/src/components/memory/contracts.py`
- Create: `apps/agentOS/src/components/memory/ports.py`
- Test: `apps/agentOS/tests/components/memory/test_memory_contracts.py`

- [ ] 定义 `MemoryContextRequest`，字段包含 request/run/step、scope、stepIntent、explicitRefs、memoryTypes、limit、tokenBudget、policyVersion、schemaVersion。
- [ ] 定义 `MemoryCandidate`、`RejectedMemory`、`CandidateSet`，保留检索模式、fallback 和拒绝阶段。
- [ ] 定义 `ContextSection`、`OmittedMemory`、`ContextPack`，通过 canonical JSON 计算稳定 `contentHash`。
- [ ] 定义 `MemoryWriteBatch`、`CommitReceipt`、`PromotionDecision`，明确 provisional、active、rejected 状态。
- [ ] 在 `ports.py` 定义 `AuthoritativeStore`、`StagingStore`、`Retriever`、`VectorIndex` 和 `AuditPort` 协议。
- [ ] 测试合同 alias、不可变 pack、hash 对字段顺序不敏感、非法负预算拒绝。

## Phase 2: Read Path Separation

### Task 4: 修复生命周期入口并实现硬门控

**Files:**
- Modify: `apps/agentOS/src/components/memory/lifecycle.py`
- Create: `apps/agentOS/src/components/memory/gating.py`
- Test: `apps/agentOS/tests/components/memory/test_gating.py`

- [ ] 将生命周期导入改为 `contracts.memory.MemoryRecord`，统一使用 `is_expired(record, now)`。
- [ ] 实现 `ScopeGuard.filter()`：先过滤 scope、过期和非 `ACTIVE` 记录，再交给检索器。
- [ ] 对显式引用执行同样 scope/status 校验，不能仅按 ID 直接返回。
- [ ] 返回结构化 `RejectedMemory`，至少包含 `scope_mismatch`、`expired`、`inactive`。
- [ ] 测试跨 run、过期、candidate/pending、显式引用越界均不进入候选集。

### Task 5: 拆出 RecallOrchestrator

**Files:**
- Create: `apps/agentOS/src/components/memory/recall.py`
- Modify: `apps/agentOS/src/components/memory/retrieval.py`
- Test: `apps/agentOS/tests/components/memory/test_recall_pipeline.py`

- [ ] 将现有 BM25 逻辑包装为 `LexicalRetriever`，将可选 vector index 包装为 `VectorRetriever`。
- [ ] 增加 `DirectRefRetriever`，显式引用优先返回且不参与普通相似度排序。
- [ ] 实现 `RecallOrchestrator.recall(request)`：硬门控 → 多路召回 → RRF 融合 → CandidateSet。
- [ ] 保持 vector 不可用时 lexical fallback，并写入结构化 fallback reason。
- [ ] 将旧 `MemoryService.hybrid_search()` 改为调用 orchestrator，确保旧返回三元组不变。
- [ ] 测试显式引用优先、跨 scope 过滤、BM25-only、vector fallback、稳定 tie-break。

### Task 6: 实现 ContextAssembler

**Files:**
- Create: `apps/agentOS/src/components/memory/assembly.py`
- Modify: `apps/agentOS/src/components/memory/service.py`
- Test: `apps/agentOS/tests/components/memory/test_context_assembly.py`

- [ ] 实现 `ContextAssembler.assemble(candidate_set, request)`，将候选分成 L0/L1/L2/L3。
- [ ] L0 采用显式引用和受控硬约束；预算不足时抛出结构化 `CONTEXT_BUDGET_EXCEEDED`。
- [ ] 其它层按融合分数和 Token 成本选择完整记录，不截断单条内容。
- [ ] 记录 omitted 原因：`budget_exceeded`、`ranked_out`、`compression_removed`。
- [ ] 生成确定性 `ContextPack`，相同候选、请求和策略必须得到相同 hash。
- [ ] 增加 `MemoryService.recall()` 和 `MemoryService.assemble()`；保留 `recall_for_step()` 作为兼容 wrapper。
- [ ] 测试 L0 不丢弃、预算边界、重复输入稳定 hash、召回与装配分离。

## Phase 3: Write Path Separation

### Task 7: 扩展 SQLite 权威存储和 staging API

**Files:**
- Modify: `apps/agentOS/src/components/memory/store.py`
- Test: `apps/agentOS/tests/components/memory/test_store_migration.py`

- [ ] 启动时创建 `memory_records` 和 `memory_staging` 表；保留旧 `execution_memory` 读取兼容。
- [ ] 为权威记录增加状态、版本、hash、来源、策略和 supersedes JSON 列。
- [ ] 提供 `stage_put/get`、`promote`、`get_active_versions` 和 `transaction()`，所有 SQL 使用参数绑定。
- [ ] 将旧 `put()` 映射到 active 写入，但禁止新提交路径直接覆盖不同内容的同逻辑 ID。
- [ ] 提供一次性迁移读取旧 JSON 并填充默认治理字段，不修改用户未跟踪数据之外的文件。
- [ ] 测试旧库打开、staging 重启恢复、版本追加、事务回滚和同 ID 内容冲突。

### Task 8: 实现 CommitCoordinator

**Files:**
- Create: `apps/agentOS/src/components/memory/commit.py`
- Modify: `apps/agentOS/src/components/memory/service.py`
- Test: `apps/agentOS/tests/components/memory/test_commit_coordinator.py`

- [ ] 实现 `commit(batch)`：校验幂等键、scope、policy、受控结构化事件和记录数量。
- [ ] 首次提交写 staging 并返回 provisional receipt；重复幂等键返回原 receipt。
- [ ] 实现 `promote(commit_id, decision)`：仅允许 allow/review 规定的决策，写 active、更新派生索引、标记 staging promoted。
- [ ] 对不同 payload 的同逻辑 ID 返回冲突错误；不得覆盖旧 active 记录。
- [ ] 让 `remember_step_output()` 调用 coordinator，保留现有返回类型和 memory ID 兼容。
- [ ] 测试 allow、reject、review、重复提交、重启后 promote、版本链和索引更新失败回滚。

### Task 9: 统一执行器与审核器写入入口

**Files:**
- Modify: `apps/agentOS/src/components/executor/node_runner.py`
- Modify: `apps/agentOS/src/runtime/review.py`
- Test: `apps/agentOS/tests/components/executor/test_event_mode.py`
- Test: `apps/agentOS/tests/runtime/test_fault_recovery.py`

- [ ] 将节点写入从直接调用 `remember_step_output()` 改成构造 `MemoryWriteBatch` 并调用 facade commit。
- [ ] 保留 `pendingMemory` 外部 payload 形状，内部只存 batch/commit 引用和结构化事件。
- [ ] 将 `_publish_committed_memory()` 改为 `promote()` wrapper，成功后再写 `memoryAccess.written=true`。
- [ ] 将 `_commit_deferred_memory()` 改为校验审核决定后调用同一 promote 流程。
- [ ] 确保审核前 pending 记录不能被 recall，审核拒绝不会生成有效 memoryRef。
- [ ] 回归普通 allow、人工审核 allow、reject、恢复重放和故障注入路径。

## Phase 4: Runtime Adoption and Derived Indexes

### Task 10: 执行器切换到 ContextPack

**Files:**
- Modify: `apps/agentOS/src/components/executor/node_runner.py`
- Modify: `apps/agentOS/src/components/executor/graph.py`
- Modify: `apps/agentOS/src/runtime/acg_execution.py`
- Test: `apps/agentOS/tests/test_acg_execution_graph.py`

- [ ] 执行器内部消费 `ContextPack` 的 sections 和 refs，不把完整候选正文写入运行状态。
- [ ] `memoryAccess` 增加 pack ID、content hash、rejected/omitted 统计，保留现有字段。
- [ ] 恢复路径校验 pack hash 和 memory refs，发现 stale revision 时结构化失败。
- [ ] 先保留旧 `memory` 列表输出，完成兼容期后再由版本开关关闭。
- [ ] 测试状态投影、checkpoint 恢复、引用校验和旧 payload 兼容。

### Task 11: 抽离派生索引管理

**Files:**
- Create: `apps/agentOS/src/components/memory/indexes.py`
- Modify: `apps/agentOS/src/components/memory/service.py`
- Modify: `apps/agentOS/src/runtime/workflow_runtime.py`
- Test: `apps/agentOS/tests/components/memory/test_index_rebuild.py`

- [ ] 定义 `DerivedIndexManager`，统一处理 vector upsert、删除和从权威记录重建。
- [ ] 初始化时校验 index version；不匹配时从 active records 重建，不能把索引当权威数据源。
- [ ] 将 service 中直接操作 vector index 的逻辑迁移到 manager。
- [ ] 增加运维/测试入口 `rebuild_memory_indexes()`，返回重建数量和失败 ID。
- [ ] 测试索引损坏/缺失后仍可从 SQLite 恢复检索，重建结果稳定。

## Phase 5: Documentation and Acceptance

### Task 12: 更新文档和验收矩阵

**Files:**
- Modify: `apps/agentOS/src/components/memory/README.md`
- Modify: `docs/开发记录/10-记忆器实现与细节逻辑.md`
- Create: `docs/开发记录/10-记忆器迁移验收矩阵.md`

- [ ] 在 README 标明当前实现阶段、兼容 API 和新 facade 的实际状态。
- [ ] 在开发记录中区分“目标架构”和“已落地能力”，避免把未来能力写成当前事实。
- [ ] 建立验收矩阵：跨 scope=0、审核前召回=0、旧数据可读、幂等重放稳定、pack hash 可复现、索引可重建、L0 不静默丢弃。
- [ ] 运行完整测试：`pytest apps/agentOS/tests -q`。
- [ ] 运行静态检查：`git diff --check`，并检查新增模块不存在错误导入和循环依赖。
- [ ] 记录未实现边界：图召回、真实 ANN、跨机事务、大对象对象存储、自动语义合并。

## Rollout Order

按以下顺序合并，每个阶段单独验证：

1. Phase 0：基线测试。
2. Phase 1：合同与端口。
3. Phase 2：读链拆分和 ContextPack。
4. Phase 3：staging、promote 和统一写链。
5. Phase 4：运行时消费和索引管理。
6. Phase 5：文档、全量回归和验收。

不要在 Phase 2 之前修改数据库格式；不要在 Phase 3 完成前删除 `pendingMemory`；不要在 Phase 4 通过前移除旧 `memory` 输出字段。


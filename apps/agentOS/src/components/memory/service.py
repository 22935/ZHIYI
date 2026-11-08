"""记忆部件的公共 Facade。"""

from copy import deepcopy
from datetime import datetime, timezone
import json

from contracts.memory import MemoryPolicy, MemoryQuery, MemoryRecord, MemoryType
from components.communicator.contracts import estimate_tokens

from .admission import admitted
from .algorithms import rerank_memories
from .retrieval import (
    EmbeddingAdapter,
    InMemoryVectorIndex,
    VectorIndex,
    lexical_scores,
    record_text,
    retrieve,
)
from .models import HybridMemoryHit, MemoryRetrievalEvent, PhaseCapsule, WorkingMemory
from .store import MemoryStore


class MemoryService:
    """提供经策略准入的内存写入、确定性检索和工作记忆构造。

    默认使用进程内 ``MemoryStore``，不提供事务、持久化或并发锁；调用者若需
    跨线程/进程一致性，应注入具备相应语义的存储实现。
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        embedding_adapter: EmbeddingAdapter | None = None,
        vector_index: VectorIndex | None = None,
    ) -> None:
        self._store = store or MemoryStore()
        # The deterministic hash adapter is a test double, not a semantic model.
        # Keep vector retrieval opt-in so a production service cannot silently add
        # an unvalidated ranking signal to BM25.
        self.embedding_adapter = embedding_adapter
        self.vector_index = vector_index
        self.last_retrieval_event: MemoryRetrievalEvent | None = None
        if self.embedding_adapter is not None and self.vector_index is None:
            self.vector_index = InMemoryVectorIndex()
        if self.embedding_adapter is not None and self.vector_index is not None:
            self.rebuild_vector_index()

    def remember(self, record: MemoryRecord, policy: MemoryPolicy | None = None) -> bool:
        """在 ``record`` 符合可选策略时写入并返回 ``True``。

        拒绝时返回 ``False`` 且不修改存储；接受时覆盖规则由底层存储定义。该
        方法不检查容量或过期，存储错误直接上抛，复杂度由注入存储决定。
        """
        if not admitted(record, policy):
            return False
        self._store.put(record)
        if self.embedding_adapter is not None and self.vector_index is not None:
            self.vector_index.upsert(
                record.memory_id,
                self.embedding_adapter.embed(record_text(record)),
            )
        return True

    def rebuild_vector_index(self) -> int:
        """Rebuild the derived vector index completely from the authoritative store."""
        count = 0
        if self.embedding_adapter is None or self.vector_index is None:
            return 0
        for record in self._store.values():
            self.vector_index.upsert(
                record.memory_id,
                self.embedding_adapter.embed(record_text(record)),
            )
            count += 1
        return count

    def hybrid_search(
        self,
        query: MemoryQuery,
        *,
        token_budget: int | None = None,
    ) -> tuple[list[MemoryRecord], list[HybridMemoryHit], MemoryRetrievalEvent]:
        """Apply metadata admission before lexical/vector scoring and RRF fusion."""
        # Admission and expiry happen before either ranker competes for slots.
        now = datetime.now(timezone.utc)
        candidates = [
            record for record in self._store.values()
            if record.expires_at is None or record.expires_at > now
        ]
        admitted_records = retrieve(
            candidates,
            query.model_copy(update={"limit": len(candidates)}),
        )
        lexical = lexical_scores(admitted_records, query.query)
        lexical_rank = sorted(admitted_records, key=lambda item: (-lexical[item.memory_id], item.memory_id))
        fallback_reason = None
        vector_enabled = self.embedding_adapter is not None and self.vector_index is not None
        if vector_enabled:
            try:
                vector_rows = self.vector_index.search(
                    self.embedding_adapter.embed(query.query),
                    max(query.limit * 4, query.limit),
                )
            except Exception:
                vector_rows = []
                fallback_reason = "VECTOR_INDEX_UNAVAILABLE"
        else:
            vector_rows = []
            fallback_reason = "SEMANTIC_MODEL_NOT_CONFIGURED"
        allowed_ids = {record.memory_id for record in admitted_records}
        vector_rows = [item for item in vector_rows if item[0] in allowed_ids]
        vector_rank = {memory_id: index for index, (memory_id, _) in enumerate(vector_rows, 1)}
        vector_score = dict(vector_rows)
        lexical_positions = {record.memory_id: index for index, record in enumerate(lexical_rank, 1)}
        hits = [
            HybridMemoryHit(
                memoryId=record.memory_id,
                lexicalScore=lexical[record.memory_id],
                vectorScore=vector_score.get(record.memory_id, 0.0),
                fusedScore=(
                    1.0 / (60 + lexical_positions[record.memory_id])
                    + (
                        1.0 / (60 + vector_rank[record.memory_id])
                        if vector_enabled and fallback_reason is None and record.memory_id in vector_rank
                        else 0.0
                    )
                ),
            )
            for record in admitted_records
        ]
        hits.sort(key=lambda item: (-item.fused_score, item.memory_id))
        by_id = {record.memory_id: record for record in admitted_records}
        selected: list[MemoryRecord] = []
        used = 0
        for hit in hits:
            record = by_id[hit.memory_id]
            cost = estimate_tokens(record.content)
            if token_budget is not None and used + cost > token_budget:
                continue
            selected.append(record)
            used += cost
            if len(selected) >= query.limit:
                break
        selected_ids = {record.memory_id for record in selected}
        selected_hits = [hit for hit in hits if hit.memory_id in selected_ids]
        event = MemoryRetrievalEvent(
            scope=query.scope or "global",
            mode=(
                "bm25_vector_rrf"
                if vector_enabled and fallback_reason is None
                else ("lexical_fallback" if vector_enabled else "bm25")
            ),
            hitRefs=[record.memory_id for record in selected],
            budget=token_budget,
            fallbackReason=fallback_reason,
        )
        self.last_retrieval_event = event
        return selected, selected_hits, event

    def create_phase_capsule(
        self,
        *,
        run_id: str,
        phase_id: str,
        source_memory_refs: list[str],
        token_budget: int = 512,
        goal: str = "",
        constraints: list[str] | None = None,
        open_questions: list[str] | None = None,
    ) -> PhaseCapsule:
        """Compress a completed phase into deterministic facts and source references."""
        if token_budget < 1:
            raise ValueError("capsule token_budget must be positive")
        records: list[MemoryRecord] = []
        for memory_ref in source_memory_refs:
            record = self._store.get(memory_ref)
            if record is None or record.scope != run_id:
                raise ValueError(f"invalid phase memory reference: {memory_ref}")
            records.append(record)
        facts: list[str] = []
        summaries: list[str] = []
        evidence_refs: list[str] = []
        risks: list[str] = []
        decisions: list[str] = []
        used = 0
        for record in records:
            text = json.dumps(record.content, ensure_ascii=False, sort_keys=True)
            cost = estimate_tokens(text)
            if used + cost > token_budget:
                continue
            facts.append(text)
            used += cost
            summary = record.content.get("summary")
            if isinstance(summary, str) and summary.strip():
                summaries.append(summary.strip())
            raw_evidence_refs = record.content.get("evidenceRefs")
            for evidence_ref in raw_evidence_refs if isinstance(raw_evidence_refs, list) else []:
                if isinstance(evidence_ref, str) and evidence_ref not in evidence_refs:
                    evidence_refs.append(evidence_ref)
            decision = record.content.get("decision")
            if isinstance(decision, str) and decision:
                decisions.append(decision)
                if decision in {"review", "deny"}:
                    # 来源记录不一定带标签（通用 remember 路径允许空 tags），
                    # 缺失时退化到记忆类别，禁止用 tags[-1] 直接下标。
                    label = record.tags[-1] if record.tags else record.memory_type.value
                    risks.append(f"{label}:{decision}")
        capsule = PhaseCapsule(
            capsuleId=f"capsule:{run_id}:{phase_id}",
            runId=run_id,
            phaseId=phase_id,
            sourceMemoryRefs=list(source_memory_refs),
            goal=str(goal)[:500],
            confirmedSummary="\n".join(summaries)[:4000],
            evidenceRefs=evidence_refs,
            constraints=[str(item)[:300] for item in (constraints or [])],
            risks=risks,
            openQuestions=[str(item)[:300] for item in (open_questions or [])],
            keyFacts=facts,
            decisions=decisions,
            tokenCount=used,
        )
        existing = self._store.get(capsule.capsule_id)
        if existing is not None:
            restored = PhaseCapsule.model_validate(existing.content)
            comparable = {"created_at"}
            if restored.model_dump(exclude=comparable) != capsule.model_dump(exclude=comparable):
                raise ValueError(f"phase capsule already exists with different content: {capsule.capsule_id}")
            return restored
        self.remember(
            MemoryRecord(
                memoryId=capsule.capsule_id,
                memoryType=MemoryType.SEMANTIC,
                content=capsule.model_dump(by_alias=True, mode="json"),
                scope=run_id,
                tags=["phase-capsule", phase_id],
            )
        )
        return capsule

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """执行本地元数据过滤后按重要度稳定重排并返回结果副本。

        检索不使用向量模型或外部索引，输入查询不会被修改；复杂度包含线性过滤
        和排序，即 O(n log n)，底层存储读取异常会直接上抛。
        """
        return rerank_memories(retrieve(self._store.values(), query))

    def recall_for_step(
        self,
        *,
        run_id: str,
        step_id: str,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        token_budget: int | None = None,
    ) -> list[MemoryRecord]:
        """为一个执行步骤召回仅属于当前 run 且尚未过期的记忆。

        ``run_id`` 被固定为查询 scope，因而调用者不能以“无 scope”的检索间接得到
        其它运行内容。``step_id`` 是明确的调用边界；类别、数量和 Token 预算都由
        节点已冻结的记忆策略传入。预算只会丢弃放不下的完整记录，绝不截断正文或
        放宽限制；负数预算属于无效策略并立即拒绝。
        """
        if token_budget is not None and token_budget < 0:
            raise ValueError("memory token_budget must be non-negative")
        records, _, event = self.hybrid_search(
            MemoryQuery(
                query=query,
                scope=run_id,
                memoryTypes=memory_types or [],
                limit=limit,
            ),
            token_budget=token_budget,
        )
        self.last_retrieval_event = event
        return records

    def assert_step_ref(self, *, run_id: str, step_id: str, memory_ref: str) -> None:
        """确认 ``memory_ref`` 指向当前运行和当前来源步骤的真实执行记忆。

        检查点中的引用可被外部篡改，因此不能仅根据固定 ID 格式推导归属。这里仅
        读取记忆合同的元数据：``scope`` 绑定 run，``execution`` 标签后的步骤标识
        绑定来源步骤；不会读取或返回记忆正文。
        """
        record = self._store.get(memory_ref)
        if record is None:
            raise ValueError(f"memory reference {memory_ref} does not exist")
        if record.scope != run_id:
            raise ValueError(
                f"memory reference {memory_ref} belongs to run {record.scope}, not run {run_id}"
            )
        source_step_id = record.tags[1] if len(record.tags) >= 2 and record.tags[0] == "execution" else ""
        if source_step_id != step_id:
            raise ValueError(
                f"memory reference {memory_ref} belongs to step {source_step_id or 'unknown'}, not {step_id}"
            )

    def remember_step_output(
        self,
        *,
        run_id: str,
        step_id: str,
        output: dict[str, object],
        memory_type: MemoryType = MemoryType.EPISODIC,
        policy: MemoryPolicy | None = None,
    ) -> MemoryRecord | None:
        """把已通过输出合同的受控字段写为当前 run 的指定类型记忆。

        调用方必须在调用前完成输出 schema 校验与字段白名单裁剪；该服务只接收
        ``controlled`` 结果，绝不从 Agent 原始响应或 WorkflowRun 回填正文。
        ``memory_type`` 由已冻结的步骤策略指定，默认情节记忆只用于兼容旧调用；若
        准入策略拒绝该类型，则返回 ``None``，让运行器不生成虚假的 memoryRef。
        """
        memory_id = f"memory:{run_id}:{step_id}"
        existing = self._store.get(memory_id)
        if existing is not None:
            if (
                existing.memory_type == memory_type
                and existing.content == dict(output)
                and existing.scope == run_id
                and existing.tags == ["execution", step_id]
            ):
                return existing if admitted(existing, policy) else None
            raise ValueError(
                f"execution memory {memory_id} already exists with different output"
            )
        record = MemoryRecord(
            memoryId=memory_id,
            memoryType=memory_type,
            content=deepcopy(dict(output)),
            scope=run_id,
            tags=["execution", step_id],
        )
        return record if self.remember(record, policy) else None

    def working_from_run(self, run: object) -> WorkingMemory:
        """从运行投影创建一份仅含已完成观察的 ``WorkingMemory``。

        返回新对象，不改变运行或访问旧 core；步骤解释规则由
        :meth:`WorkingMemory.from_run` 定义，处理复杂度随步骤数线性增长。
        """
        return WorkingMemory.from_run(run)

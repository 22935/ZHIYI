"""AgentOS 单节点固定执行管线。

每个图节点必须按同一顺序运行：装配 ContextPack → 受限记忆检索 → 熵预算与输入合同
校验 → Agent/Tool Adapter 调用 → 输出合同与字段白名单校验 → 受控记忆/血缘登记 →
返回摘要和引用。图 State 只接收最后一步的引用，真实输入输出始终留在 AgentOS 服务边界。

第三方来源：LangGraph 1.2.10，commit d56666f7fbf0d380ad84cdf0cbe5aa48ab0cc086；
来源模块 ``libs/langgraph/langgraph/pregel``、``graph/state.py``。该实现改写为调用
AgentOS 通信、记忆、Adapter 与审计边界，不暴露 LangGraph 对象；完整 MIT 许可证见
``docs/THIRD_PARTY_NOTICES.md``。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from components.communicator import CommunicationBroker, CommunicationReader, CommunicatorService, ReliableMessage
from components.communicator.contracts import ContextPack, estimate_tokens, input_revision
from components.auditor.execution_audit import ExecutionAuditService
from components.auditor.decision_store import DecisionStore, InMemoryDecisionStore
from components.memory import MemoryService, StructuredMemoryEventBuilder
from components.content import ContentManifestStore, ContentWorksetSession
from adapters.agent_invocation import AgentInvocationAdapter
from adapters.resource_execution import ResourceExecutionAdapter
from contracts.communication import validate_contract_payload
from contracts.governance import AuditRequest
from contracts.memory import MemoryPolicy, MemoryType
from contracts.workflow import RuntimeMissionRecord, RuntimeRunRecord, WorkflowDefinition, WorkflowStep
from contracts.compiled_acg import CompiledACGPackage, EvidenceManifest, MemoryManifest, SkillManifest
from contracts.execution import NodeExecutionPhase, NodeExecutionRecord
from contracts.content import ContentKind
from service.agents.base import BaseAgent, AgentRunContext
from contracts.runtime_events import RuntimeEvent
from runtime.live_events import runtime_event_broker

from .graph import ACGExecutionState
from .value_store import ExecutionValueStore, InMemoryExecutionValueStore


class EntropyBudgetExceededError(ValueError):
    """跨步骤上下文的估算熵超过运行允许的预算，Adapter 尚未被调用。"""


class ACGNodeRunner:
    """执行固定节点管线，并仅返回可安全写入执行 State 的摘要和引用。"""

    def __init__(
        self,
        *,
        task: RuntimeMissionRecord,
        run: RuntimeRunRecord,
        workflow: WorkflowDefinition,
        steps: Mapping[str, WorkflowStep],
        agents: Mapping[str, BaseAgent],
        communicator: CommunicatorService,
        memory: MemoryService,
        entropy_budget: int | None = None,
        value_store: ExecutionValueStore | None = None,
        content_manifest_store: ContentManifestStore | None = None,
        communication_modes: Mapping[str, str] | None = None,
        upstream_step_ids: Mapping[str, tuple[str, ...]] | None = None,
        execution_audit: ExecutionAuditService | None = None,
        decision_store: DecisionStore | None = None,
        agent_invoker: AgentInvocationAdapter | None = None,
        resource_execution_adapters: Mapping[str, ResourceExecutionAdapter] | None = None,
        model_runtime: object | None = None,
        model_runtimes: Mapping[str, object] | None = None,
        capability_descriptors: Mapping[str, object] | None = None,
        tool_runtime: object | None = None,
        communication_broker: CommunicationBroker | None = None,
        skill_manifest: SkillManifest | None = None,
        memory_manifest: MemoryManifest | None = None,
        evidence_manifest: EvidenceManifest | None = None,
        reliable_communication_store: object | None = None,
        compiled_package: CompiledACGPackage | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        """注入本 run 冻结的服务、步骤和 Agent 解析结果；不创建外部连接。"""
        self.task = task
        self.run = run
        self.workflow = workflow
        self.steps = dict(steps)
        self.agents = dict(agents)
        self.communicator = communicator
        self.memory = memory
        self.entropy_budget = entropy_budget
        # 显式依赖受控仓库，而不是由运行器拼接伪引用。这样节点产物的归属、读取校验
        # 与不可变副本语义集中在唯一服务边界中，State 只会接触返回的字符串引用。
        self.value_store = value_store or InMemoryExecutionValueStore()
        self.content_manifest_store = content_manifest_store
        self.communication_modes = dict(communication_modes or {})
        self.upstream_step_ids = {
            node_id: tuple(source_ids)
            for node_id, source_ids in (upstream_step_ids or {}).items()
        }
        self.execution_audit = execution_audit or ExecutionAuditService()
        # 审计决定必须先于输出、记忆和提交记录落入独立真源。最小运行器使用内存
        # 实现；ExecutionRuntime 会注入可跨进程恢复的 SQLite 实现。
        self.decision_store = decision_store or InMemoryDecisionStore()
        self.agent_invoker = agent_invoker
        self.resource_execution_adapters = dict(resource_execution_adapters or {})
        self.model_runtime = model_runtime
        # 模型绑定在 ``prepare_run`` 时冻结为 step → provider/model，再由 Runtime
        # 组装为此映射。节点不会从可变 Agent Profile 读取模型配置，恢复时也不会
        # 因全局 Agent 注册表被修改而换用另一家模型。
        self.model_runtimes = dict(model_runtimes or {})
        # Filled by the scheduler decorator for each live step attempt. It is
        # deliberately separate from commitId, which remains an idempotency key.
        self.attempt_ids: dict[str, str] = {}
        self.capability_descriptors = dict(capability_descriptors or {})
        self.tool_runtime = tool_runtime
        self.communication_broker = communication_broker
        self.skill_manifest = skill_manifest or SkillManifest()
        self.memory_manifest = memory_manifest or MemoryManifest()
        self.evidence_manifest = evidence_manifest or EvidenceManifest()
        self.reliable_communication_store = reliable_communication_store
        self.compiled_package = compiled_package
        # 仅由故障恢复测试在运行时对象上临时注入。生产装配不会设置该钩子，业务合同、
        # Blueprint 和持久化状态都不包含故障阶段或异常对象。
        self._fault_hook = fault_hook

    @classmethod
    def minimal(
        cls,
        *,
        agent: BaseAgent,
        entropy_budget: int | None = None,
        resource_execution_adapters: Mapping[str, ResourceExecutionAdapter] | None = None,
    ) -> "ACGNodeRunner":
        """构造测试用最小节点运行器，生产运行时应显式注入全部运行范围。"""
        task = RuntimeMissionRecord(missionId="mission_000000000000", title="ACG node")
        run = RuntimeRunRecord(missionId=task.mission_id, workflowId="workflow", domain="general", runtimeEngine="acg")
        workflow = WorkflowDefinition(workflowId="workflow", name="workflow", domain="general", intent="general", runtimeEngine="acg")
        step = WorkflowStep(stepId="one", name="one", agentName=agent.profile.agent_name)
        return cls(
            task=task,
            run=run,
            workflow=workflow,
            steps={"one": step},
            agents={"one": agent},
            communicator=CommunicatorService(run_id=run.run_id, mission_id=task.mission_id),
            memory=MemoryService(),
            entropy_budget=entropy_budget,
            resource_execution_adapters=resource_execution_adapters,
        )

    async def __call__(self, step_id: str, state: ACGExecutionState) -> dict[str, Any]:
        """执行一个 Step，并返回 Pregel 轮次可消费的受控结果。

        ``routeValue`` 是条件控制节点在同轮读取的短生命周期值；执行图只会使用它来
        选择已声明分支，不会把它写入 ``ACGExecutionState`` 或 checkpoint。
        """
        step = self.steps[step_id]
        agent = self.agents[step_id]
        loop_path = tuple(state.loop_paths.get(step_id, ()))
        commit_id = self._commit_id(state.run_id, step_id, step.attempt, loop_path=loop_path)
        committed = self.value_store.get_node_commit(run_id=state.run_id, commit_id=commit_id)
        if committed is not None and committed.get("stage") == "committed":
            # 重启恢复或投影中断后再次调度同一步骤时，提交记录是唯一真源。它只返回
            # 已保存的安全引用与元数据，不能重新调用 Agent、重复写记忆或制造新 Trace。
            replayed = dict(committed)
            self._publish_committed_memory(
                run_id=state.run_id,
                step_id=step_id,
                payload=replayed,
            )
            self._validate_committed_references(
                run_id=state.run_id,
                step_id=step_id,
                payload=replayed,
            )
            output_ref = replayed.get("outputRef")
            if isinstance(output_ref, str):
                # 条件值不允许进入提交记录或 checkpoint。需要路由时仅在本轮从已受控的
                # 输出引用短暂读取，之后仍由图层消费而不会持久化到执行状态。
                replayed["routeValue"] = self.value_store.get_output(
                    run_id=state.run_id,
                    output_ref=output_ref,
                )
                self._publish_advanced_communication(
                    state=state,
                    step_id=step_id,
                    output_ref=output_ref,
                    commit_id=commit_id,
                )
                if self.communication_modes.get(step_id) == "DEBATE":
                    self._advance_debate_session(
                        state=state,
                        step_id=step_id,
                        output_ref=output_ref,
                        commit_id=commit_id,
                    )
            return replayed
        # 先持久化 prepared，再进入 Agent/Tool 适配边界。若中断发生在外部调用期间，
        # 恢复会传递同一 commitId，外部实现可据此幂等重试；不会误认为已完成。
        self.value_store.prepare_node_commit(run_id=state.run_id, commit_id=commit_id)
        execution_record = NodeExecutionRecord(
            operationId=commit_id,
            executionInstanceId=f"{state.run_id}:{step_id}:{step.attempt}:{'.'.join(map(str, loop_path)) or 'root'}",
            runId=state.run_id,
            stepId=step_id,
            attemptId=self.attempt_ids.get(
                step_id,
                f"{state.run_id}:{step_id}:{step.attempt}:"
                f"{'.'.join(map(str, loop_path)) or 'root'}",
            ),
            phase=NodeExecutionPhase.PREPARED,
            loopPath=loop_path,
        )
        execution_record = self.value_store.transition_node_execution(execution_record)
        # State 只有摘要/引用。上游完整 slot 值必须由通信服务根据 outputRef 从受控
        # 仓库读取。entropyBudget 只表示 L1/L2 的规划与协作复杂度，不得在
        # L3 被重新解释为输入/输出 Token 上限或因上游摘要较多而拒绝执行。
        mode = self.communication_modes.get(step_id, "STRICT_CONTRACT")
        consumed_message_ids: list[str] = []
        if mode in {"EVENT", "DEBATE"}:
            # EVENT 是纯通知：只把 outputRef 转为证据引用，绝不调用仓库读取其正文。
            # 上游列表由编译后的依赖图注入，避免无关步骤的事件引用被额外暴露。
            source_ids = self.upstream_step_ids.get(step_id, tuple(state.output_refs))
            pending_messages = (
                self.reliable_communication_store.pending(
                    run_id=state.run_id, consumer_step_id=step_id
                )
                if self.reliable_communication_store is not None
                else ()
            )
            consumed_message_ids = [message.message_id for message in pending_messages]
            debate_phase = ""
            if mode == "DEBATE" and self.compiled_package is not None:
                debate_rules = tuple(
                    rule for rule in self.compiled_package.communication_manifest.rules
                    if rule.consumer_step_id == step_id and rule.mode.value == "DEBATE"
                )
                if not debate_rules:
                    raise ValueError(f"DEBATE step {step_id} has no manifest rules")
                spec = debate_rules[0]
                producer_ids = {
                    message.producer_step_id for message in pending_messages
                    if message.producer_step_id in spec.participant_step_ids
                }
                if len(producer_ids) < int(spec.quorum or 0):
                    raise RuntimeError(f"DEBATE_QUORUM_UNREACHED:{step_id}")
                session = state.debate_sessions.setdefault(step_id, {
                    "round": 1,
                    "phase": "propose",
                    "maxRounds": spec.max_rounds,
                    "quorum": spec.quorum,
                    "participants": list(spec.participant_step_ids),
                    "appliedCommitIds": [],
                })
                debate_phase = str(session.get("phase") or "propose")
            pack = ContextPack(
                runId=state.run_id,
                stepId=step_id,
                objective=self.workflow.description,
                stepGoal=step.goal or step.name,
                evidenceRefs=[
                    f"event:{state.output_refs[source_id]}"
                    for source_id in source_ids
                    if source_id in state.output_refs
                ] + [
                    (
                        f"debate:{debate_phase}:{message.artifact_ref}"
                        if mode == "DEBATE"
                        else f"event:{message.artifact_ref}"
                    )
                    for message in pending_messages
                ],
                sourceStepIds=list(source_ids),
            )
        elif mode == "BLACKBOARD":
            snapshot = state.blackboard_snapshots.get(step_id, {})
            entries = snapshot.get("entries") if isinstance(snapshot, dict) else {}
            refs = list(entries.values()) if isinstance(entries, dict) else []
            pack = ContextPack(
                runId=state.run_id,
                stepId=step_id,
                objective=self.workflow.description,
                stepGoal=step.goal or step.name,
                evidenceRefs=[f"blackboard:{item}" for item in refs],
                sourceStepIds=list(self.upstream_step_ids.get(step_id, ())),
            )
        elif self.communication_broker is not None:
            pack = await self._assemble_broker_context(
                state=state,
                step_id=step_id,
                step=step,
                commit_id=commit_id,
            )
            # Broker 是唯一正文读取入口；读取成功后才用已裁剪的 ContextPack 登记
            # 消费与交互血缘。账本仅封存摘要、字段名和引用，恢复会复用 commitId。
            self.communicator.record_context_consumption(pack, operation_id=commit_id)
        else:
            pack = self.communicator.assemble_execution_context(
                run_id=state.run_id,
                mission_id=self.task.mission_id,
                step_id=step_id,
                input_spec=step.input,
                upstream_refs=state.output_refs,
                value_store=self.value_store,
                objective=self.workflow.description,
                step_goal=step.goal or step.name,
                token_budget=None,
                operation_id=commit_id,
            )
        if pack.contract_status != "valid":
            raise ValueError(f"input contract is incomplete for {step_id}: {', '.join(pack.missing_fields)}")
        input_schema = step.input.get("schema", {}) if isinstance(step.input, dict) else {}
        validate_contract_payload(pack.data, input_schema, step_id=step_id, direction="input")
        memory_policy = self._memory_policy(step.input)
        explicit_memory_rules = self.memory_manifest.for_step(step_id)
        if explicit_memory_rules:
            memory_policy["read"] = bool(
                self.memory_manifest.for_step(step_id, "read")
            )
            memory_policy["write"] = bool(
                self.memory_manifest.for_step(step_id, "write")
            )
        communication_reader = self._build_communication_reader(
            state=state,
            step_id=step_id,
            mode=mode,
        )
        workset_session = self._build_content_workset_session(
            state=state,
            step_id=step_id,
            step=step,
            commit_id=commit_id,
        )
        memories = (
            self.memory.recall_for_step(
                run_id=state.run_id,
                step_id=step_id,
                query=step.name or step_id,
                memory_types=memory_policy["readTypes"] or None,
                limit=memory_policy["limit"],
                token_budget=memory_policy["tokenBudget"],
            )
            if memory_policy["read"]
            else []
        )
        memory_access = {
            "policyId": memory_policy["policyId"],
            "read": memory_policy["read"],
            "readCount": len(memories),
            "retrievalMode": "bm25_vector_rrf" if memory_policy["read"] else "disabled",
            "hitRefs": [memory.memory_id for memory in memories],
            "write": memory_policy["write"],
            "written": False,
            "readTypes": [item.value for item in memory_policy["readTypes"]],
            "writeType": (
                memory_policy["writeType"].value
                if memory_policy["writeType"] is not None
                else None
            ),
            "limit": memory_policy["limit"],
            "tokenBudget": memory_policy["tokenBudget"],
            "tokensUsed": sum(estimate_tokens(record.content) for record in memories),
            "requireAudit": memory_policy["requireAudit"],
        }
        # 每个 Step 创建独立的受限工具视图，使并行节点的事件缓冲区彼此隔离；
        # 视图只能继承既有授权集合，不能在节点内扩大权限。
        step_tool_runtime = self.tool_runtime
        if self.tool_runtime is not None and hasattr(self.tool_runtime, "scoped"):
            declared_tools = {
                rule.tool_name
                for rule in self.skill_manifest.for_step(step_id)
                if rule.tool_name
            }
            allowed = declared_tools or set(getattr(self.tool_runtime, "allowed_tools", ()))
            step_tool_runtime = self.tool_runtime.scoped(allowed)
        agent_context = AgentRunContext(
            task=self.task,
            run=self.run,
            workflow=self.workflow,
            step=step,
            memory=memories,
            contextPack=pack,
            communicationReader=communication_reader,
            contentWorksetSession=workset_session,
            toolRuntime=step_tool_runtime,
            modelRuntime=self.model_runtimes.get(step_id, self.model_runtime),
            capabilityDescriptor=self.capability_descriptors.get(step.capability or ""),
            commitId=commit_id,
            attemptId=self.attempt_ids.get(step_id),
        )
        await runtime_event_broker.publish(
            state.run_id,
            RuntimeEvent(eventType="node.started", runId=state.run_id, nodeId=step_id,
                         attemptId=self.attempt_ids.get(step_id) or commit_id or step_id, sequence=0),
        )
        output = (
            await self.agent_invoker.invoke(context=agent_context, agent=agent)
            if self.agent_invoker is not None
            else await agent.run(agent_context)
        )
        final_attempt_id = getattr(agent_context.model_runtime, "last_attempt_id", None)
        if isinstance(final_attempt_id, str) and final_attempt_id:
            self.attempt_ids[step_id] = final_attempt_id
        execution_record = self.value_store.transition_node_execution(
            execution_record.model_copy(update={"phase": NodeExecutionPhase.EXECUTED})
        )
        if communication_reader is not None:
            for index, dynamic_pack in enumerate(communication_reader.drain_packs()):
                # 每次补读都有独立角色键；节点重放时相同提交标识会复用血缘记录，
                # 不会把多次合法读取错误合并成同一次消费。
                self.communicator.record_context_consumption(
                    dynamic_pack,
                    operation_id=f"{commit_id}:dynamic:{index}",
                )
        if self.communication_broker is not None:
            state.communication_usage = self.communication_broker.usage_snapshot()
        tool_events = list(output.tool_executions)
        runtime_events = getattr(step_tool_runtime, "events", None)
        if isinstance(runtime_events, list):
            tool_events.extend(runtime_events)
        payload = dict(output.output)
        validate_contract_payload(payload, step.output_spec, step_id=step_id, direction="output")
        allowed = set((step.output_spec.get("properties") or {}).keys()) if step.output_spec else set(payload)
        controlled = {key: value for key, value in payload.items() if key in allowed}
        risk_level = (output.risk_level or "").lower()
        severity_counts = {risk_level: 1} if risk_level else {}
        decision = self.execution_audit.assess_node(
            request=AuditRequest(
                requestId=f"audit:{state.run_id}:{step_id}",
                # 审计发生在持久化前，使用一次性待定引用，避免 deny 结果落入
                # 输出仓库或记忆仓库；allow/review 后再生成正式引用。
                subjectRef=f"pending:{state.run_id}:{step_id}",
                auditType="node_output",
                evidenceRefs=[f"trace:{step_id}"],
            ),
            severity_counts=severity_counts,
            memory_access=memory_access,
        )
        self._require_audit_decision(decision)
        self.decision_store.save(run_id=state.run_id, step_id=step_id, decision=decision)
        persisted_decision = self.decision_store.assert_decision(
            run_id=state.run_id,
            step_id=step_id,
            decision_ref=decision.decision_id,
            outcomes={decision.outcome},
        )
        execution_record = self.value_store.transition_node_execution(
            execution_record.model_copy(update={
                "phase": (
                    NodeExecutionPhase.WAITING_REVIEW
                    if persisted_decision.outcome == "review"
                    else NodeExecutionPhase.AUDITED
                ),
                "audit_ref": persisted_decision.decision_id,
            })
        )
        requires_review = step.requires_review or persisted_decision.outcome == "review"
        output_evidence = controlled.get("evidence_refs") or controlled.get("evidenceRefs") or []
        evidence_refs = [
            *output.evidence_refs,
            *(output_evidence if isinstance(output_evidence, list) else []),
        ]
        evidence_refs = list(dict.fromkeys(str(item) for item in evidence_refs if str(item).strip()))
        produced_citation_refs = {
            str(item.get("citationId"))
            for item in output.sources
            if isinstance(item, dict) and str(item.get("citationId") or "").strip()
        }
        upstream_evidence_refs = {
            str(item) for item in getattr(pack, "evidence_refs", ()) if str(item).strip()
        }
        produce_allowed = bool(self.evidence_manifest.for_step(step_id, "produce"))
        consume_allowed = bool(self.evidence_manifest.for_step(step_id, "consume"))
        unauthorized = {
            item for item in evidence_refs
            if not (
                (produce_allowed and item in produced_citation_refs)
                or (consume_allowed and item in upstream_evidence_refs)
            )
        }
        if unauthorized:
            raise ValueError(
                f"step {step_id} produced unauthorized evidence references: {sorted(unauthorized)}"
            )
        memory_event = StructuredMemoryEventBuilder.build(
            run_id=state.run_id,
            step_id=step_id,
            commit_id=commit_id,
            summary=output.summary,
            evidence_refs=evidence_refs,
            audit_outcome=persisted_decision.outcome,
            upstream_step_ids=self.upstream_step_ids.get(step_id, ()),
            field_count=len(controlled),
            model_invocation_count=len(output.model_invocations),
            tool_call_count=len(tool_events),
        )
        memory_event_payload = memory_event.model_dump(by_alias=True, mode="json")
        if persisted_decision.outcome == "deny":
            return {
                "outputSummary": output.summary or f"denied:{step_id}",
                "reviewRequired": False,
                "auditDecisionRef": persisted_decision.decision_id,
                "auditOutcome": persisted_decision.outcome,
                "modelInvocations": self._safe_model_invocations(output.model_invocations),
                "memoryAccess": memory_access,
                "memoryEvent": memory_event_payload,
            }

        if self.content_manifest_store is not None and step.capability == "artifact_generation":
            controlled = self._persist_artifact_manifest(
                run_id=state.run_id,
                step_id=step_id,
                controlled=controlled,
            )

        output_ref = self.value_store.put_output(
            run_id=state.run_id,
            step_id=step_id,
            payload=controlled,
            operation_id=commit_id,
        )
        context_ref = self.value_store.put_context_pack(
            run_id=state.run_id,
            step_id=step_id,
            payload=pack.model_dump(by_alias=True, mode="json"),
            operation_id=commit_id,
        )
        self._inject_fault("after_values")
        self.communicator.record_production(
            step_id,
            controlled,
            agent_name=agent.profile.agent_name,
            operation_id=commit_id,
        )
        self._inject_fault("after_provenance")
        pending_memory: dict[str, Any] | None = None
        if persisted_decision.outcome == "allow" and not requires_review and memory_policy["write"]:
            pending_memory = {
                "outputRef": output_ref,
                "policyId": str(memory_policy["policyId"]),
                "writeType": memory_policy["writeType"].value,
                "auditDecisionRef": persisted_decision.decision_id,
                "memoryEvent": memory_event_payload,
            }
        elif requires_review and memory_policy["write"]:
            # 需要人工复核的内容只留下可校验输出引用和策略意图。正文仍在值仓库，
            # 批准前不进入正式 MemoryStore，也不产生可被下游读取的 memoryRef。
            pending_memory = {
                "outputRef": output_ref,
                "policyId": str(memory_policy["policyId"]),
                "writeType": memory_policy["writeType"].value,
                "auditDecisionRef": persisted_decision.decision_id,
                "memoryEvent": memory_event_payload,
            }
        self._inject_fault("after_memory")
        memory_access["written"] = False
        communication_reads = (
            self.communication_broker.drain_events(consumer_step_id=step_id)
            if self.communication_broker is not None
            else []
        )
        communication_refs = list(dict.fromkeys(
            str(item["outputRef"])
            for item in communication_reads
            if isinstance(item, dict) and item.get("outputRef")
        ))
        committed_execution_record = execution_record.model_copy(update={
            "phase": NodeExecutionPhase.COMMITTED,
            "artifact_refs": {
                key: value
                for key, value in {
                    "output": output_ref,
                    "context": context_ref,
                    "memory": (
                        f"memory:{state.run_id}:{step_id}"
                        if pending_memory is not None and not requires_review
                        else None
                    ),
                    "trace": f"trace:{step_id}",
                }.items()
                if isinstance(value, str)
            },
            "commit_id": commit_id,
        })
        result = {
            "commitId": commit_id,
            "outputSummary": output.summary or f"completed:{step_id}",
            "contextRef": context_ref,
            "traceRef": f"trace:{step_id}",
            "outputRef": output_ref,
            # 审计器只给出可重放的治理事实；Pregel 图在提交节点结果后决定是否中断，
            # 因此审计部件不会越权修改 WorkflowRun 或驱动图状态。
            "reviewRequired": requires_review,
            "auditDecisionRef": persisted_decision.decision_id,
            "auditOutcome": persisted_decision.outcome,
            # 模型审计只保留已由 Agent 输出的调用元数据白名单，绝不回写 prompt、
            # 生成正文或供应商对象。Trace 投影层可直接消费该紧凑列表。
            "modelInvocations": self._safe_model_invocations(output.model_invocations),
            "toolCalls": self._safe_tool_calls(tool_events),
            "provenanceEvents": self.communicator.drain_provenance_events(step_id=step_id),
            # Broker 的读取事件只含引用、字段名、计数和通道，Runtime 会投影为安全
            # Trace；正文仍只存在于 Value Store 与当前 Agent 调用栈。
            "communicationReads": communication_reads,
            "communicationRefs": communication_refs,
            "evidenceRefs": list(dict.fromkeys(str(item) for item in evidence_refs)),
            # Artifact bodies remain in the ContentManifest/Value Store boundary;
            # lifecycle projection receives only the sealed manifest references.
            "artifacts": self._safe_artifact_descriptors(controlled),
            "nodeExecution": committed_execution_record.model_dump(
                by_alias=True, mode="json"
            ),
            # 仅含策略、条数和预算统计；记忆正文始终留在 MemoryService/Store 中。
            "memoryAccess": memory_access,
            "memoryEvent": memory_event_payload,
            # 条件值只在当前 Pregel 轮次内供控制节点选择分支，绝不写入持久化 State。
            "routeValue": controlled,
            "runtimeEvents": list(getattr(output, "runtime_events", []) or []),
        }
        if not requires_review:
            result["memoryRef"] = (
                f"memory:{state.run_id}:{step_id}"
                if pending_memory is not None
                else "memory:none"
            )
        if pending_memory is not None:
            result["pendingMemory"] = pending_memory
        # 在图状态投影之前固化不可变提交边界。若后续 Runtime 在 Trace 或 checkpoint
        # 之间中断，恢复后将复用这份记录，而不是再次执行 Agent 或重复产生副作用。
        commit_record = {
            key: value
            for key, value in result.items()
            if key != "routeValue"
        }
        self.value_store.complete_node_commit(
            run_id=state.run_id,
            commit_id=commit_id,
            payload=commit_record,
        )
        await runtime_event_broker.publish(
            state.run_id,
            RuntimeEvent(eventType="node.completed", runId=state.run_id, nodeId=step_id,
                         attemptId=self.attempt_ids.get(step_id) or commit_id or step_id, sequence=0),
        )
        self._publish_committed_memory(
            run_id=state.run_id,
            step_id=step_id,
            payload=result,
        )
        self._publish_advanced_communication(
            state=state,
            step_id=step_id,
            output_ref=output_ref,
            commit_id=commit_id,
        )
        if mode == "DEBATE":
            self._advance_debate_session(
                state=state,
                step_id=step_id,
                output_ref=output_ref,
                commit_id=commit_id,
            )
        if self.reliable_communication_store is not None:
            for message_id in consumed_message_ids:
                self.reliable_communication_store.acknowledge(
                    run_id=state.run_id, message_id=message_id
                )
        self.value_store.transition_node_execution(committed_execution_record)
        return result

    def prepare_superstep(
        self, state: ACGExecutionState, ready_step_ids: tuple[str, ...]
    ) -> None:
        """Freeze advanced communication views before any sibling starts."""
        store = self.reliable_communication_store
        package = self.compiled_package
        if store is None or package is None:
            return
        for step_id in ready_step_ids:
            if self.communication_modes.get(step_id) != "BLACKBOARD":
                continue
            rules = tuple(
                rule
                for rule in package.communication_manifest.rules
                if rule.consumer_step_id == step_id and rule.mode.value == "BLACKBOARD"
            )
            partitions = tuple(dict.fromkeys(
                str(rule.partition or rule.channel) for rule in rules
            ))
            combined: dict[str, str] = {}
            versions: dict[str, int] = {}
            for partition in partitions:
                version, entries = store.blackboard_snapshot(
                    run_id=state.run_id, partition=partition
                )
                versions[partition] = version
                for key, reference in entries.items():
                    combined[f"{partition}:{key}"] = reference
            state.blackboard_snapshots[step_id] = {
                "versions": versions,
                "entries": combined,
            }

    @staticmethod
    def _advance_debate_session(
        *, state: ACGExecutionState, step_id: str, output_ref: str, commit_id: str
    ) -> None:
        session = state.debate_sessions.get(step_id)
        if not isinstance(session, dict):
            return
        applied = session.setdefault("appliedCommitIds", [])
        if commit_id in applied:
            return
        applied.append(commit_id)
        phase = str(session.get("phase") or "propose")
        current_round = int(session.get("round") or 1)
        max_rounds = int(session.get("maxRounds") or 1)
        if phase == "propose":
            session["phase"] = "critique"
        elif phase == "critique":
            session["phase"] = "vote"
        elif current_round < max_rounds:
            session["round"] = current_round + 1
            session["phase"] = "propose"
        else:
            session["phase"] = "complete"
            session["resultArtifactRef"] = output_ref

    def _publish_committed_memory(
        self, *, run_id: str, step_id: str, payload: dict[str, Any]
    ) -> None:
        pending = payload.get("pendingMemory")
        if not isinstance(pending, dict):
            return
        if payload.get("auditOutcome") != "allow" or payload.get("reviewRequired"):
            return
        write_type = pending.get("writeType")
        memory_event = pending.get("memoryEvent")
        if not isinstance(write_type, str) or not isinstance(memory_event, dict):
            raise ValueError("committed pending memory intent is incomplete")
        memory_type = MemoryType(write_type)
        record = self.memory.remember_step_output(
            run_id=run_id,
            step_id=step_id,
            output=memory_event,
            memory_type=memory_type,
            policy=MemoryPolicy(
                policyId=str(pending.get("policyId") or "default"),
                allowedTypes=[memory_type],
            ),
        )
        expected = payload.get("memoryRef")
        if record is None or (expected is not None and record.memory_id != expected):
            raise ValueError("committed memory publication does not match memoryRef")
        memory_access = payload.get("memoryAccess")
        if isinstance(memory_access, dict):
            memory_access["written"] = True
        payload.pop("pendingMemory", None)

    def _publish_advanced_communication(self, *, state, step_id: str, output_ref: str, commit_id: str) -> None:
        store = self.reliable_communication_store
        if store is None or self.communication_broker is None:
            return
        rules = [
            rule for rule in self.communication_broker.manifest.rules
            if rule.producer_step_id == step_id
        ]
        package_rules = ()
        package = self.compiled_package
        if package is not None:
            package_rules = package.communication_manifest.rules
        for rule in rules:
            mode = self.communication_modes.get(rule.consumer_step_id, "STRICT_CONTRACT")
            if mode not in {"EVENT", "DEBATE", "BLACKBOARD"}:
                continue
            spec = next((item for item in package_rules if item.producer_step_id == step_id and item.consumer_step_id == rule.consumer_step_id), None)
            if mode in {"EVENT", "DEBATE"}:
                store.publish(
                    ReliableMessage(
                        message_id=f"message:{commit_id}:{rule.consumer_step_id}",
                        run_id=state.run_id,
                        producer_step_id=step_id,
                        consumer_step_id=rule.consumer_step_id,
                        artifact_ref=output_ref,
                        correlation_id=state.run_id,
                        causation_id=commit_id,
                        sequence=len(state.completed_step_ids),
                        schema_hash=str(getattr(spec, "schema_hash", "") or "0" * 64),
                    ),
                    backlog_limit=int(getattr(spec, "backlog_limit", 1000)),
                )
            else:
                partition = str(getattr(spec, "partition", None) or rule.channel)
                version, _ = store.blackboard_snapshot(run_id=state.run_id, partition=partition)
                store.blackboard_write(
                    run_id=state.run_id, partition=partition, key=step_id,
                    artifact_ref=output_ref, expected_version=version, append=True,
                )

    @staticmethod
    def _safe_model_invocations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """裁剪模型调用审计字段，避免 prompt、响应正文或任意扩展载荷进入 Trace。"""
        allowed = {
            "provider", "model", "latencyMs", "promptVersion", "promptTemplateHash",
            "usage", "finishReason", "capability", "outputPolicy",
            "requestedOutputTokens", "effectiveOutputTokens", "effectiveReason",
            "outputExhausted", "partIndex", "callChainId",
        }
        return [
            {key: value for key, value in record.items() if key in allowed}
            for record in records
            if isinstance(record, dict)
        ]

    @staticmethod
    def _safe_tool_calls(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """裁剪工具调用审计字段，禁止参数正文进入执行事件。"""
        allowed = {"tool", "name", "status", "latencyMs", "errorCode"}
        result: list[dict[str, Any]] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            safe = {key: value for key, value in record.items() if key in allowed}
            identity = tuple(sorted((key, repr(value)) for key, value in safe.items()))
            if identity not in seen:
                seen.add(identity)
                result.append(safe)
        return result

    @staticmethod
    def _memory_policy(step_input: object) -> dict[str, Any]:
        """解析已冻结的步骤记忆策略，并拒绝无法审计的错误声明。

        策略存放在 ``WorkflowStep.input.memoryPolicy``，因为它是 ACG Blueprint
        元数据同步到本次运行后的私有边界。新格式明确用 ``readTypes`` 表示可读取的
        类别、用 ``writeType`` 表示输出写入类别，避免一个字段承担相反方向的权限。
        缺失策略与旧 ``allowedTypes`` 格式仅作兼容输入，解析结果始终是新格式。
        """
        raw = step_input.get("memoryPolicy") if isinstance(step_input, dict) else None
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("memoryPolicy must be an object")
        read = raw.get("read", True)
        write = raw.get("write", True)
        require_audit = raw.get("requireAudit", False)
        if not all(isinstance(item, bool) for item in (read, write, require_audit)):
            raise ValueError("memoryPolicy read, write and requireAudit must be booleans")
        uses_new_types = "readTypes" in raw or "writeType" in raw
        if uses_new_types and "allowedTypes" in raw:
            raise ValueError("memoryPolicy cannot mix allowedTypes with readTypes or writeType")
        if uses_new_types:
            read_raw = raw.get("readTypes", [])
            if not isinstance(read_raw, list):
                raise ValueError("memoryPolicy.readTypes must be a list")
            if read and not read_raw:
                raise ValueError("memoryPolicy.readTypes must not be empty when read is enabled")
            if write and raw.get("writeType") is None:
                raise ValueError("memoryPolicy.writeType is required when write is enabled")
            if not write and raw.get("writeType") is not None:
                raise ValueError("memoryPolicy.writeType requires write to be enabled")
            write_raw = raw.get("writeType")
        else:
            has_allowed_types = "allowedTypes" in raw
            read_raw = raw.get("allowedTypes", [])
            if not isinstance(read_raw, list):
                raise ValueError("memoryPolicy.allowedTypes must be a list")
            if has_allowed_types and not read_raw:
                raise ValueError("memoryPolicy.allowedTypes must not be empty when declared")
            # 旧策略的写入行为固定为 episodic；保留它，避免历史 Blueprint 改变结果。
            write_raw = MemoryType.EPISODIC if write else None
        try:
            read_types = [
                item if isinstance(item, MemoryType) else MemoryType(str(item))
                for item in read_raw
            ]
            write_type = (
                write_raw
                if isinstance(write_raw, MemoryType)
                else MemoryType(str(write_raw))
                if write_raw is not None
                else None
            )
        except ValueError as exc:
            raise ValueError("memoryPolicy readTypes or writeType contains an unsupported memory type") from exc
        limit = raw.get("limit", 10)
        token_budget = raw.get("tokenBudget")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("memoryPolicy.limit must be an integer between 1 and 100")
        if token_budget is not None and (
            not isinstance(token_budget, int) or isinstance(token_budget, bool) or token_budget < 0
        ):
            raise ValueError("memoryPolicy.tokenBudget must be a non-negative integer or null")
        policy_id = raw.get("policyId", "default")
        if not isinstance(policy_id, str) or not policy_id:
            raise ValueError("memoryPolicy.policyId must be a non-empty string")
        return {
            "policyId": policy_id,
            "read": read,
            "write": write,
            "readTypes": read_types,
            "writeType": write_type,
            "limit": limit,
            "tokenBudget": token_budget,
            "requireAudit": require_audit,
        }

    @staticmethod
    def _write_memory_policy(policy: Mapping[str, Any]) -> MemoryPolicy | None:
        """把步骤的单一写入类别收敛成 MemoryService 可执行的准入策略。"""
        write_type = policy["writeType"]
        if write_type is None:
            return None
        return MemoryPolicy(
            policyId=str(policy["policyId"]),
            allowedTypes=[write_type],
            requireAudit=bool(policy["requireAudit"]),
        )

    def _validate_committed_references(
        self,
        *,
        run_id: str,
        step_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        """重放提交前重验其正文引用，防止损坏记录把其他步骤的数据带回图状态。"""
        output_ref = payload.get("outputRef")
        if isinstance(output_ref, str):
            self.value_store.assert_reference(
                kind="output", run_id=run_id, step_id=step_id, reference=output_ref
            )
        context_ref = payload.get("contextRef")
        if isinstance(context_ref, str):
            self.value_store.assert_reference(
                kind="context", run_id=run_id, step_id=step_id, reference=context_ref
            )
        decision_ref = payload.get("auditDecisionRef")
        outcome = payload.get("auditOutcome")
        if isinstance(decision_ref, str) and isinstance(outcome, str):
            self.decision_store.assert_decision(
                run_id=run_id,
                step_id=step_id,
                decision_ref=decision_ref,
                outcomes={outcome},
            )

    @staticmethod
    def _require_audit_decision(decision: object) -> None:
        """记忆策略要求审计时，只接受含稳定标识和受支持结果的审计决定。"""
        decision_id = getattr(decision, "decision_id", None)
        outcome = getattr(decision, "outcome", None)
        if not isinstance(decision_id, str) or not decision_id or outcome not in {"allow", "review", "deny"}:
            raise ValueError("audit decision is required before memory write")

    def _persist_artifact_manifest(
        self, *, run_id: str, step_id: str, controlled: dict[str, Any]
    ) -> dict[str, Any]:
        """Seal artifact bodies and return only manifest references to projection."""
        raw = controlled.get("artifacts")
        if raw is None and isinstance(controlled.get("artifact"), dict):
            raw = [controlled["artifact"]]
        elif isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            return controlled
        normalized = dict(controlled)
        normalized_artifacts: list[dict[str, Any]] = []
        for raw_artifact in raw:
            if not isinstance(raw_artifact, dict):
                continue
            artifact = dict(raw_artifact)
            artifact.setdefault("artifactKey", "primary")
            manifest_id = artifact.get("manifestId")
            checksum = artifact.get("checksum")
            content = artifact.get("content")
            if not (isinstance(manifest_id, str) and manifest_id and
                    isinstance(checksum, str) and checksum):
                if not isinstance(content, str) or not content:
                    normalized_artifacts.append(artifact)
                    continue
                manifest = self.content_manifest_store.create_manifest(
                    kind=ContentKind.ARTIFACT,
                    owner_type="run",
                    owner_id=run_id,
                    media_type=str(artifact.get("mediaType") or "text/markdown"),
                    chunking_version="markdown-sections.v1",
                )
                sections: list[str] = []
                current: list[str] = []
                for line in content.splitlines(keepends=True):
                    if line.startswith("## ") and current:
                        sections.append("".join(current))
                        current = []
                    current.append(line)
                if current or not sections:
                    sections.append("".join(current))
                for sequence, section in enumerate(sections):
                    self.content_manifest_store.append_fragment(
                        manifest_id=manifest.manifest_id,
                        sequence=sequence,
                        content=section.encode("utf-8"),
                        source_refs=(step_id,),
                    )
                sealed = self.content_manifest_store.seal_manifest(manifest.manifest_id)
                artifact["manifestId"] = sealed.manifest_id
                artifact["checksum"] = sealed.checksum
            normalized_artifacts.append(artifact)
        if normalized_artifacts:
            normalized["artifacts"] = normalized_artifacts
            # Keep the singular envelope for legacy consumers and existing tests.
            if isinstance(controlled.get("artifact"), dict):
                normalized["artifact"] = normalized_artifacts[0]
        return normalized

    @staticmethod
    def _safe_artifact_descriptors(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        raw = payload.get("artifacts")
        if raw is None and isinstance(payload.get("artifact"), dict):
            raw = [payload["artifact"]]
        elif isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        allowed = {
            "artifactKey", "semanticTaskKey", "name", "title", "artifactType",
            "type", "mediaType", "manifestId", "checksum", "metadata",
        }
        descriptors: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            descriptor = {
                key: item[key]
                for key in allowed
                if item.get(key) is not None
            }
            descriptor.setdefault("artifactKey", "primary")
            descriptors.append(descriptor)
        return descriptors

    @staticmethod
    def _commit_id(run_id: str, step_id: str, attempt: int, *, loop_path: tuple[int, ...] = ()) -> str:
        """生成步骤尝试的稳定提交标识；重试次数变化才会开启新的副作用边界。"""
        suffix = f":loop:{'.'.join(map(str, loop_path))}" if loop_path else ""
        return f"commit:{run_id}:{step_id}:{max(0, attempt)}{suffix}"

    def _inject_fault(self, stage: str) -> None:
        """执行测试专用中断钩子；未注入时是零行为的私有空操作。"""
        if self._fault_hook is not None:
            self._fault_hook(stage)

    async def _assemble_broker_context(
        self,
        *,
        state: ACGExecutionState,
        step_id: str,
        step: WorkflowStep,
        commit_id: str,
    ) -> ContextPack:
        """按编译拓扑经 Broker 读取上游引用，并合并为节点可消费的最小 ContextPack。"""
        assert self.communication_broker is not None
        source_ids = self.upstream_step_ids.get(step_id, tuple(state.output_refs))
        from_map = step.input.get("from") if isinstance(step.input, dict) else None
        prefetch_map = step.input.get("prefetch") if isinstance(step.input, dict) else None
        data: dict[str, Any] = {}
        source_data: dict[str, dict[str, Any]] = {}
        evidence_refs: list[str] = []
        delivered = 0
        available = 0
        for source_id in source_ids:
            output_ref = state.output_refs.get(source_id)
            if output_ref is None:
                continue
            declared = from_map.get(source_id, []) if isinstance(from_map, dict) else []
            requested = (
                prefetch_map.get(source_id, declared)
                if isinstance(prefetch_map, dict)
                else declared
            )
            if not isinstance(requested, list):
                raise ValueError(f"inputSpec prefetch fields for {source_id} must be a list")
            partial = await self.communication_broker.read_reference(
                run_id=state.run_id,
                consumer_step_id=step_id,
                output_ref=output_ref,
                requested_fields=[str(field) for field in requested],
                max_tokens=None,
                reason=f"ACG step {step_id} requires upstream {source_id}",
            )
            data.update(partial.data)
            source_data.update(partial.source_data)
            evidence_refs.extend(item for item in partial.evidence_refs if item not in evidence_refs)
            delivered += partial.tokens_delivered
            available += partial.tokens_available
        # 预算使用是可恢复的数字投影；Broker 在运行期共享同一实例，下一次节点读取
        # 会继续累加，Runtime 重建时又会从 checkpoint 的这份计数恢复。
        state.communication_usage = self.communication_broker.usage_snapshot()
        return ContextPack(
            runId=state.run_id,
            stepId=step_id,
            objective=self.workflow.description,
            stepGoal=step.goal or step.name,
            data=data,
            sourceData=source_data,
            evidenceRefs=evidence_refs,
            tokensDelivered=delivered,
            tokensAvailable=available,
            savingRatio=(round(max(0.0, 1.0 - delivered / available), 4) if available else 0.0),
            sourceStepIds=list(source_ids),
            inputRevision=input_revision(data),
            attemptId=commit_id,
        )

    def _build_communication_reader(
        self,
        *,
        state: ACGExecutionState,
        step_id: str,
        mode: str,
    ) -> CommunicationReader | None:
        """为严格通信节点创建仅能补读其直接上游的受控读取器。"""
        if self.communication_broker is None or mode != "STRICT_CONTRACT":
            return None
        source_ids = self.upstream_step_ids.get(step_id, tuple())
        output_refs = {
            source_id: state.output_refs[source_id]
            for source_id in source_ids
            if source_id in state.output_refs
        }
        return CommunicationReader(
            broker=self.communication_broker,
            run_id=state.run_id,
            consumer_step_id=step_id,
            output_refs=output_refs,
            max_tokens=None,
        )
    def _build_content_workset_session(
        self, *, state: ACGExecutionState, step_id: str, step: WorkflowStep, commit_id: str
    ) -> ContentWorksetSession | None:
        if self.content_manifest_store is None or not isinstance(step.input, dict):
            return None
        raw = step.input.get("workset")
        if not isinstance(raw, dict):
            return None
        from contracts.content import WorksetSpec

        return ContentWorksetSession(
            store=self.content_manifest_store,
            spec=WorksetSpec.model_validate(raw),
            run_id=state.run_id,
            step_id=step_id,
            commit_id=commit_id,
        )


__all__ = ["ACGNodeRunner", "EntropyBudgetExceededError"]

"""AgentOS 融合后的 StateGraph / Pregel 执行核心。

本模块将 LangGraph 1.2.10 的 StateGraph、channel 与 Pregel 超步调度思想改写为
AgentOS 内部实现。它只负责图的编译产物执行、状态通道、并行就绪集、条件路由、
审核中断及事件流；ACG 规划、通信、记忆、Agent/Tool 适配和审计仍属于各自部件。

执行状态坚持“只存引用”：完整 slot 输入、模型输出和记忆正文不进入本状态，也不会
进入 SQLite checkpoint。条件路由所需的受控输出仅在当前 Pregel 轮次短暂使用。

第三方来源：LangGraph 1.2.10，commit d56666f7fbf0d380ad84cdf0cbe5aa48ab0cc086；
来源模块 ``graph/state.py``、``channels/base.py``、``channels/last_value.py``、
``pregel``。改写说明与完整 MIT 许可证见 ``docs/THIRD_PARTY_NOTICES.md``。
"""

from __future__ import annotations

import asyncio
from support.async_tasks import cancel_and_wait
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ACGExecutionState(BaseModel):
    """可检查点化的引用型执行状态。

    每个字段都是恢复执行所需的最小投影：已完成/活跃/跳过步骤、摘要以及各服务返回
    的引用。真实数据只能由 CommunicatorService、MemoryService 或输出存储按引用读取，
    以避免执行器绕过字段白名单、权限和审计边界。
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    run_id: str = Field(alias="runId")
    graph_id: str | None = Field(default=None, alias="graphId")
    graph_version: int = Field(default=1, alias="graphVersion", ge=1)
    # Present only after the S03 execution-permit handoff. This generation is
    # carried through checkpoints so stale work/receipts cannot alias a later
    # activated graph on the same Run.
    execution_permit_id: str | None = Field(default=None, alias="executionPermitId")
    execution_generation: str | None = Field(default=None, alias="executionGeneration")
    graph_patch_refs: list[str] = Field(default_factory=list, alias="graphPatchRefs")
    current_step_id: str | None = Field(default=None, alias="currentStepId")
    completed_step_ids: list[str] = Field(default_factory=list, alias="completedStepIds")
    active_step_ids: list[str] = Field(default_factory=list, alias="activeStepIds")
    skipped_step_ids: list[str] = Field(default_factory=list, alias="skippedStepIds")
    output_summaries: dict[str, str] = Field(default_factory=dict, alias="outputSummaries")
    # 节点输出正文位于 ExecutionValueStore；State 只保存该仓库生成的 outputRef，
    # 使 checkpoint 能重启调度而不会携带 slot 数据、模型响应或其它敏感正文。
    output_refs: dict[str, str] = Field(default_factory=dict, alias="outputRefs")
    context_refs: dict[str, str] = Field(default_factory=dict, alias="contextRefs")
    memory_refs: dict[str, str] = Field(default_factory=dict, alias="memoryRefs")
    trace_refs: dict[str, str] = Field(default_factory=dict, alias="traceRefs")
    # 通信正文与安全 Trace 均不进入 State；这里只保留已被账本封存的事件标识，
    # 恢复时 Runtime 会重新加载哈希链并检查该事件属于同一 run、task 与步骤。
    provenance_refs: dict[str, list[str]] = Field(default_factory=dict, alias="provenanceRefs")
    # 通信预算只保存已消耗的整数计数，恢复后 Broker 用它继续限制剩余额度。它不含
    # 输出、ContextPack、字段值或任何外部调用正文。
    communication_usage: dict[str, Any] = Field(default_factory=dict, alias="communicationUsage")
    control_frames: list[dict[str, Any]] = Field(default_factory=list, alias="controlFrames")
    loop_iterations: dict[str, int] = Field(default_factory=dict, alias="loopIterations")
    loop_paths: dict[str, list[int]] = Field(default_factory=dict, alias="loopPaths")
    consensus_results: dict[str, dict[str, Any]] = Field(default_factory=dict, alias="consensusResults")
    blackboard_snapshots: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="blackboardSnapshots"
    )
    debate_sessions: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="debateSessions"
    )
    checkpoint_id: str | None = Field(default=None, alias="checkpointId")
    review_payload: dict[str, Any] | None = Field(default=None, alias="reviewPayload")
    control_review_decisions: dict[str, str] = Field(
        default_factory=dict, alias="controlReviewDecisions"
    )


class ACGChannelError(ValueError):
    """同一 Pregel 轮次对一个单值状态通道进行了非法的并发写入。"""


class ExecutionDeniedError(RuntimeError):
    """The existing audit authority rejected a result before graph admission."""


class ACGSuperstepError(RuntimeError):
    """一个超步内发生节点异常后，携带失败与已取消步骤标识。"""

    def __init__(
        self,
        *,
        failed_step_ids: tuple[str, ...],
        cancelled_step_ids: tuple[str, ...],
        cause: BaseException,
    ) -> None:
        self.failed_step_ids = failed_step_ids
        self.cancelled_step_ids = cancelled_step_ids
        self.cause = cause
        super().__init__(
            "ACG superstep failed: "
            f"failed={','.join(failed_step_ids)}, cancelled={','.join(cancelled_step_ids)}"
        )


class ACGStateChannel:
    """执行状态字段通道的最小抽象。

    通道在一个 Pregel 超步结束时统一接收该轮所有任务的更新。不同通道可以定义不同
    聚合语义；当前首期使用 ``ACGLastValueChannel``，即单字段每轮只能有一个写入者。
    """

    def __init__(self, key: str) -> None:
        self.key = key

    def update(self, values: Sequence[Any]) -> bool:
        raise NotImplementedError

    def get(self) -> Any:
        raise NotImplementedError


class ACGLastValueChannel(ACGStateChannel):
    """最后值通道：一个 Pregel 轮次最多接收一次更新。

    这是 LangGraph ``LastValue`` 语义的改名实现。它将并行分支对同一状态键的竞争
    明确暴露为错误，而不是依赖不稳定的完成顺序覆盖数据。
    """

    _missing = object()

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.value: Any = self._missing

    def update(self, values: Sequence[Any]) -> bool:
        if not values:
            return False
        if len(values) != 1:
            raise ACGChannelError(f"At key '{self.key}': can receive only one value per Pregel round")
        self.value = values[0]
        return True

    def get(self) -> Any:
        if self.value is self._missing:
            raise LookupError(f"channel {self.key} is empty")
        return self.value


@dataclass(frozen=True)
class ACGNodeSpec:
    """编译后仅由执行器消费的 Step/控制节点描述。

    ACG Blueprint 仍是规划权威；本对象只是把蓝图中的通信模式、审核点和条件控制
    降为调度期可直接读取的不可变元数据，绝不泄漏到 ``contracts/``。
    """

    node_id: str
    kind: Literal["step", "control"] = "step"
    communication_mode: Literal["STRICT_CONTRACT", "EVENT", "BLACKBOARD", "DEBATE"] = "STRICT_CONTRACT"
    review_required: bool = False
    condition: "ACGConditionalRoute | None" = None
    control_type: str | None = None


@dataclass(frozen=True)
class ACGConditionalRoute:
    """从 ACG ``IF`` 控制节点编译出的受限条件路由。

    ``json_pointer`` 只读取本轮节点的受控输出；不执行任意 Python 表达式。结果仅为
    一个已声明的目标节点，未被选择的兄弟分支会在状态中标记为跳过。
    """

    source_step_id: str
    json_pointer: str
    operator: str
    targets_by_case: dict[str, str]
    default_target: str | None = None

    def select(self, source_value: dict[str, Any]) -> str | None:
        """按受限操作符求值并返回一个目标节点；无匹配时使用默认目标。"""
        value: Any = source_value
        for segment in (item for item in self.json_pointer.split("/") if item):
            if not isinstance(value, dict) or segment not in value:
                value = None
                break
            value = value[segment]
        if self.operator == "BOOLEAN":
            key = "true" if bool(value) else "false"
        elif self.operator == "EXISTS":
            key = "true" if value is not None else "false"
        elif self.operator == "IN":
            key = str(value)
        else:
            key = str(value)
        return self.targets_by_case.get(key, self.default_target)


NodeRunner = Callable[[str, ACGExecutionState], Awaitable[dict[str, Any]]]


class ACGExecutionGraph:
    """编译完成的 AgentOS 执行图，采用 Pregel 的“轮次屏障”调度。

    一个超步中所有 ready Step 并发运行；只有全体结果返回后，才统一提交摘要/引用并
    计算下一批 ready 节点。这个屏障保证并行分支不因完成时序不同而改变依赖可见性。
    控制节点没有 Agent 调用：它们在超步间推进，用于条件分支、循环和显式控制屏障。
    """

    def __init__(
        self,
        *,
        nodes: tuple[str, ...],
        edges: tuple[tuple[str, str], ...] = (),
        node_specs: dict[str, ACGNodeSpec] | None = None,
        communication_manifest: object | None = None,
        compiled_package: object | None = None,
    ) -> None:
        self.nodes = tuple(dict.fromkeys(nodes))
        self.edges = tuple(edges)
        self.node_specs = node_specs or {node_id: ACGNodeSpec(node_id=node_id) for node_id in self.nodes}
        self.communication_manifest = communication_manifest
        self.compiled_package = compiled_package
        self.control_manifest = getattr(compiled_package, "control_manifest", None)
        known = set(self.nodes)
        if set(self.node_specs) != known or any(source not in known or target not in known for source, target in self.edges):
            raise ValueError("graph nodes and edges must be declared consistently")
        self._validate_acyclic()

    def ready_steps(self, state: ACGExecutionState) -> tuple[str, ...]:
        """返回当前超步可并发执行的 Step，排除控制节点和未选择的分支。"""
        completed = set(state.completed_step_ids)
        inactive = set(state.active_step_ids) | set(state.skipped_step_ids)
        ready: list[str] = []
        for node_id in self.nodes:
            spec = self.node_specs[node_id]
            if node_id in completed or node_id in inactive or spec.kind != "step":
                continue
            predecessors = {source for source, target in self.edges if target == node_id}
            if predecessors <= completed:
                ready.append(node_id)
        return tuple(ready)

    def select_routes(self, control_id: str, source_value: dict[str, Any]) -> tuple[str, ...]:
        """供调试和编译测试读取某个条件控制节点的目标分支。"""
        route = self.node_specs[control_id].condition
        if route is None:
            return ()
        target = route.select(source_value)
        return (target,) if target else ()

    def _advance_controls(
        self,
        state: ACGExecutionState,
        route_values: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """推进满足前驱条件的控制节点，并根据路由结果标记跳过分支。"""
        self._advance_loop_frames(state, route_values or {})
        if state.review_payload is not None:
            return
        completed = set(state.completed_step_ids)
        skipped = set(state.skipped_step_ids)
        changed = True
        while changed:
            changed = False
            for control_id, spec in self.node_specs.items():
                if spec.kind != "control" or control_id in completed:
                    continue
                predecessors = {source for source, target in self.edges if target == control_id}
                effective_predecessors = predecessors - skipped
                if not effective_predecessors <= completed:
                    continue
                if spec.condition is not None:
                    value = (route_values or {}).get(spec.condition.source_step_id, {})
                    target = spec.condition.select(value)
                    if target is None:
                        raise RuntimeError(f"CONTROL_NO_MATCH:{control_id}")
                    branch_targets = {target_id for source, target_id in self.edges if source == control_id}
                    skipped.update(branch_targets - {target})
                if spec.control_type == "consensus":
                    self._resolve_consensus(state, control_id, route_values or {})
                    if state.review_payload is not None:
                        state.skipped_step_ids = [
                            node_id for node_id in self.nodes if node_id in skipped
                        ]
                        return
                state.completed_step_ids.append(control_id)
                completed.add(control_id)
                changed = True
        state.skipped_step_ids = [node_id for node_id in self.nodes if node_id in skipped]

    def _advance_loop_frames(self, state: ACGExecutionState, route_values: dict[str, dict[str, Any]]) -> None:
        if self.control_manifest is None:
            return
        completed = set(state.completed_step_ids)
        for rule in self.control_manifest.rules:
            loop = rule.loop
            if loop is None or loop.body_exit_id not in completed:
                continue
            current = int(state.loop_iterations.get(rule.control_id, 0))
            value = route_values.get(loop.condition.source_step_id, {})
            route = ACGConditionalRoute(
                source_step_id=loop.condition.source_step_id,
                json_pointer=loop.condition.json_pointer,
                operator=loop.condition.operator,
                targets_by_case=dict(loop.condition.targets_by_case),
                default_target=loop.condition.default_target,
            )
            target = route.select(value)
            if target != loop.body_entry_id:
                state.control_frames = [
                    item for item in state.control_frames if item.get("controlId") != rule.control_id
                ]
                continue
            next_iteration = current + 1
            if next_iteration >= loop.max_iterations:
                if state.control_review_decisions.pop(rule.control_id, None) == "approved":
                    state.control_frames = [
                        item
                        for item in state.control_frames
                        if item.get("controlId") != rule.control_id
                    ]
                    continue
                if loop.on_limit == "review":
                    state.review_payload = {
                        "subjectType": "control",
                        "subjectId": rule.control_id,
                        "controlId": rule.control_id,
                        "reasonCode": "LOOP_MAX_ITERATIONS",
                        "iteration": next_iteration,
                    }
                    return
                raise RuntimeError(f"LOOP_MAX_ITERATIONS:{rule.control_id}")
            region = self._loop_region(loop.body_entry_id, loop.body_exit_id)
            state.completed_step_ids = [node_id for node_id in state.completed_step_ids if node_id not in region]
            state.skipped_step_ids = [node_id for node_id in state.skipped_step_ids if node_id not in region]
            state.loop_iterations[rule.control_id] = next_iteration
            for node_id in region:
                if self.node_specs[node_id].kind == "step":
                    state.loop_paths[node_id] = [next_iteration]
            frame = {
                "controlId": rule.control_id,
                "controlType": "loop",
                "iteration": next_iteration,
                "region": sorted(region),
            }
            state.control_frames = [
                item for item in state.control_frames if item.get("controlId") != rule.control_id
            ] + [frame]

    def _loop_region(self, entry_id: str, exit_id: str) -> set[str]:
        region: set[str] = set()
        frontier = [entry_id]
        while frontier:
            node_id = frontier.pop()
            if node_id in region:
                continue
            region.add(node_id)
            if node_id == exit_id:
                continue
            frontier.extend(target for source, target in self.edges if source == node_id)
        if exit_id not in region:
            raise RuntimeError(f"loop body exit {exit_id} is unreachable from {entry_id}")
        return region

    def _resolve_consensus(self, state: ACGExecutionState, control_id: str, route_values: dict[str, dict[str, Any]]) -> None:
        if self.control_manifest is None:
            return
        rule = next((item for item in self.control_manifest.rules if item.control_id == control_id), None)
        spec = rule.consensus if rule is not None else None
        if spec is None:
            return
        votes: list[bool] = []
        for participant in spec.participant_step_ids:
            value = route_values.get(participant, {})
            raw = value.get("vote", value.get("approved"))
            if isinstance(raw, bool):
                votes.append(raw)
        approvals = sum(votes)
        committed_participants = sum(
            participant in state.completed_step_ids
            for participant in spec.participant_step_ids
        )
        if spec.strategy == "auditor":
            resolved = committed_participants >= spec.quorum
            accepted = resolved
        else:
            resolved = len(votes) >= spec.quorum
            accepted = (
                resolved and approvals == len(spec.participant_step_ids)
                if spec.strategy == "unanimous"
                else resolved and approvals > len(votes) / 2
            )
        result = {
            "votes": len(votes),
            "approvals": approvals,
            "committedParticipants": committed_participants,
            "quorum": spec.quorum,
            "accepted": accepted,
            "strategy": spec.strategy,
        }
        if state.control_review_decisions.pop(control_id, None) == "approved":
            result.update({"accepted": True, "resolvedByReview": True})
            state.consensus_results[control_id] = result
            return
        state.consensus_results[control_id] = result
        tied_majority = (
            spec.strategy == "majority"
            and bool(votes)
            and approvals * 2 == len(votes)
        )
        if not resolved or tied_majority:
            if spec.on_unresolved == "review":
                state.review_payload = {
                    "subjectType": "control",
                    "subjectId": control_id,
                    "controlId": control_id,
                    "reasonCode": "CONSENSUS_UNRESOLVED",
                    **result,
                }
            else:
                raise RuntimeError(f"CONSENSUS_UNRESOLVED:{control_id}")

    async def run(self, state: ACGExecutionState, execute: NodeRunner) -> ACGExecutionState:
        """执行至完成或审核中断；调用方应持久化每个流事件对应的状态。"""
        async for _ in self.astream(state, execute):
            pass
        return state

    async def resume(self, state: ACGExecutionState, command: Any, execute: NodeRunner) -> ACGExecutionState:
        """消费同 runId 的审核恢复命令，并从已持久化的状态继续而不重跑审核步骤。"""
        self._prepare_resume(state, command)
        return await self.run(state, execute)

    async def astream_after_resume(self, state: ACGExecutionState, command: Any, execute: NodeRunner):
        """消费恢复命令后继续产生事件流，避免 Runtime 需要绕过图的审核语义。"""
        self._prepare_resume(state, command)
        async for event in self.astream(state, execute):
            yield event

    @staticmethod
    def _prepare_resume(state: ACGExecutionState, command: Any) -> None:
        """Resolve exactly one persisted review barrier before scheduling resumes."""

        command_run_id = getattr(command, "run_id", None)
        if command_run_id != state.run_id:
            raise ValueError("resume command runId does not match execution state")
        if state.review_payload is None:
            raise ValueError("execution state is not waiting for review")
        control_id = state.review_payload.get("controlId")
        decision = getattr(command, "payload", {}).get("decision")
        if isinstance(control_id, str) and control_id:
            if decision != "approved":
                raise ValueError("control review resume requires an approved decision")
            state.control_review_decisions[control_id] = decision
        state.review_payload = None

    async def astream(self, state: ACGExecutionState, execute: NodeRunner):
        """产生 AgentOS 事件字典，供 runtime/auditor 投影为既有 TraceEvent。"""
        route_values: dict[str, dict[str, Any]] = {}
        self._advance_controls(state, route_values)
        while len(set(state.completed_step_ids) | set(state.skipped_step_ids)) < len(self.nodes):
            ready = self.ready_steps(state)
            if not ready:
                raise RuntimeError("execution graph has no schedulable step nodes")
            state.active_step_ids = list(ready)
            state.current_step_id = ready[0] if len(ready) == 1 else None
            # 在发出调度事件前就固化活动集，Runtime 投影层可以立即把“正在执行”
            # 写入 WorkflowStore，而不必等待任一节点完成。
            yield {"type": "nodes_scheduled", "stepIds": list(ready)}
            prepare_superstep = getattr(execute, "prepare_superstep", None)
            if callable(prepare_superstep):
                prepare_superstep(state, ready)
            tasks = {
                step_id: asyncio.create_task(execute(step_id, state), name=f"acg:{state.run_id}:{step_id}")
                for step_id in ready
            }
            try:
                pending_tasks = dict(tasks)
                while pending_tasks:
                    try:
                        done, pending = await asyncio.wait(
                            pending_tasks.values(), return_when=asyncio.FIRST_COMPLETED
                        )
                    except asyncio.CancelledError as exc:
                        await cancel_and_wait(pending_tasks.values(), reason=str(exc) or "execution_cancelled")
                        state.active_step_ids = []
                        raise
                    failures = [
                        step_id
                        for step_id, task in pending_tasks.items()
                        if task in done and not task.cancelled() and task.exception() is not None
                    ]
                    if failures:
                        # 已经原子提交的节点结果继续保留；尚未提交的兄弟节点进入取消态。
                        # 这样一个慢节点失败时，不会回滚此前已经可查询的完整答案。
                        cancelled = [
                            step_id for step_id in ready
                            if step_id not in failures and step_id not in state.completed_step_ids
                        ]
                        await cancel_and_wait(pending, reason="sibling_failure")
                        state.active_step_ids = []
                        cause = pending_tasks[failures[0]].exception()
                        assert cause is not None
                        # 进程终止、测试模拟断电等 ``BaseException`` 不能被误标为业务节点
                        # 失败或触发 failed run 投影；让调用栈直接中断，下一进程从持久化边界
                        # 继续。普通 ``Exception`` 仍保留完整的超步失败语义。
                        if not isinstance(cause, Exception):
                            raise cause
                        raw_audit = getattr(cause, "audit", None)
                        safe_audit_keys = {
                            "provider", "model", "latencyMs", "promptVersion",
                            "promptTemplateHash", "usage", "finishReason", "capability",
                            "outputPolicy", "requestedOutputTokens", "effectiveOutputTokens",
                            "effectiveReason", "outputExhausted", "partIndex", "callChainId",
                            "streamDiagnostics",
                        }
                        failure_invocations = (
                            [{key: value for key, value in raw_audit.items() if key in safe_audit_keys}]
                            if isinstance(raw_audit, dict) and raw_audit
                            else []
                        )
                        yield {
                            "type": "superstep_failed",
                            "stepId": failures[0],
                            "failedStepIds": failures,
                            "cancelledStepIds": cancelled,
                            "modelInvocations": failure_invocations,
                        }
                        raise ACGSuperstepError(
                            failed_step_ids=tuple(failures),
                            cancelled_step_ids=tuple(cancelled),
                            cause=cause,
                        ) from cause

                    completed_ids = sorted(
                        (step_id for step_id, task in pending_tasks.items() if task in done),
                        key=ready.index,
                    )
                    for step_id in completed_ids:
                        try:
                            event, review_payload = self._commit_node_result(
                                state=state,
                                route_values=route_values,
                                step_id=step_id,
                                result=pending_tasks[step_id].result(),
                            )
                        except BaseException:
                            await cancel_and_wait(pending_tasks.values(), reason="result_commit_failure")
                            state.active_step_ids = []
                            raise
                        yield event
                        pending_tasks.pop(step_id)
                        if review_payload is not None:
                            await cancel_and_wait(pending_tasks.values(), reason="review_interrupt")
                            from components.recovery.checkpoint import ExecutionInterrupt

                            raise ExecutionInterrupt("execution requires review", review_payload)
            finally:
                try:
                    await cancel_and_wait(tasks.values(), reason="graph_closed")
                finally:
                    state.active_step_ids = []
            for step_id in ready:
                state.blackboard_snapshots.pop(step_id, None)
            self._advance_controls(state, route_values)
            if state.review_payload is not None:
                from components.recovery.checkpoint import ExecutionInterrupt
                raise ExecutionInterrupt("control requires review", state.review_payload)
            yield {
                "type": "superstep_completed",
                "stepIds": list(ready),
            }
        state.current_step_id = None

    def _commit_node_result(
        self,
        *,
        state: ACGExecutionState,
        route_values: dict[str, dict[str, Any]],
        step_id: str,
        result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """原子提交一个已完成节点，并返回可立即投影的事件。"""
        # 严重风险由审计器给出 deny。此时节点结果不能进入 State，也不能产生
        # outputRef、memoryRef 或下游调度条件；Runtime 会将该异常收敛为失败。
        if result.get("auditOutcome") == "deny":
            raise ExecutionDeniedError(
                f"execution denied at {step_id}: {result.get('auditDecisionRef') or 'policy decision'}"
            )
        if isinstance(result.get("routeValue"), dict):
            route_values[step_id] = dict(result["routeValue"])
        if result.get("outputSummary") is not None:
            state.output_summaries[step_id] = str(result["outputSummary"])
        if result.get("outputRef") is not None:
            state.output_refs[step_id] = str(result["outputRef"])
        for key, destination in (("contextRef", state.context_refs), ("memoryRef", state.memory_refs), ("traceRef", state.trace_refs)):
            if result.get(key) is not None:
                destination[step_id] = str(result[key])
        provenance_ids: list[str] = []
        for provenance_event in result.get("provenanceEvents") or []:
            if not isinstance(provenance_event, dict):
                continue
            payload = provenance_event.get("payload")
            event_id = payload.get("eventId") if isinstance(payload, dict) else None
            if isinstance(event_id, str) and event_id:
                provenance_ids.append(event_id)
        if provenance_ids:
            # 节点提交可能在进程中断后被重放。保留首次顺序并去重，确保同一
            # 血缘事件不会因重放膨胀 checkpoint，也不会影响账本中的真实事件。
            state.provenance_refs[step_id] = list(
                dict.fromkeys([*state.provenance_refs.get(step_id, []), *provenance_ids])
            )
        state.completed_step_ids.append(step_id)
        memory_access = self._safe_memory_access(result.get("memoryAccess"))
        memory_event = self._safe_memory_event(result.get("memoryEvent"))
        # 节点结果已原子提交时，活动集立即只保留同一并行超步中仍在运行的
        # 兄弟节点；Runtime 因而可以在该节点事件后展示准确的运行态。
        state.active_step_ids = [
            item for item in state.active_step_ids
            if item not in state.completed_step_ids
        ]
        event = {
            "type": "node_completed",
            "stepId": step_id,
            "commitId": result.get("commitId"),
            "outputSummary": state.output_summaries.get(step_id, ""),
            "modelInvocations": list(result.get("modelInvocations") or []),
            "runtimeEvents": list(result.get("runtimeEvents") or []),
            "toolCalls": list(result.get("toolCalls") or []),
            "provenanceEvents": list(result.get("provenanceEvents") or []),
            "communicationReads": list(result.get("communicationReads") or []),
            "memoryAccess": memory_access,
            "memoryEvent": memory_event,
        }
        review_payload: dict[str, Any] | None = None
        if self.node_specs[step_id].review_required or result.get("reviewRequired"):
            review_payload = {
                "stepId": step_id,
                "traceRef": state.trace_refs.get(step_id),
            }
            if result.get("auditDecisionRef") is not None:
                review_payload["auditDecisionRef"] = str(result["auditDecisionRef"])
            if result.get("auditOutcome") is not None:
                review_payload["auditOutcome"] = str(result["auditOutcome"])
            pending_memory = result.get("pendingMemory")
            if isinstance(pending_memory, dict):
                # 待写意图只能携带 outputRef、策略与审计引用；正文仍在独立
                # 值仓库，人工批准前绝不进入 MemoryStore 或执行 State 主字段。
                review_payload["pendingMemory"] = dict(pending_memory)
            state.review_payload = review_payload
            # The review node has already committed successfully.  A paused
            # checkpoint therefore has no actively executing node.
            state.active_step_ids = []
        return event, review_payload

    def _validate_acyclic(self) -> None:
        """在图构造时拒绝依赖环，避免运行期出现没有 ready 节点的死锁。"""
        remaining = set(self.nodes)
        predecessors = {node: {source for source, target in self.edges if target == node} for node in self.nodes}
        while remaining:
            roots = {node for node in remaining if not (predecessors[node] & remaining)}
            if not roots:
                raise ValueError("execution graph contains a cycle")
            remaining -= roots

    @staticmethod
    def _safe_memory_access(value: object) -> dict[str, Any]:
        """白名单化节点记忆审计元数据，禁止正文或任意扩展字段进入 Trace。"""
        if not isinstance(value, dict):
            return {}
        allowed = {
            "policyId",
            "read",
            "readCount",
            "retrievalMode",
            "hitRefs",
            "write",
            "written",
            "readTypes",
            "writeType",
            "limit",
            "tokenBudget",
            "tokensUsed",
            "requireAudit",
        }
        return {key: item for key, item in value.items() if key in allowed}

    @staticmethod
    def _safe_memory_event(value: object) -> dict[str, Any]:
        """Whitelist the compact event contract before it reaches Runtime Trace."""
        if not isinstance(value, dict):
            return {}
        allowed = {
            "eventId",
            "runId",
            "stepId",
            "commitId",
            "summary",
            "evidenceRefs",
            "metrics",
            "decision",
            "relations",
        }
        return {key: item for key, item in value.items() if key in allowed}


__all__ = ["ACGChannelError", "ACGConditionalRoute", "ACGExecutionGraph", "ACGExecutionState", "ACGLastValueChannel", "ACGNodeSpec", "ACGStateChannel", "ACGSuperstepError"]

"""Focused behavior tests for the AgentOS-fused execution graph."""

from __future__ import annotations


import asyncio

import pytest

from components.executor.compiler import ACGGraphCompiler, UnsupportedCommunicationModeError
from components.executor.graph import ACGConditionalRoute, ACGExecutionGraph, ACGExecutionState, ACGNodeSpec, ACGSuperstepError
from components.executor.state_graph import ACGStateGraph
from components.executor.node_runner import ACGNodeRunner
from components.executor.value_store import InMemoryExecutionValueStore
from adapters.model_adapter import StructuredGenerationError
from components.recovery.checkpoint import ExecutionInterrupt, ExecutionResumeCommand
from components.auditor import InMemoryDecisionStore
from components.auditor.governance.trace import TraceStore
from contracts.memory import MemoryQuery, MemoryRecord, MemoryType
from contracts.compiled_acg import EvidenceManifest, EvidenceRule
from contracts.workflow import RuntimeMissionRecord, WorkflowDefinition, RuntimeRunRecord, WorkflowStep
from components.communicator import CommunicatorService
from components.memory import MemoryService
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from support.acg.planning import ACGResourcePlan, AgentBindingSpec, CommunicationSpec
from support.acg.models import (
    ACGBlueprint,
    ACGEdge,
    ConditionOperator,
    ConditionSpec,
    ConsensusSpec,
    ControlNode,
    ControlType,
    EdgeType,
    StepNode,
)


def test_execution_graph_runs_ready_steps_then_dependents() -> None:
    graph = ACGExecutionGraph(nodes=("extract", "summarize"), edges=(("extract", "summarize"),))
    state = ACGExecutionState(runId="run-1")
    observed: list[str] = []

    async def execute(step_id: str, _state: ACGExecutionState):
        observed.append(step_id)
        return {"outputSummary": f"done:{step_id}", "traceRef": f"trace:{step_id}"}

    result = asyncio.run(graph.run(state, execute))

    assert observed == ["extract", "summarize"]
    assert result.completed_step_ids == ["extract", "summarize"]
    assert result.trace_refs == {"extract": "trace:extract", "summarize": "trace:summarize"}
    assert "fullOutput" not in result.model_dump(by_alias=True)


def test_execution_graph_projects_only_provenance_event_ids_into_state() -> None:
    """图状态只保留节点归属的事件 ID，不能把通信 Trace 或正文写进 checkpoint。"""
    graph = ACGExecutionGraph(nodes=("extract",))
    state = ACGExecutionState(runId="run-1")

    async def execute(_step_id: str, _state: ACGExecutionState) -> dict:
        return {
            "outputSummary": "done",
            "provenanceEvents": [
                {"eventType": "data_produced", "payload": {"eventId": "prod_000001", "fieldNames": ["title"]}},
                {"eventType": "data_produced", "payload": {"eventId": "prod_000001", "fieldNames": ["title"]}},
            ],
        }

    result = asyncio.run(graph.run(state, execute))

    assert result.provenance_refs == {"extract": ["prod_000001"]}
    assert "fieldNames" not in str(result.model_dump(by_alias=True))


def test_execution_graph_exposes_parallel_ready_set() -> None:
    graph = ACGExecutionGraph(nodes=("left", "right", "join"), edges=(("left", "join"), ("right", "join")))

    assert graph.ready_steps(ACGExecutionState(runId="run-1")) == ("left", "right")


def test_parallel_failure_cancels_unfinished_sibling_tasks() -> None:
    """同一超步任一节点失败时，图必须取消并等待未完成的兄弟任务。"""
    graph = ACGExecutionGraph(nodes=("fail", "slow"))
    state = ACGExecutionState(runId="run-1")
    cancelled: list[str] = []

    async def execute(step_id, _state):
        if step_id == "fail":
            await asyncio.sleep(0)
            raise ValueError("expected failure")
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(step_id)
            raise

    with pytest.raises(ACGSuperstepError) as captured:
        asyncio.run(graph.run(state, execute))

    assert captured.value.failed_step_ids == ("fail",)
    assert captured.value.cancelled_step_ids == ("slow",)
    assert cancelled == ["slow"]
    assert state.completed_step_ids == []
    assert state.active_step_ids == []


def test_parallel_node_completion_is_streamed_before_sibling_finishes() -> None:
    """并行超步中先完成的节点必须先发布，不能等待最慢兄弟。"""
    graph = ACGExecutionGraph(nodes=("left", "right"))

    async def collect() -> list[dict]:
        release_right = asyncio.Event()
        state = ACGExecutionState(runId="run-1")
        events: list[dict] = []

        async def execute(step_id, _state):
            if step_id == "right":
                await release_right.wait()
            return {"outputSummary": f"{step_id} done"}

        async for event in graph.astream(state, execute):
            events.append(event)
            if event["type"] == "node_completed" and event["stepId"] == "left":
                assert state.completed_step_ids == ["left"]
                assert state.active_step_ids == ["right"]
                release_right.set()
        return events

    events = asyncio.run(collect())
    completed = [item["stepId"] for item in events if item["type"] == "node_completed"]
    assert completed == ["left", "right"]


def test_output_exhaustion_failure_event_preserves_safe_model_audit() -> None:
    graph = ACGExecutionGraph(nodes=("artifact",))

    async def execute(_step_id, _state):
        raise StructuredGenerationError(
            "MODEL_OUTPUT_EXHAUSTED",
            "capacity reached",
            audit={
                "provider": "test", "model": "model", "finishReason": "length",
                "usage": {"input_tokens": 20, "output_tokens": 10},
                "outputExhausted": True, "prompt": "must-not-enter-trace",
            },
        )

    async def collect():
        events = []
        with pytest.raises(ACGSuperstepError):
            async for event in graph.astream(ACGExecutionState(runId="run-1"), execute):
                events.append(event)
        return events

    events = asyncio.run(collect())
    failed = next(item for item in events if item["type"] == "superstep_failed")
    assert failed["stepId"] == "artifact"
    assert failed["modelInvocations"][0]["finishReason"] == "length"
    assert failed["modelInvocations"][0]["outputExhausted"] is True
    assert "prompt" not in failed["modelInvocations"][0]


def test_compiler_preserves_blackboard_communication_mode() -> None:
    blueprint = ACGBlueprint(
        graphId="acg-test",
        nodes=[StepNode(nodeId="one",  metadata={"communicationMode": "BLACKBOARD"})],
    resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="one", plannedAgentId="agent"),)),
        edges=[])

    graph = ACGGraphCompiler().compile(blueprint)

    assert graph.node_specs["one"].communication_mode == "BLACKBOARD"


def test_compiler_accepts_event_mode_without_downgrading_it() -> None:
    blueprint = ACGBlueprint(
        graphId="acg-event",
        nodes=[StepNode(nodeId="signal",  metadata={"communicationMode": "EVENT"})],
    resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="signal", plannedAgentId="agent"),)),
        edges=[])

    graph = ACGGraphCompiler().compile(blueprint)

    assert graph.node_specs["signal"].communication_mode == "EVENT"


def test_compiler_uses_dependency_edges_only() -> None:
    blueprint = ACGBlueprint(
        graphId="acg-test",
        nodes=[
            *(StepNode(nodeId=node_id) for node_id in ("one", "two", "three")),
        ],
        resourcePlan=ACGResourcePlan(
            bindings=(
                AgentBindingSpec(stepId="one", plannedAgentId="runner"),
                AgentBindingSpec(stepId="two", plannedAgentId="runner"),
                AgentBindingSpec(stepId="three", plannedAgentId="runner"),
            ),
            communication=(CommunicationSpec(
                producerStepId="one", consumerStepId="three", channel="one:three",
            ),),
        ),
        edges=[
            ACGEdge(sourceId="one", targetId="two", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="two", targetId="three", edgeType=EdgeType.DEPENDENCY),
        ],
    )

    graph = ACGGraphCompiler().compile(blueprint)

    assert graph.edges == (("one", "two"), ("two", "three"))


def test_compiler_maps_blueprint_budget_to_manifest_run_budget() -> None:
    """蓝图的总通信预算必须成为 Broker 可执行的 run 级硬上限。"""
    blueprint = ACGBlueprint(
        graphId="acg-budget",
        metadata={"communicationBudget": 120},
        nodes=[StepNode(nodeId="produce"), StepNode(nodeId="consume")],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="produce", plannedAgentId="agent"), AgentBindingSpec(stepId="consume", plannedAgentId="agent"),)),
        edges=[ACGEdge(sourceId="produce", targetId="consume", edgeType=EdgeType.DEPENDENCY)],
    )

    graph = ACGGraphCompiler().compile(blueprint, run_id="run-budget")

    assert graph.communication_manifest is not None
    assert graph.communication_manifest.run_budget == 120


def test_compiler_leaves_fan_in_unbounded_without_an_explicit_policy() -> None:
    """未显式声明通信边界时，编译器不得偷偷回退到 4096。"""
    blueprint = ACGBlueprint(
        graphId="acg-fan-in-budget",
        nodes=[
            StepNode(nodeId="left"),
            StepNode(nodeId="right"),
            StepNode(nodeId="join"), ],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="left", plannedAgentId="agent"), AgentBindingSpec(stepId="right", plannedAgentId="agent"), AgentBindingSpec(stepId="join", plannedAgentId="agent"),)),
        edges=[
            ACGEdge(sourceId="left", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="right", targetId="join", edgeType=EdgeType.DEPENDENCY), ],
    )

    graph = ACGGraphCompiler().compile(blueprint, run_id="run-fan-in")

    assert graph.communication_manifest is not None
    assert graph.communication_manifest.step_budgets == {}
    assert graph.communication_manifest.channel_budgets == {}
    assert all(rule.max_tokens is None for rule in graph.communication_manifest.rules)


def test_compiler_maps_step_dependencies_and_review_interrupt() -> None:
    blueprint = ACGBlueprint(
        graphId="acg-review",
        nodes=[
            StepNode(nodeId="draft"),
            StepNode(nodeId="approve",  reviewRequired=True)],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="draft", plannedAgentId="agent"), AgentBindingSpec(stepId="approve", plannedAgentId="agent"),)),
        edges=[ACGEdge(sourceId="draft", targetId="approve", edgeType=EdgeType.DEPENDENCY)],
    )

    graph = ACGGraphCompiler().compile(blueprint)

    assert graph.node_specs["draft"].communication_mode == "STRICT_CONTRACT"
    assert graph.node_specs["approve"].review_required is True
    assert graph.edges == (("draft", "approve"),)


def test_compiler_maps_if_control_to_conditional_route() -> None:
    true_edge = ACGEdge(edgeId="to-true", sourceId="if", targetId="true", edgeType=EdgeType.DEPENDENCY)
    false_edge = ACGEdge(edgeId="to-false", sourceId="if", targetId="false", edgeType=EdgeType.DEPENDENCY)
    blueprint = ACGBlueprint(
        graphId="acg-route",
        nodes=[
            StepNode(nodeId="source"),
            ControlNode(
                nodeId="if",
                controlType=ControlType.IF,
                conditionSpec=ConditionSpec(
                    sourceNodeId="source",
                    jsonPointer="/approved",
                    operator=ConditionOperator.BOOLEAN,
                    cases={"true": "to-true", "false": "to-false"},
                ),
                branchEdgeIds=["to-true", "to-false"],
                joinNodeId="join",
            ),
            StepNode(nodeId="true"),
            StepNode(nodeId="false"),
            ControlNode(
                nodeId="join",
                controlType=ControlType.CONSENSUS,
                consensusSpec=ConsensusSpec(
                    participantStepIds=["true", "false"],
                    quorum=1,
                    strategy="auditor",
                ),
            ), ],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="source", plannedAgentId="agent"), AgentBindingSpec(stepId="true", plannedAgentId="agent"), AgentBindingSpec(stepId="false", plannedAgentId="agent"),)),
        edges=[
            ACGEdge(sourceId="source", targetId="if", edgeType=EdgeType.DEPENDENCY),
            true_edge,
            false_edge,
            ACGEdge(sourceId="true", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="false", targetId="join", edgeType=EdgeType.DEPENDENCY), ],
    )

    graph = ACGGraphCompiler().compile(blueprint)

    assert graph.select_routes("if", {"approved": True}) == ("true",)
    assert graph.select_routes("if", {"approved": False}) == ("false",)


def test_pregel_loop_executes_only_selected_conditional_branch() -> None:
    blueprint = ACGBlueprint(
        graphId="acg-route-run",
        nodes=[
            StepNode(nodeId="source"),
            ControlNode(
                nodeId="if", controlType=ControlType.IF,
                conditionSpec=ConditionSpec(sourceNodeId="source", jsonPointer="/approved", operator=ConditionOperator.BOOLEAN, cases={"true": "to-true", "false": "to-false"}),
                branchEdgeIds=["to-true", "to-false"], joinNodeId="join",
            ),
            StepNode(nodeId="true"),
            StepNode(nodeId="false"),
            ControlNode(
                nodeId="join",
                controlType=ControlType.CONSENSUS,
                consensusSpec=ConsensusSpec(
                    participantStepIds=["true", "false"],
                    quorum=1,
                    strategy="auditor",
                ),
            ), ],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="source", plannedAgentId="agent"), AgentBindingSpec(stepId="true", plannedAgentId="agent"), AgentBindingSpec(stepId="false", plannedAgentId="agent"),)),
        edges=[
            ACGEdge(sourceId="source", targetId="if", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(edgeId="to-true", sourceId="if", targetId="true", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(edgeId="to-false", sourceId="if", targetId="false", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="true", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="false", targetId="join", edgeType=EdgeType.DEPENDENCY), ],
    )
    graph = ACGGraphCompiler().compile(blueprint)
    observed = []

    async def execute(step_id, _state):
        observed.append(step_id)
        return {"outputSummary": step_id, "routeValue": {"approved": True} if step_id == "source" else {}}

    result = asyncio.run(graph.run(ACGExecutionState(runId="run-1"), execute))

    assert observed == ["source", "true"]
    assert result.skipped_step_ids == ["false"]


def test_review_step_interrupts_after_its_result_is_committed() -> None:
    graph = ACGStateGraph().add_step("review", review_required=True).compile()
    state = ACGExecutionState(runId="run-1")

    async def execute(_step_id, _state):
        return {"outputSummary": "waiting", "traceRef": "trace:review"}

    with pytest.raises(ExecutionInterrupt) as captured:
        asyncio.run(graph.run(state, execute))

    assert state.completed_step_ids == ["review"]
    assert state.review_payload == {"stepId": "review", "traceRef": "trace:review"}
    assert captured.value.payload == state.review_payload


def test_resume_command_continues_from_interrupt_without_repeating_review_step() -> None:
    graph = (
        ACGStateGraph()
        .add_step("review", review_required=True)
        .add_step("deliver")
        .add_edge("review", "deliver")
        .compile()
    )
    state = ACGExecutionState(runId="run-1")
    observed: list[str] = []

    async def execute(step_id, _state):
        observed.append(step_id)
        return {"outputSummary": step_id}

    with pytest.raises(ExecutionInterrupt):
        asyncio.run(graph.run(state, execute))
    result = asyncio.run(
        graph.resume(
            state,
            ExecutionResumeCommand(runId="run-1", payload={"decision": "approved"}),
            execute,
        )
    )

    assert observed == ["review", "deliver"]
    assert result.review_payload is None


def test_resume_command_isolated_to_its_run() -> None:
    graph = ACGStateGraph().add_step("review", review_required=True).compile()
    state = ACGExecutionState(runId="run-1")

    with pytest.raises(ValueError, match="runId"):
        asyncio.run(graph.resume(state, ExecutionResumeCommand(runId="run-2"), lambda *_: None))


def test_auditor_consensus_accepts_committed_participants_without_vote_fields() -> None:
    """Auditor consensus is based on committed participants, so an empty vote set is not a tie."""

    blueprint = ACGBlueprint(
        graphId="acg-auditor-consensus",
        nodes=[
            StepNode(nodeId="left"),
            StepNode(nodeId="right"),
            ControlNode(
                nodeId="join",
                controlType=ControlType.CONSENSUS,
                consensusSpec=ConsensusSpec(
                    participantStepIds=["left", "right"],
                    quorum=2,
                    strategy="auditor",
                ),
            ),
            StepNode(nodeId="deliver"), ],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="left", plannedAgentId="agent"), AgentBindingSpec(stepId="right", plannedAgentId="agent"), AgentBindingSpec(stepId="deliver", plannedAgentId="agent"),)),
        edges=[
            ACGEdge(sourceId="left", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="right", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="join", targetId="deliver", edgeType=EdgeType.DEPENDENCY), ],
    )
    graph = ACGGraphCompiler().compile(blueprint)

    async def execute(step_id, _state):
        return {"outputSummary": step_id, "routeValue": {}}

    state = asyncio.run(graph.run(ACGExecutionState(runId="run-auditor"), execute))

    assert state.review_payload is None
    assert state.consensus_results["join"] == {
        "votes": 0,
        "approvals": 0,
        "committedParticipants": 2,
        "quorum": 2,
        "accepted": True,
        "strategy": "auditor",
    }
    assert state.completed_step_ids == ["left", "right", "join", "deliver"]


def test_majority_tie_resumes_once_after_control_review_approval() -> None:
    blueprint = ACGBlueprint(
        graphId="acg-majority-review",
        nodes=[
            StepNode(nodeId="left"),
            StepNode(nodeId="right"),
            ControlNode(
                nodeId="join",
                controlType=ControlType.CONSENSUS,
                consensusSpec=ConsensusSpec(
                    participantStepIds=["left", "right"],
                    quorum=2,
                    strategy="majority",
                ),
            ),
            StepNode(nodeId="deliver"), ],
        resourcePlan=ACGResourcePlan(bindings=(AgentBindingSpec(stepId="left", plannedAgentId="agent"), AgentBindingSpec(stepId="right", plannedAgentId="agent"), AgentBindingSpec(stepId="deliver", plannedAgentId="agent"),)),
        edges=[
            ACGEdge(sourceId="left", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="right", targetId="join", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="join", targetId="deliver", edgeType=EdgeType.DEPENDENCY), ],
    )
    graph = ACGGraphCompiler().compile(blueprint)
    state = ACGExecutionState(runId="run-majority")

    async def execute(step_id, _state):
        votes = {"left": True, "right": False}
        return {
            "outputSummary": step_id,
            "routeValue": ({"vote": votes[step_id]} if step_id in votes else {}),
        }

    with pytest.raises(ExecutionInterrupt) as captured:
        asyncio.run(graph.run(state, execute))

    assert captured.value.payload["subjectType"] == "control"
    assert captured.value.payload["subjectId"] == "join"
    resumed = asyncio.run(graph.resume(
        state,
        ExecutionResumeCommand(runId="run-majority", payload={"decision": "approved"}),
        execute,
    ))
    assert resumed.review_payload is None
    assert resumed.consensus_results["join"]["resolvedByReview"] is True
    assert resumed.completed_step_ids == ["left", "right", "join", "deliver"]


def test_execution_stream_is_projected_to_existing_trace_events() -> None:
    run = RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg")

    event = TraceStore().append_execution_event(
        run,
        {"type": "node_completed", "stepId": "one", "outputSummary": "stored by reference"},
    )

    assert event.event_type.value == "step_succeeded"
    assert event.step_id == "one"
    assert event.payload == {"outputSummary": "stored by reference"}


class _RecordingAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentProfile(agentName="agent", domain="general"))
        self.context = None

    async def run(self, context):
        self.context = context
        return AgentOutput(output={"answer": "accepted", "ignored": "not stored"}, summary="accepted")


class _CountingAgent(_RecordingAgent):
    """记录实际 Agent 调用次数，用于验证节点提交恢复不会重复执行。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.commit_ids: list[str | None] = []

    async def run(self, context):
        self.calls += 1
        self.commit_ids.append(context.commit_id)
        return await super().run(context)


class _EvidenceAgent(BaseAgent):
    def __init__(self, evidence_ref: str) -> None:
        super().__init__(AgentProfile(agentName="agent", domain="general"))
        self.evidence_ref = evidence_ref

    async def run(self, context):
        source = {"citationId": "citation-1", "provider": "task-input"}
        return AgentOutput(
            output={"evidence_refs": [self.evidence_ref], "sources": [source]},
            sources=[source],
            evidenceRefs=[self.evidence_ref],
            summary="evidence",
        )


def test_node_runner_uses_contract_context_memory_and_returns_references_only() -> None:
    agent = _RecordingAgent()
    memory = MemoryService()
    memory.remember(MemoryRecord(memoryId="memory-1", memoryType=MemoryType.EPISODIC, content={"fact": "known"}, scope="run-1"))
    value_store = InMemoryExecutionValueStore()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(stepId="one", name="one", agentName="agent", input={"fields": ["source"]}, outputSpec={"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}})},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        entropy_budget=100,
        value_store=value_store,
    )
    state = ACGExecutionState(runId="run-1", outputSummaries={"upstream": "source summary"})

    result = asyncio.run(runner("one", state))

    assert agent.context.context_pack.data == {}
    assert result["outputSummary"] == "accepted"
    assert result["outputRef"].startswith("output:run-1:one:")
    assert value_store.get_output(run_id="run-1", output_ref=result["outputRef"]) == {"answer": "accepted"}
    assert result["memoryRef"] == "memory:run-1:one"
    assert result["routeValue"] == {"answer": "accepted"}
    assert "output" not in result


def test_node_runner_accepts_only_manifest_authorized_runtime_evidence() -> None:
    def runner_for(evidence_ref: str) -> ACGNodeRunner:
        step = WorkflowStep(
            stepId="retrieve",
            name="retrieve",
            agentName="agent",
            outputSpec={
                "type": "object",
                "properties": {
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "sources": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["evidence_refs"],
            },
        )
        return ACGNodeRunner(
            task=RuntimeMissionRecord(missionId="mission-1", title="test"),
            run=RuntimeRunRecord(missionId="mission-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
            workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
            steps={"retrieve": step},
            agents={"retrieve": _EvidenceAgent(evidence_ref)},
            communicator=CommunicatorService(run_id="run-1", mission_id="mission-1"),
            memory=MemoryService(),
            evidence_manifest=EvidenceManifest(rules=(EvidenceRule(
                stepId="retrieve",
                evidenceNodeId="evidence::retrieve",
                access="produce",
                evidenceType="retrieved",
                source="task-input",
            ),)),
        )

    accepted = asyncio.run(runner_for("citation-1")(
        "retrieve", ACGExecutionState(runId="run-1")
    ))
    assert accepted["evidenceRefs"] == ["citation-1"]

    with pytest.raises(ValueError, match="unauthorized evidence references"):
        asyncio.run(runner_for("fabricated-citation")(
            "retrieve", ACGExecutionState(runId="run-1")
        ))


def test_node_runner_reuses_completed_commit_without_reinvoking_agent() -> None:
    """同一运行步骤在提交后被重复调度时，必须复用引用而不能再次调用 Agent。"""
    agent = _CountingAgent()
    runner = ACGNodeRunner.minimal(agent=agent)
    state = ACGExecutionState(runId="run-1")

    first = asyncio.run(runner("one", state))
    second = asyncio.run(runner("one", state))

    assert agent.calls == 1
    assert first["commitId"] == "commit:run-1:one:0"
    assert agent.commit_ids == [first["commitId"]]
    assert second["commitId"] == first["commitId"]
    assert second["outputRef"] == first["outputRef"]
    assert second["contextRef"] == first["contextRef"]
    assert second["routeValue"] == first["routeValue"]
    committed = runner.value_store.get_node_commit(
        run_id="run-1",
        commit_id=first["commitId"],
    )
    assert committed is not None
    assert "routeValue" not in committed


def test_node_runner_does_not_treat_entropy_budget_as_a_token_limit() -> None:
    agent = _RecordingAgent()
    runner = ACGNodeRunner.minimal(agent=agent, entropy_budget=0)

    asyncio.run(runner("one", ACGExecutionState(runId="run-1", outputSummaries={"upstream": "summary"})))

    assert agent.context is not None


def test_node_runner_assembles_declared_upstream_slots_from_output_references() -> None:
    """节点运行器必须从 State 的 outputRef 读取白名单 slot，不能读取摘要或全量正文。"""
    agent = _RecordingAgent()
    value_store = InMemoryExecutionValueStore()
    source_ref = value_store.put_output(
        run_id="run-1",
        step_id="extract",
        payload={"title": "public", "secret": "must-not-pass"},
    )
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"summarize": WorkflowStep(stepId="summarize", name="summarize", agentName="agent", input={"from": {"extract": ["title"]}}, outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}})},
        agents={"summarize": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=MemoryService(),
        value_store=value_store,
    )
    state = ACGExecutionState(
        runId="run-1",
        outputSummaries={"extract": "summary only"},
        outputRefs={"extract": source_ref},
    )

    asyncio.run(runner("summarize", state))

    assert agent.context.context_pack.data == {"title": "public"}


def test_node_runner_recalls_and_persists_run_scoped_controlled_memory() -> None:
    """节点仅获得当前 run 的记忆，并将白名单输出写回情节记忆。"""
    agent = _RecordingAgent()
    memory = MemoryService()
    memory.remember(MemoryRecord(memoryId="memory:run-1:known", memoryType=MemoryType.EPISODIC, content={"fact": "run-one"}, scope="run-1"))
    memory.remember(MemoryRecord(memoryId="memory:run-2:hidden", memoryType=MemoryType.EPISODIC, content={"fact": "run-two"}, scope="run-2"))
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(stepId="one", name="one", agentName="agent", outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}})},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=InMemoryExecutionValueStore(),
    )

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert [record.memory_id for record in agent.context.memory] == ["memory:run-1:known"]
    assert result["memoryRef"] == "memory:run-1:one"
    persisted = memory.recall_for_step(run_id="run-1", step_id="one", query="accepted")
    event = next(record for record in persisted if record.memory_id == "memory:run-1:one")
    assert event.content["summary"] == "accepted"
    assert event.content["decision"] == "allow"
    assert event.content["metrics"]["fieldCount"] == 1
    assert "answer" not in event.content
    assert "ignored" not in str(event.content)


def test_node_runner_obeys_step_memory_policy_and_returns_safe_access_metadata() -> None:
    """步骤可禁止读写记忆，执行结果只能暴露策略统计而不能含记忆正文。"""
    agent = _RecordingAgent()
    memory = MemoryService()
    memory.remember(
        MemoryRecord(
            memoryId="memory:run-1:known",
            memoryType=MemoryType.EPISODIC,
            content={"fact": "must-not-inject"},
            scope="run-1",
        )
    )
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(
            stepId="one",
            name="one",
            agentName="agent",
            input={"memoryPolicy": {"read": False, "write": False, "policyId": "no-memory"}},
            outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}},
        )},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=InMemoryExecutionValueStore(),
    )

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert agent.context.memory == []
    assert result["memoryRef"] == "memory:none"
    assert result["memoryAccess"] == {
        "policyId": "no-memory",
            "read": False,
            "readCount": 0,
            "retrievalMode": "disabled",
            "retrievalFallbackReason": None,
            "hitRefs": [],
        "write": False,
        "written": False,
        "readTypes": [],
        "writeType": None,
        "limit": 10,
        "tokenBudget": None,
        "tokensUsed": 0,
        "requireAudit": False,
    }
    assert "must-not-inject" not in str(result["memoryAccess"])


def test_node_runner_separates_memory_read_types_from_write_type() -> None:
    """读取范围与输出写入类别必须独立执行，避免一个白名单同时承担两种语义。"""
    agent = _RecordingAgent()
    memory = MemoryService()
    memory.remember(
        MemoryRecord(
            memoryId="memory:run-1:semantic",
            memoryType=MemoryType.SEMANTIC,
            content={"fact": "visible"},
            scope="run-1",
        )
    )
    memory.remember(
        MemoryRecord(
            memoryId="memory:run-1:episodic",
            memoryType=MemoryType.EPISODIC,
            content={"fact": "hidden"},
            scope="run-1",
        )
    )
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(
            stepId="one",
            name="one",
            agentName="agent",
            input={"memoryPolicy": {
                "policyId": "separate-types",
                "read": True,
                "readTypes": ["semantic"],
                "write": True,
                "writeType": "procedural",
            }},
            outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}},
        )},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=InMemoryExecutionValueStore(),
    )

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert [record.memory_id for record in agent.context.memory] == ["memory:run-1:semantic"]
    assert result["memoryAccess"]["readTypes"] == ["semantic"]
    assert result["memoryAccess"]["writeType"] == "procedural"
    persisted = memory.recall_for_step(
        run_id="run-1",
        step_id="later",
        query="accepted",
        memory_types=[MemoryType.PROCEDURAL],
    )
    assert [record.memory_id for record in persisted] == ["memory:run-1:one"]


def test_execution_graph_whitelists_memory_access_trace_fields() -> None:
    """图层必须再次裁剪记忆审计载荷，不能信任外部节点运行器传入的扩展字段。"""
    graph = ACGExecutionGraph(nodes=("one",))
    observed: list[dict[str, object]] = []

    async def execute(_step_id, _state):
        return {
            "outputSummary": "done",
            "memoryAccess": {
                "policyId": "safe",
                "read": True,
                "readCount": 1,
                "memoryBody": {"fact": "must-not-trace"},
            },
        }

    async def collect() -> None:
        async for event in graph.astream(ACGExecutionState(runId="run-1"), execute):
            if event["type"] == "node_completed":
                observed.append(event["memoryAccess"])

    asyncio.run(collect())

    assert observed == [{"policyId": "safe", "read": True, "readCount": 1}]


def test_node_runner_rejects_explicit_empty_memory_type_whitelist() -> None:
    """显式空白名单不能被解释为允许全部记忆类型，避免策略配置放大权限。"""
    agent = _RecordingAgent()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(
            stepId="one",
            name="one",
            agentName="agent",
            input={"memoryPolicy": {"allowedTypes": []}},
        )},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=MemoryService(),
        value_store=InMemoryExecutionValueStore(),
    )

    with pytest.raises(ValueError, match="allowedTypes must not be empty"):
        asyncio.run(runner("one", ACGExecutionState(runId="run-1")))


class _HighRiskAgent(_RecordingAgent):
    """模拟声明高风险的节点结果，验证审计决定驱动图中断。"""

    async def run(self, context):
        self.context = context
        return AgentOutput(output={"answer": "needs-review"}, summary="risk", riskLevel="high")


class _CriticalRiskAgent(_RecordingAgent):
    """模拟必须拒绝的节点结果。"""

    async def run(self, context):
        self.context = context
        return AgentOutput(output={"answer": "blocked"}, summary="critical", riskLevel="critical")


def test_node_runner_projects_high_risk_output_to_review_interrupt() -> None:
    """节点审计只返回 review 事实，由图消费该事实触发既有审核中断。"""
    agent = _HighRiskAgent()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(stepId="one", name="one", agentName="agent", outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}})},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=MemoryService(),
        value_store=InMemoryExecutionValueStore(),
    )
    graph = ACGExecutionGraph(nodes=("one",))

    with pytest.raises(ExecutionInterrupt):
        asyncio.run(graph.run(ACGExecutionState(runId="run-1"), runner))


def test_review_decision_defers_memory_write_until_human_approval() -> None:
    """审计要求人工复核时，只能保存受控 outputRef 和待写意图，不能先写正式记忆。"""
    decision_store = InMemoryDecisionStore()
    memory = MemoryService()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(
            stepId="one",
            name="one",
            agentName="agent",
            input={"memoryPolicy": {
                "read": False,
                "write": True,
                "writeType": "episodic",
                "requireAudit": True,
            }},
            outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}},
        )},
        agents={"one": _HighRiskAgent()},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=InMemoryExecutionValueStore(),
        decision_store=decision_store,
    )

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert result["auditOutcome"] == "review"
    assert "memoryRef" not in result
    assert result["memoryAccess"]["written"] is False
    assert result["pendingMemory"]["outputRef"] == result["outputRef"]
    assert result["pendingMemory"]["policyId"] == "default"
    assert result["pendingMemory"]["writeType"] == "episodic"
    assert result["pendingMemory"]["auditDecisionRef"] == result["auditDecisionRef"]
    assert result["pendingMemory"]["memoryEvent"]["decision"] == "review"
    assert "needs-review" not in str(result["pendingMemory"])
    assert memory.search(MemoryQuery(query="one", scope="run-1")) == []
    assert decision_store.assert_decision(
        run_id="run-1",
        step_id="one",
        decision_ref=result["auditDecisionRef"],
        outcomes={"review"},
    ).outcome == "review"


def test_blueprint_review_gate_defers_memory_when_output_audit_allows() -> None:
    """A declared review gate must defer memory even for an audit-allowed output."""
    memory = MemoryService()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(
            stepId="one",
            name="one",
            agentName="agent",
            reviewRequired=True,
            input={"memoryPolicy": {
                "read": False,
                "write": True,
                "writeType": "episodic",
                "requireAudit": True,
            }},
            outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}},
        )},
        agents={"one": _RecordingAgent()},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=InMemoryExecutionValueStore(),
    )

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert result["auditOutcome"] == "allow"
    assert result["reviewRequired"] is True
    assert "memoryRef" not in result
    assert result["pendingMemory"]["outputRef"] == result["outputRef"]
    assert memory.search(MemoryQuery(query="one", scope="run-1")) == []


def test_deny_decision_stops_graph_without_committing_node_result() -> None:
    """严重风险决定必须终止图，不能写入 State 或调度其下游节点。"""
    graph = ACGExecutionGraph(nodes=("danger", "deliver"), edges=(("danger", "deliver"),))
    state = ACGExecutionState(runId="run-1")
    observed: list[str] = []

    async def execute(step_id, _state):
        observed.append(step_id)
        return {
            "outputSummary": "must-not-commit",
            "outputRef": "output:run-1:danger:blocked",
            "auditOutcome": "deny",
            "auditDecisionRef": "decision:deny",
        }

    with pytest.raises(RuntimeError, match="denied"):
        asyncio.run(graph.run(state, execute))

    assert observed == ["danger"]
    assert state.completed_step_ids == []
    assert state.output_refs == {}


def test_deny_result_is_not_persisted_to_value_store_or_memory() -> None:
    """严重风险在审计决定后不得留下可被后续步骤读取的输出或记忆。"""
    agent = _CriticalRiskAgent()
    value_store = InMemoryExecutionValueStore()
    memory = MemoryService()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(stepId="one", name="one", agentName="agent", outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}})},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=value_store,
    )

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert result["auditOutcome"] == "deny"
    assert "outputRef" not in result
    assert "contextRef" not in result
    assert "memoryRef" not in result
    assert memory.search(MemoryQuery(query="one", scope="run-1")) == []


def test_node_runner_requires_auditable_decision_before_required_memory_write() -> None:
    """策略要求审计时，审计器未给出有效决定不得写入输出、记忆或血缘。"""
    class MissingAudit:
        def assess_node(self, **_kwargs):
            return None

    agent = _RecordingAgent()
    value_store = InMemoryExecutionValueStore()
    memory = MemoryService()
    runner = ACGNodeRunner(
        task=RuntimeMissionRecord(missionId="task-1", title="test"),
        run=RuntimeRunRecord(missionId="task-1", workflowId="workflow-1", domain="general", runtimeEngine="acg"),
        workflow=WorkflowDefinition(workflowId="workflow-1", name="workflow", domain="general", intent="general", runtimeEngine="acg"),
        steps={"one": WorkflowStep(
            stepId="one",
            name="one",
            agentName="agent",
            input={"memoryPolicy": {
                "read": False,
                "write": True,
                "writeType": "episodic",
                "requireAudit": True,
            }},
            outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}},
        )},
        agents={"one": agent},
        communicator=CommunicatorService(run_id="run-1", mission_id="task-1"),
        memory=memory,
        value_store=value_store,
        execution_audit=MissingAudit(),
    )

    with pytest.raises(ValueError, match="audit decision is required"):
        asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert memory.search(MemoryQuery(query="one", scope="run-1")) == []
    assert value_store.get_node_commit(run_id="run-1", commit_id="commit:run-1:one:0") == {
        "commitId": "commit:run-1:one:0",
        "stage": "prepared",
    }


def test_node_runner_injects_scoped_tool_runtime_and_safe_model_metadata() -> None:
    """节点只能拿到受限工具，返回结果只投影安全的模型调用元数据。"""
    class ToolAgent(_RecordingAgent):
        async def run(self, context):
            self.context = context
            return AgentOutput(
                output={"answer": "safe"},
                modelInvocations=[{"provider": "local", "model": "test", "usage": {"tokens": 3}}],
            )

    class ToolRuntime:
        def scoped(self, _allowed):
            return self

        async def run(self, _text, **_kwargs):
            return None

        async def execute(self, _name, _arguments, **_kwargs):
            return None

    agent = ToolAgent()
    runner = ACGNodeRunner.minimal(agent=agent)
    runner.tool_runtime = ToolRuntime()

    result = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert agent.context.tool_runtime is not None
    assert result["modelInvocations"] == [{"provider": "local", "model": "test", "usage": {"tokens": 3}}]


def test_node_runner_returns_incremental_safe_provenance_events() -> None:
    """同一提交重放应复用原血缘事件，交由 Runtime 保证不会重复写 Trace。"""
    agent = _RecordingAgent()
    runner = ACGNodeRunner.minimal(agent=agent)

    first = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))
    second = asyncio.run(runner("one", ACGExecutionState(runId="run-1")))

    assert first["provenanceEvents"]
    assert second["provenanceEvents"]
    first_ids = {event["payload"]["eventId"] for event in first["provenanceEvents"]}
    second_ids = {event["payload"]["eventId"] for event in second["provenanceEvents"]}
    assert first_ids == second_ids
    assert "accepted" not in str(first["provenanceEvents"])


def test_selected_branch_can_join_without_running_unselected_descendants():
    graph = ACGExecutionGraph(nodes=("selected", "unselected", "join", "dormant", "root"),
        edges=(("selected", "join"), ("unselected", "join"), ("unselected", "dormant")))
    state = ACGExecutionState(runId="branch-join", completedStepIds=["selected"], skippedStepIds=["unselected"])
    # R1 incorrectly treated this ordinary AND node as an implicit Join.
    # A skipped required predecessor must never authorize it.
    assert graph.ready_steps(state) == ("root",)
    # An unfinished selected predecessor continues to block the join.
    state.completed_step_ids = []
    assert graph.ready_steps(state) == ("selected", "root")
    async def execute(step_id, _state):
        assert step_id != "join"
        return {}
    result = asyncio.run(graph.run(state, execute))
    assert set(result.skipped_step_ids) == {"unselected", "join", "dormant"}


def _compiled_branch_graph(*, shared=False):
    pairs = [("root", "if"), ("if", "selected"), ("if", "skipped"),
             ("selected", "join"), ("skipped", "dormant"), ("dormant", "join"), ("join", "after")]
    if shared:
        pairs.append(("root", "dormant"))
    edges = [ACGEdge(edgeId=f"{a}:{b}", sourceId=a, targetId=b, edgeType=EdgeType.DEPENDENCY) for a,b in pairs]
    steps = ("root", "selected", "skipped", "dormant", "after")
    blueprint = ACGBlueprint(graphId="r2-branch", nodes=[
        *(StepNode(nodeId=name) for name in steps),
        ControlNode(nodeId="if", controlType=ControlType.IF,
            branchEdgeIds=["if:selected", "if:skipped"], joinNodeId="join",
            conditionSpec=ConditionSpec(sourceNodeId="root", jsonPointer="/choice",
                operator=ConditionOperator.BOOLEAN, cases={"true": "if:selected", "false": "if:skipped"})),
        ControlNode(nodeId="join", controlType=ControlType.CONSENSUS,
            consensusSpec=ConsensusSpec(participantStepIds=["selected", "dormant"], quorum=1, strategy="auditor")),
    ], edges=edges, resourcePlan=ACGResourcePlan(bindings=tuple(
        AgentBindingSpec(stepId=name, plannedAgentId="agent") for name in steps)))
    return ACGGraphCompiler().compile(blueprint)


@pytest.mark.parametrize("shared", [False, True])
def test_compiled_branch_skips_descendants_and_runs_declared_join(shared):
    graph = _compiled_branch_graph(shared=shared)
    calls = []
    async def execute(step_id, state):
        calls.append(step_id)
        if step_id == "after":
            assert "selected" in state.completed_step_ids
            assert "join" in state.completed_step_ids
        return {"routeValue": {"choice": True}}
    state = asyncio.run(graph.run(ACGExecutionState(runId="r2"), execute))
    assert calls == ["root", "selected", "after"]
    assert set(state.skipped_step_ids) == {"skipped", "dormant"}
    assert set(state.completed_step_ids) | set(state.skipped_step_ids) == set(graph.nodes)


def _branch_graph(pairs, routes):
    """Exercise the runtime DAG with explicit local IF/Join declarations."""
    nodes = tuple(dict.fromkeys(n for pair in pairs for n in pair))
    joins = {join for _, _, join in routes.values()}
    specs = {n: ACGNodeSpec(node_id=n, kind="control" if n in joins else "step") for n in nodes}
    for control, (source, cases, join) in routes.items():
        specs[control] = ACGNodeSpec(node_id=control, kind="control", control_type="if",
            condition=ACGConditionalRoute(source_step_id=source, json_pointer="/choice", operator="IN",
                targets_by_case=cases, join_node_id=join))
    return ACGExecutionGraph(nodes=nodes, edges=tuple(pairs), node_specs=specs)


@pytest.mark.parametrize("outer,inner,expected", [
    ("left", "a", ["root", "left", "a", "tail", "after"]),
    ("left", "b", ["root", "left", "b", "tail", "after"]),
    ("right", "a", ["root", "right", "after"]),
])
def test_nested_branch_regions_finish_without_executing_alternatives(outer, inner, expected):
    # Nested runtime DAGs must be safe even though the Blueprint validator
    # currently rejects nested IF/LOOP within a declared IF region.
    graph = _branch_graph([
        ("root", "outer"), ("outer", "left"), ("outer", "right"),
        ("left", "inner"), ("inner", "a"), ("inner", "b"),
        ("a", "inner_join"), ("b", "inner_join"), ("inner_join", "tail"),
        ("tail", "outer_join"), ("right", "outer_join"), ("outer_join", "after"),
    ], {"outer": ("root", {"left": "left", "right": "right"}, "outer_join"),
        "inner": ("left", {"a": "a", "b": "b"}, "inner_join")})
    calls = []
    async def execute(step_id, _state):
        calls.append(step_id)
        return {"routeValue": {"choice": outer if step_id == "root" else inner}}
    state = asyncio.run(graph.run(ACGExecutionState(runId="nested"), execute))
    assert calls == expected
    assert set(state.completed_step_ids) | set(state.skipped_step_ids) == set(graph.nodes)
    assert not (set(state.completed_step_ids) & set(state.skipped_step_ids))


@pytest.mark.parametrize("chosen", ["a", "b", "c"])
def test_multiple_alternatives_join_only_after_selected_path(chosen):
    pairs = [("root", "if"), ("join", "after")]
    for branch in ("a", "b", "c"):
        pairs.extend([("if", branch), (branch, branch + "_tail"), (branch + "_tail", "join")])
    graph = _branch_graph(pairs, {"if": ("root", {n:n for n in ("a", "b", "c")}, "join")})
    calls = []
    async def execute(step_id, _state):
        calls.append(step_id)
        return {"routeValue": {"choice": chosen}}
    state = asyncio.run(graph.run(ACGExecutionState(runId="three"), execute))
    assert calls == ["root", chosen, chosen + "_tail", "after"]
    assert set(state.skipped_step_ids) == {n for b in ("a", "b", "c") if b != chosen for n in (b, b+"_tail")}
    assert len(state.completed_step_ids) + len(state.skipped_step_ids) == len(graph.nodes)


def test_declared_join_waits_for_selected_branch_and_resumes_checkpoint():
    graph = _compiled_branch_graph()
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        # A persisted branch choice is sufficient; route values need not survive.
        state = ACGExecutionState(runId="resume", completedStepIds=["root", "if"], skippedStepIds=["skipped"])
        calls = []
        async def execute(step_id, _state):
            calls.append(step_id)
            if step_id == "selected":
                entered.set()
                await release.wait()
            return {}
        task = asyncio.create_task(graph.run(state, execute))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert "join" not in state.completed_step_ids
            assert calls == ["selected"]
        finally:
            release.set()
            await task
        assert calls == ["selected", "after"]
        assert set(state.skipped_step_ids) == {"skipped", "dormant"}
        assert set(state.completed_step_ids) | set(state.skipped_step_ids) == set(graph.nodes)
    asyncio.run(scenario())


def test_all_skipped_branches_skip_join_even_with_completed_shared_predecessor():
    graph = _branch_graph([("root", "if"), ("if", "a"), ("if", "b"),
        ("a", "join"), ("b", "join"), ("root", "join"), ("join", "after")],
        {"if": ("root", {"a": "a", "b": "b"}, "join")})
    async def execute(*_):
        pytest.fail("an all-skipped region cannot execute its Join successor")
    state = asyncio.run(graph.run(ACGExecutionState(runId="all-skipped",
        completedStepIds=["root", "if"], skippedStepIds=["a", "b"]), execute))
    assert set(state.skipped_step_ids) == {"a", "b", "join", "after"}
    assert set(state.completed_step_ids) | set(state.skipped_step_ids) == set(graph.nodes)


def test_unknown_cancelled_sibling_is_preserved_in_superstep_failure():
    from adapters.resource_execution import ResourceExecutionError
    graph = ACGExecutionGraph(nodes=("known", "unknown"))
    async def scenario():
        started = asyncio.Event()
        async def execute(step_id, _state):
            if step_id == "known":
                await started.wait()
                raise ResourceExecutionError("request rejected")
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                raise ResourceExecutionError("reply lost", outcome_unknown=True)
        with pytest.raises(ACGSuperstepError) as caught:
            await graph.run(ACGExecutionState(runId="parallel"), execute)
        assert caught.value.cause.outcome_unknown is False
        assert caught.value.outcome_unknown is True
        assert len(caught.value.causes) == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("choice", ["work", "direct"])
def test_direct_join_alternative_never_skips_the_common_boundary(choice):
    graph = _branch_graph([("root", "if"), ("if", "work"), ("if", "join"),
        ("work", "join"), ("join", "after")],
        {"if": ("root", {"work": "work", "direct": "join"}, "join")})
    calls = []
    async def execute(step_id, _state):
        calls.append(step_id)
        return {"routeValue": {"choice": choice}}
    state = asyncio.run(graph.run(ACGExecutionState(runId="direct"), execute))
    assert calls == (["root", "work", "after"] if choice == "work" else ["root", "after"])
    assert "join" in state.completed_step_ids
    assert state.skipped_step_ids == ([] if choice == "work" else ["work"])


def test_shared_join_requires_a_completed_input_from_each_conditional_region():
    graph = _branch_graph([("root", "if1"), ("root", "if2"),
        ("if1", "a"), ("if1", "b"), ("if2", "c"), ("if2", "d"),
        ("a", "join"), ("b", "join"), ("c", "join"), ("d", "join"), ("join", "after")],
        {"if1": ("root", {"yes": "a", "no": "b"}, "join"),
         "if2": ("root", {"yes": "c", "no": "d"}, "join")})
    async def scenario():
        calls = []
        async def execute(step_id, state):
            if step_id == "after":
                assert {"a", "c", "join"} <= set(state.completed_step_ids)
            calls.append(step_id)
            return {"routeValue": {"choice": "yes"}}
        state = await graph.run(ACGExecutionState(runId="shared-join"), execute)
        assert calls == ["root", "a", "c", "after"]
        assert set(state.skipped_step_ids) == {"b", "d"}
        calls.clear()
        restored = ACGExecutionState(runId="missing-region", completedStepIds=["root", "if1", "if2", "a"],
            skippedStepIds=["b", "c", "d"])
        await graph.run(restored, execute)
        assert calls == []
        assert {"join", "after"} <= set(restored.skipped_step_ids)
    asyncio.run(scenario())

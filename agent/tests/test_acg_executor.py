"""ACG 执行器（就绪集并行调度）端到端测试。

验证 Core Native 自研 ACG 引擎：
- 线性工作流经 runtime_engine=acg 执行，行为与线性一致；
- 并行分支：菱形 ACG 中两个无依赖 step 并发执行；
- 人审中断 + approve 续跑；
- 节点级统一 Trace（step_started/agent_called/step_succeeded）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, EdgeType, StepNode
from agentos.core.models.types import (
    ReviewDecision,
    ReviewDecisionType,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.runtime import WorkflowRuntime
from agentos.core.recovery import RuntimeGraphError, RuntimeGraphPatch
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore


class _Agent(BaseAgent):
    def __init__(self, name, calls):
        super().__init__(AgentProfile(agentName=name, domain="test", capabilities=[name]))
        self.calls = calls

    async def run(self, context):
        self.calls.append(context.step.step_id)
        return AgentOutput(
            output={"agent": self.profile.agent_name, "step": context.step.step_id},
            summary=f"{self.profile.agent_name} done",
        )


def _runtime(steps, agent_names, *, engine="acg"):
    registry = AgentRegistry()
    calls: list[str] = []
    for name in agent_names:
        registry.register(_Agent(name, calls))
    wf_registry = WorkflowRegistry()
    wf_registry.register(
        WorkflowDefinition(
            workflowId="acg_wf",
            name="ACG WF",
            domain="test",
            intent="demo",
            runtimeEngine=engine,
            steps=steps,
        )
    )
    runtime = WorkflowRuntime(agent_registry=registry, workflow_registry=wf_registry)
    return runtime, calls


def test_acg_engine_runs_linear_workflow():
    async def _run():
        steps = [
            WorkflowStepDefinition(stepId="a", name="A", agentName="a", nextStepId="b"),
            WorkflowStepDefinition(stepId="b", name="B", agentName="b", nextStepId="c"),
            WorkflowStepDefinition(stepId="c", name="C", agentName="c"),
        ]
        runtime, calls = _runtime(steps, ["a", "b", "c"])
        task = runtime.create_task(title="t", domain="test", intent="demo", input={})
        run = await runtime.start(task.task_id, workflow_id="acg_wf")

        assert run.status == WorkflowStatus.COMPLETED
        assert calls == ["a", "b", "c"]
        assert run.runtime_engine == "acg"
        assert run.acg_blueprint is not None
        assert set(run.completed_step_ids) == {"a", "b", "c"}
        assert run.runtime_graph.graph_version == 1
        assert all(
            run.runtime_graph.get_node(node_id).status == StepStatus.COMPLETED
            for node_id in ("a", "b", "c")
        )
        assert run.runtime_graph.get_node("c").output == run.get_step("c").output

    asyncio.run(_run())


def test_acg_material_input_starts_a_tamper_evident_provenance_chain():
    async def _run():
        runtime, _calls = _runtime(
            [WorkflowStepDefinition(stepId="parse", name="Parse", agentName="parse")],
            ["parse"],
        )
        material_id = "mat_0123456789abcdef0123456789abcdef"
        task = runtime.create_task(
            title="material",
            domain="test",
            intent="demo",
            input={
                "contractText": "合同正文",
                "sourceMaterials": [{"materialId": material_id, "uri": f"material://{material_id}"}],
            },
        )
        run = await runtime.start(task.task_id, workflow_id="acg_wf")

        productions = run.provenance["productions"]
        consumptions = run.provenance["consumptions"]
        source = next(item for item in productions if item["producerStepId"] == "__task_input__")
        assert source["evidenceRefs"] == [f"material://{material_id}"]
        assert source["eventHash"]
        initial_consumption = next(item for item in consumptions if item["consumerStepId"] == "parse")
        assert initial_consumption["producerStepIds"] == ["__task_input__"]
        assert initial_consumption["producerEventIds"] == [source["eventId"]]

    asyncio.run(_run())


def test_acg_engine_parallel_branch_executes_both():
    """注入菱形 ACG：a -> {b, c} -> d，验证 b、c 并行执行、d 在二者后。"""

    async def _run():
        steps = [
            WorkflowStepDefinition(stepId="a", name="A", agentName="a", nextStepId="d"),
            WorkflowStepDefinition(stepId="b", name="B", agentName="b"),
            WorkflowStepDefinition(stepId="c", name="C", agentName="c"),
            WorkflowStepDefinition(stepId="d", name="D", agentName="d"),
        ]
        runtime, calls = _runtime(steps, ["a", "b", "c", "d"])

        blueprint = ACGBlueprint(objective="diamond")
        for nid in ["a", "b", "c", "d"]:
            blueprint.nodes.append(StepNode(nodeId=nid, name=nid.upper(), agentName=nid))
        blueprint.edges += [
            ACGEdge(sourceId="a", targetId="b", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="a", targetId="c", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="b", targetId="d", edgeType=EdgeType.DEPENDENCY),
            ACGEdge(sourceId="c", targetId="d", edgeType=EdgeType.DEPENDENCY),
        ]

        task = runtime.create_task(
            title="t",
            domain="test",
            intent="demo",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        run = await runtime.start(task.task_id, workflow_id="acg_wf")

        assert run.status == WorkflowStatus.COMPLETED
        assert set(calls) == {"a", "b", "c", "d"}
        # a 最先、d 最后；b、c 在中间（并行，顺序不固定）
        assert calls[0] == "a"
        assert calls[-1] == "d"
        assert set(calls[1:3]) == {"b", "c"}
        assert len(run.checkpoints) == 3
        assert run.checkpoints[1].step_id == "b"
        assert run.checkpoints[1].step_ids == ["b", "c"]

    asyncio.run(_run())


def test_acg_engine_persists_running_step_before_awaiting_agent():
    class _BlockingAgent(BaseAgent):
        def __init__(self, started: asyncio.Event, release: asyncio.Event):
            super().__init__(AgentProfile(agentName="slow", domain="test", capabilities=["slow"]))
            self.started = started
            self.release = release

        async def run(self, context):
            self.started.set()
            await self.release.wait()
            return AgentOutput(output={"done": True}, summary="done")

    async def _run():
        started = asyncio.Event()
        release = asyncio.Event()
        agents = AgentRegistry()
        agents.register(_BlockingAgent(started, release))
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="observable",
                name="Observable",
                domain="test",
                intent="demo",
                runtimeEngine="acg",
                steps=[WorkflowStepDefinition(stepId="slow", name="Slow", agentName="slow")],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
        task = runtime.create_task(title="observable", domain="test", intent="demo")
        execution = asyncio.create_task(runtime.start(task.task_id, workflow_id="observable"))

        await asyncio.wait_for(started.wait(), timeout=1)
        page = runtime.workflow_store.list_runs(page=1, page_size=10)
        persisted = page.items[0]
        assert persisted.status == WorkflowStatus.RUNNING
        assert persisted.current_step_id == "slow"
        assert persisted.active_step_ids == ["slow"]
        assert persisted.get_step("slow").status == StepStatus.RUNNING
        assert persisted.get_step("slow").attempt == 1
        runtime_node = persisted.runtime_graph.get_node("slow")
        assert runtime_node.status == StepStatus.RUNNING
        assert runtime_node.attempts[-1].attempt_id
        assert runtime_node.attempts[-1].status == StepStatus.RUNNING

        release.set()
        completed = await execution
        assert completed.status == WorkflowStatus.COMPLETED

    asyncio.run(_run())


def test_acg_engine_human_review_interrupt_and_resume():
    async def _run():
        steps = [
            WorkflowStepDefinition(stepId="a", name="A", agentName="a", nextStepId="gate"),
            WorkflowStepDefinition(stepId="gate", name="Gate", agentName="gate", reviewRequired=True, nextStepId="z"),
            WorkflowStepDefinition(stepId="z", name="Z", agentName="z"),
        ]
        runtime, calls = _runtime(steps, ["a", "gate", "z"])
        task = runtime.create_task(title="t", domain="test", intent="demo", input={})
        run = await runtime.start(task.task_id, workflow_id="acg_wf", review_mode="human_in_loop")

        assert run.status == WorkflowStatus.WAITING_REVIEW
        assert "z" not in calls  # 报告步骤尚未执行
        checkpoint = run.checkpoints[-1]
        assert checkpoint.snapshot_version == 2
        assert checkpoint.snapshot_hash
        assert checkpoint.state_snapshot["runtimeGraph"]
        assert checkpoint.state_snapshot["runtimeGraph"]["nodes"][0]["status"] == "completed"
        assert not {
            "acgBlueprint",
            "steps",
            "completedStepIds",
            "activeStepIds",
            "input",
            "output",
        }.intersection(checkpoint.state_snapshot)

        resumed = await runtime.apply_review(
            ReviewDecision(runId=run.run_id, stepId="gate", decision=ReviewDecisionType.APPROVED)
        )
        assert resumed.status == WorkflowStatus.COMPLETED
        assert "z" in calls

    asyncio.run(_run())


def test_acg_checkpoint_resume_keeps_completed_diamond_branch():
    class _FailOnceAgent(_Agent):
        def __init__(self, name, calls, *, fail_once=False):
            super().__init__(name, calls)
            self.fail_once = fail_once
            self.failed = False

        async def run(self, context):
            if self.fail_once and not self.failed:
                self.failed = True
                self.calls.append(context.step.step_id)
                raise RuntimeError("planned failure")
            return await super().run(context)

    async def _run():
        calls: list[str] = []
        agents = AgentRegistry()
        for name, fail_once in [("a", False), ("b", False), ("c", True), ("d", False)]:
            agents.register(_FailOnceAgent(name, calls, fail_once=fail_once))
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="diamond",
                name="Diamond",
                domain="test",
                intent="demo",
                runtimeEngine="acg",
                steps=[WorkflowStepDefinition(stepId=node, name=node, agentName=node) for node in "abcd"],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
        blueprint = ACGBlueprint(objective="diamond")
        for node_id in "abcd":
            blueprint.nodes.append(StepNode(nodeId=node_id, name=node_id, agentName=node_id))
        blueprint.edges.extend(
            [
                ACGEdge(sourceId="a", targetId="b", edgeType=EdgeType.DEPENDENCY),
                ACGEdge(sourceId="a", targetId="c", edgeType=EdgeType.DEPENDENCY),
                ACGEdge(sourceId="b", targetId="d", edgeType=EdgeType.DEPENDENCY),
                ACGEdge(sourceId="c", targetId="d", edgeType=EdgeType.DEPENDENCY),
            ]
        )
        task = runtime.create_task(
            title="diamond",
            domain="test",
            intent="demo",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        failed = await runtime.start(task.task_id, workflow_id="diamond")

        assert failed.status == WorkflowStatus.FAILED
        checkpoint = next(item for item in failed.checkpoints if item.step_id == "b")
        recovered = await runtime.resume_from_checkpoint(
            run_id=failed.run_id,
            checkpoint_id=checkpoint.checkpoint_id,
        )

        assert recovered.status == WorkflowStatus.COMPLETED
        assert recovered.runtime_graph.graph_version == checkpoint.state_snapshot["graphVersion"]
        assert recovered.runtime_engine == "acg"
        assert calls.count("a") == 1
        assert calls.count("b") == 1
        assert calls.count("c") == 2
        assert calls.count("d") == 1

    asyncio.run(_run())


def test_older_checkpoint_cannot_overwrite_newer_runtime_graph():
    class _FailOnceAgent(_Agent):
        def __init__(self, name, calls, *, fail_once=False):
            super().__init__(name, calls)
            self.fail_once = fail_once
            self.failed = False

        async def run(self, context):
            if self.fail_once and not self.failed:
                self.failed = True
                self.calls.append(context.step.step_id)
                raise RuntimeError("planned failure")
            return await super().run(context)

    async def _run():
        calls: list[str] = []
        agents = AgentRegistry()
        for name, fail_once in [("a", False), ("b", False), ("c", True)]:
            agents.register(_FailOnceAgent(name, calls, fail_once=fail_once))
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="versioned_resume",
                name="Versioned Resume",
                domain="test",
                intent="demo",
                runtimeEngine="acg",
                steps=[WorkflowStepDefinition(stepId=node, name=node, agentName=node) for node in "abc"],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
        blueprint = ACGBlueprint(graphId="versioned_graph", objective="checkpoint versioning")
        for node_id in "abc":
            blueprint.nodes.append(StepNode(nodeId=node_id, name=node_id, agentName=node_id))
        blueprint.edges.extend(
            [
                ACGEdge(edgeId="a_b", sourceId="a", targetId="b"),
                ACGEdge(edgeId="a_c", sourceId="a", targetId="c"),
            ]
        )
        task = runtime.create_task(
            title="versioned resume",
            domain="test",
            intent="demo",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        failed = await runtime.start(task.task_id, workflow_id="versioned_resume")
        old_checkpoint = next(item for item in failed.checkpoints if item.step_id == "b")
        assert old_checkpoint.state_snapshot["graphVersion"] == 1

        patch = RuntimeGraphPatch(
            patchId="patch_before_c",
            idempotencyKey="idem_before_c",
            runId=failed.run_id,
            graphId="versioned_graph",
            baseGraphVersion=1,
            operationType="ADD_SUBGRAPH",
            sourceEventId="event_before_c",
            proposalId="proposal_before_c",
            targetNodeId="c",
            replacedIncomingEdgeIds=["a_c"],
            budgetImpact={"addedNodes": 1, "replanDepthIncrement": 1},
            addNodes=[StepNode(nodeId="remedy", agentName="c", capability="c")],
            addEdges=[
                ACGEdge(edgeId="a_remedy", sourceId="a", targetId="remedy"),
                ACGEdge(edgeId="remedy_c", sourceId="remedy", targetId="c"),
            ],
        )
        await runtime.runtime_controller.apply_patch(failed.run_id, patch)

        with pytest.raises(RuntimeGraphError) as caught:
            await runtime.resume_from_checkpoint(
                run_id=failed.run_id,
                checkpoint_id=old_checkpoint.checkpoint_id,
            )
        assert caught.value.code == "CHECKPOINT_GRAPH_VERSION_CONFLICT"
        assert runtime.workflow_store.get_run(failed.run_id).runtime_graph.graph_version == 2

    asyncio.run(_run())


def test_acg_checkpoint_resume_in_fresh_runtime(tmp_path: Path):
    class _FailingAgent(_Agent):
        async def run(self, context):
            self.calls.append(context.step.step_id)
            raise RuntimeError("planned process failure")

    def build_runtime(store, calls, *, fail_c):
        agents = AgentRegistry()
        for name in "abcd":
            agent = _FailingAgent(name, calls) if name == "c" and fail_c else _Agent(name, calls)
            agents.register(agent)
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="persistent_diamond",
                name="Persistent Diamond",
                domain="test",
                intent="demo",
                runtimeEngine="acg",
                version="1.0.0",
                steps=[WorkflowStepDefinition(stepId=node, name=node, agentName=node) for node in "abcd"],
            )
        )
        return WorkflowRuntime(
            agent_registry=agents,
            workflow_registry=workflows,
            workflow_store=store,
        )

    async def _run():
        database = tmp_path / "acg-resume.db"
        calls: list[str] = []
        runtime = build_runtime(SQLiteWorkflowStore(database), calls, fail_c=True)
        blueprint = ACGBlueprint(objective="persistent diamond")
        for node_id in "abcd":
            blueprint.nodes.append(StepNode(nodeId=node_id, name=node_id, agentName=node_id))
        blueprint.edges.extend(
            [
                ACGEdge(sourceId="a", targetId="b", edgeType=EdgeType.DEPENDENCY),
                ACGEdge(sourceId="a", targetId="c", edgeType=EdgeType.DEPENDENCY),
                ACGEdge(sourceId="b", targetId="d", edgeType=EdgeType.DEPENDENCY),
                ACGEdge(sourceId="c", targetId="d", edgeType=EdgeType.DEPENDENCY),
            ]
        )
        task = runtime.create_task(
            title="persistent diamond",
            domain="test",
            intent="demo",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        failed = await runtime.start(task.task_id, workflow_id="persistent_diamond")
        checkpoint = next(item for item in failed.checkpoints if item.step_id == "b")

        fresh_runtime = build_runtime(SQLiteWorkflowStore(database), calls, fail_c=False)
        recovered = await fresh_runtime.resume_from_checkpoint(
            run_id=failed.run_id,
            checkpoint_id=checkpoint.checkpoint_id,
        )

        assert recovered.status == WorkflowStatus.COMPLETED
        assert recovered.provenance["schemaVersion"] == 2
        assert recovered.provenance["integrityStatus"] == "valid"
        assert calls.count("a") == 1
        assert calls.count("b") == 1
        assert calls.count("c") == 2
        assert calls.count("d") == 1

    asyncio.run(_run())


def test_workflow_runtime_engine_is_required_and_native_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError, match="runtimeEngine"):
        WorkflowDefinition.model_validate(
            {
                "workflowId": "missing_engine",
                "name": "Missing",
                "domain": "test",
                "steps": [{"stepId": "a", "name": "A", "agentName": "a"}],
            }
        )

    workflow_file = tmp_path / "missing-engine.yaml"
    workflow_file.write_text(
        '{"workflowId":"missing_engine","name":"Missing","domain":"test","steps":[{"stepId":"a","name":"A","agentName":"a"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="runtimeEngine"):
        WorkflowRegistry().load_file(workflow_file)

    runtime, _ = _runtime(
        [WorkflowStepDefinition(stepId="a", name="A", agentName="a")],
        ["a"],
        engine="native",
    )
    task = runtime.create_task(title="native", domain="test", intent="demo")
    with pytest.raises(ValueError, match="Unsupported workflow runtime engine: native"):
        asyncio.run(runtime.start(task.task_id, workflow_id="acg_wf"))


def test_acg_engine_emits_unified_step_trace():
    async def _run():
        steps = [WorkflowStepDefinition(stepId="a", name="A", agentName="a")]
        runtime, _ = _runtime(steps, ["a"])
        task = runtime.create_task(title="t", domain="test", intent="demo", input={})
        run = await runtime.start(task.task_id, workflow_id="acg_wf")

        event_types = {e.event_type for e in run.trace}
        assert TraceEventType.STEP_SCHEDULED in event_types
        assert TraceEventType.STEP_STARTED in event_types
        assert TraceEventType.AGENT_CALLED in event_types
        assert TraceEventType.STEP_SUCCEEDED in event_types
        # 摘要字段存在
        succeeded = [e for e in run.trace if e.event_type == TraceEventType.STEP_SUCCEEDED][0]
        assert "outputSummary" in succeeded.payload

    asyncio.run(_run())


def test_acg_engine_emits_low_entropy_provenance_events():
    """多步工作流应产生数据生产/消费事件，并在装配时携带节省率度量。"""

    async def _run():
        steps = [
            WorkflowStepDefinition(stepId="a", name="A", agentName="a", nextStepId="b"),
            WorkflowStepDefinition(stepId="b", name="B", agentName="b"),
        ]
        runtime, _ = _runtime(steps, ["a", "b"])
        task = runtime.create_task(title="t", domain="test", intent="demo", input={})
        run = await runtime.start(task.task_id, workflow_id="acg_wf")

        event_types = {e.event_type for e in run.trace}
        assert TraceEventType.DATA_PRODUCED in event_types
        assert TraceEventType.DATA_CONSUMED in event_types

        consumed = [e for e in run.trace if e.event_type == TraceEventType.DATA_CONSUMED]
        assert consumed, "下游 b 应有数据消费事件"
        payload = consumed[0].payload
        assert "savingRatio" in payload
        assert "tokensDelivered" in payload
        assert payload["sourceStepIds"] == ["a"]

    asyncio.run(_run())


def test_acg_engine_planner_driven_static_template():
    """usePlanner=true 时，规划器命中静态模板并经 ACG 引擎执行全链路。"""

    class _LegalAgent(BaseAgent):
        def __init__(self, name, calls):
            super().__init__(AgentProfile(agentName=name, domain="legal", capabilities=[name]))
            self.calls = calls

        async def run(self, context):
            self.calls.append(context.step.step_id)
            return AgentOutput(output={"step": context.step.step_id}, summary="ok")

    async def _run():
        steps = [
            WorkflowStepDefinition(stepId="parse", name="解析", agentName="parse", nextStepId="risk"),
            WorkflowStepDefinition(stepId="risk", name="风险", agentName="risk"),
        ]
        registry = AgentRegistry()
        calls: list[str] = []
        for name in ["parse", "risk"]:
            registry.register(_LegalAgent(name, calls))
        wf_registry = WorkflowRegistry()
        wf_registry.register(
            WorkflowDefinition(
                workflowId="acg_wf",
                name="合同审查",
                domain="legal",
                intent="contract_review",
                description="解析合同并识别风险",
                runtimeEngine="acg",
                steps=steps,
            )
        )
        runtime = WorkflowRuntime(agent_registry=registry, workflow_registry=wf_registry)
        task = runtime.create_task(
            title="审查合同",
            domain="legal",
            intent="contract_review",
            input={"usePlanner": True, "userIntent": "审查这份采购合同的违约风险"},
        )
        run = await runtime.start(task.task_id, workflow_id="acg_wf")

        assert run.status == WorkflowStatus.COMPLETED
        assert calls == ["parse", "risk"]
        # 规划决策应入 trace
        planner_events = [
            e for e in run.trace
            if e.event_type == TraceEventType.TASK_STATUS_CHANGED and "Planner" in e.observation
        ]
        assert planner_events
        assert planner_events[0].payload["strategy"] == "static_template"

    asyncio.run(_run())


def test_low_entropy_context_is_the_actual_agent_memory():
    seen: list[dict] = []

    class _Producer(BaseAgent):
        def __init__(self):
            super().__init__(AgentProfile(agentName="producer", domain="test", capabilities=["produce"]))

        async def run(self, context):
            return AgentOutput(output={"wanted": 1, "secret": "must-not-leak"})

    class _Consumer(BaseAgent):
        def __init__(self):
            super().__init__(AgentProfile(agentName="consumer", domain="test", capabilities=["consume"]))

        async def run(self, context):
            seen.append(context.memory.observations)
            assert context.context_pack is not None
            return AgentOutput(output={"received": context.context_pack.data})

    async def _run():
        agents = AgentRegistry()
        agents.register(_Producer())
        agents.register(_Consumer())
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="filtered",
                name="filtered",
                domain="test",
                intent="filter",
                runtimeEngine="acg",
                steps=[
                    WorkflowStepDefinition(
                        stepId="produce",
                        name="produce",
                        agentName="producer",
                        capability="produce",
                        nextStepId="consume",
                    ),
                    WorkflowStepDefinition(
                        stepId="consume",
                        name="consume",
                        agentName="consumer",
                        capability="consume",
                        input={
                            "from": {"produce": ["wanted"]},
                            "schema": {"type": "object", "required": ["wanted"]},
                        },
                    ),
                ],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
        task = runtime.create_task(title="filter", domain="test", intent="filter")
        run = await runtime.start(task.task_id, workflow_id="filtered")

        assert run.status == WorkflowStatus.COMPLETED
        assert seen == [{"produce": {"wanted": 1}}]
        assert run.get_step("consume").resolved_input == {"wanted": 1}
        assert run.provenance["schemaVersion"] == 2
        assert len(run.provenance["interactions"]) == 1

    asyncio.run(_run())


def test_acg_run_scoped_provenance_isolated_sequentially_and_concurrently():
    class _PassAgent(BaseAgent):
        def __init__(self, name):
            super().__init__(AgentProfile(agentName=name, domain="test", capabilities=[name]))
            self.name = name

        async def run(self, context):
            if self.name == "a":
                return AgentOutput(output={"value": context.task.task_id})
            return AgentOutput(output={"ok": True})

    async def _run():
        agents = AgentRegistry()
        agents.register(_PassAgent("a"))
        agents.register(_PassAgent("b"))
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="isolated",
                name="isolated",
                domain="test",
                intent="isolated",
                runtimeEngine="acg",
                steps=[
                    WorkflowStepDefinition(stepId="a", name="a", agentName="a", nextStepId="b"),
                    WorkflowStepDefinition(
                        stepId="b",
                        name="b",
                        agentName="b",
                        input={"from": {"a": ["value"]}},
                    ),
                ],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)

        async def start_one(index: int):
            task = runtime.create_task(title=f"t{index}", domain="test", intent="isolated")
            return await runtime.start(task.task_id, workflow_id="isolated")

        first = await start_one(0)
        second = await start_one(1)
        concurrent = await asyncio.gather(start_one(2), start_one(3))
        for run in [first, second, *concurrent]:
            assert len(run.provenance["consumptions"]) == 1
            assert len(run.provenance["interactions"]) == 1
            assert {event["runId"] for event in run.provenance["productions"]} == {run.run_id}
            assert {event["runId"] for event in run.provenance["consumptions"]} == {run.run_id}

    asyncio.run(_run())


def test_declared_retry_limit_retries_real_agent_failure():
    class _FailOnceAgent(BaseAgent):
        def __init__(self):
            super().__init__(AgentProfile(agentName="retry", domain="test", capabilities=["retry"]))
            self.failed = False

        async def run(self, context):
            if not self.failed:
                self.failed = True
                raise RuntimeError("transient failure")
            return AgentOutput(output={"ok": True})

    async def _run():
        agents = AgentRegistry()
        agents.register(_FailOnceAgent())
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="retry",
                name="retry",
                domain="test",
                intent="retry",
                runtimeEngine="acg",
                steps=[
                    WorkflowStepDefinition(
                        stepId="retry",
                        name="retry",
                        agentName="retry",
                        maxRetries=1,
                    )
                ],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
        task = runtime.create_task(title="retry", domain="test", intent="retry")
        run = await runtime.start(task.task_id, workflow_id="retry")

        assert run.status == WorkflowStatus.COMPLETED
        assert run.get_step("retry").attempt == 2
        assert run.get_step("retry").retry_count == 1
        attempts = run.runtime_graph.get_node("retry").attempts
        assert len(attempts) == 2
        assert attempts[0].status == StepStatus.FAILED
        assert attempts[1].status == StepStatus.COMPLETED
        assert attempts[0].attempt_id != attempts[1].attempt_id
        assert run.runtime_graph.graph_version == 1
        assert run.recovery_count == 1
        assert TraceEventType.RUN_FAILED not in {event.event_type for event in run.trace}

    asyncio.run(_run())


def test_cancelled_runtime_node_rejects_late_agent_outcome():
    class _BlockingAgent(BaseAgent):
        def __init__(self, started: asyncio.Event, release: asyncio.Event):
            super().__init__(AgentProfile(agentName="slow", domain="test", capabilities=["slow"]))
            self.started = started
            self.release = release

        async def run(self, context):
            self.started.set()
            await self.release.wait()
            return AgentOutput(output={"late": True}, summary="late")

    async def _run():
        started = asyncio.Event()
        release = asyncio.Event()
        agents = AgentRegistry()
        agents.register(_BlockingAgent(started, release))
        workflows = WorkflowRegistry()
        workflows.register(
            WorkflowDefinition(
                workflowId="cancel_late",
                name="Cancel late",
                domain="test",
                intent="demo",
                runtimeEngine="acg",
                steps=[WorkflowStepDefinition(stepId="slow", name="Slow", agentName="slow")],
            )
        )
        runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
        task = runtime.create_task(title="cancel", domain="test", intent="demo")
        execution = asyncio.create_task(runtime.start(task.task_id, workflow_id="cancel_late"))
        await asyncio.wait_for(started.wait(), timeout=1)
        runtime.cancel(runtime.workflow_store.list_runs(page=1, page_size=1).items[0].run_id)
        release.set()
        result = await execution

        node = result.runtime_graph.get_node("slow")
        assert result.status == WorkflowStatus.CANCELLED
        assert node.status == StepStatus.CANCELLED
        assert node.output == {}
        assert node.attempts[-1].status == StepStatus.CANCELLED
        assert any(
            event.payload.get("ignored") is True and event.payload.get("reason") == "run cancelled"
            for event in result.trace
        )

    asyncio.run(_run())

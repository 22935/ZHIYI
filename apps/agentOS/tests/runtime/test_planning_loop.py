"""Real ACG execution and SQLite persistence at strategic Planner boundaries."""

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from components.auditor import SQLiteDecisionStore
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.content import SQLiteContentManifestStore
from components.executor.value_store import SQLiteExecutionValueStore
from components.memory.store import SQLiteMemoryStore
from components.mission_manager.store import WorkflowRegistry
from components.recovery.checkpoint import ACGCheckpointStore
from contracts.planning import PlannedTask, TaskPlanPatch, TaskPlanRelation
from contracts.runtime_planning import RuntimePlanningDecision, RuntimePlanningState, RuntimeWaitCondition
from contracts.workflow import WorkflowDefinition, WorkflowStepDefinition, WorkflowStatus, ReviewDecision
from runtime import ExecutionRuntime
from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge
from service.agents import AgentRegistry
from service.agents.base import BaseAgent, AgentProfile, AgentOutput
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore


class Agent(BaseAgent):
    def __init__(self, *, fail=False, verify=None):
        super().__init__(AgentProfile(agentName="runner", domain="general", capabilities=["task_understanding", "verification"]))
        self.calls = []
        self.fail = fail
        self.verify = verify

    async def run(self, context):
        self.calls.append(context.step.step_id)
        if self.fail and context.step.step_id == "B":
            self.fail = False
            raise TimeoutError("temporary failure")
        if self.verify and context.step.step_id == "A":
            return AgentOutput(output={"verification": {"status": self.verify}}, summary="executor says done")
        if context.step.capability == "task_understanding":
            return AgentOutput(output={"task_summary": "new work understood", "constraints": []})
        return AgentOutput(output={"value": context.step.step_id}, summary="executor says done")


class Planner:
    def __init__(self, choose=None):
        self.observations = []
        self.choose = choose

    def decide_runtime(self, *, observation, task_plan):
        self.observations.append(observation)
        if self.choose:
            return self.choose(observation, task_plan)
        return RuntimePlanningDecision(observationId=observation.fingerprint(), action="complete" if not observation.remaining_step_ids else "continue", reason="based on persisted facts")


def runtime_at(tmp_path, agent=None, workflow=None, *, resource_plane=None):
    agent = agent or Agent()
    agents = AgentRegistry()
    agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(workflow or WorkflowDefinition(
        workflowId="seq", name="seq", domain="general", runtimeEngine="acg",
        planningNodes=(PlannedTask(key="step:A", title="A", objective="do A"), PlannedTask(key="step:B", title="B", objective="do B")),
        planningRelations=(TaskPlanRelation(sourceKey="step:A", targetKey="step:B", relationType="depends_on"),),
        steps=(WorkflowStepDefinition(stepId="A", name="A", agentName="runner", capability="verification" if agent.verify else None), WorkflowStepDefinition(stepId="B", name="B", agentName="runner")),
    ))
    lifecycle = AcgIdentityLifecycleService(SQLiteV2Repositories(SQLiteV2Storage(str(tmp_path / "identity.sqlite3"))))
    content_store = SQLiteContentManifestStore(tmp_path / "content.sqlite3")
    runtime = ExecutionRuntime(
        agent_registry=agents, workflow_registry=workflows,
        workflow_store=SQLiteWorkflowStore(tmp_path / "workflow.sqlite3"),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "checkpoint.sqlite3"),
        execution_value_store=SQLiteExecutionValueStore(db_path=tmp_path / "values.sqlite3"),
        memory_store=SQLiteMemoryStore(db_path=tmp_path / "memory.sqlite3"),
        provenance_store=SQLiteProvenanceStore(db_path=tmp_path / "provenance.sqlite3"),
        decision_store=SQLiteDecisionStore(db_path=tmp_path / "audit.sqlite3"),
        content_manifest_store=content_store,
        identity_lifecycle=IdentityProjectionBridge(lifecycle, lifecycle.repositories, content_store),
        resource_plane=resource_plane,
    )
    return runtime, agent


def prepared(tmp_path, agent=None, workflow=None, *, input=None, resource_plane=None):
    runtime, agent = runtime_at(tmp_path, agent, workflow, resource_plane=resource_plane)
    mission = runtime.create_mission("semantic patch", workflow_id="seq", input=input)
    _, run = runtime.prepare_run(mission.mission_id)
    return runtime, agent, run


def attach(runtime, planner):
    runtime.runtime_planning_coordinator.planner_for_run = lambda _run: planner


def test_normal_execution_calls_planner_once_at_exhaustion(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    planner = Planner()
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent.calls == ["A", "B"]
    assert [o.wake_reason for o in planner.observations] == ["exhausted"]
    assert all(s.audit_outcome == "allow" and s.commit_id for s in planner.observations[0].steps)
    assert "executor says done" not in json.dumps(result.execution_state["planningLoop"])


def test_two_user_clarifications_survive_restart_before_next_fragment(tmp_path):
    from runtime.planning_interaction import RuntimePlanningInteraction, PlannerAnswerRequest
    runtime, agent, run = prepared(tmp_path, Agent(verify="passed"))
    def choose(o, p):
        if len(o.human_answers) < 2:
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="missing user choice",
                question={"prompt": "是否包含税费？" if not o.human_answers else "交付日期是什么？", "choices": ["包含", "不包含"] if not o.human_answers else []})
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="continue" if o.remaining_step_ids else "complete", reason="use user clarification")
    planner = Planner(choose)
    attach(runtime, planner)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert agent.calls == ["A"]
    first_id = paused.execution_state["planningLoop"]["current"]["observationId"]
    service = RuntimePlanningInteraction(runtime)
    request = PlannerAnswerRequest(questionId=first_id, answer="包含税费", operationId="answer-1", expectedRevision=paused.runtime_revision)
    ready = asyncio.run(service.answer(run.run_id, request))
    assert asyncio.run(service.answer(run.run_id, request)).runtime_revision == ready.runtime_revision
    recovered, agent2 = runtime_at(tmp_path, Agent(verify="passed"))
    attach(recovered, planner)
    assert asyncio.run(recovered.prepare_planning_wakeups()) == [run.run_id]
    second = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert second.status == WorkflowStatus.WAITING_REVIEW and agent2.calls == []
    assert planner.observations[-1].wake_reason == "user_input"
    assert planner.observations[-1].human_answers[0].answer == "包含税费"
    assert planner.observations[-1].human_answers[0].source_run_id == run.run_id
    service2 = RuntimePlanningInteraction(recovered)
    asyncio.run(service2.answer(run.run_id, PlannerAnswerRequest(
        questionId=service2.view(run.run_id)["question"]["questionId"], answer="十月十日", operationId="answer-2", expectedRevision=second.runtime_revision)))
    result = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent2.calls == ["B"]
    assert [a.answer for a in planner.observations[-1].human_answers] == ["包含税费", "十月十日"]
    assert not any(e.event_type == "review_decided" for e in result.trace)


def test_clarification_rejects_stale_answer_and_cannot_be_review_approved(tmp_path):
    from runtime.planning_interaction import RuntimePlanningInteraction, PlannerAnswerRequest
    from runtime.review import ReviewConflictError
    runtime, agent, run = prepared(tmp_path)
    attach(runtime, Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="clarify", question={"prompt": "你的选择？"})))
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    service = RuntimePlanningInteraction(runtime)
    question = service.view(run.run_id)["question"]
    with pytest.raises(ReviewConflictError):
        asyncio.run(service.answer(run.run_id, PlannerAnswerRequest(questionId=question["questionId"], answer="选择 A", operationId="stale", expectedRevision=paused.runtime_revision - 1)))
    with pytest.raises(ReviewConflictError):
        asyncio.run(runtime.apply_review(ReviewDecision(runId=run.run_id, stepId=paused.current_step_id, decision="approved", operationId="cannot-approve")))
    assert runtime.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW
    assert asyncio.run(runtime.prepare_planning_wakeups()) == []


def test_read_only_copilot_is_persistent_idempotent_and_uses_bounded_history(tmp_path):
    from runtime.planning_interaction import CopilotMessageRequest, RuntimePlanningInteraction
    from runtime.review import ReviewConflictError
    runtime, agent, run = prepared(tmp_path)
    asyncio.run(runtime.execute_prepared_run(run.run_id))
    revision = runtime.get_status(run.run_id).runtime_revision
    class Model:
        requests = []
        def generate_json(self, prompt, schema, **kwargs):
            self.requests.append(json.loads(prompt))
            return {"content": "已根据当前任务状态回答。"}
    model = Model()
    runtime.set_intent_llm(model)
    service = RuntimePlanningInteraction(runtime)
    for i in range(6):
        request = CopilotMessageRequest(content=f"第 {i} 个问题", operationId=f"chat-{i}")
        asyncio.run(service.message(run.run_id, request))
    assert asyncio.run(service.message(run.run_id, request))["operationId"] == "chat-5"
    assert len(model.requests) == 6 and len(model.requests[-1]["recentConversation"]) == 4
    assert runtime.get_status(run.run_id).runtime_revision == revision and agent.calls == ["A", "B"]
    with pytest.raises(ReviewConflictError):
        asyncio.run(service.message(run.run_id, CopilotMessageRequest(content="不同内容", operationId="chat-5")))
    recovered, _ = runtime_at(tmp_path)
    assert len(RuntimePlanningInteraction(recovered).view(run.run_id)["exchanges"]) == 6


def test_copilot_selection_is_request_scoped_and_enforces_permissions(tmp_path):
    from runtime.planning_interaction import CopilotMessageRequest, PlannerAnswerRequest, RuntimePlanningInteraction
    from runtime.review import ReviewConflictError
    runtime, agent, run = prepared(tmp_path)
    class Model:
        provider = "test"
        model = "default"
        def __init__(self):
            self.calls = []
        def copilot_models(self):
            return [{"id": "test/other", "provider": "test", "model": "other"}]
        def for_model(self, provider, model):
            assert (provider, model) == ("test", "other")
            parent = self
            class Selected:
                def generate_json(self, prompt, schema, **kwargs):
                    parent.calls.append(json.loads(prompt))
                    return {"content": "selected model reply"}
            return Selected()
    model = Model()
    runtime.set_intent_llm(model)
    service = RuntimePlanningInteraction(runtime)
    revision = runtime.get_status(run.run_id).runtime_revision
    request = CopilotMessageRequest(operationId="selected", content="explain", modelId="test/other", permission="read_only")
    exchange = asyncio.run(service.message(run.run_id, request))
    assert exchange["modelId"] == "test/other" and model.calls[0]["permission"] == "read_only"
    assert service.view(run.run_id)["defaultModelId"] == "test/default"
    assert model.model == "default" and runtime.get_status(run.run_id).runtime_revision == revision and not agent.calls
    assert asyncio.run(service.message(run.run_id, request)) == exchange and len(model.calls) == 1
    with pytest.raises(ReviewConflictError):
        asyncio.run(service.message(run.run_id, request.model_copy(update={"permission": "task_collaboration"})))
    with pytest.raises(ValueError, match="所选模型"):
        asyncio.run(service.message(run.run_id, request.model_copy(update={"operation_id": "unknown", "model_id": "test/unknown"})))
    with pytest.raises(ValueError, match="仅对话"):
        asyncio.run(service.answer(run.run_id, PlannerAnswerRequest(operationId="blocked", questionId="q", answer="yes", expectedRevision=revision, permission="read_only")))
    assert runtime.get_status(run.run_id).runtime_revision == revision


def test_copilot_stream_previews_before_commit_and_passes_effort(tmp_path):
    from threading import Event
    from runtime.planning_interaction import CopilotMessageRequest, RuntimePlanningInteraction, partial_reply
    runtime, _, run = prepared(tmp_path)
    gate = Event()
    class Model:
        provider = "test"
        model = "stream"
        def __init__(self):
            self.calls = []
        def copilot_models(self):
            return [{"id": "test/stream", "provider": "test", "model": "stream", "reasoningEfforts": ["high"]}]
        async def stream_generate_json(self, **kwargs):
            self.calls.append(kwargs)
            yield {"eventType": "model.output.delta", "payload": {"delta": '{"content":"first'}}
            while not gate.is_set():
                await asyncio.sleep(0.005)
            yield {"eventType": "model.output.delta", "payload": {"delta": ' second"}'}}
            yield {"eventType": "model.completed", "payload": {"data": {"content": "first second"}}}
    model = Model()
    runtime.set_intent_llm(model)
    service = RuntimePlanningInteraction(runtime)
    request = CopilotMessageRequest(operationId="stream", content="explain", reasoningEffort="high")
    async def consume():
        stream = service.stream_message(run.run_id, request)
        while True:
            event = await asyncio.wait_for(anext(stream), 5)
            if event.get("content"):
                break
        assert event == {"type": "content", "content": "first"}
        assert runtime.workflow_store.list_copilot_exchanges(run.run_id) == []
        gate.set()
        rest = [event async for event in stream]
        assert rest[-1]["type"] == "completed" and rest[-1]["exchange"]["assistant"] == "first second"
        replay = [event async for event in service.stream_message(run.run_id, request)]
        assert replay[-1]["type"] == "completed" and len(model.calls) == 1
        gate.clear()
        disconnected = service.stream_message(run.run_id, request.model_copy(update={"operation_id": "disconnected"}))
        while not (await asyncio.wait_for(anext(disconnected), 5)).get("content"):
            pass
        await disconnected.aclose()
        gate.set()
        for _ in range(200):
            if runtime.workflow_store.get_copilot_exchange(run.run_id, "disconnected"):
                break
            await asyncio.sleep(0.01)
        assert runtime.workflow_store.get_copilot_exchange(run.run_id, "disconnected")["assistant"] == "first second"
    asyncio.run(consume())
    assert model.calls[0]["reasoning_effort"] == "high"
    assert runtime.workflow_store.list_copilot_exchanges(run.run_id)[0]["reasoningEffort"] == "high"
    assert partial_reply('{"content":"a\\n\\u4e') == "a\n"
    assert partial_reply('{"content":"\\ud83d') == ""
    assert partial_reply('{"content":"\\ud83d\\ude00"}') == "😀"
    assert partial_reply('{"other":"private"}') is None


def test_copilot_stream_failure_never_persists_preview(tmp_path):
    from runtime.planning_interaction import CopilotMessageRequest, RuntimePlanningInteraction
    runtime, _, run = prepared(tmp_path)
    class Model:
        async def stream_generate_json(self, **kwargs):
            yield {"eventType": "model.output.delta", "payload": {"delta": '{"content":"partial'}}
            raise ValueError("invalid stream")
    runtime.set_intent_llm(Model())
    service = RuntimePlanningInteraction(runtime)
    async def consume():
        return [event async for event in service.stream_message(run.run_id, CopilotMessageRequest(operationId="failure", content="explain"))]
    assert asyncio.run(consume())[-1]["type"] == "error"
    assert runtime.workflow_store.list_copilot_exchanges(run.run_id) == []


def test_answer_lineage_survives_semantic_replacement(tmp_path):
    from runtime.planning_interaction import RuntimePlanningInteraction, PlannerAnswerRequest
    runtime, agent, run = prepared(tmp_path)
    def choose(o, plan):
        if not o.human_answers:
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="clarify additional work", question={"prompt": "是否需要附加分析？"})
        assert o.human_answers[0].answer == "需要" and o.human_answers[0].source_run_id == run.run_id
        if plan.plan_version == 1:
            patch = TaskPlanPatch(missionId=plan.mission_id, basePlanVersion=1, planVersion=2,
                addNodes=(PlannedTask(key="step:C", title="C", objective="additional analysis", capabilityRequirements=("task_understanding",)),))
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="revise", reason="honor user clarification", taskPlanPatch=patch)
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="complete", reason="revised plan completed")
    planner = Planner(choose)
    attach(runtime, planner)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    service = RuntimePlanningInteraction(runtime)
    asyncio.run(service.answer(run.run_id, PlannerAnswerRequest(questionId=service.view(run.run_id)["question"]["questionId"],
        answer="需要", operationId="answer-1", expectedRevision=paused.runtime_revision)))
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and result.run_id != run.run_id
    assert runtime.get_status(run.run_id).status == WorkflowStatus.SUPERSEDED
    successor = RuntimePlanningState.model_validate(result.execution_state["planningLoop"])
    assert successor.human_answers[0].source_run_id == run.run_id and successor.rounds_used == 3
    assert not successor.user_input_pending and successor.waiting is None


def test_failed_verification_does_not_certify_completion(tmp_path):
    runtime, agent, run = prepared(tmp_path, Agent(verify="failed"))
    planner = Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="complete", reason="pretend done"))
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert agent.calls == ["A"]
    assert planner.observations[0].steps[0].verification_report == "failed"
    assert result.execution_state["planningLoop"]["current"]["status"] == "rejected"
    assert result.execution_state["reviewPayload"]["subjectType"] == "planner"
    from runtime.planning_interaction import RuntimePlanningInteraction
    review = RuntimePlanningInteraction(runtime).view(run.run_id)["review"]
    assert review["decisionRejected"] and not review["canApprove"]
    assert review["subjectId"] == result.execution_state["reviewPayload"]["subjectId"]
    assert review["expectedRunUpdatedAt"] == result.updated_at.isoformat()


def test_wait_survives_restart_and_review_resumes_through_planner(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    attach(runtime, Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="external condition")))
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    recovered, agent2 = runtime_at(tmp_path)
    assert asyncio.run(recovered.close_orphaned_runs()) == []
    assert recovered.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW
    planner = Planner()
    attach(recovered, planner)
    result = asyncio.run(recovered.apply_review(ReviewDecision(runId=run.run_id, stepId=paused.current_step_id, decision="approved", operationId="external-ready")))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent2.calls == []
    assert [o.wake_reason for o in planner.observations] == ["resume"]


def test_semantic_revision_uses_existing_replacement_and_budget(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    def choose(o, plan):
        if plan.plan_version == 1:
            patch = TaskPlanPatch(missionId=plan.mission_id, basePlanVersion=1, planVersion=2,
                addNodes=(PlannedTask(key="step:C", title="C", objective="new work", capabilityRequirements=("task_understanding",)),))
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="revise", reason="additional acceptance work", taskPlanPatch=patch)
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="complete", reason="current plan done")
    planner = Planner(choose)
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    source = runtime.get_status(run.run_id)
    assert source.status == WorkflowStatus.SUPERSEDED
    assert result.status == WorkflowStatus.COMPLETED and result.run_id != run.run_id
    assert result.execution_state["planningLoop"]["roundsUsed"] == 2
    assert result.execution_state["planningLoop"]["parentObservationId"] == source.execution_state["planningLoop"]["current"]["observationId"]
    assert result.execution_state["taskPlanVersion"] == 2


def test_cancel_while_planner_decides_cannot_commit_stale_decision(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def choose(o, p):
        entered.set()
        release.wait(5)
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="complete", reason="late response")
    attach(runtime, Planner(choose))
    async def scenario():
        execution = asyncio.create_task(runtime.execute_prepared_run(run.run_id))
        assert await asyncio.to_thread(entered.wait, 5)
        runtime.cancel(run.run_id)
        release.set()
        await execution
    asyncio.run(scenario())
    assert runtime.get_status(run.run_id).status == WorkflowStatus.CANCELLED


def test_planner_budget_waits_instead_of_spinning(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    loop = RuntimePlanningState(roundsUsed=1, maxRounds=1)
    run.execution_state["planningLoop"] = loop.model_dump(by_alias=True, mode="json")
    runtime.workflow_store.save_run(run)
    planner = Planner()
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert planner.observations == []


def test_transient_failure_recovers_without_replaying_completed_work(tmp_path):
    runtime, agent, run = prepared(tmp_path, Agent(fail=True))
    planner = Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="recover" if o.wake_reason == "failure" else "complete" if not o.remaining_step_ids else "continue", reason="recover transient failure"))
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent.calls == ["A", "B", "B"]
    assert [o.wake_reason for o in planner.observations] == ["failure", "resume", "exhausted"]
    assert planner.observations[0].failure_message == "temporary failure"


@pytest.mark.parametrize("action", ["recover", "revise"])
def test_invalid_material_preserves_diagnostic_and_rejects_unchanged_retry(tmp_path, action):
    workflow = WorkflowDefinition(workflowId="seq", name="source preflight", domain="general", runtimeEngine="acg",
        planningNodes=(PlannedTask(key="step:A", title="A", objective="do A"), PlannedTask(key="step:B", title="B", objective="do B")),
        planningRelations=(TaskPlanRelation(sourceKey="step:A", targetKey="step:B", relationType="depends_on"),), steps=(
        WorkflowStepDefinition(stepId="A", name="A", agentName="runner", nextStepId="B"),
        WorkflowStepDefinition(stepId="B", name="B", agentName="runner", input={"workset": {"sourceManifestRefs": ["artifact:2"]}}),
    ))
    runtime, agent, run = prepared(tmp_path, workflow=workflow)
    def choose(o, p):
        patch = None
        if action == "revise":
            from contracts.content import WorksetSpec
            node = next(n for n in p.nodes if n.key == "step:B").model_copy(update={
                "workset": WorksetSpec(sourceManifestRefs=["manifest_other_task"]),
                "capability_requirements": ("task_understanding",),
            })
            patch = TaskPlanPatch(missionId=p.mission_id, basePlanVersion=1, planVersion=2,
                replaceKeys=("step:B",), addNodes=(node,))
        return RuntimePlanningDecision(observationId=o.fingerprint(), action=action, reason="invalid repair", taskPlanPatch=patch)
    planner = Planner(choose)
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert agent.calls == ["A"]
    observation = planner.observations[0]
    assert observation.failure_reason == "CONTENT_SOURCE_INVALID"
    assert observation.failure_step_id == "B"
    assert "artifact:2: not found" in observation.failure_message
    current = result.execution_state["planningLoop"]["current"]
    assert current["status"] == "rejected"
    reason = "Recovery authority has no supported retry" if action == "recover" else "unregistered materials"
    assert reason in current["rejection"]
    assert reason in result.execution_state["reviewPayload"]["reason"]
    assert runtime.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW


def test_registered_planner_path_uses_fresh_observation_contract(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    class Model:
        def __init__(self):
            self.requests = []
        def generate_json(self, prompt, schema, **kwargs):
            request = json.loads(prompt)
            self.requests.append(request)
            assert "observationId" in schema["properties"]
            assert "conversation" not in request
            return {"observationId": request["observationId"], "action": "complete", "reason": "all current work completed"}
    model = Model()
    runtime.set_intent_llm(model)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert len(model.requests) == 1
    assert len(model.requests[0]["observation"]["steps"]) == 2
    assert "Without waitFor or question" in model.requests[0]["instructions"]
    assert "conditionWake records an independently checked readiness condition" in model.requests[0]["instructions"]


class PowerLoss(BaseException):
    pass


@pytest.mark.parametrize("stage", ["observed", "decided"])
def test_restart_replays_durable_round_without_replaying_execution(tmp_path, stage):
    runtime, agent, run = prepared(tmp_path)
    planner = Planner()
    attach(runtime, planner)
    save = runtime.runtime_planning_coordinator.guarded_save
    def crash(snapshot):
        save(snapshot)
        current = snapshot.execution_state["planningLoop"]["current"]
        if current and current["status"] == stage:
            raise PowerLoss(stage)
    runtime.runtime_planning_coordinator.guarded_save = crash
    with pytest.raises(PowerLoss):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    recovered, agent2 = runtime_at(tmp_path)
    attach(recovered, planner)
    assert asyncio.run(recovered.close_orphaned_runs()) == []
    result = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent2.calls == []
    assert len(planner.observations) == 1


def test_restart_finishes_pending_semantic_authority_transition(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    def choose(o, plan):
        patch = TaskPlanPatch(missionId=plan.mission_id, basePlanVersion=1, planVersion=2,
            addNodes=(PlannedTask(key="step:C", title="C", objective="new work", capabilityRequirements=("task_understanding",)),))
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="revise", reason="revise", taskPlanPatch=patch)
    attach(runtime, Planner(choose))
    runtime.semantic_revision_service.commit = lambda _prepared: (_ for _ in ()).throw(PowerLoss("before semantic commit"))
    with pytest.raises(PowerLoss):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    recovered, agent2 = runtime_at(tmp_path)
    asyncio.run(recovered.close_orphaned_runs())
    source = recovered.get_status(run.run_id)
    assert source.status == WorkflowStatus.SUPERSEDED
    successor = recovered.get_status(source.execution_state["supersededByRunId"])
    planner = Planner()
    attach(recovered, planner)
    result = asyncio.run(recovered.execute_prepared_run(successor.run_id))
    assert result.status == WorkflowStatus.COMPLETED


def test_restart_finishes_pending_recovery_authority_transition(tmp_path):
    runtime, agent, run = prepared(tmp_path, Agent(fail=True))
    attach(runtime, Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="recover", reason="retry")))
    prepare = runtime.runtime_recovery_coordinator.prepare_single_step_retry
    def crash(*a, **k):
        if k.get("validate_only"):
            return prepare(*a, **k)
        raise PowerLoss("before retry prepared")
    runtime.runtime_recovery_coordinator.prepare_single_step_retry = crash
    with pytest.raises(PowerLoss):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    recovered, agent2 = runtime_at(tmp_path)
    attach(recovered, Planner())
    asyncio.run(recovered.close_orphaned_runs())
    result = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent2.calls == ["B"]


def test_planner_cannot_revise_around_audit_denial(tmp_path):
    class DeniedAgent(Agent):
        async def run(self, context):
            self.calls.append(context.step.step_id)
            return AgentOutput(output={"value": "untrusted"}, riskLevel="critical")
    runtime, agent, run = prepared(tmp_path, DeniedAgent())
    def choose(o, plan):
        assert o.failure_type == "policy"
        patch = TaskPlanPatch(missionId=plan.mission_id, basePlanVersion=1, planVersion=2,
            addNodes=(PlannedTask(key="step:C", title="C", objective="bypass", capabilityRequirements=("task_understanding",)),))
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="revise", reason="bypass denial", taskPlanPatch=patch)
    attach(runtime, Planner(choose))
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert result.execution_state["planningLoop"]["current"]["status"] == "rejected"
    assert agent.calls == ["A"]


def test_completed_projection_without_real_commit_cannot_reach_planner(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    planner = Planner()
    attach(runtime, planner)
    runtime.execution_value_store.list_node_commits = lambda **_kwargs: ()
    with pytest.raises(ValueError, match="immutable node commit"):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert planner.observations == []
    assert runtime.get_status(run.run_id).status == WorkflowStatus.FAILED


def test_state_change_during_planning_reobserves_without_replaying_agents(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    mutated = False
    def choose(o, p):
        nonlocal mutated
        if not mutated:
            with runtime.run_lock_manager.lock_for(run.run_id):
                latest = runtime.workflow_store.get_run(run.run_id)
                latest.runtime_revision += 1
                runtime.workflow_store.save_run(latest)
                mutated = True
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="complete", reason="complete current snapshot")
    planner = Planner(choose)
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    assert agent.calls == ["A", "B"]
    assert len(planner.observations) == 2


class ArtifactAgent(Agent):
    def __init__(self, body, media_type="text/markdown"):
        super().__init__()
        self.profile.capabilities.append("artifact_generation")
        self.body = body
        self.media_type = media_type

    async def run(self, context):
        if context.step.capability == "artifact_generation":
            self.calls.append(context.step.step_id)
            return AgentOutput(output={
                "deliverable": {"title": "result", "executiveSummary": "delivered", "sections": [],
                    "calculations": [], "assumptions": [], "openQuestions": [], "sourceRefs": []},
                "final_answer": "delivered", "verification": {"status": "passed", "checks": [], "unresolvedGaps": []},
                "artifact": {"artifactId": "artifact-result", "type": "report", "title": "result",
                    "content": self.body, "mediaType": self.media_type, "structuredData": {}},
            }, summary="all acceptance criteria passed")
        return await super().run(context)


def artifact_workflow():
    return WorkflowDefinition(
        workflowId="seq", name="artifact", domain="general", runtimeEngine="acg",
        planningNodes=(PlannedTask(key="step:A", title="A", objective="analysis"),
            PlannedTask(key="step:B", title="B", objective="deliver", producedArtifacts=("report",))),
        planningRelations=(TaskPlanRelation(sourceKey="step:A", targetKey="step:B", relationType="depends_on"),),
        steps=(WorkflowStepDefinition(stepId="A", name="A", agentName="runner"),
            WorkflowStepDefinition(stepId="B", name="B", agentName="runner", capability="artifact_generation")),
    )


def test_committed_artifact_excerpt_reaches_registered_planner_and_survives_restart(tmp_path):
    body = "# Results\nVerified input data.\n" + "x" * 5000
    workflow = artifact_workflow()
    runtime, agent, run = prepared(tmp_path, ArtifactAgent(body), workflow)
    requests = []
    class Model:
        def generate_json(self, prompt, schema, **kwargs):
            request = json.loads(prompt)
            requests.append(request)
            return {"observationId": request["observationId"], "action": "wait", "reason": "external acceptance"}
    runtime.set_intent_llm(Model())
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    evidence = requests[0]["observation"]["steps"][1]["artifactEvidence"][0]
    assert evidence["excerpt"].startswith("# Results\nVerified input data.")
    assert evidence["excerptTruncated"] and evidence["businessAcceptance"] == "unverified"
    assert "all acceptance criteria passed" not in json.dumps(requests)
    recovered, _ = runtime_at(tmp_path, ArtifactAgent(body), workflow)
    assert recovered.get_status(run.run_id).execution_state["planningLoop"]["current"]["observation"]["steps"][1]["artifactEvidence"][0] == evidence


def test_nonempty_sealed_artifact_check_blocks_executor_false_completion(tmp_path):
    runtime, agent, run = prepared(tmp_path, ArtifactAgent(" \n\t"), artifact_workflow())
    planner = Planner()
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert agent.calls == ["A", "B"]
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert any(b.startswith("artifact_nonempty_content:") for b in planner.observations[0].completion_blockers)
    assert result.execution_state["planningLoop"]["current"]["status"] == "rejected"


def test_artifact_evidence_tracks_reused_output_to_source_commit(tmp_path):
    workflow = artifact_workflow().model_copy(update={
        "planning_nodes": (*artifact_workflow().planning_nodes, PlannedTask(key="step:C", title="C", objective="later work")),
        "planning_relations": (*artifact_workflow().planning_relations, TaskPlanRelation(sourceKey="step:B", targetKey="step:C", relationType="depends_on")),
        "steps": (*artifact_workflow().steps, WorkflowStepDefinition(stepId="C", name="C", agentName="runner")),
    })
    class FailLater(ArtifactAgent):
        async def run(self, context):
            if context.step.step_id == "C":
                raise TimeoutError("later failure")
            return await super().run(context)
    runtime, agent, run = prepared(tmp_path, FailLater("# Real artifact"), workflow)
    attach(runtime, Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="abort", reason="failure recorded")))
    from components.executor.graph import ACGSuperstepError
    with pytest.raises(ACGSuperstepError):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    successor = runtime.prepare_single_step_retry(run.run_id, "C")
    from runtime.state_persistence import acg_execution_state_from_run
    observation = runtime.runtime_planning_coordinator.observe(successor, acg_execution_state_from_run(successor), "resume")
    evidence = next(s for s in observation.steps if s.step_id == "B").artifact_evidence[0]
    assert evidence.source_run_id == run.run_id and evidence.excerpt == "# Real artifact"


def test_reference_only_round_fingerprint_remains_backward_compatible():
    import hashlib
    from contracts.runtime_planning import RuntimePlanningObservation
    observation = RuntimePlanningObservation(missionId="mission", runId="run", graphId="graph",
        graphVersion=1, planVersion=1, wakeReason="exhausted", goal="goal",
        steps=({"stepId": "A", "taskKey": "step:A", "status": "completed"},), remainingStepIds=())
    old_payload = observation.model_dump(by_alias=True, mode="json")
    old_payload.pop("taskAcceptance")
    old_payload.pop("taskAcceptanceResults")
    old_payload.pop("conditionWake")
    old_payload.pop("humanAnswers")
    old_payload.pop("userInputs")
    for key in ("failureReason", "failureMessage", "failureSource", "failureStepId", "resourceRequirements", "resourceFailovers"):
        old_payload.pop(key)
    for step in old_payload["steps"]:
        step.pop("artifactEvidence")
    digest = hashlib.sha256(json.dumps(old_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert observation.fingerprint() == digest


def acceptance_input():
    return {"taskAcceptance": {"criteria": [
        {"criterionId": "approved-status", "artifactKey": "final", "taskKey": "step:B",
         "pointer": "/status", "operator": "equals", "expected": "ready"},
        {"criterionId": "budget", "artifactKey": "final", "taskKey": "step:B",
         "pointer": "/cost", "operator": "at_most", "expected": 100},
    ]}}


def acceptance_workflow():
    workflow = artifact_workflow()
    return workflow.model_copy(update={
        "planning_nodes": (
            workflow.planning_nodes[0].model_copy(update={"capability_requirements": ("task_understanding",)}),
            workflow.planning_nodes[1].model_copy(update={"capability_requirements": ("artifact_generation",), "logical_role": "final_synthesis"}),
        ),
        "steps": (workflow.steps[0], workflow.steps[1].model_copy(update={"logical_role": "final_synthesis"})),
    })


def test_task_acceptance_is_frozen_and_reaches_registered_planner(tmp_path):
    runtime, agent, run = prepared(tmp_path, ArtifactAgent('{"status":"ready","cost":99}', "application/json"),
        acceptance_workflow(), input=acceptance_input())
    assert run.input["taskAcceptance"] == run.execution_state["taskAcceptance"]
    requests = []
    class Model:
        def generate_json(self, prompt, schema, **kwargs):
            request = json.loads(prompt)
            requests.append(request)
            return {"observationId": request["observationId"], "action": "complete", "reason": "independent checks passed"}
    runtime.set_intent_llm(Model())
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent.calls == ["A", "B"]
    obs = requests[0]["observation"]
    assert obs["taskAcceptance"] == run.execution_state["taskAcceptance"]
    assert [r["outcome"] for r in obs["taskAcceptanceResults"]] == ["passed", "passed"]
    assert all(r["sourceRunId"] == run.run_id and r["commitId"] for r in obs["taskAcceptanceResults"])
    assert "all acceptance criteria passed" not in json.dumps(requests)


@pytest.mark.parametrize("body,media,outcome", [
    ('{"status":"ready","cost":101}', "application/json", "failed"),
    ('{"status":"ready","cost":99}', "text/plain", "unverified"),
])
def test_task_acceptance_rejects_false_completion_even_after_review_and_restart(tmp_path, body, media, outcome):
    workflow = acceptance_workflow()
    runtime, agent, run = prepared(tmp_path, ArtifactAgent(body, media), workflow, input=acceptance_input())
    attach(runtime, Planner())
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status == WorkflowStatus.WAITING_REVIEW
    current = paused.execution_state["planningLoop"]["current"]
    assert current["status"] == "rejected"
    assert current["observation"]["taskAcceptanceResults"][-1]["outcome"] == outcome
    recovered, agent2 = runtime_at(tmp_path, ArtifactAgent(body, media), workflow)
    assert asyncio.run(recovered.close_orphaned_runs()) == []
    attach(recovered, Planner())
    result = asyncio.run(recovered.apply_review(ReviewDecision(runId=run.run_id,
        stepId=paused.current_step_id, decision="approved", operationId="review-does-not-change-budget")))
    assert result.status == WorkflowStatus.WAITING_REVIEW and agent2.calls == []
    assert result.execution_state["taskAcceptance"] == run.execution_state["taskAcceptance"]


def test_planner_revises_failed_delivery_through_existing_replacement_authority(tmp_path):
    agent = ArtifactAgent('{"status":"ready","cost":101}', "application/json")
    runtime, _, run = prepared(tmp_path, agent, acceptance_workflow(), input=acceptance_input())
    def choose(o, plan):
        if plan.plan_version == 1:
            assert [r.outcome for r in o.task_acceptance_results] == ["passed", "failed"]
            agent.body = '{"status":"ready","cost":99}'
            delivery = next(n for n in plan.nodes if n.key == "step:B").model_copy(update={
                "objective": "repair excessive cost", "capability_requirements": ("artifact_generation",),
            })
            patch = TaskPlanPatch(missionId=plan.mission_id, basePlanVersion=1, planVersion=2,
                replaceKeys=("step:B",), addNodes=(delivery,))
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="revise",
                reason="repair independently failed delivery", taskPlanPatch=patch)
        return RuntimePlanningDecision(observationId=o.fingerprint(),
            action="continue" if o.remaining_step_ids else "complete", reason="use current durable state")
    planner = Planner(choose)
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and result.run_id != run.run_id, (
        result.run_id, agent.calls, [(o.wake_reason, o.remaining_step_ids, o.completion_blockers,
            [(r.outcome, r.reason) for r in o.task_acceptance_results]) for o in planner.observations])
    assert runtime.get_status(run.run_id).status == WorkflowStatus.SUPERSEDED
    assert result.execution_state["taskAcceptance"] == run.execution_state["taskAcceptance"]
    assert result.input["taskAcceptance"] == run.input["taskAcceptance"]
    assert agent.calls == ["A", "B", "A", "B"]  # Existing semantic replacement executes a fresh graph.
    assert all(r.outcome == "passed" and r.source_run_id == result.run_id for r in planner.observations[-1].task_acceptance_results)


def test_retiring_delivery_cannot_remove_caller_acceptance(tmp_path):
    runtime, agent, run = prepared(tmp_path, ArtifactAgent('{"status":"ready","cost":101}', "application/json"),
        acceptance_workflow(), input=acceptance_input())
    def choose(o, plan):
        if plan.plan_version == 1:
            patch = TaskPlanPatch(missionId=plan.mission_id, basePlanVersion=1, planVersion=2,
                retireKeys=("step:B",), removeRelations=plan.relations)
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="revise", reason="retire failed delivery", taskPlanPatch=patch)
        return RuntimePlanningDecision(observationId=o.fingerprint(), action="complete", reason="remaining plan done")
    planner = Planner(choose)
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.run_id != run.run_id and result.status == WorkflowStatus.WAITING_REVIEW
    assert result.execution_state["taskAcceptance"] == run.execution_state["taskAcceptance"]
    assert all(r.outcome == "unverified" and r.reason == "artifact_missing" for r in planner.observations[-1].task_acceptance_results)


def test_task_acceptance_tampering_prevents_executor_calls(tmp_path):
    runtime, agent, run = prepared(tmp_path, ArtifactAgent('{"status":"ready","cost":101}', "application/json"),
        acceptance_workflow(), input=acceptance_input())
    run.input["taskAcceptance"]["criteria"][1]["expected"] = 1000
    runtime.workflow_store.save_run(run)
    with pytest.raises(ValueError, match="changed after Run admission"):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert agent.calls == []


def test_retry_inherits_admitted_acceptance_and_verifies_original_commit(tmp_path):
    workflow = acceptance_workflow().model_copy(update={
        "planning_nodes": (*acceptance_workflow().planning_nodes, PlannedTask(key="step:C", title="C", objective="later work", capabilityRequirements=("verification",))),
        "planning_relations": (*acceptance_workflow().planning_relations, TaskPlanRelation(sourceKey="step:B", targetKey="step:C", relationType="depends_on")),
        "steps": (*acceptance_workflow().steps, WorkflowStepDefinition(stepId="C", name="C", agentName="runner", capability="verification")),
    })
    class FailLater(ArtifactAgent):
        async def run(self, context):
            if context.step.step_id == "C":
                raise TimeoutError("later failure")
            return await super().run(context)
    runtime, agent, run = prepared(tmp_path, FailLater('{"status":"ready","cost":99}', "application/json"),
        workflow, input=acceptance_input())
    attach(runtime, Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="abort", reason="stop after failure")))
    from components.executor.graph import ACGSuperstepError
    with pytest.raises(ACGSuperstepError):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    mission = runtime.workflow_store.get_mission(run.mission_id)
    mission.input["taskAcceptance"]["criteria"][1]["expected"] = 1
    runtime.workflow_store.save_mission(mission)
    successor = runtime.prepare_single_step_retry(run.run_id, "C")
    assert successor.execution_state["taskAcceptance"] == run.execution_state["taskAcceptance"]
    assert successor.input["taskAcceptance"] == run.input["taskAcceptance"]
    from runtime.state_persistence import acg_execution_state_from_run
    observation = runtime.runtime_planning_coordinator.observe(successor, acg_execution_state_from_run(successor), "resume")
    assert all(r.outcome == "passed" and r.source_run_id == run.run_id for r in observation.task_acceptance_results)
    assert observation.remaining_step_ids == ("C",)


def test_missing_final_document_does_not_block_resume_of_unfinished_work(tmp_path):
    runtime, agent, run = prepared(tmp_path, ArtifactAgent('{"status":"ready","cost":99}', "application/json"),
        acceptance_workflow(), input=acceptance_input())
    from runtime.state_persistence import acg_execution_state_from_run
    from runtime.planning_loop import RuntimePlanningCoordinator
    observation = runtime.runtime_planning_coordinator.observe(run, acg_execution_state_from_run(run), "resume")
    assert all(r.reason == "artifact_missing" for r in observation.task_acceptance_results)
    assert observation.completion_blockers == ()
    RuntimePlanningCoordinator.validate_decision(observation,
        RuntimePlanningDecision(observationId=observation.fingerprint(), action="continue", reason="finish authorized work"))
    with pytest.raises(ValueError, match="unresolved work"):
        RuntimePlanningCoordinator.validate_decision(observation,
            RuntimePlanningDecision(observationId=observation.fingerprint(), action="complete", reason="premature"))


def wait_planner(condition):
    def choose(o, plan):
        return RuntimePlanningDecision(observationId=o.fingerprint(),
            action="complete" if o.condition_wake else "wait", reason="observe readiness independently",
            **({} if o.condition_wake else {"waitFor": condition}))
    return Planner(choose)


@pytest.mark.parametrize("condition", [
    {"kind": "until", "notBefore": "2026-10-05T12:00:00"},
    {"kind": "until", "nodeId": "node"},
    {"kind": "node_available", "notBefore": "2026-10-05T12:00:00Z"},
    {"kind": "callback", "nodeId": "node"},
])
def test_wait_conditions_are_finite_and_timezone_aware(condition):
    with pytest.raises(ValueError):
        RuntimeWaitCondition.model_validate(condition)


def test_timer_wait_only_wakes_once_and_does_not_replay_execution(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    planner = wait_planner({"kind": "until", "notBefore": deadline})
    attach(runtime, planner)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status == WorkflowStatus.WAITING_REVIEW
    armed_id = paused.execution_state["planningLoop"]["waiting"]["observationId"]
    for _ in range(3):
        assert asyncio.run(runtime.prepare_planning_wakeups(now=deadline - timedelta(seconds=1))) == []
    assert len(planner.observations) == 1
    assert runtime.get_status(run.run_id).runtime_revision == paused.runtime_revision
    assert asyncio.run(runtime.prepare_planning_wakeups(now=deadline)) == [run.run_id]
    ready = runtime.get_status(run.run_id)
    assert ready.status == WorkflowStatus.RETRYING and ready.execution_state["reviewPayload"] is None
    # Redelivery after a lost application submission does not append another wake.
    assert asyncio.run(runtime.prepare_planning_wakeups(now=deadline)) == [run.run_id]
    assert sum(e.payload.get("runtimeEvent") == "planner.runtime.woken" for e in runtime.get_status(run.run_id).trace) == 1
    assert not any(e.event_type.value == "review_decided" for e in ready.trace)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent.calls == ["A", "B"]
    assert [o.wake_reason for o in planner.observations] == ["exhausted", "condition"]
    assert planner.observations[-1].condition_wake.observation_id == armed_id
    assert result.execution_state["planningLoop"]["waiting"] is None


@pytest.mark.parametrize("claim_before_restart", [False, True])
def test_wait_and_pending_wake_survive_restart(tmp_path, claim_before_restart):
    runtime, agent, run = prepared(tmp_path)
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    attach(runtime, wait_planner({"kind": "until", "notBefore": deadline}))
    asyncio.run(runtime.execute_prepared_run(run.run_id))
    if claim_before_restart:
        assert asyncio.run(runtime.prepare_planning_wakeups(now=deadline)) == [run.run_id]
    recovered, agent2 = runtime_at(tmp_path)
    assert asyncio.run(recovered.close_orphaned_runs()) == []
    planner = wait_planner({"kind": "until", "notBefore": deadline})
    attach(recovered, planner)
    assert asyncio.run(recovered.prepare_planning_wakeups(now=deadline)) == [run.run_id]
    result = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent2.calls == []
    assert planner.observations[0].wake_reason == "condition"


def test_node_wait_checks_persisted_current_health_after_restart(tmp_path):
    from components.resource.node_store import SQLiteNodeStore
    from components.resource.service import ResourcePlane
    from contracts.resource import NodeProfile, NodeSnapshot
    nodes = ResourcePlane(node_store=SQLiteNodeStore(tmp_path / "nodes.sqlite3"))
    nodes.register_node(
        NodeProfile(nodeId="execution-node"),
        NodeSnapshot(nodeId="execution-node", lastHeartbeat=None),
    )
    nodes.heartbeat_node("execution-node", available_memory_mb=4096)
    runtime, agent, run = prepared(tmp_path, resource_plane=nodes)
    nodes.register_node(NodeProfile(nodeId="waiting-node"), NodeSnapshot(nodeId="waiting-node"))
    attach(runtime, wait_planner({"kind": "node_available", "nodeId": "waiting-node"}))
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert agent.calls == ["A", "B"], paused.execution_state.get("failureEvents")
    assert asyncio.run(runtime.prepare_planning_wakeups()) == []
    nodes.heartbeat_node("waiting-node", queued_tasks=1)
    assert asyncio.run(runtime.prepare_planning_wakeups()) == []
    nodes.heartbeat_node("waiting-node", success=False)
    assert asyncio.run(runtime.prepare_planning_wakeups()) == []
    nodes.heartbeat_node("waiting-node")
    recovered, agent2 = runtime_at(
        tmp_path,
        resource_plane=ResourcePlane(node_store=SQLiteNodeStore(tmp_path / "nodes.sqlite3")),
    )
    planner = wait_planner({"kind": "node_available", "nodeId": "waiting-node"})
    attach(recovered, planner)
    assert asyncio.run(recovered.prepare_planning_wakeups()) == [run.run_id]
    result = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent2.calls == [], (
        result.execution_state["planningLoop"]["current"].get("rejection"),
        [(o.wake_reason, o.remaining_step_ids, o.completion_blockers, o.condition_wake) for o in planner.observations])
    proof = planner.observations[0].condition_wake
    assert proof.node_health == "online" and proof.node_observation_sequence == 3 and proof.node_snapshot_version


def test_cancelled_or_plain_manual_wait_never_auto_wakes(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    attach(runtime, Planner(lambda o, p: RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="human decision")))
    asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert asyncio.run(runtime.prepare_planning_wakeups(now=datetime.now(timezone.utc) + timedelta(days=1))) == []
    assert runtime.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW
    runtime2, _, run2 = prepared(tmp_path / "cancelled")
    attach(runtime2, wait_planner({"kind": "until", "notBefore": datetime.now(timezone.utc)}))
    asyncio.run(runtime2.execute_prepared_run(run2.run_id))
    runtime2.cancel(run2.run_id)
    assert asyncio.run(runtime2.prepare_planning_wakeups()) == []
    assert runtime2.get_status(run2.run_id).status == WorkflowStatus.CANCELLED


def test_corrupt_checkpoint_blocks_wake_without_approving_review(tmp_path):
    runtime, agent, run = prepared(tmp_path)
    attach(runtime, wait_planner({"kind": "until", "notBefore": datetime.now(timezone.utc)}))
    asyncio.run(runtime.execute_prepared_run(run.run_id))
    runtime.checkpoint_store.load = lambda **kwargs: None
    assert asyncio.run(runtime.prepare_planning_wakeups()) == []
    assert runtime.get_status(run.run_id).status == WorkflowStatus.WAITING_REVIEW
    assert agent.calls == ["A", "B"]


def test_wait_scan_pages_past_recent_runs(tmp_path):
    runtime, agent, first = prepared(tmp_path)
    attach(runtime, wait_planner({"kind": "until", "notBefore": datetime.now(timezone.utc)}))
    asyncio.run(runtime.execute_prepared_run(first.run_id))
    newer = [runtime.prepare_run(first.mission_id)[1] for _ in range(3)]
    assert asyncio.run(runtime.prepare_planning_wakeups(page_size=1)) == [first.run_id]
    assert all(runtime.get_status(r.run_id).status == WorkflowStatus.PENDING for r in newer)


def test_wake_returns_control_to_planner_before_unfinished_fragment(tmp_path):
    runtime, agent, run = prepared(tmp_path, Agent(verify="passed"))
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    def choose(o, p):
        if o.wake_reason == "verification":
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="wait before next fragment",
                waitFor={"kind": "until", "notBefore": deadline})
        return RuntimePlanningDecision(observationId=o.fingerprint(),
            action="continue" if o.remaining_step_ids else "complete", reason="use current authorized fragment")
    planner = Planner(choose)
    attach(runtime, planner)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status == WorkflowStatus.WAITING_REVIEW and agent.calls == ["A"]
    assert asyncio.run(runtime.prepare_planning_wakeups(now=deadline)) == [run.run_id]
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent.calls == ["A", "B"]
    assert [o.wake_reason for o in planner.observations] == ["verification", "condition", "exhausted"]
    assert planner.observations[1].remaining_step_ids == ("B",)


def test_wake_cannot_override_failed_task_acceptance(tmp_path):
    runtime, agent, run = prepared(tmp_path, ArtifactAgent('{"status":"ready","cost":101}', "application/json"),
        acceptance_workflow(), input=acceptance_input())
    planner = wait_planner({"kind": "until", "notBefore": datetime.now(timezone.utc)})
    attach(runtime, planner)
    asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert asyncio.run(runtime.prepare_planning_wakeups()) == [run.run_id]
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW
    assert result.execution_state["planningLoop"]["current"]["status"] == "rejected"
    assert result.execution_state["planningLoop"]["waiting"] is None
    assert asyncio.run(runtime.prepare_planning_wakeups()) == []
    assert planner.observations[-1].task_acceptance_results[-1].outcome == "failed"


def test_failed_fragment_waits_then_wakes_through_recovery_authority(tmp_path):
    runtime, agent, run = prepared(tmp_path, Agent(fail=True))
    deadline = datetime.now(timezone.utc) + timedelta(minutes=1)
    def choose(o, p):
        if o.wake_reason == "failure":
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="wait", reason="retry after cooldown",
                waitFor={"kind": "until", "notBefore": deadline})
        if o.failed_step_ids:
            assert o.wake_reason == "condition" and o.failure_id and o.recovery_action
            return RuntimePlanningDecision(observationId=o.fingerprint(), action="recover", reason="retry failed fragment")
        return RuntimePlanningDecision(observationId=o.fingerprint(),
            action="continue" if o.remaining_step_ids else "complete", reason="use current durable state")
    planner = Planner(choose)
    attach(runtime, planner)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status == WorkflowStatus.WAITING_REVIEW and agent.calls == ["A", "B"]
    assert asyncio.run(runtime.prepare_planning_wakeups(now=deadline)) == [run.run_id]
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent.calls == ["A", "B", "B"]
    assert [o.wake_reason for o in planner.observations] == ["failure", "condition", "resume", "exhausted"]
    assert len(result.execution_state["inPlaceRetryRequests"]) == 1


@pytest.mark.parametrize("stage", ["observed", "decided"])
def test_condition_round_replays_after_crash_without_repeating_wake(tmp_path, stage):
    runtime, agent, run = prepared(tmp_path)
    planner = wait_planner({"kind": "until", "notBefore": datetime.now(timezone.utc)})
    attach(runtime, planner)
    asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert asyncio.run(runtime.prepare_planning_wakeups()) == [run.run_id]
    save = runtime.runtime_planning_coordinator.guarded_save
    def crash(snapshot):
        save(snapshot)
        current = snapshot.execution_state["planningLoop"]["current"]
        if current["observation"]["wakeReason"] == "condition" and current["status"] == stage:
            raise PowerLoss(stage)
    runtime.runtime_planning_coordinator.guarded_save = crash
    with pytest.raises(PowerLoss):
        asyncio.run(runtime.execute_prepared_run(run.run_id))
    recovered, agent2 = runtime_at(tmp_path)
    attach(recovered, planner)
    assert asyncio.run(recovered.close_orphaned_runs()) == []
    result = asyncio.run(recovered.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED and agent2.calls == []
    assert [o.wake_reason for o in planner.observations] == ["exhausted", "condition"]
    assert sum(e.payload.get("runtimeEvent") == "planner.runtime.woken" for e in result.trace) == 1


def test_unobserved_node_and_exhausted_budget_require_external_resolution(tmp_path):
    runtime, _, run = prepared(tmp_path)
    attach(runtime, wait_planner({"kind": "node_available", "nodeId": "invented-node"}))
    rejected = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert rejected.execution_state["planningLoop"]["current"]["status"] == "rejected"
    assert rejected.execution_state["planningLoop"]["waiting"] is None
    other, agent, run2 = prepared(tmp_path / "budget")
    run2.execution_state["planningLoop"]["maxRounds"] = 1
    other.workflow_store.save_run(run2)
    planner = wait_planner({"kind": "until", "notBefore": datetime.now(timezone.utc)})
    attach(other, planner)
    asyncio.run(other.execute_prepared_run(run2.run_id))
    assert asyncio.run(other.prepare_planning_wakeups()) == [run2.run_id]
    result = asyncio.run(other.execute_prepared_run(run2.run_id))
    assert result.status == WorkflowStatus.WAITING_REVIEW and len(planner.observations) == 1
    assert result.execution_state["planningLoop"]["waiting"] is None


def test_many_artifacts_share_one_observation_excerpt_budget(tmp_path):
    class ManyArtifacts(ArtifactAgent):
        async def run(self, context):
            if context.step.capability == "artifact_generation":
                return AgentOutput(output={"artifacts": [
                    {"artifactKey": f"part-{i}", "type": "report", "title": f"part-{i}", "content": "x" * 3000}
                    for i in range(6)
                ]})
            return await super().run(context)
    runtime, agent, run = prepared(tmp_path, ManyArtifacts("unused"), artifact_workflow())
    planner = Planner()
    attach(runtime, planner)
    result = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert result.status == WorkflowStatus.COMPLETED
    evidence = planner.observations[0].steps[1].artifact_evidence
    assert len(evidence) == 6
    assert sum(len(e.excerpt.encode()) for e in evidence) == 8192
    assert sum(e.excerpt_status == "budget_exhausted" for e in evidence) == 2


def test_blueprint_review_gate_hides_excerpt_until_human_approval(tmp_path):
    from runtime.state_persistence import acg_execution_state_from_run
    workflow = artifact_workflow()
    workflow = workflow.model_copy(update={"steps": (workflow.steps[0],
        workflow.steps[1].model_copy(update={"review_required": True}))})
    runtime, agent, run = prepared(tmp_path, ArtifactAgent("# Review required"), workflow)
    planner = Planner()
    attach(runtime, planner)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status == WorkflowStatus.WAITING_REVIEW and not planner.observations
    observation = runtime.runtime_planning_coordinator.observe(paused, acg_execution_state_from_run(paused), "resume")
    evidence = observation.steps[1].artifact_evidence[0]
    assert evidence.excerpt == "" and evidence.excerpt_status == "review_pending"
    assert observation.completion_blockers
    result = asyncio.run(runtime.apply_review(ReviewDecision(runId=run.run_id, stepId="B", decision="approved")))
    assert result.status == WorkflowStatus.COMPLETED
    assert planner.observations[0].steps[1].artifact_evidence[0].excerpt == "# Review required"

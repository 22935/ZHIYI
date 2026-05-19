import asyncio
from pathlib import Path

import pytest

from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.agents import AgentRegistry
from agentos.packs.legal import register_pack as register_legal_pack
from agentos.core.state_machine import InvalidStateTransition, StateMachine
from agentos.core.types import (
    ReviewDecision,
    ReviewDecisionType,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.workflow_registry import WorkflowRegistry
from agentos.core.workflow_runtime import WorkflowRuntime
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore


class RecordingAgent(BaseAgent):
    def __init__(self, name, calls, fail_once=False):
        super().__init__(
            AgentProfile(
                agentName=name,
                domain="test",
                capabilities=[name],
                allowedSkills=[],
            )
        )
        self.calls = calls
        self.fail_once = fail_once
        self.failed = False

    async def run(self, context):
        self.calls.append(
            {
                "agent": self.profile.agent_name,
                "step": context.step.step_id,
                "observations": sorted(context.memory.observations.keys()),
            }
        )
        if self.fail_once and not self.failed:
            self.failed = True
            raise RuntimeError("planned failure")
        return AgentOutput(
            output={
                "agent": self.profile.agent_name,
                "step": context.step.step_id,
                "observations": dict(context.memory.observations),
            },
            summary=f"{self.profile.agent_name} completed",
        )


def _runtime_with_workflow(steps, agents):
    agent_registry = AgentRegistry()
    for agent in agents:
        agent_registry.register(agent)

    workflow_registry = WorkflowRegistry()
    workflow_registry.register(
        WorkflowDefinition(
            workflowId="test_workflow",
            name="Test Workflow",
            domain="test",
            intent="case_analysis",
            version="1.0.0",
            steps=steps,
        )
    )
    return WorkflowRuntime(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
    )


def test_state_machine_blocks_illegal_transitions():
    machine = StateMachine()

    assert machine.transition(WorkflowStatus.PENDING, WorkflowStatus.RUNNING) == WorkflowStatus.RUNNING

    with pytest.raises(InvalidStateTransition):
        machine.transition(WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING)


def test_runtime_runs_registered_workflow_with_trace_and_checkpoints():
    asyncio.run(_test_runtime_runs_registered_workflow_with_trace_and_checkpoints())


async def _test_runtime_runs_registered_workflow_with_trace_and_checkpoints():
    calls = []
    steps = [
        WorkflowStepDefinition(stepId="intake", name="Intake", agentName="intake", nextStepId="statute"),
        WorkflowStepDefinition(stepId="statute", name="Statute", agentName="statute", nextStepId="risk"),
        WorkflowStepDefinition(stepId="risk", name="Risk", agentName="risk"),
    ]
    runtime = _runtime_with_workflow(
        steps=steps,
        agents=[
            RecordingAgent("intake", calls),
            RecordingAgent("statute", calls),
            RecordingAgent("risk", calls),
        ],
    )

    task = runtime.create_task(
        title="Test case",
        domain="test",
        intent="case_analysis",
        input={"caseText": "合同违约并存在转账证据"},
    )
    run = await runtime.start(task.task_id, workflow_id="test_workflow")

    assert run.status == WorkflowStatus.COMPLETED
    assert [call["agent"] for call in calls] == ["intake", "statute", "risk"]
    assert calls[1]["observations"] == ["intake"]
    assert calls[2]["observations"] == ["intake", "statute"]
    assert all(step.status == StepStatus.COMPLETED for step in run.steps)
    assert len(run.checkpoints) == 3
    assert [checkpoint.step_id for checkpoint in run.checkpoints] == ["intake", "statute", "risk"]

    event_types = [event.event_type for event in run.trace]
    assert TraceEventType.TASK_CREATED in event_types
    assert TraceEventType.STEP_STARTED in event_types
    assert TraceEventType.AGENT_CALLED in event_types
    assert TraceEventType.CHECKPOINT_CREATED in event_types
    assert TraceEventType.RUN_COMPLETED in event_types


def test_runtime_waits_for_review_and_continues_after_approval():
    asyncio.run(_test_runtime_waits_for_review_and_continues_after_approval())


async def _test_runtime_waits_for_review_and_continues_after_approval():
    calls = []
    steps = [
        WorkflowStepDefinition(stepId="intake", name="Intake", agentName="intake", nextStepId="risk"),
        WorkflowStepDefinition(
            stepId="risk",
            name="Risk",
            agentName="risk",
            reviewRequired=True,
            nextStepId="draft",
        ),
        WorkflowStepDefinition(stepId="draft", name="Draft", agentName="draft"),
    ]
    runtime = _runtime_with_workflow(
        steps=steps,
        agents=[
            RecordingAgent("intake", calls),
            RecordingAgent("risk", calls),
            RecordingAgent("draft", calls),
        ],
    )
    task = runtime.create_task("Review task", "test", "case_analysis", {"caseText": "需要人工审核"})

    run = await runtime.start(task.task_id, workflow_id="test_workflow", review_mode="human_in_loop")

    assert run.status == WorkflowStatus.WAITING_REVIEW
    assert run.current_step_id == "risk"
    assert run.get_step("risk").status == StepStatus.WAITING_REVIEW
    assert [call["agent"] for call in calls] == ["intake", "risk"]

    reviewed = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="risk",
            decision=ReviewDecisionType.APPROVED,
            reviewer="reviewer_001",
            comment="风险说明可进入文书生成",
        )
    )

    assert reviewed.status == WorkflowStatus.COMPLETED
    assert [call["agent"] for call in calls] == ["intake", "risk", "draft"]
    assert reviewed.get_step("draft").status == StepStatus.COMPLETED


def test_runtime_recovers_from_checkpoint_after_step_failure():
    asyncio.run(_test_runtime_recovers_from_checkpoint_after_step_failure())


async def _test_runtime_recovers_from_checkpoint_after_step_failure():
    calls = []
    steps = [
        WorkflowStepDefinition(stepId="intake", name="Intake", agentName="intake", nextStepId="risk"),
        WorkflowStepDefinition(stepId="risk", name="Risk", agentName="risk"),
    ]
    runtime = _runtime_with_workflow(
        steps=steps,
        agents=[
            RecordingAgent("intake", calls),
            RecordingAgent("risk", calls, fail_once=True),
        ],
    )
    task = runtime.create_task("Recover task", "test", "case_analysis", {"caseText": "第一次风险评估失败"})

    failed = await runtime.start(task.task_id, workflow_id="test_workflow")

    assert failed.status == WorkflowStatus.FAILED
    assert failed.current_step_id == "risk"
    assert failed.get_step("risk").status == StepStatus.FAILED
    assert [checkpoint.step_id for checkpoint in failed.checkpoints] == ["intake"]

    recovered = await runtime.resume_from_checkpoint(
        run_id=failed.run_id,
        checkpoint_id=failed.checkpoints[-1].checkpoint_id,
    )

    assert recovered.status == WorkflowStatus.COMPLETED
    assert recovered.recovery_count == 1
    assert recovered.get_step("risk").status == StepStatus.COMPLETED
    event_types = [event.event_type for event in recovered.trace]
    assert TraceEventType.RUN_RECOVERED in event_types


def test_legal_demo_pack_registers_agents_and_workflow():
    asyncio.run(_test_legal_demo_pack_registers_agents_and_workflow())


async def _test_legal_demo_pack_registers_agents_and_workflow():
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    task = runtime.create_task(
        title="合同审查",
        domain="legal",
        intent="contract_review",
        input={"caseText": "甲乙双方合同逾期交付，存在转账记录和微信聊天证据。"},
    )
    run = await runtime.start(task.task_id, review_mode="human_in_loop")

    assert task.recommended_workflow == "legal_contract_review_v1"
    assert run.status == WorkflowStatus.WAITING_REVIEW
    assert run.current_step_id == "risk"
    assert run.get_step("case_intake").output["case_summary"]
    assert run.get_step("statute").output["legal_basis"]

    completed = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="risk",
            decision=ReviewDecisionType.APPROVED,
            reviewer="legal_reviewer",
        )
    )

    assert completed.status == WorkflowStatus.COMPLETED
    assert completed.output["final_answer"]
    assert completed.output["artifacts"]["draft"]


def test_agentos_core_api_task_run_review_flow():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    task_response = client.post(
        "/ai/core/tasks",
        json={
            "title": "合同审查",
            "domain": "legal",
            "intent": "contract_review",
            "input": {"caseText": "合同逾期交付，存在转账记录。"},
            "securityLevel": "internal",
        },
    )
    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["recommendedWorkflow"] == "legal_contract_review_v1"

    run_response = client.post(
        "/ai/core/workflows/runs",
        json={"taskId": task_payload["taskId"], "reviewMode": "human_in_loop"},
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["status"] == "waiting_review"
    assert run_payload["currentStepId"] == "risk"

    review_response = client.post(
        f"/ai/core/workflows/runs/{run_payload['runId']}/reviews",
        json={"stepId": "risk", "decision": "approved", "reviewer": "api_reviewer"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "completed"

    status_response = client.get(f"/ai/core/workflows/runs/{run_payload['runId']}")
    assert status_response.status_code == 200
    assert status_response.json()["output"]["final_answer"]

    trace_response = client.get(f"/ai/core/workflows/runs/{run_payload['runId']}/trace")
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["runId"] == run_payload["runId"]
    assert trace_payload["workflowId"] == "legal_contract_review_v1"
    assert trace_payload["eventCount"] == len(trace_payload["events"])
    assert any(event["eventType"] == "review_decided" for event in trace_payload["events"])

    markdown_response = client.get(
        f"/ai/core/workflows/runs/{run_payload['runId']}/trace",
        params={"format": "markdown"},
    )
    assert markdown_response.status_code == 200
    assert f"# Workflow Trace: {run_payload['runId']}" in markdown_response.text
    assert "`review_decided`" in markdown_response.text

    checkpoints_response = client.get(f"/ai/core/workflows/runs/{run_payload['runId']}/checkpoints")
    assert checkpoints_response.status_code == 200
    checkpoints_payload = checkpoints_response.json()
    assert checkpoints_payload["runId"] == run_payload["runId"]
    assert checkpoints_payload["total"] >= 1
    assert checkpoints_payload["items"][0]["checkpointId"].startswith("ckpt_")

    reviews_response = client.get(f"/ai/core/workflows/runs/{run_payload['runId']}/reviews")
    assert reviews_response.status_code == 200
    reviews_payload = reviews_response.json()
    assert reviews_payload["runId"] == run_payload["runId"]
    assert reviews_payload["total"] == 1
    assert reviews_payload["items"][0]["decision"] == "approved"
    assert reviews_payload["items"][0]["reviewer"] == "api_reviewer"

    metrics_response = client.get(
        "/ai/core/workflows/metrics",
        params={"workflowId": "legal_contract_review_v1"},
    )
    assert metrics_response.status_code == 200
    metrics_payload = metrics_response.json()
    assert metrics_payload["workflowId"] == "legal_contract_review_v1"
    assert metrics_payload["metrics"]["totalRuns"] == 1
    assert metrics_payload["metrics"]["completionRate"] == 1.0
    assert metrics_payload["metrics"]["reviewCount"] == 1


def test_workbench_can_start_workflow_in_one_request():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/core/workflows/start",
        json={
            "title": "Workbench合同审查",
            "domain": "legal",
            "intent": "contract_review",
            "input": {"caseText": "供应商逾期交付，合同约定违约金。"},
            "reviewMode": "human_in_loop",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["recommendedWorkflow"] == "legal_contract_review_v1"
    assert payload["run"]["status"] == "waiting_review"
    assert payload["run"]["currentStepId"] == "risk"
    assert payload["run"]["input"]["caseText"] == "供应商逾期交付，合同约定违约金。"


def test_chat_can_upgrade_message_to_workflow_run():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/chat/workflows/upgrade",
        json={
            "text": "客户说合同逾期交付，想评估诉讼风险。",
            "contextId": "chat_ctx_001",
            "roleId": "legal-assistant",
            "context": [{"role": "user", "content": "前面讨论过交付时间。"}],
            "domain": "legal",
            "intent": "case_analysis",
            "reviewMode": "human_in_loop",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "chat"
    assert payload["task"]["input"]["source"] == "chat"
    assert payload["task"]["input"]["caseText"] == "客户说合同逾期交付，想评估诉讼风险。"
    assert payload["task"]["input"]["chatContextId"] == "chat_ctx_001"
    assert payload["task"]["input"]["chatContext"][0]["content"] == "前面讨论过交付时间。"
    assert payload["run"]["status"] == "waiting_review"
    assert payload["run"]["currentStepId"] == "risk"


def test_legacy_lawyer_agent_chat_endpoint_returns_status_payload():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/agent/lawyer/chat",
        json={"text": "Supplier delayed delivery under a contract.", "sessionId": "session_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sessionId"] == "session_001"
    assert "法律初步分析" in payload["answer"]
    assert "风险等级" in payload["answer"]
    assert "Legal analysis completed" not in payload["answer"]
    assert "legal basis item" not in payload["answer"]
    assert "risk_assessment" in payload["skillsUsed"]
    assert len(payload["trace"]) >= 1
    assert payload["trace"][0]["action"] == "case_understanding"


def test_legacy_programmer_agent_chat_endpoint_returns_full_deliverable():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentos.packs.programmer import register_pack as register_programmer_pack
    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_programmer_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/agent/programmer/chat",
        json={
            "text": "开发一个简单的用户认证与权限管理模块，技术栈为 Python FastAPI + JWT。",
            "sessionId": "programmer_session_001",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sessionId"] == "programmer_session_001"
    assert "功能规格" in payload["answer"]
    assert "```python" in payload["answer"]
    assert "```mermaid" in payload["answer"]
    assert "Requirement analysis ready" not in payload["answer"]
    assert "code_generation" in payload["skillsUsed"]
    assert "diagram_generation" in payload["skillsUsed"]
    assert payload["codeGeneration"]["code"].find("def create_access_token") >= 0
    assert payload["diagramGeneration"]["mermaid_code"].startswith("flowchart")
    assert any(step["action"] == "code_generation" for step in payload["trace"])


def test_legacy_teacher_agent_chat_endpoint_returns_chinese_lesson_plan():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentos.packs.education import register_pack as register_education_pack
    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_education_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/agent/teacher/chat",
        json={"text": "请为初二数学一次函数设计一节45分钟课程。", "sessionId": "teacher_session_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sessionId"] == "teacher_session_001"
    assert "教学设计" in payload["answer"]
    assert "教学目标" in payload["answer"]
    assert "Lesson plan ready" not in payload["answer"]
    assert "lesson_plan_generation" in payload["skillsUsed"]
    assert payload["lessonPlan"]["subject"] == "数学"
    assert payload["lessonPlan"]["grade"] == "初二"


def test_legacy_writer_agent_chat_endpoint_detects_science_fiction_genre():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentos.packs.writer import register_pack as register_writer_pack
    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_writer_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    response = client.post(
        "/ai/agent/writer/chat",
        json={"text": "生成科幻小说的大纲，主题是海底城市和失控AI。", "sessionId": "writer_session_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sessionId"] == "writer_session_001"
    assert "科幻" in payload["answer"]
    assert "Story outline ready" not in payload["answer"]
    assert "outline_generate" in payload["skillsUsed"]


def test_agentos_core_api_lists_tasks_and_runs_with_filters():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agentos_core import create_router

    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    runtime = WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)

    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    client.post(
        "/ai/chat/workflows/upgrade",
        json={
            "text": "聊天升级案件分析",
            "contextId": "chat_ctx_list",
            "domain": "legal",
            "intent": "case_analysis",
            "reviewMode": "human_in_loop",
        },
    )
    workbench_response = client.post(
        "/ai/core/workflows/start",
        json={
            "title": "工作台合同审查",
            "domain": "legal",
            "intent": "contract_review",
            "input": {"source": "workbench", "caseText": "工作台合同审查"},
            "reviewMode": "human_in_loop",
        },
    )
    assert workbench_response.status_code == 200

    runs_response = client.get(
        "/ai/core/workflows/runs",
        params={"status": "waiting_review", "source": "workbench", "page": 1, "pageSize": 10},
    )
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert runs_payload["total"] == 1
    assert runs_payload["page"] == 1
    assert runs_payload["pageSize"] == 10
    assert runs_payload["items"][0]["input"]["source"] == "workbench"
    assert runs_payload["items"][0]["workflowId"] == "legal_contract_review_v1"

    tasks_response = client.get(
        "/ai/core/tasks",
        params={"source": "chat", "domain": "legal"},
    )
    assert tasks_response.status_code == 200
    tasks_payload = tasks_response.json()
    assert tasks_payload["total"] == 1
    assert tasks_payload["items"][0]["input"]["source"] == "chat"
    assert tasks_payload["items"][0]["recommendedWorkflow"] == "legal_case_analysis_v1"


def test_default_runtime_uses_sqlite_store_when_env_is_set(tmp_path, monkeypatch):
    from app.api import agentos_core

    db_path = tmp_path / "workflow.db"
    monkeypatch.setenv("AGENTOS_WORKFLOW_DB_PATH", str(db_path))

    runtime = agentos_core.build_default_runtime()

    assert isinstance(runtime.workflow_store, SQLiteWorkflowStore)
    assert Path(runtime.workflow_store.db_path) == db_path


def test_default_runtime_uses_memory_store_when_env_is_missing(monkeypatch):
    from app.api import agentos_core

    monkeypatch.delenv("AGENTOS_WORKFLOW_DB_PATH", raising=False)

    runtime = agentos_core.build_default_runtime()

    assert isinstance(runtime.workflow_store, MemoryWorkflowStore)


def test_default_runtime_registers_packs_through_manifest_loader(monkeypatch):
    from agentos.core import workflow_runtime

    calls = []

    def fake_register_installed_packs(agent_registry, workflow_registry):
        calls.append((agent_registry, workflow_registry))
        return []

    monkeypatch.setattr(workflow_runtime, "register_installed_packs", fake_register_installed_packs)
    monkeypatch.delenv("AGENTOS_WORKFLOW_DB_PATH", raising=False)

    runtime = workflow_runtime.build_default_runtime()

    assert calls == [(runtime.agent_registry, runtime.workflow_registry)]

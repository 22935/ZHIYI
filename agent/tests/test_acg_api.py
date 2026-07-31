"""ACG 引擎 API 端到端集成测试（阶段6）。

验证通过 FastAPI 用 Core Native ACG 引擎跑通工作流，并经 /acg 视图端点
拿到拓扑蓝图、数据血缘、低熵指标与恢复轨迹——前端可视化面板的数据源。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.core.models.types import WorkflowDefinition, WorkflowStepDefinition
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from app.api.agentos_core import _safe_runtime_projection, create_router


class _Agent(BaseAgent):
    def __init__(self, name):
        super().__init__(AgentProfile(agentName=name, domain="demo", capabilities=[name]))

    async def run(self, context):
        if context.step.step_id == "c":
            return AgentOutput(
                output={
                    "final_answer": "# Final delivery\n\nComplete result.",
                    "artifact": {
                        "artifactId": "artifact_demo",
                        "type": "report",
                        "title": "Demo result",
                        "mediaType": "text/markdown",
                        "content": "# Final delivery\n\nComplete result.",
                        "structuredData": {"summary": "Complete result."},
                    },
                },
                summary="ok",
            )
        return AgentOutput(
            output={"step": context.step.step_id, "summary": "结论", "evidence_refs": [f"ev_{context.step.step_id}"]},
            summary="ok",
        )


def _client(fault=None):
    steps = [
        WorkflowStepDefinition(stepId="a", name="A", agentName="a", nextStepId="b"),
        WorkflowStepDefinition(stepId="b", name="B", agentName="b", nextStepId="c"),
        WorkflowStepDefinition(stepId="c", name="C", agentName="c"),
    ]
    ar = AgentRegistry()
    for n in ["a", "b", "c"]:
        ar.register(_Agent(n))
    wr = WorkflowRegistry()
    wr.register(
        WorkflowDefinition(
            workflowId="demo_acg", name="demo", domain="demo", intent="demo",
            runtimeEngine="acg", steps=steps,
        )
    )
    runtime = WorkflowRuntime(agent_registry=ar, workflow_registry=wr)
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    return TestClient(app)


def test_acg_engine_end_to_end_via_api():
    client = _client()
    task = client.post(
        "/ai/core/tasks",
        json={"title": "demo", "domain": "demo", "intent": "demo", "input": {}},
    ).json()
    run = client.post(
        "/ai/core/workflows/runs",
        json={"taskId": task["taskId"], "workflowId": "demo_acg"},
    ).json()
    assert run["status"] == "completed"
    assert run["runtimeEngine"] == "acg"
    assert run["acgBlueprint"] is not None
    assert set(run["completedStepIds"]) == {"a", "b", "c"}


def test_acg_view_endpoint_exposes_topology_and_provenance():
    client = _client()
    task = client.post(
        "/ai/core/tasks", json={"title": "demo", "domain": "demo", "intent": "demo", "input": {}}
    ).json()
    run = client.post(
        "/ai/core/workflows/runs", json={"taskId": task["taskId"], "workflowId": "demo_acg"}
    ).json()

    acg = client.get(f"/ai/core/workflows/runs/{run['runId']}/acg")
    assert acg.status_code == 200
    view = acg.json()
    assert view["engine"] == "acg"
    assert view["acgBlueprint"]["nodes"]
    assert all("activation" in edge for edge in view["acgBlueprint"]["edges"])
    assert view["branchDecisions"] == []
    assert view["selectedEdgeIds"] == []
    assert view["terminatedEdgeIds"] == []
    assert view["skippedByConditionCount"] == 0
    assert view["conditionalDecisionCount"] == 0
    # 数据血缘：3 步至少有 2 次消费（b←a, c←b）
    assert len(view["provenance"]["productions"]) == 3
    assert len(view["provenance"]["consumptions"]) >= 2
    assert view["provenance"]["schemaVersion"] == 2
    assert view["provenance"]["integrityStatus"] == "valid"
    assert view["interactions"]
    assert len(view["stepStates"]) == 3
    assert {
        "currentBinding",
        "bindingHistory",
        "bindingSwitchCount",
        "attempts",
        "sourcePatchId",
        "createdGraphVersion",
        "outputVersion",
        "outputSummary",
        "errorSummary",
    }.issubset(view["stepStates"][0])
    assert view["stepStates"][0]["attempts"][0]["attemptId"]
    assert "resolvedInput" not in view["stepStates"][0]["attempts"][0]
    # 低熵指标存在
    metrics = view["lowEntropyMetrics"]
    assert "averageSavingRatio" in metrics
    assert "effectiveSavingRatio" in metrics
    assert "tokensSaved" in metrics
    assert metrics["interactionCount"] == len(view["interactions"])
    assert metrics["contractViolationCount"] == 0
    # 调度轨迹存在（就绪集调度可见）
    assert view["scheduleTrace"]
    assert len(view["deliverables"]) == 3
    assert view["stepOutputs"] == view["deliverables"]
    assert view["finalReport"].startswith("# Final delivery")
    assert view["finalArtifacts"] == [
        {
            "artifactId": "artifact_demo",
            "type": "report",
            "title": "Demo result",
            "mediaType": "text/markdown",
            "content": "# Final delivery\n\nComplete result.",
            "structuredData": {"summary": "Complete result."},
            "stepId": "c",
        }
    ]


def test_acg_view_recovery_trace_after_fault_injection():
    client = _client()
    task = client.post(
        "/ai/core/tasks",
        json={
            "title": "demo",
            "domain": "demo",
            "intent": "demo",
            "input": {"faultInjection": {"step_id": "b", "fault_type": "timeout", "max_triggers": 1}},
        },
    ).json()
    run = client.post(
        "/ai/core/workflows/runs", json={"taskId": task["taskId"], "workflowId": "demo_acg"}
    ).json()
    # 自愈后仍完成
    assert run["status"] == "completed"

    view = client.get(f"/ai/core/workflows/runs/{run['runId']}/acg").json()
    # 恢复轨迹应包含 run_recovered（local_replan）
    recovery = view["recoveryTrace"]
    assert any(e["eventType"] == "run_recovered" for e in recovery)
    assert view["lowEntropyMetrics"]["recoveryCount"] >= 1


def test_acg_view_404_for_unknown_run():
    client = _client()
    assert client.get("/ai/core/workflows/runs/nonexistent/acg").status_code == 404


def test_runtime_audit_projection_redacts_sensitive_fields_and_bounds_text():
    projected = _safe_runtime_projection(
        {
            "reasonCode": "SAFE_REASON",
            "authorization": "Bearer secret",
            "nested": {"apiKey": "secret-key", "details": "x" * 2500},
        }
    )

    assert projected["reasonCode"] == "SAFE_REASON"
    assert projected["authorization"] == "[redacted]"
    assert projected["nested"]["apiKey"] == "[redacted]"
    assert len(projected["nested"]["details"]) < 2100

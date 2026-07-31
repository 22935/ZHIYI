import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.agents import AgentRegistry
from agentos.core.models.types import ReviewDecision, ReviewDecisionType, StepStatus, WorkflowStatus
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from app.api.agentos_core import create_router
from app.execution.runtime import configure_runtime
from app.llm.config import LLMConfig
from app.llm.gateway import LLMGateway, set_llm_gateway_for_tests
from packs.legal import register_pack as register_legal_pack


def _runtime() -> WorkflowRuntime:
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    register_legal_pack(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        capability_catalog=runtime.capability_catalog,
    )
    return configure_runtime(runtime)


async def _start(runtime: WorkflowRuntime):
    task = runtime.create_task(
        title="合同审查",
        domain="legal",
        intent="contract_review",
        input={"source": "test", "contractText": "甲方委托乙方开发 CRM，签署后付款 30%，上线后付款 70%。"},
    )
    return await runtime.start(task.task_id, workflow_id="legal_contract_review_v1", review_mode="human_in_loop")


def test_canonical_contract_review_runs_on_acg_and_waits_for_review():
    async def run_test():
        run = await _start(runtime)
        assert run.workflow_id == "legal_contract_review_v1"
        assert run.runtime_engine == "acg"
        assert run.implementation_id == "legal_contract_review_v1"
        assert run.status == WorkflowStatus.WAITING_REVIEW
        assert run.current_step_id == "human_review"
        assert run.get_step("human_review").status == StepStatus.WAITING_REVIEW
        artifacts = run.output["artifacts"]
        assert artifacts["parse_contract"]["contract_type"]
        assert artifacts["risk_detect"]["risks"]
        assert artifacts["legal_evidence_match"]["evidences"]
        assert "suggestion_generate" in artifacts
        assert "report_generate" not in artifacts
        assert run.acg_blueprint is not None
        assert runtime.list_checkpoints(run.run_id)

    runtime = _runtime()
    asyncio.run(run_test())


def test_acg_contract_review_approve_reject_and_need_more_info():
    async def run_test():
        runtime = _runtime()
        waiting = await _start(runtime)
        more = await runtime.apply_review(ReviewDecision(
            runId=waiting.run_id, stepId="human_review", decision=ReviewDecisionType.NEED_MORE_INFO,
            reviewer="reviewer", comment="请补充验收附件",
        ))
        assert more.status == WorkflowStatus.WAITING_REVIEW
        rejected = await runtime.apply_review(ReviewDecision(
            runId=more.run_id, stepId="human_review", decision=ReviewDecisionType.REJECTED,
            reviewer="reviewer", comment="驳回",
        ))
        assert rejected.status == WorkflowStatus.FAILED

        approved_waiting = await _start(runtime)
        completed = await runtime.apply_review(ReviewDecision(
            runId=approved_waiting.run_id, stepId="human_review", decision=ReviewDecisionType.APPROVED,
            reviewer="reviewer", comment="通过",
        ))
        assert completed.status == WorkflowStatus.COMPLETED
        assert completed.get_step("report_generate").status == StepStatus.COMPLETED
        artifacts = completed.output["artifacts"]
        report = artifacts["report_generate"]["report_markdown"]
        assert report
        assert "不构成最终法律意见" in report
        assert "Evidence 依据链" in report
        assert "审核意见：通过" in report
        assert artifacts["risk_detect"]["risks"]
        assert artifacts["legal_evidence_match"]["evidences"]

    asyncio.run(run_test())


class _InvalidJSONProvider:
    provider_name = "invalid-json"
    model = "invalid-json"

    def generate_text(self, prompt: str, **kwargs):
        return "invalid"

    def generate_json(self, prompt: str, schema: dict, **kwargs):
        return {"invalid": True}


def test_acg_contract_review_invalid_llm_json_fails_closed_without_invented_results():
    async def run_test():
        runtime = _runtime()
        waiting = await _start(runtime)
        assert waiting.recovery_count == 2
        assert {item["stepId"] for item in waiting.execution_state["degradedSteps"]} == {
            "parse_contract",
            "risk_detect",
        }
        run = await runtime.apply_review(ReviewDecision(
            runId=waiting.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.APPROVED,
            reviewer="reviewer",
        ))
        parse = run.output["artifacts"]["parse_contract"]
        risks = run.output["artifacts"]["risk_detect"]
        assert parse["contract_type"] == ""
        assert parse["parties"] == []
        assert parse["analysis_status"] == "unavailable"
        assert risks["risks"] == []
        assert risks["analysis_status"] == "unavailable"
        assert parse["_llm"]["source"] == "fallback"
        assert risks["_llm"]["source"] == "fallback"
        assert run.recovery_count == 3
        assert {item["stepId"] for item in run.execution_state["degradedSteps"]} == {
            "parse_contract",
            "risk_detect",
            "report_generate",
        }
        assert "3 次降级恢复" in run.lifecycle_message

    set_llm_gateway_for_tests(LLMGateway(provider=_InvalidJSONProvider()))
    try:
        asyncio.run(run_test())
    finally:
        set_llm_gateway_for_tests(None)


def test_acg_contract_review_partial_retrieval_does_not_fabricate_evidence(monkeypatch):
    from packs.legal.agents import contract_review_migration as migration

    class _PartialFailureRetriever:
        def __init__(self):
            self.calls = 0

        def retrieve(self, *, risk, contract_type, top_k):
            self.calls += 1
            if self.calls == 1:
                return [{
                    "id": "ev-live-01",
                    "stepId": "legal_evidence_match",
                    "riskId": str(risk.get("id") or ""),
                    "sourceType": "law",
                    "sourceName": "测试法律知识库",
                    "content": "测试依据",
                    "citationText": "第一项风险的真实检索依据。",
                    "confidence": 0.9,
                }]
            raise RuntimeError("partial retrieval failure")

    class _TwoRiskProvider(_InvalidJSONProvider):
        def generate_json(self, prompt: str, schema: dict, **kwargs):
            from app.llm.schemas import compact_schema_name

            if compact_schema_name(schema) != "risk_detect":
                return super().generate_json(prompt, schema, **kwargs)
            return {
                "risks": [
                    {
                        "id": f"risk-test-{index}",
                        "title": "付款安排需要复核",
                        "level": "high",
                        "clause": "测试条款",
                        "reason": "测试原因",
                        "consequence": "测试后果",
                        "suggestion": "测试建议",
                        "evidenceIds": [],
                    }
                    for index in (1, 2)
                ]
            }

    monkeypatch.setattr(migration, "LegalEvidenceRetriever", _PartialFailureRetriever)
    set_llm_gateway_for_tests(LLMGateway(provider=_TwoRiskProvider()))
    try:
        run = asyncio.run(_start(_runtime()))
    finally:
        set_llm_gateway_for_tests(None)

    evidence_output = run.output["artifacts"]["legal_evidence_match"]
    assert [item.get("riskId") for item in evidence_output["evidences"]] == ["risk-test-1"]
    assert evidence_output["retrieval"]["status"] == "incomplete"
    assert evidence_output["retrieval"]["unmatched_risk_ids"] == ["risk-test-2"]
    assert len(evidence_output["retrieval"]["errors"]) == 1
    assert all(item.get("sourceType") != "mock" for item in evidence_output["evidences"])


def test_acg_contract_review_api_trace_checkpoint_and_metrics():
    runtime = _runtime()
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)
    started = client.post("/ai/core/workflows/start", json={
        "title": "合同审查", "domain": "legal", "intent": "contract_review",
        "workflowId": "legal_contract_review_v1", "reviewMode": "human_in_loop",
        "input": {"contractText": "甲方委托乙方开发 CRM。"},
    }).json()["run"]
    assert started["runtimeEngine"] == "acg"
    assert "implementationId" in started
    run_id = started["runId"]
    assert client.get(f"/ai/core/workflows/runs/{run_id}/trace").json()["workflowId"] == "legal_contract_review_v1"
    assert client.get(f"/ai/core/workflows/runs/{run_id}/checkpoints").json()["total"] >= 1
    view = client.get(f"/ai/core/workflows/runs/{run_id}/acg").json()
    assert view["engine"] == "acg"
    assert view["acgBlueprint"]["nodes"]
    assert client.get("/ai/core/workflows/metrics", params={"workflowId": "legal_contract_review_v1"}).json()["workflowId"] == "legal_contract_review_v1"


def test_llm_gateway_without_complete_configuration_is_unavailable():
    gateway = LLMGateway(config=LLMConfig(provider="openai-compatible", base_url="", api_key="", model=""))
    assert gateway.provider_name == "unavailable"


def test_llm_config_reads_provider_key_from_secret_file(monkeypatch, tmp_path):
    secret = tmp_path / "deepseek_api_key"
    secret.write_text("test-secret", encoding="utf-8")
    monkeypatch.delenv("AGENTOS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY_FILE", str(secret))

    config = LLMConfig.from_env()

    assert config.provider == "openai-compatible"
    assert config.api_key == "test-secret"
    assert config.base_url == "https://api.deepseek.com/v1"


def test_force_dynamic_contract_review_builds_executable_data_dependencies():
    async def run_test():
        runtime = _runtime()
        task = runtime.create_task(
            title="动态合同审查",
            domain="legal",
            intent="contract_review_acg",
            input={
                "contractText": "甲方委托乙方开发 CRM，签署后付款 30%，上线后付款 70%。",
                "userIntent": (
                    "解析合同并进行条款分类，识别付款、验收和知识产权风险，"
                    "检索证据依据，生成修改建议、人工审核要点和最终报告。"
                ),
                "usePlanner": True,
                "forceDynamicPlanning": True,
                "thinkingMode": "disabled",
            },
        )
        run = await runtime.start(
            task.task_id,
            workflow_id="legal_contract_review_v1",
            review_mode="auto",
        )

        assert run.status == WorkflowStatus.COMPLETED
        assert run.steps
        artifacts = run.output["artifacts"]
        assert artifacts["risk_detect"]["risks"]
        assert artifacts["legal_evidence_match"]["evidences"]
        report_artifact = artifacts["report_generate"]
        assert report_artifact["report_markdown"]
        assert report_artifact["_llm"]["source"] == "deterministic"
        assert report_artifact["_llm"]["latency_ms"] == 0
        assert "条款分类摘要" in report_artifact["report_markdown"]
        assert "签署前处理结论" in report_artifact["report_markdown"]
        blueprint = run.acg_blueprint
        assert blueprint is not None
        nodes = blueprint["nodes"]
        edges = blueprint["edges"]
        assert sum(node["nodeType"] == "step" for node in nodes) == 7
        assert all(node["nodeType"] != "skill" for node in nodes)
        assert all(
            "allowedSkills" not in node.get("metadata", {})
            for node in nodes
            if node["nodeType"] == "step"
        )
        assert run.runtime_graph is not None
        runtime_steps = [
            node for node in run.runtime_graph.nodes if node.node_type.value == "step"
        ]
        assert all(node.current_binding.get("allowedSkills") for node in runtime_steps)
        review_node = next(node for node in nodes if node["nodeId"] == "human_review")
        assert review_node["reviewRequired"] is True
        connected_ids = {
            node_id
            for edge in edges
            for node_id in (edge["sourceId"], edge["targetId"])
        }
        assert {node["nodeId"] for node in nodes}.issubset(connected_ids)
        planner = next(
            event for event in run.trace
            if event.event_type.value == "task_status_changed" and "Planner" in event.observation
        )
        assert planner.payload["strategy"] == "dynamic_generation"

        schedule = [event.payload["batch"] for event in run.trace if event.event_type.value == "step_scheduled"]
        classify_round = next(index for index, batch in enumerate(schedule) if "clause_classify" in batch)
        risk_round = next(index for index, batch in enumerate(schedule) if "risk_detect" in batch)
        assert classify_round < risk_round

    asyncio.run(run_test())


def test_force_dynamic_review_preserves_deep_thinking_until_report():
    async def run_test():
        runtime = _runtime()
        task = runtime.create_task(
            title="复杂合同深度审查",
            domain="legal",
            intent="contract_review_acg",
            input={
                "contractText": "甲方委托乙方开发跨境数据处理系统，并约定分阶段付款与验收。",
                "userIntent": "解析合同、分类条款、识别风险、匹配依据、提出建议、人工审核并生成报告。",
                "usePlanner": True,
                "forceDynamicPlanning": True,
                "thinkingMode": "deep",
            },
        )

        waiting = await runtime.start(
            task.task_id,
            workflow_id="legal_contract_review_v1",
            review_mode="human_in_loop",
        )
        assert waiting.status == WorkflowStatus.WAITING_REVIEW
        assert waiting.current_step_id == "human_review"
        assert waiting.output["artifacts"]["contract_parse"]["_llm"]["thinking_mode"] == "deep"
        planner = next(
            event for event in waiting.trace
            if event.event_type.value == "task_status_changed" and "Planner" in event.observation
        )
        assert planner.payload["thinkingMode"] == "deep"

        completed = await runtime.apply_review(ReviewDecision(
            runId=waiting.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.APPROVED,
            reviewer="reviewer",
            comment="通过",
        ))
        assert completed.status == WorkflowStatus.COMPLETED
        assert completed.output["artifacts"]["report_generate"]["_llm"]["thinking_mode"] == "deep"

    asyncio.run(run_test())

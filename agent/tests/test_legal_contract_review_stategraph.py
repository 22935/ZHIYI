import asyncio

from app.llm.config import LLMConfig
from app.llm.gateway import LLMGateway, set_llm_gateway_for_tests
from app.rag import LegalDocumentLoader, LegalTextSplitter
from app.rag.providers.keyword_retriever import KeywordLegalEvidenceRetriever
from agentos.agents import AgentRegistry
from agentos.core.types import ReviewDecision, ReviewDecisionType, StepStatus, WorkflowStatus
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from packs.legal import register_pack as register_legal_pack


def _runtime() -> WorkflowRuntime:
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()
    register_legal_pack(agent_registry=agent_registry, workflow_registry=workflow_registry)
    return WorkflowRuntime(agent_registry=agent_registry, workflow_registry=workflow_registry)


async def _start_stategraph_run(runtime: WorkflowRuntime):
    task = runtime.create_task(
        title="软件开发服务合同审查",
        domain="legal",
        intent="contract_review_stategraph",
        input={
            "source": "workbench",
            "contractText": "甲方委托乙方开发 CRM 系统，签署后支付 30%，上线后支付 70%。",
        },
    )
    return await runtime.start(
        task_id=task.task_id,
        workflow_id="legal_contract_review_stategraph_v1",
        review_mode="human_in_loop",
    )


def test_stategraph_contract_review_starts_and_waits_for_human_review():
    asyncio.run(_test_stategraph_contract_review_starts_and_waits_for_human_review())


async def _test_stategraph_contract_review_starts_and_waits_for_human_review():
    runtime = _runtime()
    run = await _start_stategraph_run(runtime)

    assert run.workflow_id == "legal_contract_review_stategraph_v1"
    assert run.status == WorkflowStatus.WAITING_REVIEW
    assert run.current_step_id == "human_review"
    assert run.get_step("human_review").status == StepStatus.WAITING_REVIEW
    assert run.get_step("report_generate").status == StepStatus.PENDING

    artifacts = run.output["artifacts"]
    assert artifacts["parse_contract"]["contract_type"]
    assert len(artifacts["risk_detect"]["risks"]) == 3
    evidences = artifacts["legal_evidence_match"]["evidences"]
    assert len(evidences) >= 3
    assert all(item["riskId"] for item in evidences)
    assert all(item["sourceType"] for item in evidences)
    assert all(item["sourceName"] for item in evidences)
    assert all(item["citationText"] for item in evidences)
    assert all("retrievalScore" in item for item in evidences)
    assert "report_generate" not in artifacts
    assert runtime.list_checkpoints(run.run_id)
    assert runtime.trace_store.export_json(run)["eventCount"] >= 1
    trace_payloads = [event.payload for event in run.trace]
    assert any(payload.get("node_name") == "parse_contract" and payload.get("source") == "mock" for payload in trace_payloads)
    assert any(payload.get("node_name") == "risk_detect" and payload.get("source") == "mock" for payload in trace_payloads)


def test_stategraph_contract_review_approved_resumes_and_generates_report():
    asyncio.run(_test_stategraph_contract_review_approved_resumes_and_generates_report())


async def _test_stategraph_contract_review_approved_resumes_and_generates_report():
    runtime = _runtime()
    run = await _start_stategraph_run(runtime)

    completed = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.APPROVED,
            reviewer="legal_reviewer",
            comment="风险结论可以进入报告生成。",
        )
    )

    assert completed.status == WorkflowStatus.COMPLETED
    assert completed.current_step_id is None
    assert completed.get_step("human_review").status == StepStatus.COMPLETED
    assert completed.get_step("report_generate").status == StepStatus.COMPLETED

    artifacts = completed.output["artifacts"]
    assert len(artifacts["risk_detect"]["risks"]) == 3
    assert len(artifacts["legal_evidence_match"]["evidences"]) >= 3
    assert "软件开发服务合同审查报告" in artifacts["report_generate"]["report_markdown"]
    assert "未接入正式法律法规 RAG" in artifacts["report_generate"]["report_markdown"]
    assert "Evidence 依据链" in artifacts["report_generate"]["report_markdown"]
    assert artifacts["legal_evidence_match"]["evidences"][0]["citationText"] in artifacts["report_generate"]["report_markdown"]
    assert all(
        not item.get("metadata", {}).get("articleNo")
        for item in artifacts["legal_evidence_match"]["evidences"]
    )
    assert any(
        event.payload.get("node_name") == "report_generate" and event.payload.get("source") == "mock"
        for event in completed.trace
    )


def test_stategraph_contract_review_rejected_does_not_generate_report():
    asyncio.run(_test_stategraph_contract_review_rejected_does_not_generate_report())


async def _test_stategraph_contract_review_rejected_does_not_generate_report():
    runtime = _runtime()
    run = await _start_stategraph_run(runtime)

    rejected = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.REJECTED,
            reviewer="legal_reviewer",
            comment="风险结论不足，驳回。",
        )
    )

    assert rejected.status == WorkflowStatus.FAILED
    assert rejected.current_step_id == "human_review"
    assert "report_generate" not in rejected.output["artifacts"]


def test_stategraph_contract_review_need_more_info_does_not_generate_report():
    asyncio.run(_test_stategraph_contract_review_need_more_info_does_not_generate_report())


async def _test_stategraph_contract_review_need_more_info_does_not_generate_report():
    runtime = _runtime()
    run = await _start_stategraph_run(runtime)

    waiting = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.NEED_MORE_INFO,
            reviewer="legal_reviewer",
            comment="需要补充验收附件。",
        )
    )

    assert waiting.status == WorkflowStatus.WAITING_REVIEW
    assert waiting.current_step_id == "human_review"
    assert waiting.get_step("report_generate").status == StepStatus.PENDING
    assert "report_generate" not in waiting.output["artifacts"]


def test_stategraph_contract_review_unsupported_review_decision_is_explicit():
    asyncio.run(_test_stategraph_contract_review_unsupported_review_decision_is_explicit())


async def _test_stategraph_contract_review_unsupported_review_decision_is_explicit():
    runtime = _runtime()
    run = await _start_stategraph_run(runtime)

    try:
        await runtime.apply_review(
            ReviewDecision(
                runId=run.run_id,
                stepId="human_review",
                decision=ReviewDecisionType.CANCELLED,
                reviewer="legal_reviewer",
                comment="取消。",
            )
        )
    except ValueError as exc:
        assert "Unsupported review decision" in str(exc)
    else:
        raise AssertionError("cancelled should be explicit unsupported for stategraph contract review")


def test_stategraph_contract_review_artifact_paths():
    asyncio.run(_test_stategraph_contract_review_artifact_paths())


async def _test_stategraph_contract_review_artifact_paths():
    runtime = _runtime()
    run = await _start_stategraph_run(runtime)
    completed = await runtime.apply_review(
        ReviewDecision(
            runId=run.run_id,
            stepId="human_review",
            decision=ReviewDecisionType.APPROVED,
            reviewer="legal_reviewer",
            comment="通过。",
        )
    )

    output = completed.output
    assert output["artifacts"]["risk_detect"]["risks"]
    assert output["artifacts"]["legal_evidence_match"]["evidences"]
    assert output["artifacts"]["report_generate"]["report_markdown"]


class _InvalidJSONProvider:
    provider_name = "invalid-json-provider"
    model = "invalid-json-model"

    def generate_text(self, prompt: str, **kwargs):
        return "not-json"

    def generate_json(self, prompt: str, schema: dict, **kwargs):
        return {"invalid": True}


def test_stategraph_contract_review_invalid_llm_json_falls_back_to_mock():
    asyncio.run(_test_stategraph_contract_review_invalid_llm_json_falls_back_to_mock())


async def _test_stategraph_contract_review_invalid_llm_json_falls_back_to_mock():
    set_llm_gateway_for_tests(LLMGateway(provider=_InvalidJSONProvider()))
    try:
        runtime = _runtime()
        run = await _start_stategraph_run(runtime)
        assert run.output["artifacts"]["parse_contract"]["contract_type"] == "软件开发服务合同"
        assert run.output["artifacts"]["risk_detect"]["risks"]
        assert any(
            event.payload.get("node_name") == "parse_contract" and event.payload.get("source") == "mock_fallback"
            for event in run.trace
        )
        completed = await runtime.apply_review(
            ReviewDecision(
                runId=run.run_id,
                stepId="human_review",
                decision=ReviewDecisionType.APPROVED,
                reviewer="legal_reviewer",
                comment="通过。",
            )
        )
        assert completed.output["artifacts"]["report_generate"]["report_markdown"]
        assert any(
            event.payload.get("node_name") == "report_generate" and event.payload.get("source") == "mock_fallback"
            for event in completed.trace
        )
    finally:
        set_llm_gateway_for_tests(None)


def test_llm_gateway_missing_openai_compatible_config_falls_back_to_mock():
    gateway = LLMGateway(
        config=LLMConfig(
            provider="openai-compatible",
            base_url="",
            api_key="",
            model="",
            timeout_seconds=30,
        )
    )
    assert gateway.provider_name == "mock"


def test_legal_document_loader_and_splitter_load_local_knowledge():
    documents = LegalDocumentLoader().load()
    assert documents
    assert any("演示资料" in document.content for document in documents)

    chunks = LegalTextSplitter().split(documents)
    assert chunks
    assert all(chunk.content for chunk in chunks)


def test_keyword_retriever_returns_evidence():
    chunks = LegalTextSplitter().split(LegalDocumentLoader().load())
    retriever = KeywordLegalEvidenceRetriever(chunks=chunks)
    results = retriever.retrieve(
        risk={
            "id": "risk-payment-01",
            "title": "尾款支付条件过于单一",
            "clause": "系统上线后支付 70%。",
            "reason": "缺少验收、缺陷修复和发票条件。",
        },
        contract_type="软件开发服务合同",
        top_k=2,
    )

    assert results
    assert all(item["riskId"] == "risk-payment-01" for item in results)
    assert all(item["sourceType"] in {"law", "template", "internal_rule"} for item in results)
    assert all(item["sourceName"] for item in results)
    assert all(item["citationText"] for item in results)
    assert all(item["retrievalScore"] > 0 for item in results)


def test_legal_evidence_match_falls_back_when_retriever_has_no_results(monkeypatch):
    from app.graphs import legal_contract_review_stategraph as graph_module

    class _EmptyRetriever:
        def retrieve(self, *, risk, contract_type="", top_k=2):
            return []

    monkeypatch.setattr(graph_module, "LegalEvidenceRetriever", lambda: _EmptyRetriever())
    state = {
        "run_id": "run-test",
        "workflow_id": "legal_contract_review_stategraph_v1",
        "contract_text": "",
        "steps": {},
        "risks": [{"id": "risk-empty-01", "title": "完全无匹配风险", "reason": "无关键词"}],
        "evidences": [],
        "traces": [],
        "review": {},
        "artifacts": {"parse_contract": {"contract_type": "unknown"}},
    }

    result = graph_module.legal_evidence_match_node(state)
    evidences = result["artifacts"]["legal_evidence_match"]["evidences"]
    assert evidences
    assert evidences[0]["riskId"] == "risk-empty-01"
    assert evidences[0]["sourceType"] == "mock"
    assert result["traces"][-1]["payload"]["retriever_type"] == "keyword"
    assert result["traces"][-1]["payload"]["fallback"] is True
    assert result["traces"][-1]["payload"]["result_count"] == len(evidences)


def test_stategraph_contract_review_api_start_review_resume_flow():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.agentos_core import create_router

    runtime = _runtime()
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")
    client = TestClient(app)

    start_response = client.post(
        "/ai/core/workflows/start",
        json={
            "title": "软件开发服务合同审查",
            "domain": "legal",
            "intent": "contract_review_stategraph",
            "workflowId": "legal_contract_review_stategraph_v1",
            "reviewMode": "human_in_loop",
            "input": {"source": "workbench", "contractText": "甲方委托乙方开发 CRM 系统。"},
        },
    )
    assert start_response.status_code == 200
    run_payload = start_response.json()["run"]
    assert run_payload["status"] == "waiting_review"
    assert run_payload["currentStepId"] == "human_review"

    review_response = client.post(
        f"/ai/core/workflows/runs/{run_payload['runId']}/reviews",
        json={
            "stepId": "human_review",
            "decision": "approved",
            "reviewer": "api_reviewer",
            "comment": "通过。",
        },
    )
    assert review_response.status_code == 200
    completed = review_response.json()
    assert completed["status"] == "completed"
    assert completed["output"]["artifacts"]["report_generate"]["report_markdown"]

    trace_response = client.get(f"/ai/core/workflows/runs/{run_payload['runId']}/trace")
    assert trace_response.status_code == 200
    assert trace_response.json()["workflowId"] == "legal_contract_review_stategraph_v1"

    checkpoints_response = client.get(f"/ai/core/workflows/runs/{run_payload['runId']}/checkpoints")
    assert checkpoints_response.status_code == 200
    assert checkpoints_response.json()["total"] >= 1

    metrics_response = client.get(
        "/ai/core/workflows/metrics",
        params={"workflowId": "legal_contract_review_stategraph_v1"},
    )
    assert metrics_response.status_code == 200
    assert metrics_response.json()["workflowId"] == "legal_contract_review_stategraph_v1"

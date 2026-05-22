from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from app.llm.gateway import get_llm_gateway
from app.llm.prompts import (
    render_parse_contract_prompt,
    render_report_generate_prompt,
    render_risk_detect_prompt,
)
from app.llm.schemas import PARSE_CONTRACT_SCHEMA, REPORT_GENERATE_SCHEMA, RISK_DETECT_SCHEMA
from app.rag import LegalEvidenceRetriever
from app.rag.legal_evidence_schema import normalize_evidence
from agentos.core.checkpoint import CheckpointStore
from agentos.core.review import ReviewManager
from agentos.core.trace import TraceStore
from agentos.core.types import (
    AgentTask,
    ReviewDecision,
    ReviewDecisionType,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStep,
    WorkflowStatus,
    utc_now,
)
from agentos.stores.workflow_store import WorkflowStore


WORKFLOW_ID = "legal_contract_review_stategraph_v1"


class ContractReviewState(TypedDict, total=False):
    run_id: str
    workflow_id: str
    contract_text: str
    current_step: Optional[str]
    status: str
    steps: Dict[str, Dict[str, Any]]
    risks: List[Dict[str, Any]]
    evidences: List[Dict[str, Any]]
    traces: List[Dict[str, Any]]
    review: Dict[str, Any]
    artifacts: Dict[str, Any]
    report_markdown: str
    error: Optional[str]


STEP_SEQUENCE = [
    "parse_contract",
    "classify_clauses",
    "risk_detect",
    "legal_evidence_match",
    "suggestion_generate",
    "human_review",
    "report_generate",
]


def _copy_state(state: ContractReviewState) -> ContractReviewState:
    return deepcopy(dict(state))


def _append_trace(
    state: ContractReviewState,
    *,
    step_id: str,
    event_type: str,
    observation: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    traces = list(state.get("traces", []))
    traces.append(
        {
            "eventType": event_type,
            "stepId": step_id,
            "agentName": step_id,
            "observation": observation,
            "payload": payload or {},
        }
    )
    state["traces"] = traces


def _set_step(
    state: ContractReviewState,
    step_id: str,
    status: str,
    output: Optional[Dict[str, Any]] = None,
) -> None:
    steps = dict(state.get("steps", {}))
    step = dict(steps.get(step_id, {}))
    step["status"] = status
    if output is not None:
        step["output"] = output
    steps[step_id] = step
    state["steps"] = steps
    state["current_step"] = step_id


def _artifacts(state: ContractReviewState) -> Dict[str, Any]:
    artifacts = dict(state.get("artifacts", {}))
    state["artifacts"] = artifacts
    return artifacts


def _llm_trace_payload(
    *,
    node_name: str,
    provider: str,
    model: str,
    source: str,
    success: bool,
    latency_ms: int = 0,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "node_name": node_name,
        "provider": provider,
        "model": model,
        "source": source,
        "success": success,
        "latency_ms": max(0, int(latency_ms or 0)),
    }
    if error:
        payload["error"] = str(error)[:240]
    return payload


def _gateway_json_or_fallback(
    *,
    node_name: str,
    prompt: str,
    schema: Dict[str, Any],
    fallback: Dict[str, Any],
    validator,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    gateway = get_llm_gateway()
    try:
        response = gateway.generate_json(prompt, schema)
        data = validator(response.get("data", {}))
        provider = str(response.get("provider") or gateway.provider_name)
        source = "mock" if provider == "mock" else "llm"
        return data, _llm_trace_payload(
            node_name=node_name,
            provider=provider,
            model=str(response.get("model") or gateway.model),
            source=source,
            success=True,
            latency_ms=int(response.get("latency_ms") or 0),
        )
    except Exception as exc:
        return fallback, _llm_trace_payload(
            node_name=node_name,
            provider=getattr(gateway, "provider_name", "unknown"),
            model=getattr(gateway, "model", "unknown"),
            source="mock_fallback",
            success=False,
            error=str(exc),
        )


def _validate_parse_contract_output(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("parse_contract output must be an object")
    parties = data.get("parties")
    if not isinstance(parties, list):
        raise ValueError("parse_contract.parties must be a list")
    return {
        "contract_title": str(data.get("contract_title") or "unknown"),
        "parties": [
            {
                "name": str(item.get("name") or "unknown") if isinstance(item, dict) else "unknown",
                "role": str(item.get("role") or "unknown") if isinstance(item, dict) else "unknown",
            }
            for item in parties
        ],
        "contract_type": str(data.get("contract_type") or "unknown"),
        "key_dates": data.get("key_dates") if isinstance(data.get("key_dates"), list) else [],
        "amounts": data.get("amounts") if isinstance(data.get("amounts"), list) else [],
        "obligations": data.get("obligations") if isinstance(data.get("obligations"), list) else [],
        "summary": str(data.get("summary") or "unknown"),
    }


def _validate_risk_detect_output(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("risks"), list):
        raise ValueError("risk_detect output must contain risks list")
    risks: List[Dict[str, Any]] = []
    for index, item in enumerate(data["risks"], start=1):
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or "medium").lower()
        if level not in {"high", "medium", "low"}:
            level = "medium"
        risks.append(
            {
                "id": str(item.get("id") or f"risk-{index:02d}"),
                "title": str(item.get("title") or "未命名风险"),
                "level": level,
                "clause": str(item.get("clause") or ""),
                "reason": str(item.get("reason") or "基于合同文本本身，风险原因待补充。"),
                "consequence": str(item.get("consequence") or ""),
                "suggestion": str(item.get("suggestion") or ""),
                "evidenceIds": [],
            }
        )
    if not risks:
        raise ValueError("risk_detect risks list is empty")
    return {"risks": risks}


def _validate_report_generate_output(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("report_markdown"), str):
        raise ValueError("report_generate output must contain report_markdown")
    report = data["report_markdown"].strip()
    if not report:
        raise ValueError("report_markdown is empty")
    disclaimer = "当前报告未接入正式法律法规 RAG，法律依据部分仅为演示或待补充；本报告不构成最终法律意见，需律师复核。"
    if "未接入正式法律法规 RAG" not in report:
        report = f"{report.rstrip()}\n\n## 免责声明\n{disclaimer}\n"
    return {"report_markdown": report}


def _mock_parse_contract_output(text: str) -> Dict[str, Any]:
    return {
        "contract_title": "软件开发服务合同",
        "parties": [
            {"name": "甲方", "role": "委托方"},
            {"name": "乙方", "role": "开发服务方"},
        ],
        "contract_type": "软件开发服务合同",
        "key_dates": [],
        "amounts": ["签署后 30%", "上线后 70%"],
        "obligations": ["开发 CRM 系统", "完成上线交付", "配合验收"],
        "summary": (text[:220] if text else "未提供合同文本。"),
    }


def _risk_items() -> List[Dict[str, Any]]:
    return [
        {
            "id": "risk-payment-01",
            "title": "尾款支付条件过于单一",
            "level": "high",
            "clause": "合同签署后支付 30%，系统上线后支付 70%。",
            "reason": "尾款触发条件只绑定上线，缺少验收、缺陷修复、发票和上线失败处理。",
            "consequence": "上线后仍存在严重缺陷时，付款与整改责任容易发生争议。",
            "suggestion": "",
            "evidenceIds": ["ev-payment-01", "ev-acceptance-01"],
        },
        {
            "id": "risk-acceptance-01",
            "title": "验收标准缺少客观指标",
            "level": "medium",
            "clause": "如无重大问题视为验收通过。",
            "reason": "重大问题没有定义，也未写明验收材料、测试用例、反馈期限和整改次数。",
            "consequence": "双方可能对缺陷严重程度、是否通过验收和延期责任产生争议。",
            "suggestion": "",
            "evidenceIds": ["ev-acceptance-01"],
        },
        {
            "id": "risk-ip-01",
            "title": "知识产权共同所有安排不清",
            "level": "high",
            "clause": "项目源代码归双方共同所有。",
            "reason": "共同所有未说明使用、转让、二次开发、开源组件和第三方素材的授权边界。",
            "consequence": "后续商业化、系统迭代或对外交付源码时可能产生权属冲突。",
            "suggestion": "",
            "evidenceIds": ["ev-ip-01"],
        },
    ]


def _evidence_items() -> List[Dict[str, Any]]:
    items = [
        {
            "id": "ev-payment-01",
            "stepId": "legal_evidence_match",
            "riskId": "risk-payment-01",
            "sourceType": "mock",
            "sourceName": "演示依据，待 RAG 接入",
            "title": "软件开发合同审查模板库",
            "content": "付款节点通常应与里程碑、阶段验收和缺陷修复期绑定。",
            "citationText": "付款条款应明确付款比例、触发条件、发票条件与逾期处理。",
            "chunkId": "",
            "confidence": 0.92,
            "retrievalScore": 0.0,
            "metadata": {"lawName": "", "articleNo": "", "sourcePath": "", "demo": True},
        },
        {
            "id": "ev-acceptance-01",
            "stepId": "legal_evidence_match",
            "riskId": "risk-acceptance-01",
            "sourceType": "mock",
            "sourceName": "演示依据，待 RAG 接入",
            "title": "技术服务项目验收审查要点",
            "content": "仅以无重大问题作为验收标准，容易造成缺陷范围和整改期限争议。",
            "citationText": "验收条款宜列明验收材料、测试标准、反馈期限和最终确认方式。",
            "chunkId": "",
            "confidence": 0.89,
            "retrievalScore": 0.0,
            "metadata": {"lawName": "", "articleNo": "", "sourcePath": "", "demo": True},
        },
        {
            "id": "ev-ip-01",
            "stepId": "legal_evidence_match",
            "riskId": "risk-ip-01",
            "sourceType": "mock",
            "sourceName": "演示依据，待 RAG 接入",
            "title": "民法典合同编与著作权相关规则",
            "content": "定制开发成果权属应结合委托目的、费用结构和源码交付明确约定。",
            "citationText": "知识产权归属、使用范围、源码交付和开源组件合规应分别约定。",
            "chunkId": "",
            "confidence": 0.9,
            "retrievalScore": 0.0,
            "metadata": {"lawName": "", "articleNo": "", "sourcePath": "", "demo": True},
        },
    ]
    return [normalize_evidence(item, risk_id=str(item.get("riskId") or "")) for item in items]


def _fallback_evidence_for_risk(risk: Dict[str, Any], index: int) -> Dict[str, Any]:
    fallback_items = _evidence_items()
    risk_id = str(risk.get("id") or f"risk-{index:02d}")
    matched = next((item for item in fallback_items if item.get("riskId") == risk_id), None)
    if matched is None:
        matched = fallback_items[(index - 1) % len(fallback_items)]
    item = dict(matched)
    item["id"] = str(item.get("id") or f"ev-mock-{index:02d}")
    item["riskId"] = risk_id
    item["sourceType"] = "mock"
    item["sourceName"] = "演示依据，待正式法律知识库校验"
    item["metadata"] = {"lawName": "", "articleNo": "", "sourcePath": "", "demo": True}
    return normalize_evidence(item, risk_id=risk_id)


def _evidence_trace_payload(
    *,
    result_count: int,
    fallback: bool,
    error: Optional[str] = None,
    top_k: int = 2,
) -> Dict[str, Any]:
    payload = {
        "retriever_type": "keyword",
        "top_k": top_k,
        "result_count": result_count,
        "fallback": fallback,
    }
    if error:
        payload["error"] = str(error)[:240]
    return payload


def _append_evidence_appendix(report: str, evidences: List[Dict[str, Any]]) -> str:
    if not evidences:
        return report
    if "Evidence 依据链" in report and any(str(item.get("citationText") or "") in report for item in evidences):
        return report
    lines = ["", "## Evidence 依据链"]
    for index, item in enumerate(evidences, start=1):
        marker = ""
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if item.get("sourceType") == "mock" or metadata.get("demo"):
            marker = "（演示依据 / 待正式法律知识库校验）"
        lines.append(
            f"{index}. [{item.get('sourceType')}] {item.get('sourceName')} {marker}：{item.get('citationText')}"
        )
    return f"{report.rstrip()}\n" + "\n".join(lines) + "\n"


def parse_contract_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    text = state.get("contract_text", "")
    output = {
        "contract_summary": text[:500] or "未提供合同文本。",
        "contract_type": "软件开发服务合同",
        "parties": ["甲方：委托方", "乙方：开发服务方"],
        "scope": "CRM 系统需求梳理、原型设计、系统开发、测试部署和上线支持。",
        "payment_terms": "签署后 30%，上线后 70%。",
        "acceptance_terms": "无重大问题视为验收通过。",
        "ip_terms": "源代码归双方共同所有。",
    }
    output, llm_trace = _gateway_json_or_fallback(
        node_name="parse_contract",
        prompt=render_parse_contract_prompt(text),
        schema=PARSE_CONTRACT_SCHEMA,
        fallback=_mock_parse_contract_output(text),
        validator=_validate_parse_contract_output,
    )
    _artifacts(state)["parse_contract"] = output
    _set_step(state, "parse_contract", StepStatus.COMPLETED.value, output)
    _append_trace(state, step_id="parse_contract", event_type=TraceEventType.AGENT_CALLED.value, observation="Contract parsed.", payload=llm_trace)
    return state


def classify_clauses_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    output = {
        "clauses": [
            {"category": "付款", "attention": "尾款应绑定验收和稳定运行。"},
            {"category": "交付", "attention": "应明确交付物清单和源码交付范围。"},
            {"category": "违约", "attention": "应补充延期、质量缺陷和保密违约责任。"},
            {"category": "解除", "attention": "应明确重大违约、逾期和验收失败时的解除权。"},
            {"category": "争议解决", "attention": "应补充管辖法院或仲裁机构。"},
        ],
        "clause_count": 5,
    }
    _artifacts(state)["classify_clauses"] = output
    _set_step(state, "classify_clauses", StepStatus.COMPLETED.value, output)
    _append_trace(state, step_id="classify_clauses", event_type=TraceEventType.AGENT_CALLED.value, observation="Contract clauses classified.", payload=output)
    return state


def risk_detect_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    risks = _risk_items()
    output = {
        "risks": risks,
        "risk_summary": {
            "high": 2,
            "medium": 1,
            "low": 0,
            "conclusion": "付款、验收和知识产权条款需要在签署前补强。",
        },
        "risk_level": "high",
        "risk_score": 82,
    }
    output, llm_trace = _gateway_json_or_fallback(
        node_name="risk_detect",
        prompt=render_risk_detect_prompt(contract_text=state.get("contract_text", ""), state={"artifacts": _artifacts(state)}),
        schema=RISK_DETECT_SCHEMA,
        fallback={"risks": _risk_items()},
        validator=_validate_risk_detect_output,
    )
    risks = output["risks"]
    risk_counts = {
        "high": sum(1 for risk in risks if risk.get("level") == "high"),
        "medium": sum(1 for risk in risks if risk.get("level") == "medium"),
        "low": sum(1 for risk in risks if risk.get("level") == "low"),
    }
    output["risk_summary"] = {
        **risk_counts,
        "conclusion": "风险判断基于合同文本本身，正式法律依据待 RAG 补充。",
    }
    output["risk_level"] = "high" if risk_counts["high"] else "medium"
    output["risk_score"] = 82 if risk_counts["high"] else 60
    state["risks"] = risks
    _artifacts(state)["risk_detect"] = output
    _set_step(state, "risk_detect", StepStatus.COMPLETED.value, output)
    _append_trace(state, step_id="risk_detect", event_type=TraceEventType.AGENT_CALLED.value, observation=f"Detected {len(risks)} contract risk item(s).", payload=llm_trace)
    return state


def legal_evidence_match_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    risks = state.get("risks", [])
    contract_type = str(_artifacts(state).get("parse_contract", {}).get("contract_type") or "")
    top_k = 2
    fallback = False
    error = None
    evidences: List[Dict[str, Any]] = []
    try:
        retriever = LegalEvidenceRetriever()
        for index, risk in enumerate(risks, start=1):
            results = retriever.retrieve(risk=risk, contract_type=contract_type, top_k=top_k)
            if results:
                evidences.extend(results)
            else:
                fallback = True
                evidences.append(_fallback_evidence_for_risk(risk, index))
        if not evidences:
            fallback = True
            evidences = _evidence_items()
    except Exception as exc:
        fallback = True
        error = str(exc)
        evidences = [_fallback_evidence_for_risk(risk, index) for index, risk in enumerate(risks, start=1)] or _evidence_items()

    evidences = [normalize_evidence(item, risk_id=str(item.get("riskId") or "")) for item in evidences]
    output = {
        "evidences": evidences,
        "citations": [item["citationText"] for item in evidences],
    }
    state["evidences"] = evidences
    _artifacts(state)["legal_evidence_match"] = output
    _set_step(state, "legal_evidence_match", StepStatus.COMPLETED.value, output)
    _append_trace(
        state,
        step_id="legal_evidence_match",
        event_type=TraceEventType.AGENT_CALLED.value,
        observation="Matched legal evidence to risks.",
        payload=_evidence_trace_payload(result_count=len(evidences), fallback=fallback, error=error, top_k=top_k),
    )
    return state


def suggestion_generate_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    suggestions = {
        "risk-payment-01": "改为需求确认 20% + 原型确认 20% + 测试验收 30% + 稳定运行 30%，并补充发票和逾期规则。",
        "risk-acceptance-01": "列明功能清单、性能指标、验收流程、书面反馈期限和视为验收通过的前置条件。",
        "risk-ip-01": "明确甲方享有定制成果著作财产权，乙方保留通用工具权利，并承诺第三方组件合规。",
    }
    risks = []
    for risk in state.get("risks", []):
        item = dict(risk)
        item["suggestion"] = suggestions.get(str(item.get("id")), "")
        risks.append(item)
    output = {
        "revision_suggestions": [
            {
                "riskId": risk.get("id"),
                "title": risk.get("title"),
                "suggestion": risk.get("suggestion"),
                "requiresBusinessDecision": risk.get("level") == "high",
            }
            for risk in risks
        ],
        "manual_review_focus": ["尾款触发条件", "验收标准客观化", "知识产权归属与复用边界"],
    }
    state["risks"] = risks
    _artifacts(state)["risk_detect"]["risks"] = risks
    _artifacts(state)["suggestion_generate"] = output
    _set_step(state, "suggestion_generate", StepStatus.COMPLETED.value, output)
    _append_trace(state, step_id="suggestion_generate", event_type=TraceEventType.AGENT_CALLED.value, observation="Generated revision suggestions.", payload=output)
    return state


def human_review_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    output = {
        "review_status": "pending",
        "reviewer": "demo.lawyer",
        "review_focus": _artifacts(state).get("suggestion_generate", {}).get("manual_review_focus", []),
        "risks": state.get("risks", []),
        "message": "等待律师或业务负责人确认风险结论后进入报告生成。",
    }
    state["status"] = WorkflowStatus.WAITING_REVIEW.value
    state["review"] = output
    _artifacts(state)["human_review"] = output
    _set_step(state, "human_review", StepStatus.WAITING_REVIEW.value, output)
    _append_trace(state, step_id="human_review", event_type=TraceEventType.REVIEW_REQUIRED.value, observation="Human review required before report generation.", payload=output)
    return state


def report_generate_node(state: ContractReviewState) -> ContractReviewState:
    state = _copy_state(state)
    review = dict(state.get("review", {}))
    if review.get("status") != ReviewDecisionType.APPROVED.value:
        state["status"] = WorkflowStatus.FAILED.value
        state["error"] = "Report generation requires approved human review."
        _set_step(state, "report_generate", StepStatus.FAILED.value, {"error": state["error"]})
        _append_trace(state, step_id="report_generate", event_type=TraceEventType.STEP_FAILED.value, observation=state["error"])
        return state

    risks = state.get("risks", [])
    evidences = state.get("evidences", [])
    risk_lines = "\n".join(
        f"{index}. {risk.get('title')}：{risk.get('reason')}\n   建议：{risk.get('suggestion')}"
        for index, risk in enumerate(risks, start=1)
    )
    evidence_lines = "\n".join(
        f"{index}. {item.get('sourceName')}：{item.get('citationText')}（演示依据 / 待正式法律知识库校验）"
        for index, item in enumerate(evidences, start=1)
    )
    report_markdown = f"""# 软件开发服务合同审查报告

## 一、审查结论
合同具备基础交易结构，但付款、验收和知识产权条款需要在签署前补强。

## 二、风险点
{risk_lines}

## 三、Evidence 依据链
{evidence_lines}

## 四、人工审核
审核结论：approved
审核意见：{review.get('comment', '')}
"""
    report_result, llm_trace = _gateway_json_or_fallback(
        node_name="report_generate",
        prompt=render_report_generate_prompt(
            {
                "artifacts": _artifacts(state),
                "risks": risks,
                "evidences": evidences,
                "review": review,
            }
        ),
        schema=REPORT_GENERATE_SCHEMA,
        fallback=_validate_report_generate_output({"report_markdown": report_markdown}),
        validator=_validate_report_generate_output,
    )
    report_markdown = report_result["report_markdown"]
    report_markdown = _append_evidence_appendix(report_markdown, evidences)
    output = {
        "report_markdown": report_markdown,
        "report": {
            "riskItems": risks,
            "evidenceAppendix": evidences,
            "reviewStatus": "approved",
        },
    }
    state["status"] = WorkflowStatus.COMPLETED.value
    state["current_step"] = None
    state["report_markdown"] = report_markdown
    _artifacts(state)["report_generate"] = output
    _set_step(state, "human_review", StepStatus.COMPLETED.value, _artifacts(state).get("human_review", {}))
    _set_step(state, "report_generate", StepStatus.COMPLETED.value, output)
    state["current_step"] = None
    _append_trace(state, step_id="report_generate", event_type=TraceEventType.AGENT_CALLED.value, observation="Contract review report generated.", payload=llm_trace)
    return state


def build_contract_review_graph():
    builder = StateGraph(ContractReviewState)
    builder.add_node("parse_contract", parse_contract_node)
    builder.add_node("classify_clauses", classify_clauses_node)
    builder.add_node("risk_detect", risk_detect_node)
    builder.add_node("legal_evidence_match", legal_evidence_match_node)
    builder.add_node("suggestion_generate", suggestion_generate_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("report_generate", report_generate_node)
    builder.add_edge(START, "parse_contract")
    builder.add_edge("parse_contract", "classify_clauses")
    builder.add_edge("classify_clauses", "risk_detect")
    builder.add_edge("risk_detect", "legal_evidence_match")
    builder.add_edge("legal_evidence_match", "suggestion_generate")
    builder.add_edge("suggestion_generate", "human_review")
    builder.add_edge("human_review", "report_generate")
    builder.add_edge("report_generate", END)
    return builder.compile(checkpointer=InMemorySaver(), interrupt_before=["report_generate"])


class LegalContractReviewStateGraphRuntime:
    """Adapter that exposes the LangGraph StateGraph as AgentOS WorkflowRun objects."""

    def __init__(
        self,
        *,
        workflow_store: WorkflowStore,
        trace_store: TraceStore,
        checkpoint_store: CheckpointStore,
        review_manager: ReviewManager,
    ):
        self.workflow_store = workflow_store
        self.trace_store = trace_store
        self.checkpoint_store = checkpoint_store
        self.review_manager = review_manager
        self.graph = build_contract_review_graph()
        self._synced_trace_counts: Dict[str, int] = {}
        self._checkpointed_steps: Dict[str, set[str]] = {}

    async def start(self, *, task: AgentTask, run: WorkflowRun, workflow: WorkflowDefinition) -> WorkflowRun:
        task.recommended_workflow = workflow.workflow_id
        task.status = WorkflowStatus.RUNNING
        task.updated_at = utc_now()
        self.workflow_store.save_task(task)

        self.trace_store.append(
            run=run,
            event_type=TraceEventType.TASK_CREATED,
            observation=f"Task created: {task.title}",
            payload=task.model_dump(by_alias=True, mode="json"),
        )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_STARTED,
            observation=f"LangGraph workflow started: {workflow.workflow_id}",
            payload={"workflowId": workflow.workflow_id, "threadId": run.run_id},
        )
        self.workflow_store.save_run(run)

        state = self._initial_state(run)
        result = self.graph.invoke(state, self._config(run.run_id))
        return self._sync_run_from_state(task=task, run=run, state=dict(result))

    async def apply_review(self, decision: ReviewDecision) -> WorkflowRun:
        run = self.workflow_store.get_run(decision.run_id)
        task = self.workflow_store.get_task(run.task_id)
        self.review_manager.record(run, decision)

        if decision.decision == ReviewDecisionType.APPROVED:
            review = {
                "status": ReviewDecisionType.APPROVED.value,
                "decision": ReviewDecisionType.APPROVED.value,
                "reviewer": decision.reviewer,
                "comment": decision.comment,
            }
            result = self.graph.invoke(
                Command(update={"review": review, "status": WorkflowStatus.RUNNING.value}),
                self._config(run.run_id),
            )
            return self._sync_run_from_state(task=task, run=run, state=dict(result))

        step = run.get_step("human_review")
        if decision.decision == ReviewDecisionType.NEED_MORE_INFO:
            step.status = StepStatus.WAITING_REVIEW
            run.status = WorkflowStatus.WAITING_REVIEW
            run.current_step_id = "human_review"
            run.error = decision.comment or "Human reviewer requested more information."
            run.updated_at = utc_now()
            task.status = WorkflowStatus.WAITING_REVIEW
            task.updated_at = utc_now()
            self.workflow_store.save_task(task)
            self.workflow_store.save_run(run)
            return run

        if decision.decision != ReviewDecisionType.REJECTED:
            raise ValueError(
                f"Unsupported review decision for {WORKFLOW_ID}: {decision.decision.value}"
            )

        step.status = StepStatus.FAILED
        run.status = WorkflowStatus.FAILED
        run.current_step_id = "human_review"
        run.error = decision.comment or "Human review rejected the workflow."
        run.updated_at = utc_now()
        task.status = WorkflowStatus.FAILED
        task.updated_at = utc_now()
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_FAILED,
            step_id="human_review",
            observation=run.error,
        )
        self.workflow_store.save_task(task)
        self.workflow_store.save_run(run)
        return run

    def _initial_state(self, run: WorkflowRun) -> ContractReviewState:
        return {
            "run_id": run.run_id,
            "workflow_id": run.workflow_id,
            "contract_text": str(run.input.get("contractText") or run.input.get("contract_text") or ""),
            "current_step": "parse_contract",
            "status": WorkflowStatus.RUNNING.value,
            "steps": {
                step.step_id: {
                    "status": step.status.value,
                    "output": dict(step.output),
                }
                for step in run.steps
            },
            "risks": [],
            "evidences": [],
            "traces": [],
            "review": {},
            "artifacts": {},
            "report_markdown": "",
            "error": None,
        }

    def _sync_run_from_state(self, *, task: AgentTask, run: WorkflowRun, state: Dict[str, Any]) -> WorkflowRun:
        artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
        steps = state.get("steps") if isinstance(state.get("steps"), dict) else {}

        for step in run.steps:
            step_state = steps.get(step.step_id, {}) if isinstance(steps.get(step.step_id), dict) else {}
            status = step_state.get("status")
            if status:
                step.status = StepStatus(status)
            output = step_state.get("output")
            if isinstance(output, dict):
                step.output = output
            elif isinstance(artifacts.get(step.step_id), dict):
                step.output = dict(artifacts[step.step_id])
            if step.status in {StepStatus.COMPLETED, StepStatus.WAITING_REVIEW}:
                step.started_at = step.started_at or utc_now()
            if step.status == StepStatus.COMPLETED:
                step.completed_at = step.completed_at or utc_now()

        run.status = WorkflowStatus(state.get("status") or WorkflowStatus.RUNNING.value)
        run.current_step_id = state.get("current_step")
        if run.status == WorkflowStatus.COMPLETED:
            run.current_step_id = None
        run.output = {
            "final_answer": state.get("report_markdown") or "",
            "artifacts": artifacts,
        }
        run.error = state.get("error")
        run.updated_at = utc_now()

        self._sync_traces(run, state.get("traces", []))
        self._sync_checkpoints(run)

        task.status = run.status
        task.updated_at = utc_now()
        if run.status == WorkflowStatus.COMPLETED:
            self.trace_store.append(
                run=run,
                event_type=TraceEventType.RUN_COMPLETED,
                observation="LangGraph workflow completed.",
                payload=run.output,
            )
        self.workflow_store.save_task(task)
        self.workflow_store.save_run(run)
        return run

    def _sync_traces(self, run: WorkflowRun, traces: Any) -> None:
        if not isinstance(traces, list):
            return
        start = self._synced_trace_counts.get(run.run_id, 0)
        for index, item in enumerate(traces[start:], start=start):
            if not isinstance(item, dict):
                continue
            event_type = TraceEventType(item.get("eventType") or TraceEventType.AGENT_CALLED.value)
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            payload["langgraphTraceIndex"] = index
            self.trace_store.append(
                run=run,
                event_type=event_type,
                step_id=item.get("stepId"),
                agent_name=item.get("agentName"),
                observation=str(item.get("observation") or ""),
                payload=payload,
            )
        self._synced_trace_counts[run.run_id] = len(traces)

    def _sync_checkpoints(self, run: WorkflowRun) -> None:
        checkpointed = self._checkpointed_steps.setdefault(run.run_id, set())
        for step in run.steps:
            if step.step_id in checkpointed:
                continue
            if step.status not in {StepStatus.COMPLETED, StepStatus.WAITING_REVIEW}:
                continue
            self.checkpoint_store.create(run, step.step_id)
            checkpointed.add(step.step_id)

    @staticmethod
    def _config(run_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": run_id}}


__all__ = [
    "ContractReviewState",
    "LegalContractReviewStateGraphRuntime",
    "WORKFLOW_ID",
    "build_contract_review_graph",
]

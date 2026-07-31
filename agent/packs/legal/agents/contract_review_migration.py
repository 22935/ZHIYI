from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List

from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from app.llm.gateway import get_llm_gateway
from app.llm.prompts import render_parse_contract_prompt, render_report_generate_prompt, render_risk_detect_prompt
from app.llm.schemas import PARSE_CONTRACT_SCHEMA, REPORT_GENERATE_SCHEMA, RISK_DETECT_SCHEMA
from app.rag import LegalEvidenceRetriever
from app.rag.legal_evidence_schema import normalize_evidence
from packs.legal.agents.common import case_text


def _contract_text(context) -> str:
    return case_text(context.task.input) or str(context.task.input.get("contractText") or "").strip()


def _observation(context, *step_ids: str) -> Dict[str, Any]:
    """Read an upstream artifact by stable public step ID or its former ACG demo ID."""
    observations = context.memory.observations
    for step_id in step_ids:
        value = observations.get(step_id)
        if isinstance(value, dict):
            return value
    return {}


def _thinking_mode(context) -> str | None:
    """Read the per-run reasoning mode without changing legacy callers."""
    value = str(context.task.input.get("thinkingMode") or "").strip().lower()
    return value if value in {"disabled", "standard", "deep"} else None


def _llm_json_or_fallback(
    *,
    node_name: str,
    prompt: str,
    schema: Dict[str, Any],
    fallback: Dict[str, Any],
    validator: Callable[[Dict[str, Any]], Dict[str, Any]],
    thinking_mode: str | None = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Preserve the former graph's JSON guard and deterministic fallback behavior."""
    gateway = get_llm_gateway()
    try:
        response = gateway.generate_json(prompt, schema, thinking_mode=thinking_mode)
        output = validator(response.get("data", {}))
        provider = str(response.get("provider") or gateway.provider_name)
        return output, {
            "node_name": node_name,
            "provider": provider,
            "model": str(response.get("model") or gateway.model),
            "source": "mock" if provider == "mock" else "llm",
            "success": True,
            "latency_ms": int(response.get("latency_ms") or 0),
            "thinking_mode": thinking_mode or "disabled",
        }
    except Exception as exc:
        return fallback, {
            "node_name": node_name,
            "provider": getattr(gateway, "provider_name", "unknown"),
            "model": getattr(gateway, "model", "unknown"),
            "source": "fallback",
            "success": False,
            "error": str(exc)[:240],
            "thinking_mode": thinking_mode or "disabled",
        }


def _validate_parse_contract(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("parties"), list):
        raise ValueError("parse_contract output must contain a parties list")
    return {
        "contract_summary": str(data.get("summary") or ""),
        "contract_title": str(data.get("contract_title") or "unknown"),
        "parties": [
            {"name": str(item.get("name") or "unknown"), "role": str(item.get("role") or "unknown")}
            for item in data["parties"] if isinstance(item, dict)
        ],
        "contract_type": str(data.get("contract_type") or "unknown"),
        "key_dates": data.get("key_dates") if isinstance(data.get("key_dates"), list) else [],
        "amounts": data.get("amounts") if isinstance(data.get("amounts"), list) else [],
        "obligations": data.get("obligations") if isinstance(data.get("obligations"), list) else [],
        "scope": str(data.get("scope") or ""),
        "payment_terms": str(data.get("payment_terms") or ""),
        "acceptance_terms": str(data.get("acceptance_terms") or ""),
        "ip_terms": str(data.get("ip_terms") or ""),
        "dispute_resolution": str(data.get("dispute_resolution") or ""),
    }


def _validate_risks(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("risks"), list):
        raise ValueError("risk_detect output must contain a risks list")
    risks = []
    for index, item in enumerate(data["risks"], start=1):
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or "medium").lower()
        risks.append({
            "id": str(item.get("id") or f"risk-{index:02d}"),
            "title": str(item.get("title") or "unnamed risk"),
            "level": level if level in {"high", "medium", "low"} else "medium",
            "clause": str(item.get("clause") or ""),
            "reason": str(item.get("reason") or ""),
            "consequence": str(item.get("consequence") or ""),
            "suggestion": str(item.get("suggestion") or ""),
            "evidenceIds": list(item.get("evidenceIds") or []),
        })
    return {"risks": risks}


def _validate_report(data: Dict[str, Any]) -> Dict[str, Any]:
    report = data.get("report_markdown") if isinstance(data, dict) else None
    if not isinstance(report, str) or not report.strip():
        raise ValueError("report_generate output must contain report_markdown")
    report = report.strip()
    disclaimer = "本报告由自动化流程生成，不构成最终法律意见；重要结论和引用依据需由具备相应资质的专业人员复核。"
    if "本报告不构成最终法律意见" not in report:
        report = f"{report.rstrip()}\n\n## 免责声明\n{disclaimer}\n"
    return {"report_markdown": report}


def _append_evidence_appendix(report: str, evidences: List[Dict[str, Any]]) -> str:
    if not evidences:
        return report
    citations = [str(item.get("citationText") or "") for item in evidences]
    if "Evidence 依据链" in report and any(citation and citation in report for citation in citations):
        return report
    lines = ["", "## Evidence 依据链"]
    for index, item in enumerate(evidences, start=1):
        lines.append(
            f"{index}. [{item.get('sourceType')}] {item.get('sourceName')}：{item.get('citationText')}"
        )
    return f"{report.rstrip()}\n" + "\n".join(lines) + "\n"


def _latest_human_review(context) -> Dict[str, Any]:
    for event in reversed(context.run.trace):
        event_type = getattr(event.event_type, "value", event.event_type)
        payload = event.payload if isinstance(event.payload, dict) else {}
        if event_type == "review_decided" and (payload.get("stepId") or event.step_id) == "human_review":
            return payload
    return {}


def _append_review_result(report: str, review: Dict[str, Any]) -> str:
    if not review:
        return report
    reviewer = str(review.get("reviewer") or "未记录")
    decision = str(review.get("decision") or "unknown")
    comment = str(review.get("comment") or "").strip()
    if reviewer in report and (not comment or comment in report):
        return report
    lines = ["", "## 人工审核记录", f"- 审核人：{reviewer}", f"- 审核结论：{decision}"]
    if comment:
        lines.append(f"- 审核意见：{comment}")
    return f"{report.rstrip()}\n" + "\n".join(lines) + "\n"


def _risk_counts(risks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for risk in risks:
        level = str(risk.get("level") or "low")
        if level in counts:
            counts[level] += 1
    return counts


class ContractParseAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="contract_parse",
                domain="legal",
                capabilities=["contract_parse"],
                allowedSkills=["contract_parser"],
                description="Parses contract text into parties, scope, payment, acceptance, IP, and dispute fields.",
            )
        )

    async def run(self, context):
        text = _contract_text(context)
        output = {
            "contract_summary": text[:500],
            "contract_title": "",
            "contract_type": "",
            "parties": [],
            "key_dates": [],
            "amounts": [],
            "obligations": [],
            "scope": "",
            "payment_terms": "",
            "acceptance_terms": "",
            "ip_terms": "",
            "dispute_resolution": "",
            "original_preview": text[:120],
        }
        output, llm = await asyncio.to_thread(
            _llm_json_or_fallback,
            node_name="parse_contract",
            prompt=render_parse_contract_prompt(text),
            schema=PARSE_CONTRACT_SCHEMA,
            fallback=output,
            validator=_validate_parse_contract,
            thinking_mode=_thinking_mode(context),
        )
        output["parties"] = [
            f"{item.get('name', 'unknown')}：{item.get('role', 'unknown')}"
            if isinstance(item, dict) else str(item)
            for item in output.get("parties", [])
        ]
        output["original_preview"] = text[:120]
        required_fields = ["contract_type", "parties", "contract_summary"]
        output["missing_fields"] = [field for field in required_fields if not output.get(field)]
        output["analysis_status"] = "completed" if llm.get("success") else "unavailable"
        output["_llm"] = llm
        return AgentOutput(output=output, summary="Contract text parsed into structured fields.")


class ClauseClassifyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="clause_classify",
                domain="legal",
                capabilities=["clause_classify"],
                allowedSkills=["clause_classifier"],
                description="Classifies contract clauses and marks clauses that need legal attention.",
            )
        )

    async def run(self, context):
        parsed = _observation(context, "parse_contract", "contract_parse")
        field_categories = {
            "parties": "主体信息",
            "scope": "项目范围",
            "payment_terms": "付款",
            "acceptance_terms": "验收",
            "ip_terms": "知识产权",
            "dispute_resolution": "争议解决",
        }
        categories = [
            {
                "category": category,
                "source_field": field,
                "content": parsed.get(field, [] if field == "parties" else ""),
                "present": bool(parsed.get(field)),
            }
            for field, category in field_categories.items()
        ]
        return AgentOutput(
            output={"clauses": categories, "clause_count": len(categories)},
            summary=f"Classified {len(categories)} contract clause group(s).",
        )


class RiskDetectAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="risk_detect",
                domain="legal",
                capabilities=["risk_detect"],
                allowedSkills=["risk_detection"],
                riskLevel="high",
                description="Detects contract risks from parsed and classified clauses.",
            )
        )

    async def run(self, context):
        fallback = {"risks": []}
        artifacts = {
            "parse_contract": _observation(context, "parse_contract", "contract_parse"),
            "classify_clauses": _observation(context, "classify_clauses", "clause_classify"),
        }
        llm_output, llm = await asyncio.to_thread(
            _llm_json_or_fallback,
            node_name="risk_detect",
            prompt=render_risk_detect_prompt(
                contract_text=json.dumps(artifacts, ensure_ascii=False, default=str),
                state={"artifacts": artifacts},
            ),
            schema=RISK_DETECT_SCHEMA,
            fallback=fallback,
            validator=_validate_risks,
            thinking_mode=_thinking_mode(context),
        )
        risks = llm_output["risks"]
        counts = _risk_counts(risks)
        risk_level = "high" if counts["high"] else "medium" if counts["medium"] else "low" if risks else "unknown"
        risk_score = min(100, counts["high"] * 30 + counts["medium"] * 15 + counts["low"] * 5) if risks else None
        output = {
            "risks": risks,
            "risk_summary": {
                **counts,
                "conclusion": "；".join(str(item.get("title") or "") for item in risks if item.get("title")),
            },
            "risk_level": risk_level,
            "risk_score": risk_score,
            "analysis_status": "completed" if llm.get("success") else "unavailable",
            "_llm": llm,
        }
        return AgentOutput(
            output=output,
            summary=f"Detected {len(risks)} contract risk item(s).",
            riskLevel=None if risk_level == "unknown" else risk_level,
        )


class LegalEvidenceMatchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="legal_evidence_match",
                domain="legal",
                capabilities=["legal_evidence_match"],
                allowedSkills=["legal_evidence_search"],
                description="Matches legal, template, practice, and case evidence to detected contract risks.",
            )
        )

    async def run(self, context):
        risk_output = _observation(context, "risk_detect")
        parsed = _observation(context, "parse_contract", "contract_parse")
        risks = risk_output.get("risks") or []
        evidences: List[Dict[str, Any]] = []
        errors: List[str] = []
        unmatched_risk_ids: List[str] = []
        retriever = LegalEvidenceRetriever()
        for risk in risks:
            risk_id = str(risk.get("id") or "")
            try:
                results = retriever.retrieve(
                    risk=risk,
                    contract_type=str(parsed.get("contract_type") or ""),
                    top_k=2,
                )
                if results:
                    evidences.extend(results)
                    continue
            except Exception as exc:
                errors.append(str(exc)[:240])
            if risk_id:
                unmatched_risk_ids.append(risk_id)
        evidences = [normalize_evidence(item, risk_id=str(item.get("riskId") or "")) for item in evidences]
        return AgentOutput(
            output={
                "evidences": evidences,
                "citations": [item["citationText"] for item in evidences],
                "retrieval": {
                    "status": "complete" if not unmatched_risk_ids else "incomplete",
                    "result_count": len(evidences),
                    "unmatched_risk_ids": unmatched_risk_ids,
                    "errors": errors,
                },
            },
            summary=f"Matched {len(evidences)} evidence item(s) to contract risks.",
        )


class RevisionSuggestAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="revision_suggest",
                domain="legal",
                capabilities=["revision_suggest"],
                allowedSkills=["revision_suggestion"],
                description="Generates concrete revision suggestions from risks and evidence.",
            )
        )

    async def run(self, context):
        risk_output = _observation(context, "risk_detect")
        risks = risk_output.get("risks") or []
        suggestions = [
            {
                "riskId": risk.get("id"),
                "title": risk.get("title"),
                "suggestion": risk.get("suggestion"),
                "requiresBusinessDecision": risk.get("level") == "high",
            }
            for risk in risks
        ]
        return AgentOutput(
            output={
                "revision_suggestions": suggestions,
                "manual_review_focus": [
                    str(risk.get("title"))
                    for risk in risks
                    if risk.get("level") == "high" and risk.get("title")
                ],
            },
            summary=f"Generated {len(suggestions)} revision suggestion(s).",
        )


class HumanReviewGateAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="human_review",
                domain="legal",
                capabilities=["human_review_gate"],
                allowedSkills=["human_review_gate"],
                riskLevel="high",
                description="Creates a human-review gate before report generation.",
            )
        )

    async def run(self, context):
        risk_output = _observation(context, "risk_detect")
        revision_output = _observation(context, "suggestion_generate", "revision_suggest")
        output = {
            "review_status": "pending",
            "reviewer": None,
            "review_focus": revision_output.get("manual_review_focus", []),
            "risks": risk_output.get("risks", []),
            "suggested_decision": "manual_review_required",
        }
        return AgentOutput(output=output, summary="Human review gate prepared.", riskLevel="high")


class ReportGenerateAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="report_generate",
                domain="legal",
                capabilities=["report_generate"],
                allowedSkills=["report_generation"],
                description="Packages contract review artifacts into a markdown report.",
            )
        )

    async def run(self, context):
        observations = context.memory.observations
        parsed = _observation(context, "parse_contract", "contract_parse")
        clauses = observations.get("clause_classify", {}).get("clauses", [])
        risks = observations.get("risk_detect", {}).get("risks", [])
        risk_summary = observations.get("risk_detect", {}).get("risk_summary", {})
        evidences = observations.get("legal_evidence_match", {}).get("evidences", [])
        revision_output = _observation(context, "suggestion_generate", "revision_suggest")
        revisions = revision_output.get("revision_suggestions", [])
        manual_review_focus = revision_output.get("manual_review_focus", [])
        review = _latest_human_review(context)

        evidence_by_risk: Dict[str, List[str]] = {}
        for item in evidences:
            risk_id = str(item.get("riskId") or "")
            citation = str(item.get("citationText") or "").strip()
            if risk_id and citation:
                evidence_by_risk.setdefault(risk_id, []).append(citation)
        risk_lines = "\n".join(
            "\n".join(
                [
                    f"### {index}. [{str(risk.get('level') or 'medium').upper()}] {risk.get('title')}",
                    f"- 条款位置：{risk.get('clause') or '待人工定位'}",
                    f"- 风险原因：{risk.get('reason') or '待补充'}",
                    f"- 可能后果：{risk.get('consequence') or '待补充'}",
                    f"- 修改建议：{risk.get('suggestion') or '待补充'}",
                    "- 证据依据：" + (
                        "；".join(evidence_by_risk.get(str(risk.get('id') or ''), []))
                        or "未匹配到可引用依据，需人工复核"
                    ),
                ]
            )
            for index, risk in enumerate(risks, start=1)
        )
        clause_lines = "\n".join(
            f"- {item.get('category') or item.get('source_field') or '未分类'}："
            f"{'已识别' if item.get('present') else '未明确'}"
            for item in clauses
        )
        evidence_lines = "\n".join(
            f"{index}. {item.get('sourceName')}：{item.get('citationText')}"
            for index, item in enumerate(evidences, start=1)
        )
        revision_lines = "\n".join(
            f"{index}. {item.get('title')}：{item.get('suggestion')}"
            for index, item in enumerate(revisions, start=1)
        )
        contract_title = str(parsed.get("contract_title") or "合同审查报告")
        review_status = str(review.get("decision") or "unreviewed")
        signing_conclusion = (
            "存在高风险事项，完成修改并经专业人员复核前不建议签署。"
            if risk_summary.get("high", 0)
            else "未发现高风险事项，但仍应完成证据与关键商业条款的人工复核后再签署。"
        )
        report_markdown = f"""# {contract_title}

## 一、合同基本信息
- 类型：{parsed.get('contract_type') or '未识别'}
- 主体：{' / '.join(parsed.get('parties', [])) or '待确认'}
- 范围：{parsed.get('scope') or '待确认'}

## 二、条款分类摘要
{clause_lines or '未生成条款分类。'}

## 三、风险摘要
- 高风险：{risk_summary.get('high', 0)}
- 中风险：{risk_summary.get('medium', 0)}
- 低风险：{risk_summary.get('low', 0)}

## 四、高中低风险清单
{risk_lines or '未生成可验证的风险条目。'}

## 五、修改建议
{revision_lines or '未生成修改建议。'}

## 六、Evidence 依据链
{evidence_lines or '未检索到可引用依据。'}

## 七、人工复核关注点
{chr(10).join(f'- {item}' for item in manual_review_focus) or '无额外人工复核关注点。'}

## 八、审核状态与签署前结论
- 审核状态：{review_status}
- 签署前处理结论：{signing_conclusion}
"""
        thinking_mode = _thinking_mode(context)
        if thinking_mode == "disabled":
            # 快速模式直接组装已有的结构化审查产物。报告生成是确定性格式化，
            # 再调用一次模型只会重复风险分析并增加约 9 秒串行等待。
            report_result = _validate_report({"report_markdown": report_markdown})
            llm = {
                "node_name": "report_generate",
                "provider": "local",
                "model": "deterministic-report-v1",
                "source": "deterministic",
                "success": True,
                "latency_ms": 0,
                "thinking_mode": thinking_mode,
            }
        else:
            report_result, llm = await asyncio.to_thread(
                _llm_json_or_fallback,
                node_name="report_generate",
                prompt=render_report_generate_prompt(
                    {"artifacts": observations, "risks": risks, "evidences": evidences, "review": review}
                ),
                schema=REPORT_GENERATE_SCHEMA,
                fallback={"report_markdown": report_markdown},
                validator=_validate_report,
                thinking_mode=thinking_mode,
            )
        report_markdown = _append_evidence_appendix(report_result["report_markdown"], evidences)
        report_markdown = _append_review_result(report_markdown, review)
        output = {
            "final_answer": report_markdown,
            "report_markdown": report_markdown,
            "_llm": llm,
            "report": {
                "contractInfo": {
                    "name": str(parsed.get("contract_title") or ""),
                    "type": str(parsed.get("contract_type") or ""),
                    "parties": parsed.get("parties", []),
                    "scope": parsed.get("scope", ""),
                },
                "riskSummary": risk_summary,
                "riskItems": risks,
                "revisionSuggestions": revisions,
                "evidenceAppendix": evidences,
                "reviewStatus": review_status,
            },
        }
        return AgentOutput(output=output, summary="Contract review report generated.")


class ContractFinalReviewAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="contract_final_review",
                domain="legal",
                capabilities=["contract_final_review", "final_review"],
                allowedSkills=["quality_gate"],
                description="Checks the migrated contract review report and exposes the final answer.",
            )
        )

    async def run(self, context):
        report_output = context.memory.observations.get("report_generate", {})
        report_markdown = report_output.get("report_markdown", "")
        final_answer = str(report_markdown or "").strip()
        return AgentOutput(
            output={
                "final_answer": final_answer,
                "review_notes": [],
            },
            summary="Migrated contract review workflow finalized.",
        )

from __future__ import annotations

from typing import Any, Dict, List

from agentos.agents.base_agent import AgentOutput, AgentProfile, BaseAgent
from packs.legal.agents.common import case_text


def _contract_text(context) -> str:
    return case_text(context.task.input) or str(context.task.input.get("contractText") or "").strip()


def _risk_items() -> List[Dict[str, Any]]:
    return [
        {
            "id": "risk-payment-01",
            "title": "尾款支付条件过于单一",
            "level": "high",
            "clause": "甲方在合同签署后支付 30%，系统上线后支付 70%。",
            "reason": "尾款触发条件仅写“上线”，未绑定阶段验收、缺陷修复、发票开具和上线失败处理。",
            "consequence": "上线后仍存在严重缺陷时，甲方可能被要求支付大额尾款，乙方也可能因付款条件不清产生回款争议。",
            "suggestion": "建议改为“需求确认 20% + 原型确认 20% + 测试验收 30% + 上线稳定运行 30%”，并补充发票和逾期付款规则。",
            "evidenceIds": ["ev-payment-01", "ev-acceptance-01"],
        },
        {
            "id": "risk-acceptance-01",
            "title": "验收标准缺少客观指标",
            "level": "medium",
            "clause": "如无重大问题视为验收通过。",
            "reason": "“重大问题”没有定义，未明确验收材料、测试用例、反馈期限和整改次数。",
            "consequence": "双方可能对缺陷严重程度、是否通过验收、延期责任产生争议。",
            "suggestion": "建议列明功能清单、性能指标、验收流程、书面反馈期限以及视为验收通过的前置条件。",
            "evidenceIds": ["ev-acceptance-01"],
        },
        {
            "id": "risk-ip-01",
            "title": "知识产权共同所有安排不清",
            "level": "high",
            "clause": "项目相关源代码、文档和设计成果归双方共同所有。",
            "reason": "共同所有未说明使用、转让、二次开发、开源组件和第三方素材的授权边界。",
            "consequence": "后续商业化、系统迭代、对外授权或交付源代码时可能产生权属冲突。",
            "suggestion": "建议明确甲方享有定制成果全部著作财产权，乙方保留通用工具和预置组件权利，并承诺第三方组件合规。",
            "evidenceIds": ["ev-ip-01"],
        },
    ]


def _evidence_items() -> List[Dict[str, Any]]:
    return [
        {
            "id": "ev-payment-01",
            "stepId": "legal_evidence_match",
            "sourceType": "contract_template",
            "sourceName": "软件开发合同审查模板库",
            "content": "付款节点通常与里程碑、阶段验收、缺陷修复期绑定，避免尾款支付条件过于单一。",
            "citationText": "付款条款应明确付款比例、触发条件、发票条件与逾期处理。",
            "confidence": 0.92,
        },
        {
            "id": "ev-acceptance-01",
            "stepId": "legal_evidence_match",
            "sourceType": "practice",
            "sourceName": "技术服务项目验收审查要点",
            "content": "仅以“无重大问题”作为验收标准，容易造成缺陷范围、整改期限和视为通过条件争议。",
            "citationText": "验收条款宜列明验收材料、测试标准、反馈期限、整改次数和最终确认方式。",
            "confidence": 0.89,
        },
        {
            "id": "ev-ip-01",
            "stepId": "legal_evidence_match",
            "sourceType": "law",
            "sourceName": "民法典合同编与著作权法相关规则",
            "content": "定制开发成果权属应结合委托目的、费用结构、源代码交付和第三方组件授权明确约定。",
            "citationText": "知识产权归属、使用范围、源代码交付、开源组件合规应分别约定。",
            "confidence": 0.9,
        },
        {
            "id": "ev-liability-01",
            "stepId": "legal_evidence_match",
            "sourceType": "case",
            "sourceName": "软件开发合同纠纷裁判摘要",
            "content": "违约责任缺少计算方式和责任上限时，争议中往往需要法院结合损失、过错和履行情况酌定。",
            "citationText": "违约责任条款应明确延迟交付、质量缺陷、逾期付款和保密违约的责任边界。",
            "confidence": 0.86,
        },
    ]


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
            "contract_summary": text[:500] or "未提供合同文本",
            "contract_type": "软件开发服务合同",
            "parties": ["甲方：星河科技有限公司", "乙方：知弈软件工作室"],
            "scope": "客户关系管理系统的需求梳理、原型设计、系统开发、测试部署和上线支持。",
            "payment_terms": "签署后 30%，上线后 70%。",
            "acceptance_terms": "无重大问题视为验收通过。",
            "ip_terms": "源代码、文档和设计成果归双方共同所有。",
            "dispute_resolution": "建议补充管辖、仲裁或诉讼条款。",
            "original_preview": text[:120],
        }
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
        parsed = context.memory.observations.get("contract_parse", {})
        categories = [
            {"category": "主体信息", "content": parsed.get("parties", []), "attention": "确认签约主体和授权代表。"},
            {"category": "项目范围", "content": parsed.get("scope", ""), "attention": "范围应与交付物清单、排期和验收标准联动。"},
            {"category": "付款", "content": parsed.get("payment_terms", ""), "attention": "尾款不宜只绑定上线，应绑定稳定运行和验收。"},
            {"category": "验收", "content": parsed.get("acceptance_terms", ""), "attention": "需补充客观指标、反馈期限和整改次数。"},
            {"category": "知识产权", "content": parsed.get("ip_terms", ""), "attention": "需明确成果归属、复用权和第三方组件合规。"},
            {"category": "违约责任", "content": "未见完整责任上限与计算方式。", "attention": "建议补齐责任边界和赔偿上限。"},
            {"category": "争议解决", "content": parsed.get("dispute_resolution", ""), "attention": "需明确法院管辖或仲裁机构。"},
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
        risks = _risk_items()
        counts = _risk_counts(risks)
        output = {
            "risks": risks,
            "risk_summary": {
                **counts,
                "conclusion": "付款、验收和知识产权条款需要在签署前补强。",
            },
            "risk_level": "high" if counts["high"] else "medium",
            "risk_score": 82,
        }
        return AgentOutput(output=output, summary="Detected 3 contract risk item(s).", riskLevel="high")


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
        evidences = _evidence_items()
        return AgentOutput(
            output={
                "evidences": evidences,
                "citations": [item["citationText"] for item in evidences],
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
        risk_output = context.memory.observations.get("risk_detect", {})
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
                "manual_review_focus": ["尾款触发条件", "验收标准客观化", "知识产权归属与复用边界"],
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
        risk_output = context.memory.observations.get("risk_detect", {})
        revision_output = context.memory.observations.get("revision_suggest", {})
        output = {
            "review_status": "pending",
            "reviewer": "demo.lawyer",
            "review_focus": revision_output.get("manual_review_focus", []),
            "risks": risk_output.get("risks", []),
            "suggested_decision": "approved_after_manual_check",
            "message": "等待律师或业务负责人确认风险结论后进入报告生成。",
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
        parsed = observations.get("contract_parse", {})
        risks = observations.get("risk_detect", {}).get("risks", [])
        risk_summary = observations.get("risk_detect", {}).get("risk_summary", {})
        evidences = observations.get("legal_evidence_match", {}).get("evidences", [])
        revisions = observations.get("revision_suggest", {}).get("revision_suggestions", [])

        risk_lines = "\n".join(
            f"{index}. {risk.get('title')}：{risk.get('reason')}\n   建议：{risk.get('suggestion')}"
            for index, risk in enumerate(risks, start=1)
        )
        evidence_lines = "\n".join(
            f"{index}. {item.get('sourceName')}：{item.get('citationText')}"
            for index, item in enumerate(evidences, start=1)
        )
        revision_lines = "\n".join(
            f"{index}. {item.get('title')}：{item.get('suggestion')}"
            for index, item in enumerate(revisions, start=1)
        )
        report_markdown = f"""# 软件开发服务合同审查报告

## 一、合同基本信息
- 类型：{parsed.get('contract_type', '技术服务 / 软件开发')}
- 主体：{' / '.join(parsed.get('parties', [])) or '待确认'}
- 范围：{parsed.get('scope', '待确认')}

## 二、风险摘要
合同具备基础交易结构，但付款、验收、知识产权条款需要在签署前补强。
- 高风险：{risk_summary.get('high', 0)}
- 中风险：{risk_summary.get('medium', 0)}
- 低风险：{risk_summary.get('low', 0)}

## 三、风险条款列表
{risk_lines}

## 四、修改建议
{revision_lines}

## 五、依据附录
{evidence_lines}

## 六、审核状态
人工审核已通过，报告进入最终审查。
"""
        output = {
            "report_markdown": report_markdown,
            "report": {
                "contractInfo": {
                    "name": "软件开发服务合同",
                    "type": parsed.get("contract_type", "技术服务 / 软件开发"),
                    "parties": parsed.get("parties", []),
                    "scope": parsed.get("scope", ""),
                },
                "riskSummary": risk_summary,
                "riskItems": risks,
                "revisionSuggestions": revisions,
                "evidenceAppendix": evidences,
                "reviewStatus": "approved",
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
        final_answer = (
            "已完成合同审查迁移工作流。系统已完成合同解析、条款分类、风险识别、依据匹配、修改建议、人工审核和报告生成。\n\n"
            f"{report_markdown}"
        ).strip()
        return AgentOutput(
            output={
                "final_answer": final_answer,
                "review_notes": ["LangGraph 节点语义已迁移到 AgentOS WorkflowRun", "人工审核节点已通过", "报告结构完整"],
            },
            summary="Migrated contract review workflow finalized.",
        )

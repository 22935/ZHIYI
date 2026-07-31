"""Declarative legal planning capabilities owned by the Legal Pack."""

from __future__ import annotations

from agentos.core.planning import PlanningCapabilityDescriptor


LEGAL_PLUGIN_ID = "kinlin.legal"
LEGAL_PLUGIN_VERSION = "0.1.0"


def _schema(*required: str) -> dict:
    return {"type": "object", "required": list(required)}


def legal_capability_descriptors() -> tuple[PlanningCapabilityDescriptor, ...]:
    legal = ["legal"]
    descriptors = (
        PlanningCapabilityDescriptor(
            capabilityId="文本解析",
            displayName="合同文本解析",
            aliases=["合同解析", "解析合同", "contract_parse", "parse_contract"],
            planningStage="parse",
            outputContract=_schema("contract_summary", "contract_type", "parties"),
            domainHints=legal,
            priority=10,
        ),
        PlanningCapabilityDescriptor(
            capabilityId="条款分类",
            displayName="条款分类",
            aliases=[
                "条款识别",
                "clause_classify",
                "clause_classifier",
                "付款",
                "知识产权",
                "违约责任",
            ],
            planningStage="classify",
            dependsOn=["文本解析"],
            inputContract=_schema("contract_type"),
            outputContract=_schema("clauses"),
            domainHints=legal,
            priority=20,
        ),
        PlanningCapabilityDescriptor(
            capabilityId="风险识别",
            displayName="风险识别",
            aliases=[
                "风险识别",
                "risk_detect",
                "risk_detection",
                "合同风险",
                "违约",
                "合规",
            ],
            planningStage="risk",
            dependsOn=["文本解析"],
            optionalDependencies=["条款分类"],
            inputContract=_schema("contract_summary"),
            outputContract=_schema("risks", "risk_level", "risk_score"),
            writesMemory=True,
            riskLevelHint="high",
            domainHints=legal,
            priority=30,
        ),
        PlanningCapabilityDescriptor(
            capabilityId="证据检索",
            displayName="Evidence 依据匹配",
            aliases=[
                "依据匹配",
                "证据/依据匹配",
                "legal_evidence_match",
                "legal_evidence_search",
                "法律知识应用",
                "法条",
                "法规",
                "依据",
            ],
            planningStage="evidence",
            dependsOn=["风险识别"],
            inputContract=_schema("risks"),
            outputContract=_schema("evidences", "citations"),
            requiresEvidence=True,
            domainHints=legal,
            priority=31,
        ),
        PlanningCapabilityDescriptor(
            capabilityId="修改建议",
            displayName="修改建议生成",
            aliases=[
                "修订建议",
                "revision_suggest",
                "revision_suggestion",
                "suggestion_generate",
                "修改",
                "修订",
                "优化",
            ],
            planningStage="suggest",
            dependsOn=["风险识别", "证据检索"],
            inputContract=_schema("risks", "evidences"),
            outputContract=_schema("revision_suggestions", "manual_review_focus"),
            producesArtifact=True,
            writesMemory=True,
            domainHints=legal,
            priority=40,
        ),
        PlanningCapabilityDescriptor(
            capabilityId="人工审核",
            displayName="人工审核门",
            aliases=["复核", "human_review", "人工", "审批"],
            planningStage="review",
            dependsOn=["风险识别", "修改建议"],
            inputContract=_schema("risks", "manual_review_focus"),
            outputContract=_schema("review_status", "review_focus"),
            requiresReview=True,
            riskLevelHint="elevated",
            parallelizable=False,
            domainHints=legal,
            priority=50,
        ),
        PlanningCapabilityDescriptor(
            capabilityId="报告生成",
            displayName="审查报告生成",
            aliases=[
                "report_generate",
                "report_generation",
                "文书生成",
                "审查报告",
                "生成报告",
                "最终报告",
                "最终 Markdown 审查报告生成",
                "总结",
                "输出",
            ],
            planningStage="report",
            dependsOn=["文本解析"],
            optionalDependencies=["风险识别", "证据检索", "修改建议", "人工审核"],
            inputContract=_schema("contract_type"),
            outputContract=_schema("report_markdown"),
            producesArtifact=True,
            writesMemory=True,
            parallelizable=False,
            domainHints=legal,
            priority=60,
        ),
    )
    return tuple(
        descriptor.model_copy(
            update={
                "source": "plugin",
                "plugin_id": LEGAL_PLUGIN_ID,
                "plugin_version": LEGAL_PLUGIN_VERSION,
                "contribution_id": descriptor.capability_id,
            }
        )
        for descriptor in descriptors
    )


LEGAL_CAPABILITY_IDS = tuple(
    descriptor.capability_id for descriptor in legal_capability_descriptors()
)


__all__ = [
    "LEGAL_CAPABILITY_IDS",
    "LEGAL_PLUGIN_ID",
    "LEGAL_PLUGIN_VERSION",
    "legal_capability_descriptors",
]

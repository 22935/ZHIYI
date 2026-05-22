"""法律 Pack 的智能体实现，负责法律工作流中的专业步骤执行。"""


from packs.legal.agents.case_intake import CaseIntakeAgent
from packs.legal.agents.contract_review_migration import (
    ClauseClassifyAgent,
    ContractFinalReviewAgent,
    ContractParseAgent,
    HumanReviewGateAgent,
    LegalEvidenceMatchAgent,
    ReportGenerateAgent,
    RevisionSuggestAgent,
    RiskDetectAgent,
)
from packs.legal.agents.draft import DraftAgent
from packs.legal.agents.evidence import EvidenceAgent
from packs.legal.agents.review import ReviewAgent
from packs.legal.agents.risk import RiskAgent
from packs.legal.agents.statute import StatuteAgent

__all__ = [
    "CaseIntakeAgent",
    "ClauseClassifyAgent",
    "ContractFinalReviewAgent",
    "ContractParseAgent",
    "DraftAgent",
    "EvidenceAgent",
    "HumanReviewGateAgent",
    "LegalEvidenceMatchAgent",
    "ReportGenerateAgent",
    "RevisionSuggestAgent",
    "ReviewAgent",
    "RiskAgent",
    "RiskDetectAgent",
    "StatuteAgent",
]

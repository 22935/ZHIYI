"""法律 Pack 的注册入口与包级配置。"""


from pathlib import Path

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


def register_pack(agent_registry, workflow_registry) -> None:
    """注册法律示例 Pack，并保持 Core 与法律业务逻辑解耦。"""

    for agent in [
        CaseIntakeAgent(),
        StatuteAgent(),
        EvidenceAgent(),
        RiskAgent(),
        DraftAgent(),
        ReviewAgent(),
        ContractParseAgent(),
        ClauseClassifyAgent(),
        RiskDetectAgent(),
        LegalEvidenceMatchAgent(),
        RevisionSuggestAgent(),
        HumanReviewGateAgent(),
        ReportGenerateAgent(),
        ContractFinalReviewAgent(),
    ]:
        agent_registry.register(agent)

    workflow_registry.load_directory(Path(__file__).resolve().parent / "workflows")

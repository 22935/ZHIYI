from typing import Dict, Optional

from app.agent_core.schema.agent_types import PlannedAction, SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill, NoOpSkill
from app.agent_core.skills.case_understanding_skill import CaseUnderstandingSkill
from app.agent_core.skills.case_retrieval_skill import CaseRetrievalSkill
from app.agent_core.skills.document_generation_skill import DocumentGenerationSkill
from app.agent_core.skills.evidence_analysis_skill import EvidenceAnalysisSkill
from app.agent_core.skills.hearing_outline_generation_skill import HearingOutlineGenerationSkill
from app.agent_core.skills.jurisdiction_determination_skill import JurisdictionDeterminationSkill
from app.agent_core.skills.limitation_calculation_skill import LimitationCalculationSkill
from app.agent_core.skills.risk_assessment_skill import RiskAssessmentSkill
from app.agent_core.skills.statute_retrieval_skill import StatuteRetrievalSkill


class ToolRouter:
    """Routes planned actions to concrete skills."""

    def __init__(self, skills: Optional[Dict[str, BaseSkill]] = None):
        if skills is None:
            skills = {
                "case_understanding": CaseUnderstandingSkill(),
                "statute_retrieval": StatuteRetrievalSkill(),
                "case_retrieval": CaseRetrievalSkill(),
                "evidence_analysis": EvidenceAnalysisSkill(),
                "limitation_calculation": LimitationCalculationSkill(),
                "jurisdiction_determination": JurisdictionDeterminationSkill(),
                "hearing_outline_generation": HearingOutlineGenerationSkill(),
                "document_generation": DocumentGenerationSkill(),
                "risk_assessment": RiskAssessmentSkill(),
            }
        self.skills = skills

    async def run(self, action: PlannedAction, request: SkillRequest) -> SkillResult:
        skill = self.skills.get(action.action, NoOpSkill(action.action))
        return await skill.run(request)

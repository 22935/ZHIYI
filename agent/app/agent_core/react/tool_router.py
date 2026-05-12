from typing import Dict, List, Optional

from app.agent_core.schema.agent_types import PlannedAction, SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill, NoOpSkill
from app.agent_core.skills.case_retrieval_skill import CaseRetrievalSkill
from app.agent_core.skills.case_understanding_skill import CaseUnderstandingSkill
from app.agent_core.skills.document_generation_skill import DocumentGenerationSkill
from app.agent_core.skills.evidence_analysis_skill import EvidenceAnalysisSkill
from app.agent_core.skills.hearing_outline_generation_skill import HearingOutlineGenerationSkill
from app.agent_core.skills.jurisdiction_determination_skill import JurisdictionDeterminationSkill
from app.agent_core.skills.limitation_calculation_skill import LimitationCalculationSkill
from app.agent_core.skills.risk_assessment_skill import RiskAssessmentSkill
from app.agent_core.skills.statute_retrieval_skill import StatuteRetrievalSkill
from app.agent_core.skills.teacher import (
    ClassroomInteractionDesignSkill,
    ErrorAnalysisQuestionPushSkill,
    HomeworkGradingSkill,
    LearningPathPlanningSkill,
    LessonPlanGenerationSkill,
    ParentCommunicationSuggestionSkill,
    ProgressReportGenerationSkill,
    StudentDiagnosisSkill,
    TutoringQASkill,
)
from app.agent_core.skills.programmer import (
    CodeGenerationSkill,
    CodebaseSemanticSearchSkill,
    DiagramGenerationSkill,
    RequirementAnalysisSkill,
)
from app.agent_core.skills.writer import (
    CharacterRelationSkill,
    ContentWriteSkill,
    InspirationExpandSkill,
    OutlineGenerateSkill,
)

class ToolRouter:
    """Routes planned actions to concrete skills by role."""

    def __init__(self, skills: Optional[Dict[str, BaseSkill]] = None, enabled_roles: Optional[List[str]] = None):
        self.skills_by_role: Dict[str, Dict[str, BaseSkill]] = {}
        normalized_enabled = {
            (role or "").strip().lower()
            for role in (enabled_roles or ["lawyer", "teacher", "programmer", "writer"])
            if (role or "").strip()
        }

        if "lawyer" in normalized_enabled:
            self.register_skills_for_role("lawyer", skills or self._build_default_lawyer_skills())
        if "teacher" in normalized_enabled:
            self.register_skills_for_role("teacher", self._build_default_teacher_skills())
        if "programmer" in normalized_enabled:
            self.register_skills_for_role("programmer", self._build_default_programmer_skills())
        if "writer" in normalized_enabled:
            self.register_skills_for_role("writer", self._build_default_writer_skills())

    def _build_default_lawyer_skills(self) -> Dict[str, BaseSkill]:
        return {
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

    def _build_default_teacher_skills(self) -> Dict[str, BaseSkill]:
        return {
            "student_diagnosis": StudentDiagnosisSkill(),
            "lesson_plan_generation": LessonPlanGenerationSkill(),
            "homework_grading": HomeworkGradingSkill(),
            "error_analysis_question_push": ErrorAnalysisQuestionPushSkill(),
            "tutoring_qa": TutoringQASkill(),
            "learning_path_planning": LearningPathPlanningSkill(),
            "progress_report_generation": ProgressReportGenerationSkill(),
            "classroom_interaction_design": ClassroomInteractionDesignSkill(),
            "parent_communication_suggestion": ParentCommunicationSuggestionSkill(),
        }

    def _build_default_writer_skills(self) -> Dict[str, BaseSkill]:
        return {
            "inspiration_expand": InspirationExpandSkill(),
            "outline_generate": OutlineGenerateSkill(),
            "content_write": ContentWriteSkill(),
            "character_relation_map": CharacterRelationSkill(),
        }

    def _build_default_programmer_skills(self) -> Dict[str, BaseSkill]:
        return {
            "requirement_analysis": RequirementAnalysisSkill(),
            "codebase_semantic_search": CodebaseSemanticSearchSkill(),
            "code_generation": CodeGenerationSkill(),
            "diagram_generation": DiagramGenerationSkill(),
        }

    def register_skills_for_role(self, role: str, skills: Dict[str, BaseSkill]) -> None:
        normalized_role = (role or "").strip().lower()
        if not normalized_role:
            raise ValueError("role is required when registering role-based skills")
        self.skills_by_role[normalized_role] = dict(skills or {})

    async def run(self, action: PlannedAction, request: SkillRequest, role: str = "lawyer") -> SkillResult:
        normalized_role = (role or "lawyer").strip().lower()
        skills = self.skills_by_role.get(normalized_role)
        if skills is None:
            skills = self.skills_by_role.get("lawyer", {})

        skill = skills.get(action.action, NoOpSkill(action.action))
        return await skill.run(request)

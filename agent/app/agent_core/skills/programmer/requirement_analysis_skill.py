import asyncio
import logging
from typing import Any, Dict

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.programmer.common import ProgrammerSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class RequirementAnalysisSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("requirement_analysis")
        self.ai_service = ai_service or AIService()

    def _fallback_output(self, requirement_text: str, reason: str) -> Dict[str, Any]:
        requirement = requirement_text or "Implement requested feature."
        return {
            "requirement": requirement,
            "functional_requirements": [
                "Clarify user-facing behavior and success criteria.",
                "Define API or interface input/output contracts.",
                "Handle validation and error paths.",
            ],
            "inputs": ["User request", "Optional context from codebase search"],
            "outputs": ["Structured technical plan", "Implementation-ready steps"],
            "boundary_conditions": [
                "Empty input or invalid parameters",
                "Dependency unavailable or timeout",
                "Backward compatibility constraints",
            ],
            "acceptance_criteria": [
                "Feature path works as specified",
                "Error path is predictable and documented",
                "Output can be implemented directly",
            ],
            "suggested_modules": [],
            "fallback_reason": reason,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        requirement_text = str(action_input.get("requirement", request.text or "")).strip()

        prompt = ProgrammerSkillHelper.load_prompt(
            "requirement_analysis.txt",
            (
                "You are a senior software architect.\n"
                "Analyze requirement and return strict JSON with keys:\n"
                "functional_requirements, inputs, outputs, boundary_conditions, "
                "acceptance_criteria, suggested_modules.\n"
                "Requirement:\n{requirement}\n"
            ),
        ).replace("{requirement}", requirement_text)

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-6:],
            )
            llm_json = ProgrammerSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("RequirementAnalysisSkill LLM call failed: %s", exc)

        output = self._fallback_output(requirement_text, reason="llm_unavailable")
        if llm_json:
            output = ProgrammerSkillHelper.merge_fallback_json(output, llm_json)

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Requirement analysis completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        requirement_text = str((request.action_input or {}).get("requirement", request.text or "")).strip()
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(requirement_text, reason="timeout"),
                message="Requirement analysis timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("RequirementAnalysisSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(requirement_text, reason="error"),
                message="Requirement analysis error, fallback returned.",
            )

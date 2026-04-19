import asyncio
import logging
from typing import Any, Dict

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.writer.common import WriterSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class InspirationExpandSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("inspiration_expand")
        self.ai_service = ai_service or AIService()

    def _fallback_output(self, premise: str, reason: str) -> Dict[str, Any]:
        return {
            "premise": premise,
            "creative_tree": WriterSkillHelper.default_creative_tree(premise),
            "fallback_reason": reason,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        premise = str(action_input.get("premise", request.text or "")).strip() or "Story idea"

        prompt = WriterSkillHelper.load_prompt(
            "inspiration_expand.txt",
            (
                "You are a creative writing assistant.\n"
                "Given premise: {premise}\n"
                "Return strict JSON only with key creative_tree.\n"
                "creative_tree must be an object with id,label,description,children.\n"
            ),
        ).replace("{premise}", premise)

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-6:],
            )
            llm_json = WriterSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("InspirationExpandSkill LLM call failed: %s", exc)

        if llm_json:
            tree = WriterSkillHelper.normalize_creative_tree(llm_json, premise=premise)
            output = {"premise": premise, "creative_tree": tree}
        else:
            output = self._fallback_output(premise=premise, reason="llm_unavailable")

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Inspiration expansion completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        premise = str(action_input.get("premise", request.text or "")).strip() or "Story idea"
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(premise=premise, reason="timeout"),
                message="Inspiration expansion timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("InspirationExpandSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(premise=premise, reason="error"),
                message="Inspiration expansion error, fallback returned.",
            )

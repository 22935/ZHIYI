import asyncio
import json
import logging
from typing import Any, Dict

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class ParentCommunicationSuggestionSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("parent_communication_suggestion")
        self.ai_service = ai_service or AIService()

    def _fallback_output(self, summary: str, concerns: Any, reason: str) -> Dict[str, Any]:
        concern_list = TeacherSkillHelper.ensure_list(concerns) or ["学习习惯", "基础巩固"]
        return {
            "communication_points": [
                "先肯定学生近期的努力和进步",
                "客观说明当前薄弱环节及表现",
                "与家长达成可执行的协同计划",
            ],
            "dialogue_scripts": [
                "孩子这段时间有明显投入，我们希望继续保持。",
                "目前在关键步骤完整性上还需要加强，建议家庭侧每天固定10分钟复盘。",
            ],
            "home_support_actions": ["固定学习时段", "错题本每周复盘2次", "过程性鼓励而非只看分数"],
            "tone_suggestion": "积极、具体、合作",
            "concern_areas": concern_list,
            "summary": summary,
            "note": f"Fallback parent communication used: {reason}",
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        summary = str(action_input.get("student_performance_summary", request.text or ""))
        concerns = action_input.get("concern_areas", [])

        prompt = TeacherSkillHelper.load_prompt(
            "parent_communication_prompt.txt",
            "请输出家长沟通JSON。",
        )
        prompt = prompt.replace("{student_performance_summary}", summary)
        prompt = prompt.replace("{concern_areas}", json.dumps(concerns, ensure_ascii=False))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            llm_json = TeacherSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("ParentCommunicationSuggestionSkill LLM call failed: %s", exc)

        output = self._fallback_output(summary=summary, concerns=concerns, reason="llm_unavailable" if not llm_json else "fallback_merge")

        if llm_json:
            output["communication_points"] = (
                TeacherSkillHelper.ensure_list(llm_json.get("communication_points")) or output["communication_points"]
            )
            output["dialogue_scripts"] = TeacherSkillHelper.ensure_list(llm_json.get("dialogue_scripts")) or output["dialogue_scripts"]
            output["home_support_actions"] = (
                TeacherSkillHelper.ensure_list(llm_json.get("home_support_actions")) or output["home_support_actions"]
            )
            output["tone_suggestion"] = str(llm_json.get("tone_suggestion", output["tone_suggestion"]))

        return SkillResult(skillName=self.name, success=True, output=output, message="Parent communication suggestion generated.")

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    summary=str(action_input.get("student_performance_summary", request.text or "")),
                    concerns=action_input.get("concern_areas", []),
                    reason="timeout",
                ),
                message="Parent communication timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("ParentCommunicationSuggestionSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    summary=str(action_input.get("student_performance_summary", request.text or "")),
                    concerns=action_input.get("concern_areas", []),
                    reason="error",
                ),
                message="Parent communication error, fallback returned.",
            )

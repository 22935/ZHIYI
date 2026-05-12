import asyncio
import logging
from typing import Any, Dict, List

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.writer.common import WriterSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class CharacterRelationSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("character_relation_map")
        self.ai_service = ai_service or AIService()

    def _resolve_inputs(self, request: SkillRequest) -> Dict[str, Any]:
        action_input = request.action_input or {}
        story_description = str(action_input.get("story_description", request.text or "")).strip()
        character_list = WriterSkillHelper.ensure_list(action_input.get("character_list"))
        return {
            "story_description": story_description,
            "character_list": character_list,
        }

    def _fallback_output(self, story_description: str, character_list: List[str], reason: str) -> Dict[str, Any]:
        graph = WriterSkillHelper.default_relation_graph(
            story_description=story_description,
            character_list=character_list,
        )
        return {
            "story_description": story_description,
            "character_list": character_list,
            "relation_graph": graph,
            "fallback_reason": reason,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        inputs = self._resolve_inputs(request)
        story_description = inputs["story_description"]
        character_list = inputs["character_list"]

        prompt = WriterSkillHelper.load_prompt(
            "character_relation.txt",
            (
                "你是一名人物关系图助手，请始终使用简体中文（JSON 键名保持原样）。\n"
                "故事描述：\n{story_description}\n\n"
                "角色列表：\n{character_list}\n\n"
                "请仅返回严格 JSON：\n"
                "{\"relation_graph\": {\"nodes\": [{\"id\":\"\", \"label\":\"\", \"group\":\"\"}], "
                "\"edges\": [{\"from\":\"\", \"to\":\"\", \"label\":\"\"}]}}\n"
            ),
        )
        prompt = prompt.replace("{story_description}", story_description)
        prompt = prompt.replace("{character_list}", ", ".join(character_list))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-6:],
            )
            llm_json = WriterSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("CharacterRelationSkill LLM call failed: %s", exc)

        if llm_json:
            graph = WriterSkillHelper.normalize_relation_graph(
                payload=llm_json,
                story_description=story_description,
                character_list=character_list,
            )
            output = {
                "story_description": story_description,
                "character_list": character_list,
                "relation_graph": graph,
            }
        else:
            output = self._fallback_output(
                story_description=story_description,
                character_list=character_list,
                reason="llm_unavailable",
            )

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="人物关系图生成完成。",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        inputs = self._resolve_inputs(request)
        story_description = inputs["story_description"]
        character_list = inputs["character_list"]

        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(story_description, character_list, reason="timeout"),
                message="人物关系图生成超时，已返回降级结果。",
            )
        except Exception as exc:
            logger.error("CharacterRelationSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(story_description, character_list, reason="error"),
                message="人物关系图生成执行异常，已返回降级结果。",
            )

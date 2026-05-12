import asyncio
import logging
from typing import Any, Dict

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.writer.common import WriterSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class ContentWriteSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("content_write")
        self.ai_service = ai_service or AIService()

    def _resolve_outline_context(self, request: SkillRequest) -> str:
        action_input = request.action_input or {}
        raw = str(action_input.get("outline_context", "")).strip()
        if raw:
            return raw

        observations = request.memory.get("observations", {})
        if isinstance(observations, dict):
            outline_payload = observations.get("outline_generate", {})
            if isinstance(outline_payload, dict):
                markdown = str(outline_payload.get("outline_markdown", "")).strip()
                if markdown:
                    return markdown

        return str(request.text or "").strip()

    def _fallback_content(self, outline_context: str, chapter_index: int, style: str) -> str:
        safe_style = style or "自然叙事"
        safe_outline = outline_context or "未提供大纲上下文。"
        return (
            f"# 第{chapter_index}章\n\n"
            f"风格：{safe_style}\n\n"
            "主角在关键抉择前短暂停步，反复衡量失败代价。\n"
            "一个新线索改变了行动方向，迫使其做出艰难选择。\n"
            "章节结尾，风险进一步抬升，下一轮冲突清晰可见。\n\n"
            "上下文锚点：\n"
            f"{safe_outline[:500]}"
        )

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        outline_context = self._resolve_outline_context(request)
        chapter_index = WriterSkillHelper.to_int(action_input.get("chapter_index"), 1)
        chapter_index = max(1, chapter_index)
        style = str(action_input.get("style", "自然叙事")).strip() or "自然叙事"

        prompt = WriterSkillHelper.load_prompt(
            "content_write.txt",
            (
                "你是一名小说写作助手，请始终使用简体中文。\n"
                "请按风格 {style} 写作第 {chapter_index} 章。\n"
                "大纲上下文：\n{outline_context}\n"
                "仅返回章节正文。\n"
            ),
        )
        prompt = prompt.replace("{outline_context}", outline_context)
        prompt = prompt.replace("{chapter_index}", str(chapter_index))
        prompt = prompt.replace("{style}", style)

        content = ""
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-8:],
            )
            content = (llm_response.get("text", "") or "").strip()
        except Exception as exc:
            logger.warning("ContentWriteSkill LLM call failed: %s", exc)

        if not content:
            content = self._fallback_content(
                outline_context=outline_context,
                chapter_index=chapter_index,
                style=style,
            )

        output = {
            "outline_context": outline_context,
            "chapter_index": chapter_index,
            "style": style,
            "content": content,
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="正文写作完成。",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        outline_context = self._resolve_outline_context(request)
        chapter_index = WriterSkillHelper.to_int(action_input.get("chapter_index"), 1)
        style = str(action_input.get("style", "自然叙事")).strip() or "自然叙事"

        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            fallback = self._fallback_content(
                outline_context=outline_context,
                chapter_index=chapter_index,
                style=style,
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output={"content": fallback, "chapter_index": chapter_index, "style": style},
                message="正文写作超时，已返回降级结果。",
            )
        except Exception as exc:
            logger.error("ContentWriteSkill failed: %s", exc, exc_info=True)
            fallback = self._fallback_content(
                outline_context=outline_context,
                chapter_index=chapter_index,
                style=style,
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output={"content": fallback, "chapter_index": chapter_index, "style": style},
                message="正文写作执行异常，已返回降级结果。",
            )

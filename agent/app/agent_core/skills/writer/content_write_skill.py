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
        safe_style = style or "natural narrative"
        safe_outline = outline_context or "No outline provided."
        return (
            f"# Chapter {chapter_index}\n\n"
            f"Style: {safe_style}\n\n"
            "The protagonist pauses before a decisive action, replaying the cost of failure.\n"
            "A new clue shifts the direction of the journey, forcing a difficult choice.\n"
            "By the end of the chapter, the stakes are raised and the next conflict is clear.\n\n"
            "Context anchor:\n"
            f"{safe_outline[:500]}"
        )

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        outline_context = self._resolve_outline_context(request)
        chapter_index = WriterSkillHelper.to_int(action_input.get("chapter_index"), 1)
        chapter_index = max(1, chapter_index)
        style = str(action_input.get("style", "natural narrative")).strip() or "natural narrative"

        prompt = WriterSkillHelper.load_prompt(
            "content_write.txt",
            (
                "You are a fiction writer.\n"
                "Write chapter {chapter_index} in style: {style}\n"
                "Outline context:\n{outline_context}\n"
                "Return chapter text only.\n"
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
            message="Content writing completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        outline_context = self._resolve_outline_context(request)
        chapter_index = WriterSkillHelper.to_int(action_input.get("chapter_index"), 1)
        style = str(action_input.get("style", "natural narrative")).strip() or "natural narrative"

        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
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
                message="Content writing timeout, fallback returned.",
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
                message="Content writing error, fallback returned.",
            )

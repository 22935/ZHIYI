import asyncio
import logging
from typing import Any, Dict

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.writer.common import WriterSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class OutlineGenerateSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("outline_generate")
        self.ai_service = ai_service or AIService()

    def _derive_creative_selection(self, request: SkillRequest) -> str:
        action_input = request.action_input or {}
        from_input = str(action_input.get("creative_selection", "")).strip()
        if from_input:
            return from_input

        observations = request.memory.get("observations", {})
        if isinstance(observations, dict):
            inspiration_payload = observations.get("inspiration_expand", {})
            if isinstance(inspiration_payload, dict):
                tree = inspiration_payload.get("creative_tree", {})
                if isinstance(tree, dict):
                    from_tree = WriterSkillHelper.creative_tree_to_selection(tree)
                    if from_tree:
                        return from_tree

        return str(request.text or "").strip()

    def _fallback_markdown(self, creative_selection: str, chapters_count: int) -> str:
        safe_selection = creative_selection or "故事概念"
        count = max(3, min(20, chapters_count or 6))
        lines = [
            "# 故事大纲",
            "",
            "## 核心创意",
            safe_selection,
            "",
        ]
        for index in range(1, count + 1):
            lines.append(f"## 第{index}章")
            lines.append(f"- 章节目标：推进本章核心冲突。")
            lines.append("- 关键事件：抬升风险并揭示新信息。")
            lines.append("- 情绪节拍：呈现角色抉择与变化。")
            lines.append("")
        return "\n".join(lines).strip()

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        creative_selection = self._derive_creative_selection(request)
        chapters_count = WriterSkillHelper.to_int(action_input.get("chapters_count"), 6)
        chapters_count = max(3, min(20, chapters_count))

        prompt = WriterSkillHelper.load_prompt(
            "outline_generate.txt",
            (
                "你是一名故事架构师，请始终使用简体中文。\n"
                "创意方向：\n{creative_selection}\n"
                "目标章节数：{chapters_count}\n"
                "请仅返回 Markdown，并按章节清晰递进。\n"
            ),
        )
        prompt = prompt.replace("{creative_selection}", creative_selection)
        prompt = prompt.replace("{chapters_count}", str(chapters_count))

        outline_markdown = ""
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-6:],
            )
            outline_markdown = (llm_response.get("text", "") or "").strip()
        except Exception as exc:
            logger.warning("OutlineGenerateSkill LLM call failed: %s", exc)

        if not outline_markdown:
            outline_markdown = self._fallback_markdown(
                creative_selection=creative_selection,
                chapters_count=chapters_count,
            )

        output = {
            "creative_selection": creative_selection,
            "chapters_count": chapters_count,
            "outline_markdown": outline_markdown,
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="大纲生成完成。",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        creative_selection = self._derive_creative_selection(request)
        chapters_count = WriterSkillHelper.to_int((request.action_input or {}).get("chapters_count"), 6)
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            fallback = self._fallback_markdown(creative_selection=creative_selection, chapters_count=chapters_count)
            return SkillResult(
                skillName=self.name,
                success=True,
                output={"outline_markdown": fallback, "creative_selection": creative_selection},
                message="大纲生成超时，已返回降级结果。",
            )
        except Exception as exc:
            logger.error("OutlineGenerateSkill failed: %s", exc, exc_info=True)
            fallback = self._fallback_markdown(creative_selection=creative_selection, chapters_count=chapters_count)
            return SkillResult(
                skillName=self.name,
                success=True,
                output={"outline_markdown": fallback, "creative_selection": creative_selection},
                message="大纲生成执行异常，已返回降级结果。",
            )

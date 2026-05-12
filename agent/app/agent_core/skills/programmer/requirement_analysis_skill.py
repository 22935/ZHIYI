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
        requirement = requirement_text or "实现用户请求的功能。"
        return {
            "requirement": requirement,
            "functional_requirements": [
                "明确用户可见行为与成功标准。",
                "定义 API 或接口的输入输出契约。",
                "覆盖参数校验与异常路径处理。",
            ],
            "inputs": ["用户请求", "来自代码库检索的可选上下文"],
            "outputs": ["结构化技术方案", "可直接实施的步骤"],
            "boundary_conditions": [
                "输入为空或参数非法",
                "依赖不可用或超时",
                "向后兼容约束",
            ],
            "acceptance_criteria": [
                "功能路径按规格可用",
                "错误路径可预期且可追踪",
                "输出内容可直接用于实现",
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
                "你是一名资深软件架构师，请始终使用简体中文（JSON 键名保持原样）。\n"
                "请分析需求并返回严格 JSON，包含键：\n"
                "functional_requirements, inputs, outputs, boundary_conditions, "
                "acceptance_criteria, suggested_modules。\n"
                "需求：\n{requirement}\n"
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
            message="需求分析完成。",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        requirement_text = str((request.action_input or {}).get("requirement", request.text or "")).strip()
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(requirement_text, reason="timeout"),
                message="需求分析超时，已返回降级结果。",
            )
        except Exception as exc:
            logger.error("RequirementAnalysisSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(requirement_text, reason="error"),
                message="需求分析执行异常，已返回降级结果。",
            )

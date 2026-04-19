import asyncio
import json
import logging
from typing import Any, Dict, List

from app.agent_core.retrieval.education_index_builder import education_index_builder
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class LearningPathPlanningSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("learning_path_planning")
        self.ai_service = ai_service or AIService()

    def _build_rule_schedule(self, available_days: int, kp_names: List[str], current_level: str) -> List[Dict[str, Any]]:
        days = max(1, min(7, available_days))
        base_minutes = 50 if current_level in {"low", "基础"} else 40
        schedule: List[Dict[str, Any]] = []

        for day in range(1, days + 1):
            core = kp_names[(day - 1) % len(kp_names)] if kp_names else "基础巩固"
            review = kp_names[(day) % len(kp_names)] if len(kp_names) > 1 else "错题复盘"
            schedule.append(
                {
                    "day": day,
                    "core_task": f"学习{core}",
                    "consolidation_task": f"完成{review}相关练习",
                    "minutes": base_minutes,
                }
            )
        return schedule

    def _to_markdown(self, schedule: List[Dict[str, Any]], resource_list: List[str]) -> str:
        lines = [
            "| 天数 | 核心任务 | 巩固任务 | 预计时长 |",
            "|---|---|---|---|",
        ]
        for item in schedule:
            lines.append(
                f"| Day {item['day']} | {item['core_task']} | {item['consolidation_task']} | {item['minutes']}分钟 |"
            )

        lines.append("\n资源建议：")
        for resource in resource_list:
            lines.append(f"- {resource}")
        return "\n".join(lines)

    def _fallback_output(
        self,
        subject: str,
        current_level: str,
        target_score: int,
        available_days: int,
        kp_payload: List[Dict[str, Any]],
        reason: str,
    ) -> Dict[str, Any]:
        kp_names = [item.get("name", "") for item in kp_payload if item.get("name")]
        schedule = self._build_rule_schedule(available_days=available_days, kp_names=kp_names, current_level=current_level)
        resources = ["教材例题", "单元基础题", "错题本复盘"]
        markdown = self._to_markdown(schedule, resources)
        return {
            "subject": subject,
            "current_level": current_level,
            "target_score": target_score,
            "available_days": available_days,
            "schedule": schedule,
            "resource_recommendations": resources,
            "plan": markdown,
            "summary": f"Fallback learning path used: {reason}",
            "knowledge_points": kp_payload,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        subject = str(action_input.get("subject", "数学"))
        current_level = str(action_input.get("current_level", "medium"))
        target_score = TeacherSkillHelper.to_int(action_input.get("target_score", 85), 85)
        available_days = max(1, TeacherSkillHelper.to_int(action_input.get("available_days", 7), 7))

        kp_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.KNOWLEDGE_POINTS_COLLECTION,
            query_text=f"{subject} {request.text} {current_level}",
            top_k=8,
            fallback_fields=["name", "mastery_criteria", "prerequisites", "subject", "grade"],
        )
        kp_payload = [row.get("metadata", {}) for row in kp_rows]

        prompt = TeacherSkillHelper.load_prompt(
            "learning_path_prompt.txt",
            "请输出学习路径Markdown。",
        )
        prompt = prompt.replace("{subject}", subject)
        prompt = prompt.replace("{current_level}", current_level)
        prompt = prompt.replace("{target_score}", str(target_score))
        prompt = prompt.replace("{available_days}", str(available_days))
        prompt = prompt.replace("{knowledge_points}", json.dumps(kp_payload, ensure_ascii=False))

        llm_markdown = ""
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            llm_markdown = (llm_response.get("text", "") or "").strip()
        except Exception as exc:
            logger.warning("LearningPathPlanningSkill LLM call failed: %s", exc)

        output = self._fallback_output(
            subject=subject,
            current_level=current_level,
            target_score=target_score,
            available_days=available_days,
            kp_payload=kp_payload,
            reason="llm_unavailable" if not llm_markdown else "fallback_merge",
        )

        if llm_markdown:
            output["plan"] = llm_markdown

        return SkillResult(skillName=self.name, success=True, output=output, message="Learning path planning completed.")

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    subject=str(action_input.get("subject", "数学")),
                    current_level=str(action_input.get("current_level", "medium")),
                    target_score=TeacherSkillHelper.to_int(action_input.get("target_score", 85), 85),
                    available_days=TeacherSkillHelper.to_int(action_input.get("available_days", 7), 7),
                    kp_payload=[],
                    reason="timeout",
                ),
                message="Learning path planning timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("LearningPathPlanningSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    subject=str(action_input.get("subject", "数学")),
                    current_level=str(action_input.get("current_level", "medium")),
                    target_score=TeacherSkillHelper.to_int(action_input.get("target_score", 85), 85),
                    available_days=TeacherSkillHelper.to_int(action_input.get("available_days", 7), 7),
                    kp_payload=[],
                    reason="error",
                ),
                message="Learning path planning error, fallback returned.",
            )

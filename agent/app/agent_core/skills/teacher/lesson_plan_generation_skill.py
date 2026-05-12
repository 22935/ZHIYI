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


class LessonPlanGenerationSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("lesson_plan_generation")
        self.ai_service = ai_service or AIService()

    def _fallback_markdown(
        self,
        topic: str,
        subject: str,
        grade: str,
        duration: str,
        class_profile: str,
        template_names: List[str],
        kp_names: List[str],
    ) -> str:
        focus_points = kp_names[:4] or ["核心知识点梳理", "基础训练"]
        template_hint = "、".join(template_names[:2]) if template_names else "通用新授课模板"
        return (
            f"# 课题\n{grade}{subject}：{topic}\n\n"
            "## 教学目标\n"
            "1. 理解本课核心概念并能完成基础应用。\n"
            "2. 能解释关键步骤并完成分层练习。\n"
            "3. 形成错题反思与自我检查习惯。\n\n"
            "## 教学重难点\n"
            f"- 重点：{focus_points[0]}\n"
            f"- 难点：{focus_points[1] if len(focus_points) > 1 else '综合应用'}\n\n"
            "## 教学过程\n"
            "### 1. 导入（8分钟）\n"
            f"- 结合班级学情：{class_profile or '关注计算与审题能力'}。\n"
            "- 通过真实情境问题引出本课目标。\n\n"
            "### 2. 新授（15分钟）\n"
            f"- 采用模板：{template_hint}。\n"
            f"- 围绕知识点：{'、'.join(focus_points)}。\n"
            "- 教师示范+学生口头复述。\n\n"
            "### 3. 练习与反馈（15分钟）\n"
            "- 基础题：巩固概念与步骤。\n"
            "- 提升题：迁移应用与错因分析。\n"
            "- 课堂即时反馈并纠偏。\n\n"
            "### 4. 总结（2分钟）\n"
            "- 学生总结今日收获与疑点，教师补充。\n\n"
            "## 分层作业\n"
            "- 基础层：完成5道基础题，重在步骤规范。\n"
            "- 提升层：完成2道综合题并写1条错因反思。\n\n"
            "## 课堂评价与反思\n"
            f"- 课时安排：{duration}。\n"
            "- 关注学生参与度、正确率和表达完整性。\n"
        )

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        topic = str(action_input.get("topic", request.text or "本课主题"))
        subject = str(action_input.get("subject", "数学"))
        grade = str(action_input.get("grade", "八年级"))
        duration = str(action_input.get("duration", "1课时"))
        class_profile = str(action_input.get("class_profile", ""))

        template_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.LESSON_TEMPLATES_COLLECTION,
            query_text=f"{subject} {grade} {topic}",
            top_k=3,
            fallback_fields=["template_name", "subject", "grade", "lesson_type", "sample_content"],
        )
        kp_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.KNOWLEDGE_POINTS_COLLECTION,
            query_text=f"{subject} {grade} {topic}",
            top_k=6,
            fallback_fields=["name", "prerequisites", "mastery_criteria", "vector_content"],
        )

        template_payload = [row.get("metadata", {}) for row in template_rows]
        kp_payload = [row.get("metadata", {}) for row in kp_rows]
        template_names = [item.get("template_name", "") for item in template_payload if item.get("template_name")]
        kp_names = [item.get("name", "") for item in kp_payload if item.get("name")]

        prompt = TeacherSkillHelper.load_prompt(
            "lesson_plan_prompt.txt",
            "请生成完整教案Markdown，包含教学目标、重难点、教学过程和分层作业。",
        )
        prompt = prompt.replace("{topic}", topic)
        prompt = prompt.replace("{subject}", subject)
        prompt = prompt.replace("{grade}", grade)
        prompt = prompt.replace("{duration}", duration)
        prompt = prompt.replace("{class_profile}", class_profile)
        prompt = prompt.replace("{lesson_templates}", json.dumps(template_payload, ensure_ascii=False))
        prompt = prompt.replace("{knowledge_points}", json.dumps(kp_payload, ensure_ascii=False))

        lesson_plan_markdown = ""
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            lesson_plan_markdown = (llm_response.get("text", "") or "").strip()
        except Exception as exc:
            logger.warning("LessonPlanGenerationSkill LLM call failed: %s", exc)

        if not lesson_plan_markdown:
            lesson_plan_markdown = self._fallback_markdown(
                topic=topic,
                subject=subject,
                grade=grade,
                duration=duration,
                class_profile=class_profile,
                template_names=template_names,
                kp_names=kp_names,
            )

        output = {
            "topic": topic,
            "subject": subject,
            "grade": grade,
            "duration": duration,
            "lesson_plan": lesson_plan_markdown,
            "template_refs": template_payload,
            "knowledge_points": kp_payload,
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Lesson plan generated.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            fallback = self._fallback_markdown(
                topic=str(action_input.get("topic", request.text or "本课主题")),
                subject=str(action_input.get("subject", "数学")),
                grade=str(action_input.get("grade", "八年级")),
                duration=str(action_input.get("duration", "1课时")),
                class_profile=str(action_input.get("class_profile", "")),
                template_names=[],
                kp_names=[],
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output={"lesson_plan": fallback},
                message="Lesson plan generation timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("LessonPlanGenerationSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            fallback = self._fallback_markdown(
                topic=str(action_input.get("topic", request.text or "本课主题")),
                subject=str(action_input.get("subject", "数学")),
                grade=str(action_input.get("grade", "八年级")),
                duration=str(action_input.get("duration", "1课时")),
                class_profile=str(action_input.get("class_profile", "")),
                template_names=[],
                kp_names=[],
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output={"lesson_plan": fallback},
                message="Lesson plan generation error, fallback returned.",
            )

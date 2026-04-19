import asyncio
import json
import logging
from typing import Any, Dict

from app.agent_core.retrieval.education_index_builder import education_index_builder
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class TutoringQASkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("tutoring_qa")
        self.ai_service = ai_service or AIService()

    def _fallback_output(self, question: str, subject: str, grade: str, kp_payload: Any, reason: str) -> Dict[str, Any]:
        return {
            "question": question,
            "subject": subject,
            "grade": grade,
            "guided_answer": "我们先不急着给结论，先确认已知条件，再列出可以使用的公式或规律。",
            "hints": ["先圈出题目中的已知量", "写出对应公式", "代入前先统一单位"],
            "steps": ["读题并标注条件", "选择知识点", "分步计算或推理", "检查结果"],
            "summary": f"Fallback tutoring used: {reason}",
            "knowledge_points": kp_payload,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        question = str(action_input.get("question", request.text or ""))
        subject = str(action_input.get("subject", "数学"))
        grade = str(action_input.get("student_grade", action_input.get("grade", "八年级")))

        kp_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.KNOWLEDGE_POINTS_COLLECTION,
            query_text=f"{subject} {grade} {question}",
            top_k=4,
            fallback_fields=["name", "mastery_criteria", "vector_content", "subject", "grade"],
        )
        kp_payload = [row.get("metadata", {}) for row in kp_rows]

        prompt = TeacherSkillHelper.load_prompt(
            "qa_tutor_prompt.txt",
            "请输出引导式答疑JSON，字段guided_answer,hints,steps,summary。",
        )
        prompt = prompt.replace("{question}", question)
        prompt = prompt.replace("{grade}", grade)
        prompt = prompt.replace("{subject}", subject)
        prompt = prompt.replace("{knowledge_points}", json.dumps(kp_payload, ensure_ascii=False))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            llm_json = TeacherSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("TutoringQASkill LLM call failed: %s", exc)

        output = self._fallback_output(
            question=question,
            subject=subject,
            grade=grade,
            kp_payload=kp_payload,
            reason="llm_unavailable" if not llm_json else "fallback_merge",
        )

        if llm_json:
            output["guided_answer"] = str(llm_json.get("guided_answer", output["guided_answer"]))
            output["hints"] = TeacherSkillHelper.ensure_list(llm_json.get("hints")) or output["hints"]
            output["steps"] = TeacherSkillHelper.ensure_list(llm_json.get("steps")) or output["steps"]
            output["summary"] = str(llm_json.get("summary", output["summary"]))

        return SkillResult(skillName=self.name, success=True, output=output, message="Tutoring QA completed.")

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    question=str(action_input.get("question", request.text or "")),
                    subject=str(action_input.get("subject", "数学")),
                    grade=str(action_input.get("student_grade", action_input.get("grade", "八年级"))),
                    kp_payload=[],
                    reason="timeout",
                ),
                message="Tutoring QA timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("TutoringQASkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    question=str(action_input.get("question", request.text or "")),
                    subject=str(action_input.get("subject", "数学")),
                    grade=str(action_input.get("student_grade", action_input.get("grade", "八年级"))),
                    kp_payload=[],
                    reason="error",
                ),
                message="Tutoring QA error, fallback returned.",
            )

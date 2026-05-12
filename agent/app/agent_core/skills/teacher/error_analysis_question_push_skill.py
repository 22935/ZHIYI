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


class ErrorAnalysisQuestionPushSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("error_analysis_question_push")
        self.ai_service = ai_service or AIService()

    def _fallback_output(
        self,
        question: str,
        student_answer: str,
        correct_answer: str,
        kp_tags: List[str],
        kp_details: List[Dict[str, Any]],
        similar_questions: List[Dict[str, Any]],
        reason: str,
    ) -> Dict[str, Any]:
        gaps = kp_tags or [item.get("name", "基础概念") for item in kp_details[:2] if item.get("name")]
        if not gaps:
            gaps = ["审题与步骤完整性"]

        return {
            "question": question,
            "knowledge_gap": gaps,
            "gap_details": kp_details,
            "analysis_summary": f"Fallback error attribution used: {reason}",
            "root_causes": ["关键步骤缺失", "概念调用不稳定"],
            "remediation_suggestions": ["先完成同知识点基础题", "做题后写1条错因反思"],
            "similar_questions": similar_questions,
            "student_answer": student_answer,
            "correct_answer": correct_answer,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        question = str(action_input.get("question", request.text or ""))
        student_answer = str(action_input.get("student_answer", ""))
        correct_answer = str(action_input.get("correct_answer", ""))
        kp_tags = TeacherSkillHelper.ensure_list(action_input.get("knowledge_point_tags", []))

        kp_query = " ".join(kp_tags) if kp_tags else f"{question} {correct_answer}"
        kp_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.KNOWLEDGE_POINTS_COLLECTION,
            query_text=kp_query,
            top_k=4,
            fallback_fields=["name", "mastery_criteria", "vector_content", "subject", "grade"],
        )
        kp_details = [
            {
                "id": row.get("id", ""),
                "name": row.get("metadata", {}).get("name", ""),
                "subject": row.get("metadata", {}).get("subject", ""),
                "grade": row.get("metadata", {}).get("grade", ""),
                "mastery_criteria": row.get("metadata", {}).get("mastery_criteria", ""),
            }
            for row in kp_rows
        ]

        prompt = TeacherSkillHelper.load_prompt(
            "error_attribution_prompt.txt",
            "请输出错题归因JSON，字段knowledge_gap,root_causes,remediation_suggestions,analysis_summary。",
        )
        prompt = prompt.replace("{question}", question)
        prompt = prompt.replace("{correct_answer}", correct_answer)
        prompt = prompt.replace("{student_answer}", student_answer)
        prompt = prompt.replace("{knowledge_point_tags}", json.dumps(kp_tags, ensure_ascii=False))
        prompt = prompt.replace("{matched_knowledge_points}", json.dumps(kp_details, ensure_ascii=False))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            llm_json = TeacherSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("ErrorAnalysisQuestionPushSkill LLM call failed: %s", exc)

        gaps = TeacherSkillHelper.ensure_list(llm_json.get("knowledge_gap")) if llm_json else []
        if not gaps:
            gaps = kp_tags or [item.get("name", "") for item in kp_details if item.get("name")]

        question_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.QUESTION_BANK_COLLECTION,
            query_text=" ".join(gaps) if gaps else question,
            top_k=3,
            fallback_fields=["question_text", "knowledge_points", "difficulty", "question_type", "subject", "grade"],
        )
        similar_questions = []
        for row in question_rows:
            metadata = row.get("metadata", {}) if isinstance(row.get("metadata", {}), dict) else {}
            similar_questions.append(
                {
                    "id": row.get("id", ""),
                    "question_text": metadata.get("question_text", ""),
                    "answer": metadata.get("answer", ""),
                    "knowledge_points": metadata.get("knowledge_points", []),
                    "difficulty": metadata.get("difficulty", ""),
                    "question_type": metadata.get("question_type", ""),
                    "grade": metadata.get("grade", ""),
                    "subject": metadata.get("subject", ""),
                    "score": row.get("score", 0.0),
                }
            )

        output = self._fallback_output(
            question=question,
            student_answer=student_answer,
            correct_answer=correct_answer,
            kp_tags=kp_tags,
            kp_details=kp_details,
            similar_questions=similar_questions,
            reason="llm_unavailable" if not llm_json else "fallback_merge",
        )

        if llm_json:
            output["knowledge_gap"] = gaps or output["knowledge_gap"]
            output["analysis_summary"] = str(llm_json.get("analysis_summary", output["analysis_summary"]))
            output["root_causes"] = TeacherSkillHelper.ensure_list(llm_json.get("root_causes")) or output["root_causes"]
            output["remediation_suggestions"] = (
                TeacherSkillHelper.ensure_list(llm_json.get("remediation_suggestions")) or output["remediation_suggestions"]
            )

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Error attribution and question push completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            fallback = self._fallback_output(
                question=str(action_input.get("question", request.text or "")),
                student_answer=str(action_input.get("student_answer", "")),
                correct_answer=str(action_input.get("correct_answer", "")),
                kp_tags=TeacherSkillHelper.ensure_list(action_input.get("knowledge_point_tags", [])),
                kp_details=[],
                similar_questions=[],
                reason="timeout",
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output=fallback,
                message="Error attribution timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("ErrorAnalysisQuestionPushSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            fallback = self._fallback_output(
                question=str(action_input.get("question", request.text or "")),
                student_answer=str(action_input.get("student_answer", "")),
                correct_answer=str(action_input.get("correct_answer", "")),
                kp_tags=TeacherSkillHelper.ensure_list(action_input.get("knowledge_point_tags", [])),
                kp_details=[],
                similar_questions=[],
                reason="error",
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output=fallback,
                message="Error attribution error, fallback returned.",
            )

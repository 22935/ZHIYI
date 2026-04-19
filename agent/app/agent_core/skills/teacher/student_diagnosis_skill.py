import asyncio
import json
import logging
import statistics
from typing import Any, Dict, List

from app.agent_core.federated.federated_adapter import FederatedAdapter
from app.agent_core.retrieval.education_index_builder import education_index_builder
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class StudentDiagnosisSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None, federated_adapter: FederatedAdapter = None):
        super().__init__("student_diagnosis")
        self.ai_service = ai_service or AIService()
        self.federated_adapter = federated_adapter or FederatedAdapter()

    def _calc_mastery(self, scores: List[float]) -> Dict[str, Any]:
        if not scores:
            return {"base_score": 65.0, "volatility": 0.0, "trend": "unknown"}

        avg_score = sum(scores) / len(scores)
        volatility = statistics.pstdev(scores) if len(scores) > 1 else 0.0
        trend = "up" if scores[-1] > scores[0] else "down" if scores[-1] < scores[0] else "flat"

        calibrated = avg_score - min(12.0, volatility * 0.8)
        return {
            "base_score": TeacherSkillHelper.clamp_score(calibrated),
            "volatility": round(volatility, 2),
            "trend": trend,
        }

    def _score_to_level(self, score: float) -> str:
        if score >= 80:
            return "high"
        if score >= 60:
            return "medium"
        return "low"

    def _fallback_output(
        self,
        student_id: str,
        subject: str,
        grade: str,
        scores: List[float],
        knowledge_points: List[Dict[str, Any]],
        reason: str,
    ) -> Dict[str, Any]:
        mastery = self._calc_mastery(scores)
        base_score = mastery["base_score"]
        weak_points = [
            item.get("metadata", {}).get("name", "基础知识巩固")
            for item in knowledge_points[:2]
            if item.get("metadata", {}).get("name")
        ]
        if not weak_points:
            weak_points = ["计算准确性", "审题完整性"]

        strengths = ["学习态度稳定"] if base_score >= 65 else ["愿意配合完成练习"]
        learning_style = "稳健型" if mastery["volatility"] <= 8 else "波动型"

        return {
            "student_id": student_id,
            "subject": subject,
            "grade": grade,
            "weak_points": weak_points,
            "strengths": strengths,
            "mastery_score": round(base_score, 2),
            "mastery_level": self._score_to_level(base_score),
            "learning_style": learning_style,
            "trend": mastery["trend"],
            "volatility": mastery["volatility"],
            "diagnosis_summary": f"Fallback diagnosis used: {reason}",
            "recommended_actions": ["先补齐薄弱知识点", "每日10-15分钟针对性训练"],
            "federated": {
                "enabled": self.federated_adapter.enabled,
                "applied": False,
                "risk_adjustment": 0.0,
                "confidence": 0.0,
                "federated_nodes_count": 0,
            },
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        student_id = str(action_input.get("student_id", "unknown_student"))
        subject = str(action_input.get("subject", "数学"))
        grade = str(action_input.get("grade", "八年级"))
        teacher_notes = str(action_input.get("teacher_notes", ""))
        recent_scores = TeacherSkillHelper.parse_scores(action_input.get("recent_scores", []))

        query_text = f"{subject} {grade} {request.text}"
        knowledge_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.KNOWLEDGE_POINTS_COLLECTION,
            query_text=query_text,
            top_k=6,
            fallback_fields=["name", "subject", "grade", "mastery_criteria", "vector_content"],
        )
        knowledge_names = [row.get("metadata", {}).get("name", "") for row in knowledge_rows if row.get("metadata", {}).get("name")]

        mastery = self._calc_mastery(recent_scores)
        base_score = mastery["base_score"]

        prompt = TeacherSkillHelper.load_prompt(
            "diagnosis_prompt.txt",
            "请输出学情诊断JSON，字段包含weak_points,strengths,mastery_level,learning_style,diagnosis_summary,next_actions。",
        )
        prompt = prompt.replace("{student_id}", student_id)
        prompt = prompt.replace("{subject}", subject)
        prompt = prompt.replace("{grade}", grade)
        prompt = prompt.replace("{recent_scores}", json.dumps(recent_scores, ensure_ascii=False))
        prompt = prompt.replace("{teacher_notes}", teacher_notes)
        prompt = prompt.replace("{knowledge_points}", json.dumps(knowledge_names, ensure_ascii=False))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await asyncio.wait_for(
                self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:]),
                timeout=6,
            )
            llm_json = TeacherSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except asyncio.TimeoutError:
            logger.warning("StudentDiagnosisSkill LLM call timed out.")
        except Exception as exc:
            logger.warning("StudentDiagnosisSkill LLM call failed: %s", exc)

        output = self._fallback_output(
            student_id=student_id,
            subject=subject,
            grade=grade,
            scores=recent_scores,
            knowledge_points=knowledge_rows,
            reason="llm_unavailable" if not llm_json else "fallback_merge",
        )

        if llm_json:
            output["weak_points"] = TeacherSkillHelper.ensure_list(llm_json.get("weak_points")) or output["weak_points"]
            output["strengths"] = TeacherSkillHelper.ensure_list(llm_json.get("strengths")) or output["strengths"]
            output["learning_style"] = str(llm_json.get("learning_style", output["learning_style"]))
            output["diagnosis_summary"] = str(llm_json.get("diagnosis_summary", output["diagnosis_summary"]))
            output["recommended_actions"] = TeacherSkillHelper.ensure_list(llm_json.get("next_actions")) or output["recommended_actions"]

            llm_level = str(llm_json.get("mastery_level", "")).strip().lower()
            if llm_level in {"low", "medium", "high"}:
                output["mastery_level"] = llm_level

        enable_federated = bool(action_input.get("enableFederated", False))
        if enable_federated and self.federated_adapter.enabled:
            enhancement = await self.federated_adapter.get_risk_enhancement(
                {
                    "student_id": student_id,
                    "subject": subject,
                    "grade": grade,
                    "recent_scores": recent_scores,
                    "teacher_notes": teacher_notes,
                }
            )
            if enhancement:
                adjustment = -TeacherSkillHelper.to_float(enhancement.get("risk_adjustment", 0.0)) * 20.0
                adjusted = TeacherSkillHelper.clamp_score(output["mastery_score"] + adjustment)
                output["base_mastery_score"] = output["mastery_score"]
                output["mastery_score"] = round(adjusted, 2)
                output["mastery_level"] = self._score_to_level(adjusted)
                output["federated"] = {
                    "enabled": True,
                    "applied": True,
                    "risk_adjustment": round(TeacherSkillHelper.to_float(enhancement.get("risk_adjustment", 0.0)), 4),
                    "confidence": round(TeacherSkillHelper.to_float(enhancement.get("confidence", 0.0)), 4),
                    "federated_nodes_count": TeacherSkillHelper.to_int(enhancement.get("federated_nodes_count", 0)),
                }

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Student diagnosis completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            fallback = self._fallback_output(
                student_id=str(request.action_input.get("student_id", "unknown_student")),
                subject=str(request.action_input.get("subject", "数学")),
                grade=str(request.action_input.get("grade", "八年级")),
                scores=TeacherSkillHelper.parse_scores(request.action_input.get("recent_scores", [])),
                knowledge_points=[],
                reason="timeout",
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output=fallback,
                message="Student diagnosis timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("StudentDiagnosisSkill failed: %s", exc, exc_info=True)
            fallback = self._fallback_output(
                student_id=str(request.action_input.get("student_id", "unknown_student")),
                subject=str(request.action_input.get("subject", "数学")),
                grade=str(request.action_input.get("grade", "八年级")),
                scores=TeacherSkillHelper.parse_scores(request.action_input.get("recent_scores", [])),
                knowledge_points=[],
                reason="error",
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output=fallback,
                message="Student diagnosis error, fallback returned.",
            )

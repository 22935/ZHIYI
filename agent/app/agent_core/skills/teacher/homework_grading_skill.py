import asyncio
import difflib
import json
import logging
from typing import Any, Dict, List

from app.agent_core.federated.federated_adapter import FederatedAdapter
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class HomeworkGradingSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None, federated_adapter: FederatedAdapter = None):
        super().__init__("homework_grading")
        self.ai_service = ai_service or AIService()
        self.federated_adapter = federated_adapter or FederatedAdapter()

    def _heuristic_score(self, reference_answer: str, student_answer: str) -> float:
        if not student_answer.strip():
            return 10.0
        if not reference_answer.strip():
            return 65.0
        ratio = difflib.SequenceMatcher(None, reference_answer.strip(), student_answer.strip()).ratio()
        return TeacherSkillHelper.clamp_score(35 + ratio * 60)

    def _fallback_output(self, question: str, reference_answer: str, student_answer: str, reason: str) -> Dict[str, Any]:
        score = self._heuristic_score(reference_answer, student_answer)
        corrections = []
        if not student_answer.strip():
            corrections.append("答案为空，建议先写出关键步骤再作答")
        elif score < 60:
            corrections.append("建议对照参考答案补全关键推理步骤")
            corrections.append("重点检查公式代入和单位书写")
        else:
            corrections.append("继续保持，注意表达完整性")

        return {
            "question": question,
            "score": round(score, 2),
            "feedback": f"Fallback grading used: {reason}",
            "corrections": corrections,
            "model_answer": reference_answer or "请结合课堂知识点组织完整答案",
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
        question = str(action_input.get("question", request.text or ""))
        reference_answer = str(action_input.get("reference_answer", ""))
        student_answer = str(action_input.get("student_answer", ""))
        rubric = action_input.get("rubric", {})

        prompt = TeacherSkillHelper.load_prompt(
            "grading_prompt.txt",
            "请输出批改JSON，字段score,feedback,corrections,model_answer。",
        )
        prompt = prompt.replace("{question}", question)
        prompt = prompt.replace("{reference_answer}", reference_answer)
        prompt = prompt.replace("{student_answer}", student_answer)
        prompt = prompt.replace("{rubric}", json.dumps(rubric, ensure_ascii=False))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await asyncio.wait_for(
                self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:]),
                timeout=45,
            )
            llm_json = TeacherSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except asyncio.TimeoutError:
            logger.warning("HomeworkGradingSkill LLM call timed out.")
        except Exception as exc:
            logger.warning("HomeworkGradingSkill LLM call failed: %s", exc)

        output = self._fallback_output(
            question=question,
            reference_answer=reference_answer,
            student_answer=student_answer,
            reason="llm_unavailable" if not llm_json else "fallback_merge",
        )

        if llm_json:
            parsed_score = TeacherSkillHelper.to_float(llm_json.get("score", output["score"]), output["score"])
            output["score"] = round(TeacherSkillHelper.clamp_score(parsed_score), 2)
            output["feedback"] = str(llm_json.get("feedback", output["feedback"]))
            output["corrections"] = TeacherSkillHelper.ensure_list(llm_json.get("corrections")) or output["corrections"]
            output["model_answer"] = str(llm_json.get("model_answer", output["model_answer"]))
            output["strengths"] = TeacherSkillHelper.ensure_list(llm_json.get("strengths"))
            output["mistakes"] = TeacherSkillHelper.ensure_list(llm_json.get("mistakes"))

        # Rule calibration for score sanity.
        heuristic = self._heuristic_score(reference_answer, student_answer)
        output["score"] = round((output["score"] * 0.7 + heuristic * 0.3), 2)
        if not student_answer.strip():
            output["score"] = min(output["score"], 20.0)

        enable_federated = bool(action_input.get("enableFederated", False))
        if enable_federated and self.federated_adapter.enabled:
            enhancement = await self.federated_adapter.get_risk_enhancement(
                {
                    "question": question,
                    "rubric": rubric,
                    "reference_answer": reference_answer,
                    "student_answer": student_answer,
                }
            )
            if enhancement:
                adjustment = -TeacherSkillHelper.to_float(enhancement.get("risk_adjustment", 0.0)) * 10
                output["base_score"] = output["score"]
                output["score"] = round(TeacherSkillHelper.clamp_score(output["score"] + adjustment), 2)
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
            message="Homework grading completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            fallback = self._fallback_output(
                question=str(action_input.get("question", request.text or "")),
                reference_answer=str(action_input.get("reference_answer", "")),
                student_answer=str(action_input.get("student_answer", "")),
                reason="timeout",
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output=fallback,
                message="Homework grading timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("HomeworkGradingSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            fallback = self._fallback_output(
                question=str(action_input.get("question", request.text or "")),
                reference_answer=str(action_input.get("reference_answer", "")),
                student_answer=str(action_input.get("student_answer", "")),
                reason="error",
            )
            return SkillResult(
                skillName=self.name,
                success=True,
                output=fallback,
                message="Homework grading error, fallback returned.",
            )

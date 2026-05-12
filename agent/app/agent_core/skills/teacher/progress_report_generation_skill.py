import asyncio
import json
import logging
from typing import Any, Dict, List

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class ProgressReportGenerationSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("progress_report_generation")
        self.ai_service = ai_service or AIService()

    def _compute_trend(self, performance_data: Any) -> Dict[str, Any]:
        scores: List[float] = []
        if isinstance(performance_data, list):
            for item in performance_data:
                if isinstance(item, dict):
                    if "score" in item:
                        scores.append(TeacherSkillHelper.to_float(item.get("score"), -1))
                else:
                    scores.append(TeacherSkillHelper.to_float(item, -1))
        elif isinstance(performance_data, dict):
            raw_scores = performance_data.get("scores", [])
            for item in raw_scores if isinstance(raw_scores, list) else []:
                scores.append(TeacherSkillHelper.to_float(item, -1))

        scores = [score for score in scores if score >= 0]
        if not scores:
            return {"trend": "unknown", "delta": 0.0, "average": 0.0, "latest": 0.0}

        delta = scores[-1] - scores[0] if len(scores) > 1 else 0.0
        trend = "improving" if delta > 3 else "declining" if delta < -3 else "stable"
        average = sum(scores) / len(scores)
        return {
            "trend": trend,
            "delta": round(delta, 2),
            "average": round(average, 2),
            "latest": round(scores[-1], 2),
            "scores": scores,
        }

    def _fallback_report(self, student_id: str, period: str, trend: Dict[str, Any], reason: str) -> str:
        return (
            "# 学情报告\n"
            f"## 学生信息\n- 学生ID：{student_id}\n- 统计周期：{period}\n\n"
            "## 成绩趋势\n"
            f"- 趋势：{trend.get('trend', 'unknown')}\n"
            f"- 变化值：{trend.get('delta', 0.0)}\n"
            f"- 平均分：{trend.get('average', 0.0)}\n"
            f"- 最近一次：{trend.get('latest', 0.0)}\n\n"
            "## 优势与亮点\n- 学习任务完成度较稳定。\n\n"
            "## 薄弱项分析\n- 计算准确性与步骤完整性仍需加强。\n\n"
            "## 阶段建议\n- 每周进行2次错题归因复盘。\n- 每次练习后补写关键步骤。\n\n"
            f"## 说明\n- Fallback report used: {reason}\n"
        )

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        student_id = str(action_input.get("student_id", "unknown_student"))
        period = str(action_input.get("period", "近4周"))
        performance_data = action_input.get("performance_data", {})

        trend = self._compute_trend(performance_data)

        prompt = TeacherSkillHelper.load_prompt(
            "report_generation_prompt.txt",
            "请输出学情报告Markdown。",
        )
        prompt = prompt.replace("{student_id}", student_id)
        prompt = prompt.replace("{period}", period)
        prompt = prompt.replace("{performance_data}", json.dumps(performance_data, ensure_ascii=False))
        prompt = prompt.replace("{trend}", json.dumps(trend, ensure_ascii=False))

        report_markdown = ""
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            report_markdown = (llm_response.get("text", "") or "").strip()
        except Exception as exc:
            logger.warning("ProgressReportGenerationSkill LLM call failed: %s", exc)

        if not report_markdown:
            report_markdown = self._fallback_report(student_id=student_id, period=period, trend=trend, reason="llm_unavailable")

        output = {
            "student_id": student_id,
            "period": period,
            "trend": trend,
            "report": report_markdown,
            "summary": "Progress report generated.",
        }
        return SkillResult(skillName=self.name, success=True, output=output, message="Progress report generated.")

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            student_id = str(action_input.get("student_id", "unknown_student"))
            period = str(action_input.get("period", "近4周"))
            trend = self._compute_trend(action_input.get("performance_data", {}))
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "student_id": student_id,
                    "period": period,
                    "trend": trend,
                    "report": self._fallback_report(student_id, period, trend, "timeout"),
                },
                message="Progress report timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("ProgressReportGenerationSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            student_id = str(action_input.get("student_id", "unknown_student"))
            period = str(action_input.get("period", "近4周"))
            trend = self._compute_trend(action_input.get("performance_data", {}))
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "student_id": student_id,
                    "period": period,
                    "trend": trend,
                    "report": self._fallback_report(student_id, period, trend, "error"),
                },
                message="Progress report error, fallback returned.",
            )

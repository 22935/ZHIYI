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


class ClassroomInteractionDesignSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("classroom_interaction_design")
        self.ai_service = ai_service or AIService()

    def _fallback_output(
        self,
        topic: str,
        grade: str,
        subject: str,
        class_size: int,
        methods_payload: List[Dict[str, Any]],
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "topic": topic,
            "grade": grade,
            "subject": subject,
            "class_size": class_size,
            "interaction_script": "导入提问-同伴讨论-展示点评三段式互动。",
            "question_chain": [
                "这个问题的已知条件有哪些？",
                "如果换一种表示方式，结论会变吗？",
                "你能解释为什么这个步骤是必要的吗？",
            ],
            "group_activity": "4人一组完成任务单，组内先统一解题思路，再派代表讲解。",
            "board_design": ["左侧写学习目标", "中区写核心例题", "右侧记录错因关键词"],
            "timing_suggestion": ["导入5分钟", "活动15分钟", "汇报10分钟", "总结5分钟"],
            "teaching_methods": methods_payload,
            "summary": f"Fallback interaction design used: {reason}",
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        topic = str(action_input.get("topic", request.text or "本课主题"))
        grade = str(action_input.get("grade", "八年级"))
        subject = str(action_input.get("subject", "数学"))
        class_size = max(10, TeacherSkillHelper.to_int(action_input.get("class_size", 40), 40))

        method_rows = TeacherSkillHelper.query_collection(
            collection_name=education_index_builder.TEACHING_METHODS_COLLECTION,
            query_text=f"{subject} {grade} {topic}",
            top_k=4,
            fallback_fields=["method_name", "applicable_scenarios", "implementation_steps", "examples"],
        )
        methods_payload = [row.get("metadata", {}) for row in method_rows]

        prompt = TeacherSkillHelper.load_prompt(
            "interaction_design_prompt.txt",
            "请输出课堂互动设计JSON。",
        )
        prompt = prompt.replace("{topic}", topic)
        prompt = prompt.replace("{grade}", grade)
        prompt = prompt.replace("{subject}", subject)
        prompt = prompt.replace("{class_size}", str(class_size))
        prompt = prompt.replace("{teaching_methods}", json.dumps(methods_payload, ensure_ascii=False))

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(text=prompt, context=request.memory.get("history", [])[-6:])
            llm_json = TeacherSkillHelper.extract_json_obj(llm_response.get("text", ""))
        except Exception as exc:
            logger.warning("ClassroomInteractionDesignSkill LLM call failed: %s", exc)

        output = self._fallback_output(
            topic=topic,
            grade=grade,
            subject=subject,
            class_size=class_size,
            methods_payload=methods_payload,
            reason="llm_unavailable" if not llm_json else "fallback_merge",
        )

        if llm_json:
            output["interaction_script"] = str(llm_json.get("interaction_script", output["interaction_script"]))
            output["question_chain"] = TeacherSkillHelper.ensure_list(llm_json.get("question_chain")) or output["question_chain"]
            output["group_activity"] = str(llm_json.get("group_activity", output["group_activity"]))
            output["board_design"] = TeacherSkillHelper.ensure_list(llm_json.get("board_design")) or output["board_design"]
            output["timing_suggestion"] = (
                TeacherSkillHelper.ensure_list(llm_json.get("timing_suggestion")) or output["timing_suggestion"]
            )

        return SkillResult(skillName=self.name, success=True, output=output, message="Interaction design completed.")

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    topic=str(action_input.get("topic", request.text or "本课主题")),
                    grade=str(action_input.get("grade", "八年级")),
                    subject=str(action_input.get("subject", "数学")),
                    class_size=TeacherSkillHelper.to_int(action_input.get("class_size", 40), 40),
                    methods_payload=[],
                    reason="timeout",
                ),
                message="Interaction design timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("ClassroomInteractionDesignSkill failed: %s", exc, exc_info=True)
            action_input = request.action_input or {}
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    topic=str(action_input.get("topic", request.text or "本课主题")),
                    grade=str(action_input.get("grade", "八年级")),
                    subject=str(action_input.get("subject", "数学")),
                    class_size=TeacherSkillHelper.to_int(action_input.get("class_size", 40), 40),
                    methods_payload=[],
                    reason="error",
                ),
                message="Interaction design error, fallback returned.",
            )

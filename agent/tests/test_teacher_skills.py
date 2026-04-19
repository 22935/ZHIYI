import asyncio
import importlib
from typing import Any, Dict, List
from unittest.mock import patch

from app.agent_core.schema.agent_types import SkillRequest
from app.agent_core.skills.teacher.classroom_interaction_design_skill import ClassroomInteractionDesignSkill
from app.agent_core.skills.teacher.error_analysis_question_push_skill import ErrorAnalysisQuestionPushSkill
from app.agent_core.skills.teacher.homework_grading_skill import HomeworkGradingSkill
from app.agent_core.skills.teacher.learning_path_planning_skill import LearningPathPlanningSkill
from app.agent_core.skills.teacher.lesson_plan_generation_skill import LessonPlanGenerationSkill
from app.agent_core.skills.teacher.parent_communication_suggestion_skill import ParentCommunicationSuggestionSkill
from app.agent_core.skills.teacher.progress_report_generation_skill import ProgressReportGenerationSkill
from app.agent_core.skills.teacher.student_diagnosis_skill import StudentDiagnosisSkill
from app.agent_core.skills.teacher.tutoring_qa_skill import TutoringQASkill
from app.agent_core.skills.teacher.common import TeacherSkillHelper


class FakeAIService:
    async def generate_text(self, text: str, role_id: str = None, context: List[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        prompt = text or ""
        if "批改JSON" in prompt:
            return {
                "text": """{
  "score": 82,
  "feedback": "思路基本正确，最后一步计算有误。",
  "corrections": ["检查运算符号", "补全关键步骤"],
  "model_answer": "先列式，再化简，最后检验。",
  "strengths": ["步骤较完整"],
  "mistakes": ["计算错误"]
}"""
            }
        if "错题归因JSON" in prompt:
            return {
                "text": """{
  "knowledge_gap": ["勾股定理应用"],
  "root_causes": ["公式代入顺序混乱"],
  "remediation_suggestions": ["先做基础代入题"],
  "analysis_summary": "主要问题是代入与化简不稳定。"
}"""
            }
        if "学情诊断JSON" in prompt:
            return {
                "text": """{
  "weak_points": ["函数图像理解"],
  "strengths": ["课堂参与积极"],
  "mastery_level": "medium",
  "learning_style": "视觉型",
  "diagnosis_summary": "基础尚可，迁移应用偏弱。",
  "next_actions": ["每日1题图像题", "每周一次错题复盘"]
}"""
            }
        if "引导式答疑JSON" in prompt:
            return {
                "text": """{
  "guided_answer": "先找已知量，再判断用哪个公式。",
  "hints": ["圈出已知条件", "写出关系式"],
  "steps": ["读题", "列式", "计算", "检查"],
  "summary": "先方法后结果。"
}"""
            }
        if "课堂互动设计JSON" in prompt:
            return {
                "text": """{
  "interaction_script": "情境导入-同伴讨论-全班展示",
  "question_chain": ["条件是什么？", "为什么这么做？", "还能怎么做？"],
  "group_activity": "四人小组协作完成任务单",
  "board_design": ["目标", "例题", "错因"],
  "timing_suggestion": ["导入5分钟", "讨论10分钟", "展示10分钟"]
}"""
            }
        if "家长沟通JSON" in prompt:
            return {
                "text": """{
  "communication_points": ["肯定进步", "指出问题", "达成计划"],
  "dialogue_scripts": ["孩子近期状态积极。", "建议固定复盘时间。"],
  "home_support_actions": ["每日10分钟复盘"],
  "tone_suggestion": "积极合作"
}"""
            }
        if "学情报告Markdown" in prompt:
            return {"text": "# 学情报告\n\n## 成绩趋势\n总体稳步提升。"}
        if "学习路径Markdown" in prompt:
            return {"text": "| 天数 | 核心任务 | 巩固任务 | 预计时长 |\n|---|---|---|---|\n| Day 1 | 复习函数 | 练习3题 | 40分钟 |"}
        if "Markdown教案" in prompt or "输出Markdown教案" in prompt:
            return {
                "text": "# 课题\n八年级数学：勾股定理\n\n## 教学目标\n1. 理解定理。\n\n## 教学重难点\n- 重点：定理应用\n\n## 教学过程\n### 导入\n### 新授\n### 练习\n### 总结\n\n## 分层作业\n- 基础层\n- 提升层\n\n## 课堂评价与反思\n- 关注步骤表达"
            }
        return {"text": "{}"}


def _build_request(text: str, action_input: Dict[str, Any]) -> SkillRequest:
    return SkillRequest(
        sessionId="teacher-test-session",
        text=text,
        actionInput=action_input,
        memory={"history": [{"role": "user", "content": text}]},
    )


async def _assert_timeout_fallback(skill, request: SkillRequest) -> None:
    module = importlib.import_module(skill.__class__.__module__)
    async def _timeout_wait_for(coro, timeout):
        try:
            coro.close()
        except Exception:
            pass
        raise asyncio.TimeoutError

    with patch.object(module.asyncio, "wait_for", new=_timeout_wait_for):
        result = await skill.run(request)
    assert result.success is True
    assert "timeout" in result.message.lower()


async def test_student_diagnosis_skill():
    skill = StudentDiagnosisSkill(ai_service=FakeAIService())
    request = _build_request(
        "请诊断学生学情",
        {
            "student_id": "stu_001",
            "subject": "数学",
            "grade": "八年级",
            "recent_scores": [62, 70, 75, 68],
            "teacher_notes": "计算准确率偏低",
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"weak_points", "strengths", "mastery_level", "learning_style"}.issubset(result.output.keys())
    await _assert_timeout_fallback(skill, request)


async def test_lesson_plan_generation_skill():
    skill = LessonPlanGenerationSkill(ai_service=FakeAIService())
    request = _build_request(
        "为勾股定理备课",
        {
            "topic": "勾股定理",
            "subject": "数学",
            "grade": "八年级",
            "duration": "1课时",
            "class_profile": "计算能力偏弱",
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert "lesson_plan" in result.output and "## 教学目标" in result.output["lesson_plan"]
    assert isinstance(result.output.get("template_refs", []), list)
    assert isinstance(result.output.get("knowledge_points", []), list)
    await _assert_timeout_fallback(skill, request)


async def test_homework_grading_skill():
    skill = HomeworkGradingSkill(ai_service=FakeAIService())
    request = _build_request(
        "请批改作业",
        {
            "question": "求直角三角形斜边",
            "reference_answer": "c^2=a^2+b^2，代入并开方。",
            "student_answer": "先列公式，再算出c=5。",
            "rubric": {"步骤": 60, "结果": 40},
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"score", "feedback", "corrections", "model_answer"}.issubset(result.output.keys())
    await _assert_timeout_fallback(skill, request)


async def test_error_analysis_question_push_skill():
    skill = ErrorAnalysisQuestionPushSkill(ai_service=FakeAIService())
    request = _build_request(
        "分析错题并推题",
        {
            "question": "已知直角边3和4，求斜边",
            "student_answer": "3+4=7",
            "correct_answer": "5",
            "knowledge_point_tags": ["勾股定理"],
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert "knowledge_gap" in result.output
    assert isinstance(result.output.get("similar_questions", []), list)
    await _assert_timeout_fallback(skill, request)


async def test_tutoring_qa_skill():
    skill = TutoringQASkill(ai_service=FakeAIService())
    request = _build_request(
        "这道题怎么做",
        {
            "question": "为什么要先统一单位？",
            "subject": "物理",
            "student_grade": "八年级",
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"guided_answer", "hints", "steps"}.issubset(result.output.keys())
    assert isinstance(result.output.get("knowledge_points", []), list)
    await _assert_timeout_fallback(skill, request)


async def test_learning_path_planning_skill():
    skill = LearningPathPlanningSkill(ai_service=FakeAIService())
    request = _build_request(
        "制定学习路径",
        {
            "current_level": "medium",
            "target_score": 88,
            "available_days": 7,
            "subject": "数学",
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"schedule", "plan", "resource_recommendations"}.issubset(result.output.keys())
    assert isinstance(result.output.get("knowledge_points", []), list)
    await _assert_timeout_fallback(skill, request)


async def test_progress_report_generation_skill():
    skill = ProgressReportGenerationSkill(ai_service=FakeAIService())
    request = _build_request(
        "生成学情报告",
        {
            "student_id": "stu_002",
            "period": "近4周",
            "performance_data": {"scores": [66, 70, 74, 78]},
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"report", "trend"}.issubset(result.output.keys())
    await _assert_timeout_fallback(skill, request)


async def test_classroom_interaction_design_skill():
    skill = ClassroomInteractionDesignSkill(ai_service=FakeAIService())
    request = _build_request(
        "设计课堂互动",
        {
            "topic": "杠杆原理",
            "grade": "八年级",
            "subject": "物理",
            "class_size": 46,
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"interaction_script", "question_chain", "group_activity", "board_design"}.issubset(result.output.keys())
    assert isinstance(result.output.get("teaching_methods", []), list)
    await _assert_timeout_fallback(skill, request)


async def test_parent_communication_suggestion_skill():
    skill = ParentCommunicationSuggestionSkill(ai_service=FakeAIService())
    request = _build_request(
        "给出家校沟通建议",
        {
            "student_performance_summary": "近期成绩有波动，作业拖延。",
            "concern_areas": ["学习习惯", "计算准确率"],
        },
    )
    result = await skill.run(request)
    assert result.success is True
    assert {"communication_points", "dialogue_scripts", "home_support_actions"}.issubset(result.output.keys())
    await _assert_timeout_fallback(skill, request)


async def test_collection_query_smoke():
    kp_rows = TeacherSkillHelper.query_collection("edu_knowledge_points", "数学 八年级 勾股定理", top_k=2)
    qb_rows = TeacherSkillHelper.query_collection("edu_question_bank", "勾股定理", top_k=2)
    lt_rows = TeacherSkillHelper.query_collection("edu_lesson_templates", "数学 八年级 新授课", top_k=2)
    tm_rows = TeacherSkillHelper.query_collection("edu_teaching_methods", "物理 互动", top_k=2)

    assert len(kp_rows) > 0
    assert len(qb_rows) > 0
    assert len(lt_rows) > 0
    assert len(tm_rows) > 0


async def _main():
    await test_student_diagnosis_skill()
    print("[PASS] student_diagnosis")
    await test_lesson_plan_generation_skill()
    print("[PASS] lesson_plan_generation")
    await test_homework_grading_skill()
    print("[PASS] homework_grading")
    await test_error_analysis_question_push_skill()
    print("[PASS] error_analysis_question_push")
    await test_tutoring_qa_skill()
    print("[PASS] tutoring_qa")
    await test_learning_path_planning_skill()
    print("[PASS] learning_path_planning")
    await test_progress_report_generation_skill()
    print("[PASS] progress_report_generation")
    await test_classroom_interaction_design_skill()
    print("[PASS] classroom_interaction_design")
    await test_parent_communication_suggestion_skill()
    print("[PASS] parent_communication_suggestion")
    await test_collection_query_smoke()
    print("[PASS] collection_query_smoke")


if __name__ == "__main__":
    asyncio.run(_main())

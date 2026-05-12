import asyncio
import json
import logging
import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter

from app.api.language_guard import ensure_simplified_chinese
from app.agent_core.memory.session_memory import session_memory_store
from app.agent_core.react.executor import ReactExecutor
from app.agent_core.react.planner import ReactPlanner
from app.agent_core.react.tool_router import ToolRouter
from app.agent_core.schema.agent_types import AgentTeacherRequest, AgentTeacherResponse
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)
router = APIRouter()

ai_service = AIService()
planner = ReactPlanner()
tool_router = ToolRouter(enabled_roles=["teacher"])
executor = ReactExecutor(tool_router=tool_router)
AGENT_SYNTHESIS_TIMEOUT = float(os.getenv("AGENT_SYNTHESIS_TIMEOUT", "180"))


def _build_teacher_context(observations: Dict[str, Any]) -> str:
    sections: List[str] = []
    mapping = [
        ("student_diagnosis", observations.get("student_diagnosis", {})),
        ("lesson_plan_generation", observations.get("lesson_plan_generation", {})),
        ("homework_grading", observations.get("homework_grading", {})),
        ("error_analysis_question_push", observations.get("error_analysis_question_push", {})),
        ("tutoring_qa", observations.get("tutoring_qa", {})),
        ("learning_path_planning", observations.get("learning_path_planning", {})),
        ("progress_report_generation", observations.get("progress_report_generation", {})),
        ("classroom_interaction_design", observations.get("classroom_interaction_design", {})),
        ("parent_communication_suggestion", observations.get("parent_communication_suggestion", {})),
    ]

    for title, payload in mapping:
        if payload:
            sections.append(f"[{title}]")
            sections.append(json.dumps(payload, ensure_ascii=False))

    return "\n".join(sections)


def _build_fallback_answer(user_text: str, skills_used: List[str], observations: Dict[str, Any]) -> str:
    lines = [
        "教师 Agent 结构化降级结果：",
        f"1) 用户请求：{user_text}",
        f"2) 已调用技能：{', '.join(skills_used) if skills_used else '无'}",
    ]

    for index, action in enumerate(skills_used, start=3):
        payload = observations.get(action, {})
        if isinstance(payload, dict):
            preview = json.dumps(payload, ensure_ascii=False)[:220]
        else:
            preview = str(payload)[:220]
        lines.append(f"{index}) {action}：{preview}")

    return "\n".join(lines)


def _render_student_diagnosis_answer(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""

    summary = str(payload.get("diagnosis_summary", "") or "").strip()
    mastery_level = str(payload.get("mastery_level", "") or "").strip()
    learning_style = str(payload.get("learning_style", "") or "").strip()
    mastery_score = payload.get("mastery_score")
    weak_points = [str(item).strip() for item in payload.get("weak_points", []) if str(item).strip()]
    strengths = [str(item).strip() for item in payload.get("strengths", []) if str(item).strip()]
    actions = [str(item).strip() for item in payload.get("recommended_actions", []) if str(item).strip()]

    if not any([summary, mastery_level, learning_style, weak_points, strengths, actions, mastery_score is not None]):
        return ""

    lines: List[str] = []
    if summary:
        lines.append(summary)

    profile_parts: List[str] = []
    if mastery_level:
        profile_parts.append(f"掌握水平：{mastery_level}")
    if mastery_score is not None:
        profile_parts.append(f"掌握得分：{mastery_score}")
    if learning_style:
        profile_parts.append(f"学习风格：{learning_style}")
    if profile_parts:
        lines.append("；".join(profile_parts))

    if weak_points:
        lines.append(f"薄弱点：{'、'.join(weak_points[:4])}")
    if strengths:
        lines.append(f"优势：{'、'.join(strengths[:4])}")
    if actions:
        lines.append(f"建议行动：{'；'.join(actions[:4])}")

    return "\n".join(lines).strip()


def _extract_preferred_answer(skills_used: List[str], observations: Dict[str, Any]) -> str:
    preferred_fields = [
        ("lesson_plan_generation", ["lesson_plan", "plan", "markdown", "draft"]),
        ("homework_grading", ["feedback", "comment", "summary", "report"]),
        ("progress_report_generation", ["report", "markdown", "summary"]),
        ("classroom_interaction_design", ["interaction_script", "script", "outline", "plan"]),
        ("parent_communication_suggestion", ["communication_points", "script", "summary"]),
        ("tutoring_qa", ["answer", "guided_answer", "response"]),
        ("learning_path_planning", ["plan", "weekly_plan", "summary"]),
    ]

    used_set = set(skills_used or [])
    for action, fields in preferred_fields:
        if action not in used_set:
            continue
        payload = observations.get(action, {})
        if not isinstance(payload, dict):
            continue
        for field in fields:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    if "student_diagnosis" in used_set:
        diagnosis_answer = _render_student_diagnosis_answer(observations.get("student_diagnosis", {}))
        if diagnosis_answer:
            return diagnosis_answer

    return ""


def _pick_teacher_federated(observations: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(observations, dict):
        return {}

    candidates: List[Dict[str, Any]] = []
    for action in ("student_diagnosis", "homework_grading"):
        payload = observations.get(action, {})
        if not isinstance(payload, dict):
            continue
        fed = payload.get("federated", {})
        if isinstance(fed, dict) and fed:
            candidates.append(fed)

    for item in candidates:
        if item.get("applied"):
            return item
    return candidates[0] if candidates else {}


@router.post("/agent/teacher/chat", response_model=AgentTeacherResponse)
async def teacher_agent_chat(request: AgentTeacherRequest):
    session_id = request.session_id or str(uuid4())
    user_text = request.text

    try:
        history = session_memory_store.get_history(session_id)
        plan = planner.plan(user_text, history, role="teacher")
        trace, skills_used, observations = await executor.execute(
            plan=plan,
            session_id=session_id,
            text=user_text,
            memory={"history": history},
            role="teacher",
        )

        answer = _extract_preferred_answer(skills_used=skills_used, observations=observations)
        if not answer:
            context_text = _build_teacher_context(observations)
            synthesis_prompt = (
                "你是一名专业教师助手。请基于结构化技能结果输出简洁、可执行的答复，并且必须始终使用简体中文。\n"
                "要求：\n"
                "1. 先给可直接执行的结果。\n"
                "2. 若是追问优化，仅修改用户要求的部分。\n"
                "3. 信息不足时，明确列出缺失信息。\n\n"
                f"用户请求：{user_text}\n\n"
                f"结构化结果：\n{context_text}"
            )
            try:
                llm_response = await asyncio.wait_for(
                    ai_service.generate_text(text=synthesis_prompt, context=history[-8:] if history else None),
                    timeout=AGENT_SYNTHESIS_TIMEOUT,
                )
                answer = (llm_response.get("text", "") or "").strip()
            except Exception:
                answer = ""

        if not answer:
            answer = _build_fallback_answer(user_text=user_text, skills_used=skills_used, observations=observations)

        answer = await ensure_simplified_chinese(answer, ai_service=ai_service, history=history)

        session_memory_store.append_message(session_id, "user", user_text)
        session_memory_store.append_message(session_id, "assistant", answer)

        diagnosis_info = observations.get("student_diagnosis", {}) if isinstance(observations, dict) else {}
        federated_info = _pick_teacher_federated(observations)

        return AgentTeacherResponse(
            success=True,
            answer=answer,
            sessionId=session_id,
            skillsUsed=skills_used,
            trace=trace,
            riskLevel=diagnosis_info.get("mastery_level") if isinstance(diagnosis_info, dict) else None,
            federated=federated_info if isinstance(federated_info, dict) else {},
            message="教师 Agent 工作流执行完成。",
        )
    except Exception as exc:
        logger.error("Teacher agent chat failed", exc_info=True)
        return AgentTeacherResponse(
            success=False,
            answer="抱歉，教师 Agent 当前不可用，请稍后重试。",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated={},
            message="教师 Agent 执行失败。",
            error=str(exc),
        )

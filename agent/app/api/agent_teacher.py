import asyncio
import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter

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
tool_router = ToolRouter()
executor = ReactExecutor(tool_router=tool_router)


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
        "TeacherAgent structured fallback result:",
        f"1) User request: {user_text}",
        f"2) Skills used: {', '.join(skills_used) if skills_used else 'none'}",
    ]

    for index, action in enumerate(skills_used, start=3):
        payload = observations.get(action, {})
        if isinstance(payload, dict):
            preview = json.dumps(payload, ensure_ascii=False)[:220]
        else:
            preview = str(payload)[:220]
        lines.append(f"{index}) {action}: {preview}")

    return "\n".join(lines)


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
                "You are a professional teacher assistant. Provide a concise, actionable answer based on"
                " the structured skill outputs.\n"
                "Requirements:\n"
                "1. Give a practical result first.\n"
                "2. If this is a follow-up refinement, only update the requested part.\n"
                "3. If information is missing, list exactly what is needed.\n\n"
                f"User request: {user_text}\n\n"
                f"Structured outputs:\n{context_text}"
            )
            try:
                llm_response = await asyncio.wait_for(
                    ai_service.generate_text(text=synthesis_prompt, context=history[-8:] if history else None),
                    timeout=15,
                )
                answer = (llm_response.get("text", "") or "").strip()
            except Exception:
                answer = ""

        if not answer:
            answer = _build_fallback_answer(user_text=user_text, skills_used=skills_used, observations=observations)

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
            message="Teacher agent workflow completed.",
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
            message="Teacher agent execution failed.",
            error=str(exc),
        )

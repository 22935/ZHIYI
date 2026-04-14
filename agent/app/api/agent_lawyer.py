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
from app.agent_core.schema.agent_types import AgentLawyerRequest, AgentLawyerResponse
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)
router = APIRouter()

ai_service = AIService()
planner = ReactPlanner()
tool_router = ToolRouter()
executor = ReactExecutor(tool_router=tool_router)


def _collect_top_items(items: List[Dict[str, Any]], max_count: int = 3) -> List[Dict[str, Any]]:
    return items[: max(0, max_count)] if isinstance(items, list) else []


def _build_agent_context(observations: Dict[str, Any]) -> str:
    lines: List[str] = []

    case_info = observations.get("case_understanding", {})
    if case_info:
        lines.append("[Case Understanding]")
        lines.append(json.dumps(case_info, ensure_ascii=False))

    statute_items = _collect_top_items(observations.get("statute_retrieval", {}).get("statutes", []), 3)
    if statute_items:
        lines.append("[Statute Retrieval]")
        lines.append(json.dumps(statute_items, ensure_ascii=False))

    case_items = _collect_top_items(observations.get("case_retrieval", {}).get("cases", []), 3)
    if case_items:
        lines.append("[Case Retrieval]")
        lines.append(json.dumps(case_items, ensure_ascii=False))

    risk_info = observations.get("risk_assessment", {})
    if risk_info:
        lines.append("[Risk Assessment]")
        lines.append(json.dumps(risk_info, ensure_ascii=False))

    draft_info = observations.get("document_generation", {})
    if draft_info:
        lines.append("[Document Generation Summary]")
        lines.append(
            json.dumps(
                {
                    "document_type": draft_info.get("document_type"),
                    "sections": draft_info.get("sections", []),
                },
                ensure_ascii=False,
            )
        )

    return "\n".join(lines)


def _is_drafting_intent(user_text: str) -> bool:
    lowered = (user_text or "").lower()
    drafting_hints = [
        "起诉状",
        "答辩状",
        "律师函",
        "文书",
        "draft",
        "template",
    ]
    return any(token in user_text for token in drafting_hints if token) or any(
        token in lowered for token in ["draft", "template"]
    )


def _build_fallback_answer(user_text: str, observations: Dict[str, Any]) -> str:
    case_info = observations.get("case_understanding", {})
    risk = observations.get("risk_assessment", {})
    statutes = observations.get("statute_retrieval", {}).get("statutes", [])
    cases = observations.get("case_retrieval", {}).get("cases", [])

    facts = case_info.get("facts", user_text)
    legal_issues = case_info.get("legal_issues", [])
    risk_level = risk.get("risk_level", "unknown")
    risk_score = risk.get("risk_score", "N/A")

    return (
        "以下是基于当前结构化流程生成的法律分析（降级输出）：\n"
        f"1) 案情摘要：{facts}\n"
        f"2) 争议焦点：{legal_issues}\n"
        f"3) 法条命中数：{len(statutes)}，判例命中数：{len(cases)}\n"
        f"4) 风险等级：{risk_level}（score={risk_score}）\n"
        "建议你补充证据清单、关键时间线与合同/沟通记录，以便进一步提升分析准确度。"
    )


@router.post("/agent/lawyer/chat", response_model=AgentLawyerResponse)
async def lawyer_agent_chat(request: AgentLawyerRequest):
    session_id = request.session_id or str(uuid4())
    user_text = request.text

    try:
        history = session_memory_store.get_history(session_id)
        plan = planner.plan(user_text, history)
        trace, skills_used, observations = await executor.execute(
            plan=plan,
            session_id=session_id,
            text=user_text,
            memory={"history": history},
        )

        # drafting requests can directly return generated draft
        if _is_drafting_intent(user_text):
            draft = observations.get("document_generation", {}).get("draft", "")
            if draft:
                answer = draft
            else:
                answer = _build_fallback_answer(user_text, observations)
        else:
            agent_context = _build_agent_context(observations)
            synthesis_prompt = (
                "你是专业律师智能体，请基于以下结构化结果给出最终答复。要求：\n"
                "1. 先给结论，再给依据（法条+判例）。\n"
                "2. 明确风险等级与建议动作。\n"
                "3. 若信息不足，请列出需补充材料。\n\n"
                f"用户问题：{user_text}\n\n"
                f"结构化结果：\n{agent_context}\n"
            )
            try:
                llm_response = await asyncio.wait_for(
                    ai_service.generate_text(text=synthesis_prompt, context=history[-8:] if history else None),
                    timeout=15,
                )
                answer = llm_response.get("text", "") or _build_fallback_answer(user_text, observations)
            except Exception:
                answer = _build_fallback_answer(user_text, observations)

        session_memory_store.append_message(session_id, "user", user_text)
        session_memory_store.append_message(session_id, "assistant", answer)

        risk_info = observations.get("risk_assessment", {}) if isinstance(observations, dict) else {}
        federated_info = risk_info.get("federated", {}) if isinstance(risk_info, dict) else {}

        return AgentLawyerResponse(
            success=True,
            answer=answer,
            sessionId=session_id,
            skillsUsed=skills_used,
            trace=trace,
            riskLevel=risk_info.get("risk_level") if isinstance(risk_info, dict) else None,
            federated=federated_info if isinstance(federated_info, dict) else {},
            message="Lawyer agent phase-3 workflow completed.",
        )
    except Exception as exc:
        logger.error("Lawyer agent chat failed", exc_info=True)
        return AgentLawyerResponse(
            success=False,
            answer="抱歉，律师智能体当前不可用，请稍后再试。",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated={},
            message="Lawyer agent execution failed.",
            error=str(exc),
        )

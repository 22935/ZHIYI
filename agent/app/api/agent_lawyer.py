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
from app.agent_core.schema.agent_types import AgentLawyerRequest, AgentLawyerResponse
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)
router = APIRouter()

ai_service = AIService()
planner = ReactPlanner()
tool_router = ToolRouter(enabled_roles=["lawyer"])
executor = ReactExecutor(tool_router=tool_router)
AGENT_SYNTHESIS_TIMEOUT = float(os.getenv("AGENT_SYNTHESIS_TIMEOUT", "180"))


def _collect_top_items(items: List[Dict[str, Any]], max_count: int = 3) -> List[Dict[str, Any]]:
    return items[: max(0, max_count)] if isinstance(items, list) else []


def _build_agent_context(observations: Dict[str, Any]) -> str:
    sections: List[str] = []

    mapping = [
        ("案情理解", observations.get("case_understanding", {})),
        ("证据分析", observations.get("evidence_analysis", {})),
        ("诉讼时效", observations.get("limitation_calculation", {})),
        ("管辖法院", observations.get("jurisdiction_determination", {})),
        ("风险评估", observations.get("risk_assessment", {})),
    ]
    for title, payload in mapping:
        if payload:
            sections.append(f"[{title}]")
            sections.append(json.dumps(payload, ensure_ascii=False))

    statute_items = _collect_top_items(observations.get("statute_retrieval", {}).get("statutes", []), 3)
    if statute_items:
        sections.append("[法条检索]")
        sections.append(json.dumps(statute_items, ensure_ascii=False))

    case_items = _collect_top_items(observations.get("case_retrieval", {}).get("cases", []), 3)
    if case_items:
        sections.append("[判例检索]")
        sections.append(json.dumps(case_items, ensure_ascii=False))

    hearing = observations.get("hearing_outline_generation", {})
    if hearing:
        sections.append("[庭审提纲]")
        sections.append(json.dumps({"agenda": hearing.get("agenda", [])}, ensure_ascii=False))

    draft_info = observations.get("document_generation", {})
    if draft_info:
        sections.append("[文书生成]")
        sections.append(
            json.dumps(
                {
                    "document_type": draft_info.get("document_type"),
                    "sections": draft_info.get("sections", []),
                },
                ensure_ascii=False,
            )
        )

    return "\n".join(sections)


def _is_drafting_intent(user_text: str) -> bool:
    text = user_text or ""
    lowered = text.lower()
    hints = ["文书", "起诉状", "答辩状", "律师函", "草稿", "draft", "template"]
    return any(token in text for token in hints) or any(token in lowered for token in hints)


def _is_hearing_intent(user_text: str) -> bool:
    text = user_text or ""
    hints = ["开庭", "庭审", "提纲", "发问", "质证"]
    return any(token in text for token in hints)


def _build_fallback_answer(user_text: str, observations: Dict[str, Any]) -> str:
    case_info = observations.get("case_understanding", {})
    evidence = observations.get("evidence_analysis", {})
    limitation = observations.get("limitation_calculation", {})
    jurisdiction = observations.get("jurisdiction_determination", {})
    risk = observations.get("risk_assessment", {})
    statutes = observations.get("statute_retrieval", {}).get("statutes", [])
    cases = observations.get("case_retrieval", {}).get("cases", [])

    return (
        "以下为律师 Agent 的结构化降级结果：\n"
        f"1) 案情摘要：{case_info.get('facts', user_text)}\n"
        f"2) 证据结论：{evidence.get('overall_assessment', '暂无')}\n"
        f"3) 时效状态：{limitation.get('status', '未计算')}\n"
        f"4) 管辖建议数量：{len(jurisdiction.get('recommended_courts', []))}\n"
        f"5) 法条命中：{len(statutes)}，判例命中：{len(cases)}\n"
        f"6) 风险等级：{risk.get('risk_level', '未知')}（{risk.get('risk_score', 'N/A')}）\n"
        "建议：补充关键证据和日期信息后再次提问，可获得更精准结果。"
    )


@router.post("/agent/lawyer/chat", response_model=AgentLawyerResponse)
async def lawyer_agent_chat(request: AgentLawyerRequest):
    session_id = request.session_id or str(uuid4())
    user_text = request.text

    try:
        history = session_memory_store.get_history(session_id)
        plan = planner.plan(user_text, history, role="lawyer")
        trace, skills_used, observations = await executor.execute(
            plan=plan,
            session_id=session_id,
            text=user_text,
            memory={"history": history},
            role="lawyer",
        )

        if _is_hearing_intent(user_text):
            outline = observations.get("hearing_outline_generation", {}).get("outline", "")
            answer = outline or _build_fallback_answer(user_text, observations)
        elif _is_drafting_intent(user_text):
            draft = observations.get("document_generation", {}).get("draft", "")
            answer = draft or _build_fallback_answer(user_text, observations)
        else:
            context_text = _build_agent_context(observations)
            synthesis_prompt = (
                "你是专业律师智能体，请基于结构化结果输出最终回答，并且必须始终使用简体中文。\n"
                "要求：\n"
                "1. 先给结论，再给依据（法条/判例/证据/程序）。\n"
                "2. 若涉及时效或管辖，必须单独列出行动建议。\n"
                "3. 信息不足时，明确写出待补充清单。\n\n"
                f"用户问题：{user_text}\n\n结构化结果：\n{context_text}"
            )
            try:
                llm_response = await asyncio.wait_for(
                    ai_service.generate_text(text=synthesis_prompt, context=history[-8:] if history else None),
                    timeout=AGENT_SYNTHESIS_TIMEOUT,
                )
                answer = (llm_response.get("text", "") or "").strip() or _build_fallback_answer(user_text, observations)
            except Exception:
                answer = _build_fallback_answer(user_text, observations)

        answer = await ensure_simplified_chinese(answer, ai_service=ai_service, history=history)

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
            message="律师 Agent 工作流执行完成。",
        )
    except Exception as exc:
        logger.error("Lawyer agent chat failed", exc_info=True)
        return AgentLawyerResponse(
            success=False,
            answer="抱歉，律师 Agent 当前不可用，请稍后重试。",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated={},
            message="律师 Agent 执行失败。",
            error=str(exc),
        )

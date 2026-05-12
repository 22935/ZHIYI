import asyncio
import json
import logging
import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter

from app.api.language_guard import ensure_simplified_chinese
from app.agent_core.federated.federated_adapter import FederatedAdapter
from app.agent_core.memory.session_memory import session_memory_store
from app.agent_core.react.executor import ReactExecutor
from app.agent_core.react.planner import ReactPlanner
from app.agent_core.react.tool_router import ToolRouter
from app.agent_core.schema.agent_types import AgentProgrammerRequest, AgentProgrammerResponse
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)
router = APIRouter()

ai_service = AIService()
planner = ReactPlanner()
tool_router = ToolRouter(enabled_roles=["programmer"])
executor = ReactExecutor(tool_router=tool_router)
AGENT_SYNTHESIS_TIMEOUT = float(os.getenv("AGENT_SYNTHESIS_TIMEOUT", "180"))
federated_adapter = FederatedAdapter()


def _default_federated_info() -> Dict[str, Any]:
    return {
        "enabled": federated_adapter.enabled,
        "applied": False,
        "risk_adjustment": 0.0,
        "confidence": 0.0,
        "federated_nodes_count": 0,
    }


async def _collect_federated_info(user_text: str, skills_used: List[str], observations: Dict[str, Any]) -> Dict[str, Any]:
    info = _default_federated_info()
    if not federated_adapter.enabled:
        return info

    payload = {
        "role": "programmer",
        "query": user_text,
        "skills_used": skills_used,
    }
    if isinstance(observations, dict):
        requirement = observations.get("requirement_analysis")
        if isinstance(requirement, dict):
            payload["requirement_analysis"] = {
                "requirement": requirement.get("requirement"),
                "functional_requirements": requirement.get("functional_requirements", []),
            }
        search = observations.get("codebase_semantic_search")
        if isinstance(search, dict):
            hits = search.get("hits", []) if isinstance(search.get("hits"), list) else []
            payload["search_hit_count"] = len(hits)
            payload["search_files"] = [
                hit.get("file_path")
                for hit in hits[:5]
                if isinstance(hit, dict) and hit.get("file_path")
            ]

    enhancement = await federated_adapter.get_risk_enhancement(payload)
    if not enhancement:
        return info

    info["applied"] = True
    info["risk_adjustment"] = round(float(enhancement.get("risk_adjustment", 0.0) or 0.0), 4)
    info["confidence"] = round(float(enhancement.get("confidence", 0.0) or 0.0), 4)
    info["federated_nodes_count"] = int(enhancement.get("federated_nodes_count", 0) or 0)
    return info


def _build_programmer_context(observations: Dict[str, Any]) -> str:
    sections: List[str] = []
    mapping = [
        ("requirement_analysis", observations.get("requirement_analysis", {})),
        ("codebase_semantic_search", observations.get("codebase_semantic_search", {})),
        ("code_generation", observations.get("code_generation", {})),
        ("diagram_generation", observations.get("diagram_generation", {})),
    ]
    for title, payload in mapping:
        if payload:
            sections.append(f"[{title}]")
            sections.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(sections)


def _summarize_search(payload: Dict[str, Any]) -> str:
    hits = payload.get("hits", []) if isinstance(payload.get("hits"), list) else []
    if not hits:
        return "代码检索完成，未发现直接匹配项。"

    top_paths: List[str] = []
    for item in hits[:3]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("file_path") or "")
        if path and path not in top_paths:
            top_paths.append(path)
    if top_paths:
        return f"代码检索命中 {len(hits)} 条，Top 文件：{', '.join(top_paths)}。"
    return f"代码检索命中 {len(hits)} 条。"


def _summarize_requirement(payload: Dict[str, Any]) -> str:
    requirement = str(payload.get("requirement", "")).strip() or "未命名需求"
    fr = payload.get("functional_requirements", []) if isinstance(payload.get("functional_requirements"), list) else []
    io_inputs = payload.get("inputs", []) if isinstance(payload.get("inputs"), list) else []
    io_outputs = payload.get("outputs", []) if isinstance(payload.get("outputs"), list) else []

    lines = [
        f"需求技术规格：{requirement}",
        f"- 功能需求数：{len(fr)}",
        f"- 输入项数：{len(io_inputs)}",
        f"- 输出项数：{len(io_outputs)}",
    ]
    if fr:
        preview = "; ".join(str(item) for item in fr[:3])
        lines.append(f"- 关键要点：{preview}")
    return "\n".join(lines)


def _extract_preferred_answer(skills_used: List[str], observations: Dict[str, Any]) -> str:
    used_set = set(skills_used or [])

    if "diagram_generation" in used_set:
        payload = observations.get("diagram_generation", {})
        if isinstance(payload, dict):
            mermaid_code = str(payload.get("mermaid_code", "")).strip()
            diagram_type = str(payload.get("diagram_type", "")).strip()
            title = str(payload.get("title", "")).strip() or "生成图示"
            if mermaid_code:
                prefix = f"{title} ({diagram_type})" if diagram_type else title
                return f"{prefix}\n\n```mermaid\n{mermaid_code}\n```"

    if "code_generation" in used_set:
        payload = observations.get("code_generation", {})
        if isinstance(payload, dict):
            code = str(payload.get("code", "")).strip()
            lang = str(payload.get("target_language", "")).strip()
            explanation = str(payload.get("explanation", "")).strip()
            if code:
                code_block = f"```{lang or 'text'}\n{code}\n```"
                if explanation:
                    return f"{explanation}\n\n{code_block}"
                return code_block

    if "requirement_analysis" in used_set:
        payload = observations.get("requirement_analysis", {})
        if isinstance(payload, dict):
            summary = _summarize_requirement(payload)
            if summary:
                return summary

    if "codebase_semantic_search" in used_set:
        payload = observations.get("codebase_semantic_search", {})
        if isinstance(payload, dict):
            summary = _summarize_search(payload)
            if summary:
                return summary

    return ""


def _build_fallback_answer(user_text: str, skills_used: List[str], observations: Dict[str, Any]) -> str:
    lines = [
        "程序员 Agent 结构化降级结果：",
        f"1) 用户请求：{user_text}",
        f"2) 已调用技能：{', '.join(skills_used) if skills_used else '无'}",
    ]

    for index, action in enumerate(skills_used, start=3):
        payload = observations.get(action, {})
        if isinstance(payload, dict):
            preview = json.dumps(payload, ensure_ascii=False)[:260]
        else:
            preview = str(payload)[:260]
        lines.append(f"{index}) {action}：{preview}")

    return "\n".join(lines)


@router.post("/agent/programmer/chat", response_model=AgentProgrammerResponse)
async def programmer_agent_chat(request: AgentProgrammerRequest):
    session_id = request.session_id or str(uuid4())
    user_text = request.text

    try:
        history = session_memory_store.get_history(session_id)
        plan = planner.plan(user_text, history, role="programmer")
        trace, skills_used, observations = await executor.execute(
            plan=plan,
            session_id=session_id,
            text=user_text,
            memory={"history": history},
            role="programmer",
        )

        answer = _extract_preferred_answer(skills_used=skills_used, observations=observations)
        if not answer:
            context_text = _build_programmer_context(observations)
            synthesis_prompt = (
                "你是一名专业软件工程助手。请基于结构化结果生成简洁、可执行的答复，"
                "并且必须始终使用简体中文。\n"
                "要求：\n"
                "1. 优先给出可落地结果。\n"
                "2. 若包含代码，仅保留必要说明。\n"
                "3. 若生成 Mermaid，请保留 mermaid 代码块。\n"
                "4. 信息不足时，明确列出缺失字段。\n\n"
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
        federated_info = await _collect_federated_info(
            user_text=user_text,
            skills_used=skills_used,
            observations=observations if isinstance(observations, dict) else {},
        )

        return AgentProgrammerResponse(
            success=True,
            answer=answer,
            sessionId=session_id,
            skillsUsed=skills_used,
            trace=trace,
            federated=federated_info,
            message="程序员 Agent 工作流执行完成。",
            requirement_analysis=observations.get("requirement_analysis") if isinstance(observations, dict) else None,
            codebase_semantic_search=observations.get("codebase_semantic_search") if isinstance(observations, dict) else None,
            code_generation=observations.get("code_generation") if isinstance(observations, dict) else None,
            diagram_generation=observations.get("diagram_generation") if isinstance(observations, dict) else None,
        )
    except Exception as exc:
        logger.error("Programmer agent chat failed", exc_info=True)
        return AgentProgrammerResponse(
            success=False,
            answer="抱歉，程序员 Agent 当前不可用，请稍后重试。",
            sessionId=session_id,
            skillsUsed=[],
            trace=[],
            federated=_default_federated_info(),
            message="程序员 Agent 执行失败。",
            error=str(exc),
        )
